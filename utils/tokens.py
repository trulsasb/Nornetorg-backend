import hashlib

INVITATION_EXPIRE_DAYS = 7


def hash_invitation_token(raw_token: str) -> str:
    # SHA-256 (not bcrypt) is deliberate: this is a high-entropy random token
    # (secrets.token_urlsafe), not a low-entropy user-chosen password -- it
    # doesn't need a slow, salted KDF, just protection against the DB itself
    # leaking usable tokens.
    return hashlib.sha256(raw_token.encode()).hexdigest()
