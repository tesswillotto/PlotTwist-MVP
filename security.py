"""Password hashing helpers (salted PBKDF2). Passwords are never stored in plain text."""
import hashlib
import hmac
import os

_ITERATIONS = 200_000


def hash_password(password: str, salt_hex: str = None):
    """Return (salt_hex, hash_hex). A new random salt is made when none is given."""
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Constant-time check of a password against a stored salt and hash."""
    _, candidate = hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, hash_hex)
