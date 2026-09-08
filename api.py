import hmac
import os
import secrets
import uuid
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Path, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from arxiv_manager import download_specific_arxiv_paper, search_arxiv_metadata
from auth_db import (
    create_user,
    get_user_by_email,
    verify_password,
)
from checker import analyze_document
from db_manager import add_file_to_db, delete_source_from_db, get_all_indexed_sources


load_dotenv()

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError("JWT_SECRET_KEY must be set when APP_ENV=production")
    JWT_SECRET_KEY = secrets.token_hex(32)

FRONTEND_URLS = [url.strip().rstrip("/") for url in os.getenv(
    "FRONTEND_URLS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if url.strip()]
if not FRONTEND_URLS or "*" in FRONTEND_URLS:
    raise RuntimeError("FRONTEND_URLS must list explicit origins; wildcard origins are not allowed")
if IS_PRODUCTION and any(not url.startswith("https://") for url in FRONTEND_URLS):
    raise RuntimeError("Production FRONTEND_URLS must use HTTPS")

COOKIE_SECURE = os.getenv("COOKIE_SECURE", str(IS_PRODUCTION)).lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none" if (IS_PRODUCTION or COOKIE_SECURE) else "lax")
if IS_PRODUCTION and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SECURE must be true when APP_ENV=production")

UPLOAD_FOLDER = "./temp_uploads"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".txt"}
ALGORITHM = "HS256"
ACCESS_TOKEN_LIFETIME = timedelta(hours=8)
# Bound concurrent CPU-heavy jobs (embedding/index/analyze) so one request
# cannot starve the event loop for everyone else on a small instance.
MAX_HEAVY_JOBS = max(1, int(os.getenv("MAX_HEAVY_JOBS", "2")))
HEAVY_RETRY_AFTER_SECONDS = 30
heavy_job_semaphore = asyncio.Semaphore(MAX_HEAVY_JOBS)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


async def run_heavy_job(func, *args):
    """Run blocking CPU/network work in a thread without freezing the loop.

    Raises 503 with Retry-After when all heavy slots are busy (backpressure
    instead of silently queueing minutes of work).
    """
    if heavy_job_semaphore.locked():
        raise HTTPException(
            status_code=503,
            headers={"Retry-After": str(HEAVY_RETRY_AFTER_SECONDS)},
            detail="Server is busy processing other documents. Please retry shortly.",
        )
    async with heavy_job_semaphore:
        return await run_in_threadpool(func, *args)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Graceful shutdown (e.g. Render SIGTERM on sleep/redeploy): push one
    # final snapshot synchronously. No-op when snapshots are unconfigured.
    try:
        from storage_sync import flush_backup

        flush_backup()
    except Exception as e:
        print(f"[SNAPSHOT] shutdown flush failed: {e}", flush=True)


app = FastAPI(docs_url=None if IS_PRODUCTION else "/docs", redoc_url=None, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "X-Access-Token"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _sweep_stale_uploads(max_age_hours=24):
    """Remove orphaned temp uploads left by killed/interrupted requests."""
    import time

    now = time.time()
    try:
        names = os.listdir(UPLOAD_FOLDER)
    except OSError:
        return
    for name in names:
        path = os.path.join(UPLOAD_FOLDER, name)
        try:
            if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_hours * 3600:
                os.remove(path)
        except OSError:
            pass


_sweep_stale_uploads()


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    # HTTPException/RateLimitExceeded keep their specific handlers; this is the
    # last resort so tracebacks and server paths never leak to clients.
    print(f"[ERROR] unhandled {request.method} {request.url.path}: {exc!r}", flush=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/deep")
def deep_health_check():
    """Component-level health for orchestrators: model, vector DB, disk, users DB."""
    import shutil

    components = {}
    ok = True

    try:
        import model_manager

        components["model"] = "ready" if model_manager._model is not None else "not_loaded"
    except Exception as e:
        ok = False
        components["model"] = f"error: {e}"

    try:
        from db_manager import client as chroma_client

        chroma_client.heartbeat()
        components["vector_db"] = "ready"
    except Exception as e:
        ok = False
        components["vector_db"] = f"error: {e}"

    try:
        from auth_db import _connect as _users_connect

        conn = _users_connect()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
        components["users_db"] = "ready"
    except Exception as e:
        ok = False
        components["users_db"] = f"error: {e}"

    try:
        free_mb = shutil.disk_usage(".").free // (1024 * 1024)
        components["disk_free_mb"] = free_mb
        if free_mb < 100:
            ok = False
            components["disk"] = "low"
        else:
            components["disk"] = "ready"
    except Exception as e:
        ok = False
        components["disk"] = f"error: {e}"

    status = {"status": "ok" if ok else "degraded", "components": components}
    return JSONResponse(content=status, status_code=200 if ok else 503)


def create_access_token(user_id: int):
    expires_at = datetime.now(timezone.utc) + ACCESS_TOKEN_LIFETIME
    csrf_token = secrets.token_urlsafe(32)
    return jwt.encode(
        {"sub": str(user_id), "csrf": csrf_token, "iat": datetime.now(timezone.utc), "exp": expires_at},
        JWT_SECRET_KEY,
        algorithm=ALGORITHM,
    ), csrf_token


def _read_session(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        else:
            token = request.headers.get("X-Access-Token", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["sub", "exp", "csrf"]})
        user_id = int(payload["sub"])
        if user_id < 1 or not isinstance(payload["csrf"], str):
            raise ValueError
        return user_id, payload["csrf"]
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(request: Request):
    return _read_session(request)[0]


async def require_csrf(request: Request):
    _, expected_token = _read_session(request)
    supplied_token = request.headers.get("X-CSRF-Token", "")
    if not hmac.compare_digest(supplied_token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


class UserAuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)


class ArxivDownloadRequest(BaseModel):
    pdf_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=300)


@app.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, user: UserAuthRequest):
    email = str(user.email)
    success, msg = create_user(email, user.password)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": "Account created! You can now log in."}


@app.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, response: Response, user: UserAuthRequest):
    db_user = get_user_by_email(str(user.email))
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token, csrf_token = create_access_token(db_user["id"])
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        path="/",
    )
    return {"status": "success", "email": db_user["email"], "access_token": token, "csrf_token": csrf_token}


