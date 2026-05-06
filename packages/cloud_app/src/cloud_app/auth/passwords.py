"""Bcrypt password hashing — pure functions, no I/O."""
import bcrypt


def hash_password(plaintext: str, *, rounds: int = 12) -> str:
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False
