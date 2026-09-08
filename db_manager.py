import os
import chromadb
from chromadb.config import Settings
from model_manager import encode_texts
from storage_sync import (
    chroma_db_path,
    mutation_lock,
    restore_on_boot,
    schedule_backup,
)
from utils import extract_text_from_document, get_sliding_windows

DB_PATH = chroma_db_path()
MAX_VECTORS_PER_USER = max(1, int(os.getenv("MAX_VECTORS_PER_USER", "10000")))
# Restore durable state first: on ephemeral hosts the local dir starts empty.
restore_on_boot()
client = chromadb.PersistentClient(path=DB_PATH, settings=Settings(anonymized_telemetry=False))

def get_user_collection(user_id):
    return client.get_or_create_collection(name=f"user_{user_id}_docs")

def get_all_indexed_sources(user_id):
    collection = get_user_collection(user_id)
    try:
        data = collection.get(include=["metadatas"])
        if not data or not data["metadatas"]: return []
        by_filename = {}
        for meta in data["metadatas"]:
            filename = meta.get("source", "unknown")
            by_filename.setdefault(filename, meta.get("title") or filename)
        return [
            {"filename": filename, "title": title}
            for filename, title in sorted(by_filename.items())
        ]
    except Exception as e:
        # Never disguise a database failure as an empty library.
        print(f"[DB ERROR] get_all_indexed_sources failed: {e}", flush=True)
        raise

def add_file_to_db(user_id, file_path, filename, title=None, source_url=None):
    collection = get_user_collection(user_id)
    pages_data, extract_info = extract_text_from_document(file_path)
    if not pages_data:
        return False, "Extraction failed or PDF is empty."

    chunks_data, chunks_capped = get_sliding_windows(pages_data)
    if not chunks_data:
        return False, "No valid text chunks found."

    try:
        existing_vectors = collection.count()
    except Exception:
        existing_vectors = 0
    if existing_vectors + len(chunks_data) > MAX_VECTORS_PER_USER:
        return False, (
            f"Personal library quota exceeded ({MAX_VECTORS_PER_USER} chunks). "
            "Delete an indexed source before adding a new one."
        )

    display_title = (title or "").strip() or filename
    documents = [item['text'] for item in chunks_data]
    metadatas = [
        {"source": filename, "title": display_title, "url": source_url or "", "page": item['page']}
        for item in chunks_data
    ]
    ids = [f"{filename}_{i}" for i in range(len(chunks_data))]

    embeddings = encode_texts(documents)

    with mutation_lock:
        collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
    message = f"Successfully indexed {len(documents)} chunks."
    if extract_info.get("truncated") or chunks_capped:
        message += " Note: this large document was truncated during indexing."
    schedule_backup()
    return True, message

def delete_source_from_db(user_id, filename):
    collection = get_user_collection(user_id)
    try:
        with mutation_lock:
            collection.delete(where={"source": filename})
        schedule_backup()
        return True, f"Deleted vectors for {filename}."
    except Exception as e:
        return False, str(e)
