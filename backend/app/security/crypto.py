import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def new_guest_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ip_hash(ip: str | None) -> str | None:
    if not ip:
        return None
    return hmac.new(get_settings().app_secret.encode(), ip.encode(), hashlib.sha256).hexdigest()


def issue_local_token(user_id: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iss": "pivotpilot-local",
        "aud": "pivotpilot",
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_ttl_minutes),
    }
    return jwt.encode(payload, s.app_secret, algorithm="HS256")


def decode_local_token(token: str) -> str | None:
    try:
        data = jwt.decode(
            token, get_settings().app_secret, algorithms=["HS256"], audience="pivotpilot", issuer="pivotpilot-local"
        )
        return str(data["sub"])
    except jwt.PyJWTError:
        return None
