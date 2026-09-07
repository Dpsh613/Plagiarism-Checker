import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

from dotenv import load_dotenv


load_dotenv()
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_FROM = os.getenv("SMTP_FROM")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS")
def _get_backend_url():
    if os.getenv("BACKEND_URL"):
        return os.getenv("BACKEND_URL").rstrip("/")
    if os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN').rstrip('/')}"
    if os.getenv("RENDER_EXTERNAL_URL"):
        return os.getenv("RENDER_EXTERNAL_URL").rstrip("/")
    return "http://localhost:8000"


def _get_frontend_url():
    if os.getenv("FRONTEND_URL"):
        return os.getenv("FRONTEND_URL").rstrip("/")
    frontend_urls = os.getenv("FRONTEND_URLS", "")
    if frontend_urls:
        first_url = frontend_urls.split(",")[0].strip()
        if first_url and first_url != "*":
            return first_url.rstrip("/")
    return "http://localhost:5173"


def _get_smtp_config():
    """Resolve SMTP settings. Provider-agnostic with Gmail-compatible defaults.

    Minimal setup (Gmail): SMTP_EMAIL + SMTP_PASSWORD only.
    Provider relay (e.g. Resend): SMTP_HOST + SMTP_PORT + SMTP_USER +
    SMTP_PASSWORD + SMTP_FROM. SMTP_FROM defaults to the login user.
    """
    sender = (os.getenv("SMTP_EMAIL") or SMTP_EMAIL or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or SMTP_PASSWORD or "").replace(" ", "").strip()
    host = (os.getenv("SMTP_HOST") or SMTP_HOST or "smtp.gmail.com").strip()
    try:
        port = int((os.getenv("SMTP_PORT") or SMTP_PORT or "587").strip())
    except ValueError:
        port = 587
    user = (os.getenv("SMTP_USER") or SMTP_USER or sender).strip()
    sender_from = (os.getenv("SMTP_FROM") or SMTP_FROM or sender).strip()
    starttls_raw = os.getenv("SMTP_STARTTLS", SMTP_STARTTLS if SMTP_STARTTLS is not None else "true")
    use_starttls = starttls_raw.strip().lower() == "true"
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from": sender_from,
        "starttls": use_starttls,
    }


def smtp_is_configured():
    cfg = _get_smtp_config()
    return bool(cfg["user"] and cfg["password"] and cfg["from"])


def _send_email(target_email: str, subject: str, text: str, html: str) -> bool:
    cfg = _get_smtp_config()
    if not smtp_is_configured():
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = cfg["from"]
    message["To"] = target_email
    message.attach(MIMEText(text, "plain"))
    message.attach(MIMEText(html, "html"))

    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from"], target_email, message.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                if cfg["starttls"]:
                    server.starttls()
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from"], target_email, message.as_string())
        return True
    except Exception as e:
        # Never log credentials: only host, port and the server's error message.
        print(f"[SMTP ERROR {cfg['host']}:{cfg['port']}]: {e}", flush=True)
        return False


def send_verification_email(target_email: str, token: str):
    verify_link = f"{_get_backend_url()}/verify?token={quote(token, safe='')}"
    return _send_email(
        target_email,
        "Verify your CheckMate Account",
        f"Verify your email address by opening this link:\n{verify_link}",
        f'<html><body><h2>Welcome to CheckMate!</h2><p>Verify your email address:</p><a href="{verify_link}">Verify Email</a></body></html>',
    )


def send_password_reset_email(target_email: str, token: str):
    # Fragments are never included in HTTP Referer headers or server access logs.
    reset_link = f"{_get_frontend_url()}/#reset_token={quote(token, safe='')}"
    return _send_email(
        target_email,
        "Reset your CheckMate Password",
        f"Reset your password by opening this link:\n{reset_link}\nThis link expires in one hour.",
        f'<html><body><h2>Reset Your Password</h2><p><a href="{reset_link}">Reset Password</a></p><p>This link expires in one hour.</p></body></html>',
    )