@app.get("/csrf-token")
@limiter.limit("60/minute")
async def csrf_token(request: Request):
    _, token = _read_session(request)
    return {"csrf_token": token}


@app.post("/logout", dependencies=[Depends(require_csrf)])
async def logout(response: Response):
    response.delete_cookie(key="access_token", httponly=True, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE, path="/")
    return {"status": "success", "message": "Logged out successfully"}


@app.post("/analyze", dependencies=[Depends(require_csrf)])
@limiter.limit("10/minute")
async def analyze_endpoint(request: Request, file: UploadFile = File(...), user_id: int = Depends(get_current_user)):
    original_filename = file.filename or ""
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are allowed.")

    file_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}{ext}")
    total_size = 0
    first_chunk = b""
    try:
        with open(file_path, "xb") as buffer:
            while chunk := await file.read(1024 * 1024):
                if not first_chunk:
                    first_chunk = chunk
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")
                buffer.write(chunk)

        if not first_chunk:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if ext == ".pdf" and not first_chunk.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file.")
        if ext == ".txt" and b"\x00" in first_chunk:
            raise HTTPException(status_code=400, detail="Invalid text file.")
        return JSONResponse(content=await run_heavy_job(analyze_document, user_id, file_path))
    finally:
        await file.close()
        if os.path.exists(file_path):
            os.remove(file_path)


@app.get("/database/files")
@limiter.limit("20/minute")
async def get_files(request: Request, user_id: int = Depends(get_current_user)):
    try:
        return {"files": get_all_indexed_sources(user_id)}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Document database is temporarily unavailable. Please retry shortly.",
        )


@app.delete("/database/files/{filename}", dependencies=[Depends(require_csrf)])
@limiter.limit("20/minute")
async def delete_from_db(request: Request, filename: str = Path(min_length=1, max_length=300), user_id: int = Depends(get_current_user)):
    success, msg = delete_source_from_db(user_id, filename)
    if not success:
        raise HTTPException(status_code=400, detail="Unable to delete that indexed source.")
    return {"status": "success", "message": msg}


@app.get("/arxiv/search")
@limiter.limit("10/minute")
async def search_arxiv(request: Request, topic: str = Query(min_length=1, max_length=200), user_id: int = Depends(get_current_user)):
    try:
        return {"results": await run_heavy_job(search_arxiv_metadata, topic)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to search arXiv right now (it may be rate-limiting us).")


@app.post("/arxiv/download", dependencies=[Depends(require_csrf)])
@limiter.limit("5/minute")
async def download_arxiv(request: Request, req: ArxivDownloadRequest, user_id: int = Depends(get_current_user)):
    success, msg = await run_heavy_job(
        download_specific_arxiv_paper,
        req.pdf_url,
        req.title,
        lambda fpath, fname, title, url: add_file_to_db(user_id, fpath, fname, title=title, source_url=url),
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0" if IS_PRODUCTION else "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api:app", host=host, port=port, reload=not IS_PRODUCTION)
