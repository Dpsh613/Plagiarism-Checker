"""Durable state on ephemeral hosts (e.g. Render free tier).

Local SQLite/Chroma files vanish on redeploy or sleep. This module snapshots
the durable state (users DB + vector DB) to S3-compatible object storage
(free tiers: Cloudflare R2, Supabase Storage S3 gateway, etc.):

- boot: if local state is missing and a snapshot exists, restore it.
- after every mutation (index/delete): schedule a debounced background backup.
- graceful shutdown (FastAPI lifespan): flush one final backup synchronously.

Transient files (temp_uploads/, dataset_pdfs/, model cache) are excluded:
uploads are deleted after analysis and arXiv PDFs are re-downloadable.

All S3 interaction is best-effort and never fails a user request. Without
snapshot env vars configured, every function is a deliberate no-op.
"""

import io
import os
import sqlite3
import threading
import time
import zipfile

BACKUP_DEBOUNCE_SECONDS = max(30, int(os.getenv("BACKUP_DEBOUNCE_SECONDS", "120")))
STATE_RELATIVE_PATHS = ("users.sqlite", "my_plagiarism_db")


def data_dir():
    return os.getenv("CHECKMATE_DATA_DIR", ".")


def users_db_path():
    return os.path.join(data_dir(), "users.sqlite")


def chroma_db_path():
    return os.path.join(data_dir(), "my_plagiarism_db")


def snapshot_configured():
    return bool(
        os.getenv("SNAPSHOT_BUCKET")
        and os.getenv("SNAPSHOT_ACCESS_KEY")
        and os.getenv("SNAPSHOT_SECRET_KEY")
        and os.getenv("SNAPSHOT_ENDPOINT")
    )


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("SNAPSHOT_ENDPOINT"),
        aws_access_key_id=os.getenv("SNAPSHOT_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("SNAPSHOT_SECRET_KEY"),
        region_name=os.getenv("SNAPSHOT_REGION", "auto"),
    )


def _sqlite_checkpoint(path):
    """Flush WAL content into the main DB file so a file copy is consistent."""
    if not os.path.exists(path):
        return
    try:
        conn = sqlite3.connect(path, timeout=10)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[SNAPSHOT] checkpoint skipped for {path}: {e}", flush=True)


def create_snapshot_bytes():
    """Zip durable state into bytes. Raises if nothing durable exists."""
    buffer = io.BytesIO()
    added = False
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in STATE_RELATIVE_PATHS:
            path = os.path.join(data_dir(), rel)
            if os.path.isfile(path):
                if path.endswith(".sqlite"):
                    _sqlite_checkpoint(path)
                archive.write(path, rel)
                added = True
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for name in files:
                        full = os.path.join(root, name)
                        archive.write(full, os.path.relpath(full, data_dir()))
                        added = True
    if not added:
        raise FileNotFoundError("no durable state to snapshot")
    return buffer.getvalue()


def restore_snapshot_bytes(payload: bytes):
    """Unpack a snapshot into the data dir. Caller must ensure stores are closed."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.namelist():
            target = os.path.normpath(os.path.join(data_dir(), member))
            if not target.startswith(os.path.abspath(data_dir())):
                raise ValueError(f"unsafe snapshot entry: {member}")
            if member.endswith("/"):
                continue
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as dest:
                dest.write(source.read())


def _local_state_present():
    """True if there is any local state worth keeping (never overwrite it)."""
    if os.path.exists(users_db_path()):
        return True
    chroma = chroma_db_path()
    if os.path.isdir(chroma) and any(os.scandir(chroma)):
        return True
    return False


def restore_on_boot():
    """Download and unpack the snapshot when booting with empty local state."""
    if not snapshot_configured() or _local_state_present():
        return False
    try:
        client = _s3_client()
        response = client.get_object(
            Bucket=os.getenv("SNAPSHOT_BUCKET"), Key="checkmate-data.zip"
        )
        restore_snapshot_bytes(response["Body"].read())
        print("[SNAPSHOT] restored state from object storage.", flush=True)
        return True
    except Exception as e:
        print(f"[SNAPSHOT] restore skipped/failed: {e}", flush=True)
        return False


_backup_lock = threading.Lock()
_backup_timer = None

# Shared with db_manager: held during vector-store writes and during snapshot
# creation so a backup never zips a half-written store.
mutation_lock = threading.Lock()


def _upload_snapshot():
    try:
        with mutation_lock:
            payload = create_snapshot_bytes()
        client = _s3_client()
        client.put_object(
            Bucket=os.getenv("SNAPSHOT_BUCKET"),
            Key="checkmate-data.zip",
            Body=payload,
        )
        print(f"[SNAPSHOT] backup uploaded ({len(payload) // 1024} KB).", flush=True)
    except Exception as e:
        print(f"[SNAPSHOT] backup failed: {e}", flush=True)


def schedule_backup():
    """Coalesce rapid mutations into one debounced background upload."""
    if not snapshot_configured():
        return
    global _backup_timer
    with _backup_lock:
        if _backup_timer is not None:
            _backup_timer.cancel()
        timer = threading.Timer(BACKUP_DEBOUNCE_SECONDS, _upload_snapshot)
        timer.daemon = True
        _backup_timer = timer
        timer.start()


def flush_backup():
    """Synchronous final upload for graceful shutdown. Best-effort."""
    if not snapshot_configured():
        return
    global _backup_timer
    with _backup_lock:
        if _backup_timer is not None:
            _backup_timer.cancel()
            _backup_timer = None
    _upload_snapshot()
