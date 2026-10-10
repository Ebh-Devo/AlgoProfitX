from datetime import datetime, timedelta, timezone
from functools import lru_cache
import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings


password_hasher = PasswordHasher()

ALGORITHM = "HS256"
TOKEN_TYPE = "access"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


@lru_cache(maxsize=1)
def _decoy_password_hash() -> str:
    """A fixed hash of a random secret, made by the same hasher (algorithm and cost) as real hashes."""
    return password_hasher.hash(secrets.token_urlsafe(32))


def verify_password_or_decoy(password: str, password_hash: str | None) -> bool:
    """Always perform one full password verification, even when no account exists.

    Login uses this for unknown, inactive and active accounts alike so response time does not reveal
    whether an account exists. With no hash the decoy is verified and the result is always False.
    """
    candidate = password_hash if password_hash is not None else _decoy_password_hash()
    matched = verify_password(password, candidate)
    return matched and password_hash is not None


def create_access_token(subject: str) -> str:
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )

    payload = {
        "sub": subject,
        "type": TOKEN_TYPE,
        "exp": expires_at,
        "iat": issued_at,
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": settings.auth_jwt_key_id},
    )


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("kid") != settings.auth_jwt_key_id:
            raise ValueError("Invalid token key identifier")
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
        )

        if payload.get("type") != TOKEN_TYPE:
            raise ValueError("Invalid token type")

        if not payload.get("sub"):
            raise ValueError("Token subject is missing")
        if not payload.get("iat"):
            raise ValueError("Token issue time is missing")
        try:
            uuid.UUID(payload["jti"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Token identifier is invalid") from exc

        return payload

    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
