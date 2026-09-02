"""Password hashing and JWT token helpers.

Centralises every cryptographic primitive the auth slice needs in one place so
the route handlers never touch Argon2 or PyJWT directly. Keeping it isolated
also makes it trivial to rotate the hashing scheme or signing algorithm later
without touching business logic.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

# Argon2id is the current OWASP-recommended password hash. The default
# PasswordHasher() parameters (time cost, memory cost, parallelism) are tuned
# for a balance of security and latency; do NOT lower them for speed.
password_hasher = PasswordHasher()

settings = get_settings()


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id.

    Returns a self-contained string (scheme + salt + hash + parameters) that
    can be stored directly in the `hashed_password` column. The salt is
    generated internally, so two calls with the same password differ.
    """
    return password_hasher.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against an Argon2id hash.

    `VerifyMismatchError` is raised for a wrong password and
    `InvalidHashError` for a malformed/corrupted stored hash; both mean the
    credential is bad, so they collapse to `False` rather than leaking which
    condition occurred.
    """
    try:
        password_hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return True


def _base_claims(user_id: int, token_type: str, expires_delta: timedelta) -> dict:
    """Build the common JWT claim set shared by access and refresh tokens."""
    now = datetime.now(UTC)
    return {
        # JWT spec (RFC 7519) says `sub` MUST be a string. Storing the user id
        # as a string avoids an int/str mismatch when decoding on other runtimes.
        "sub": str(user_id),
        # `type` lets a single decode path distinguish access vs refresh tokens,
        # preventing a refresh token from being presented where an access token
        # is required (and vice versa).
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }


def create_access_token(user_id: int) -> str:
    """Create a short-lived access token for API authorization."""
    return jwt.encode(
        _base_claims(
            user_id,
            "access",
            timedelta(minutes=settings.access_token_expire_minutes),
        ),
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(user_id: int, jti: str) -> str:
    """Create a longer-lived refresh token bound to a `jti` id.

    `jti` (JWT ID) is a unique identifier for this specific token. It is stored
    server-side alongside the token hash so the token can be looked up for
    rotation (revoke the old one, issue a new one) and later for reuse
    detection. Callers generate the `jti` (a `uuid4`) so they can persist it
    in the same transaction that issues the token.
    """
    return jwt.encode(
        {
            **_base_claims(
                user_id,
                "refresh",
                timedelta(days=settings.refresh_token_expire_days),
            ),
            "jti": jti,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    """Decode and verify a JWT, returning its claims.

    Raises `jwt.PyJWTError` (the base class for all PyJWT failures — expiry,
    bad signature, malformed token, etc.) on any problem. The CALLER is
    responsible for catching it and mapping it to an HTTP error, because the
    appropriate response differs by endpoint (401 for most, idempotent 204 for
    logout).
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def hash_token(token: str) -> str:
    """Return a SHA-256 hex digest of a raw token.

    Refresh tokens are stored as a hash, NOT in plaintext, so a database leak
    does not hand an attacker reusable tokens. Hashing is deterministic (unlike
    Argon2), which is fine here because tokens are high-entropy (128+ bits of
    randomness) and we need a *lookup* key — we never need to verify a token
    by brute-forcing its hash. Comparisons against the stored hash use
    `secrets.compare_digest` to stay constant-time.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "hash_token",
    "verify_password",
]
