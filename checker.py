import re
import chromadb
from model_manager import encode_texts
from utils import extract_text_from_document, get_sliding_windows
from db_manager import get_user_collection

def extract_trigrams(words):
    return {" ".join(words[i:i+3]) for i in range(len(words)-2)}


def trigram_positions(words):
    """Map each trigram to the word indices where it starts."""
    positions = {}
    for i in range(len(words) - 2):
        trigram = " ".join(words[i:i+3])
        positions.setdefault(trigram, []).append(i)
    return positions


def calculate_ngram_overlap(student_text, db_text):
    """
    Match 3-word chunks, counting every matched word *occurrence*.
    Returns (coverage, matched_count, matched_words):
    coverage and matched_count use positional counting so repeated
    vocabulary is not under-counted; matched_words feeds highlighting.
    """
    s_words = re.findall(r'\b\w+\b', student_text.lower())
    db_words = re.findall(r'\b\w+\b', db_text.lower())

    if len(s_words) < 3 or len(db_words) < 3:
        return 0.0, 0, set()

    s_positions = trigram_positions(s_words)
    db_trigrams = extract_trigrams(db_words)

    covered = [False] * len(s_words)
    for trigram, starts in s_positions.items():
        if trigram in db_trigrams:
            for start in starts:
                covered[start] = covered[start + 1] = covered[start + 2] = True

    matched_count = sum(covered)
    matched_words = {word for word, is_covered in zip(s_words, covered) if is_covered}
    coverage = matched_count / len(s_words)
    return coverage, matched_count, matched_words

EXACT_MATCH_COVERAGE = 0.60
PARAPHRASE_COVERAGE = 0.20
# Semantic fallback: high embedding similarity with only modest word overlap
# still signals a rewrite rather than coincidence. Calibrated: medium synonym
# rewrites score sim ~0.84 with low trigram coverage, while unrelated text
# scores ~0.0 and topical-but-original text stays below ~0.5.
PARAPHRASE_SIMILARITY = 0.80
PARAPHRASE_MIN_COVERAGE = 0.05


def analyze_document(user_id, paper_path):
    collection = get_user_collection(user_id)
    pages_data, extract_info = extract_text_from_document(paper_path)
    input_chunks, chunks_capped = get_sliding_windows(pages_data)

    if not input_chunks: return {"error": "No text extracted."}

    truncated = bool(extract_info.get("truncated") or chunks_capped)

    # True document length: raw page text, counted once (chunks overlap).
    total_words_in_doc = sum(len(re.findall(r'\b\w+\b', entry['text'])) for entry in pages_data)
    total_plagiarized_words = 0

    source_contributions = {}
    source_titles = {}
    detailed_segments = []

    input_texts = [item['text'] for item in input_chunks]
    input_embeddings = encode_texts(input_texts)

    batch_results = collection.query(
        query_embeddings=input_embeddings,
        n_results=3, # Dropped to 3 to save CPU cycles
        include=["documents", "metadatas", "distances"]
    )

    for i, item in enumerate(input_chunks):
        sent_text = item['text']
        candidates_docs = batch_results['documents'][i] if batch_results['documents'] else []
        candidates_meta = batch_results['metadatas'][i] if batch_results['metadatas'] else []
        candidates_dist = []
        if batch_results.get('distances'):
            candidates_dist = batch_results['distances'][i] if batch_results['distances'] else []

        best_score = 0.0
        best_matched_count = 0
        best_similarity = 0.0
        best_source = None
        best_title = None
        best_match_text = None
        best_matched_words = set()

        for idx, db_doc in enumerate(candidates_docs):
            score, matched_count, matched_words = calculate_ngram_overlap(sent_text, db_doc)
            # Chroma default space is cosine: similarity = 1 - distance.
            similarity = 0.0
            if idx < len(candidates_dist) and candidates_dist[idx] is not None:
                similarity = max(0.0, min(1.0, 1.0 - candidates_dist[idx]))
            best_similarity = max(best_similarity, similarity)
            if score > best_score:
                best_score = score
                best_matched_count = matched_count
                best_matched_words = matched_words
                best_source = candidates_meta[idx]['source']
                best_title = candidates_meta[idx].get('title') or best_source
                best_match_text = db_doc

        match_status = "ORIGINAL"
        if best_score > EXACT_MATCH_COVERAGE:
            match_status = "EXACT MATCH"
        elif best_score > PARAPHRASE_COVERAGE or (
            best_similarity >= PARAPHRASE_SIMILARITY and best_score > PARAPHRASE_MIN_COVERAGE
        ):
            match_status = "PARAPHRASED"

        if best_matched_count > 0:
            total_plagiarized_words += best_matched_count
            source_contributions[best_source] = source_contributions.get(best_source, 0) + best_matched_count
            source_titles[best_source] = best_title or best_source

        detailed_segments.append({
            "text": sent_text,
            "page": item['page'],
            "status": match_status,
            "source": best_source if best_score > 0 else None,
            "matched_words": list(best_matched_words), # Pass exact words to frontend
            "matched_db_text": best_match_text if best_score > 0 else None,
            "similarity": round(best_similarity, 4)
        })

    final_plag_percent = min((total_plagiarized_words / total_words_in_doc) * 100, 100) if total_words_in_doc > 0 else 0
    
    # Sort sources to assign consistent Turnitin-like colors on frontend
    sources_list = [
        {"filename": k, "title": source_titles.get(k, k), "matched_words": v}
        for k, v in sorted(source_contributions.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "summary": {
            "plagiarism_percent": round(final_plag_percent, 2),
            "total_words": total_words_in_doc,
            "plagiarized_words": total_plagiarized_words,
            "truncated": truncated
        },
        "sources": sources_list,
        "segments": detailed_segments
    }
