import hashlib
import os
import tempfile
import time
from urllib.parse import urljoin, urlsplit

import arxiv
import requests


DATASET_FOLDER = "dataset_pdfs"
MAX_ARXIV_DOWNLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_ARXIV_HOSTS = {"arxiv.org", "export.arxiv.org"}
MAX_REDIRECT_HOPS = 3
STALE_TEMP_MAX_AGE_HOURS = 24
os.makedirs(DATASET_FOLDER, exist_ok=True)


def cleanup_stale_temp_files():
    """Remove orphaned arXiv temp files (e.g. left by killed requests)."""
    now = time.time()
    try:
        names = os.listdir(DATASET_FOLDER)
    except OSError:
        return
    for name in names:
        if not (name.startswith("arxiv_") and name.endswith(".pdf")):
            continue
        path = os.path.join(DATASET_FOLDER, name)
        try:
            if now - os.path.getmtime(path) > STALE_TEMP_MAX_AGE_HOURS * 3600:
                os.remove(path)
        except OSError:
            pass


cleanup_stale_temp_files()


def search_arxiv_metadata(topic: str, max_results: int = 10, retries: int = 3):
    last_error = None
    for attempt in range(retries):
        try:
            client = arxiv.Client()
            search = arxiv.Search(query=topic, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
            return [
                {
                    "title": result.title,
                    "authors": [author.name for author in result.authors],
                    "published": result.published.strftime("%Y-%m-%d"),
                    "summary": result.summary[:200] + "...",
                    "pdf_url": result.pdf_url,
                }
                for result in client.results(search)
            ]
        except Exception as e:
            last_error = e
            time.sleep(2 ** attempt)
    raise last_error


def _is_valid_arxiv_pdf_url(pdf_url: str) -> bool:
    parsed = urlsplit(pdf_url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_ARXIV_HOSTS
        and parsed.port is None
        and parsed.path.startswith("/pdf/")
    )


def _resolve_redirect_target(current_url: str, location: str):
    """Follow one redirect hop only if it stays on an allowed arXiv host."""
    if not location:
        return None
    target = urljoin(current_url, location)
    return target if _is_valid_arxiv_pdf_url(target) else None


def _resolve_final_url(pdf_url: str):
    """Follow same-host redirects (e.g. versioned .pdf URLs) to the real file."""
    url = pdf_url
    for _ in range(MAX_REDIRECT_HOPS):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "CheckMate/1.0"},
                stream=True,
                timeout=(5, 15),
                allow_redirects=False,
            )
        except requests.RequestException:
            return None
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            resolved = _resolve_redirect_target(url, location)
            if resolved is None:
                return None
            url = resolved
            continue
        response.close()
        return url
    return None


def download_specific_arxiv_paper(pdf_url: str, title: str, db_manager_add_func, retries: int = 2):
    """Download a bounded PDF from arXiv, index it, and always remove the temporary file."""
    if not _is_valid_arxiv_pdf_url(pdf_url):
        return False, "Invalid arXiv PDF URL."

    final_url = _resolve_final_url(pdf_url)
    if final_url is None:
        return False, "arXiv did not return the requested PDF."

    # Do not use a supplied title as a filesystem name. A stable URL-derived name
    # avoids traversal, filename-length issues, and concurrent-request collisions.
    # The human-readable title travels in collection metadata instead.
    filename = f"arxiv_{hashlib.sha256(pdf_url.encode('utf-8')).hexdigest()[:24]}.pdf"
    file_path = None
    last_error = None
    for attempt in range(retries + 1):
        file_path = None
        try:
            with requests.get(
                final_url,
                headers={"User-Agent": "CheckMate/1.0"},
                stream=True,
                timeout=(5, 30),
                allow_redirects=False,
            ) as response:
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"arXiv is busy right now (HTTP {response.status_code})."
                    time.sleep(2 ** attempt)
                    continue
                if response.status_code != 200:
                    return False, "arXiv did not return the requested PDF."
                content_type = response.headers.get("Content-Type", "").lower()
                if "pdf" not in content_type:
                    return False, "arXiv returned an unexpected file type."

                with tempfile.NamedTemporaryFile(mode="xb", suffix=".pdf", prefix="arxiv_", dir=DATASET_FOLDER, delete=False) as output:
                    file_path = output.name
                    total_size = 0
                    first_chunk = b""
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        if not first_chunk:
                            first_chunk = chunk
                        total_size += len(chunk)
                        if total_size > MAX_ARXIV_DOWNLOAD_BYTES:
                            return False, "arXiv PDF exceeds the 10MB limit."
                        output.write(chunk)

            if not first_chunk.startswith(b"%PDF-"):
                return False, "arXiv returned an invalid PDF."
            return db_manager_add_func(file_path, filename, title, pdf_url)
        except requests.RequestException as e:
            last_error = e
            time.sleep(2 ** attempt)
        except OSError:
            return False, "Unable to store the arXiv PDF temporarily."
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
    if last_error is not None:
        print(f"[ARXIV] download failed after retries: {last_error}", flush=True)
    return False, "Unable to download the arXiv PDF right now. arXiv may be rate-limiting us, please try again."
