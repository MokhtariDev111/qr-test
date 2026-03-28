import qrcode
import io
import base64
import secrets
from datetime import datetime, timedelta
from app.core.config import settings


def generate_qr_token() -> str:
    return secrets.token_urlsafe(32)


import socket

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def generate_qr_image(session_id: int, token: str, frontend_url: str) -> str:
    data = f"{frontend_url}/student?token={session_id}:{token}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode()


def get_qr_expiry() -> datetime:
    return datetime.utcnow() + timedelta(seconds=settings.qr_refresh_interval)
