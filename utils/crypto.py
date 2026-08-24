from cryptography.fernet import Fernet, InvalidToken

from utils.env import settings


def _get_fernet() -> Fernet:
    if not settings.SETTINGS_ENCRYPTION_KEY:
        raise RuntimeError(
            "SETTINGS_ENCRYPTION_KEY is not set -- required to store/read encrypted "
            "seller credentials (Vipps API keys). Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.SETTINGS_ENCRYPTION_KEY.encode())


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Could not decrypt value -- wrong key or corrupted data")
