# utils/env.py
from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App-konfig
    APP_MODE: str = "test"  # test | live

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/nornetorg"

    # Bakgrunnsjobber
    REDIS_URL: str = "redis://localhost:6379/0"

    # Frontend
    FRONTEND_URL: str = "https://nornetorg.no"

    # Selgerverifisering -- se SPEC.md 3.3 punkt 2. E-postverifisering alene
    # er kun tillatt i SELLER_EMAIL_ONLY_GRACE_DAYS dager etter LAUNCH_DATE;
    # deretter kreves BankID (egen fremtidig modul -- ikke bygget ennå).
    # LAUNCH_DATE er bevisst None inntil en reell lanseringsdato er satt --
    # fristen håndheves ikke mens dette er None, uansett hvor lenge appen
    # har kjørt i test/utvikling.
    LAUNCH_DATE: date | None = None
    SELLER_EMAIL_ONLY_GRACE_DAYS: int = 60

    # Sikkerhet
    JWT_SECRET: str = "supersecret"
    JWT_EXPIRE_HOURS: int = 24

    # Fernet-nøkkel brukt til å kryptere selgeres Vipps-kredensialer og
    # lagrede betalingsmetode-referanser i databasen. Generer med:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SETTINGS_ENCRYPTION_KEY: str | None = None

    # Stripe -- plattformens EGEN konto (for Connect-onboarding av selgere
    # OG for å trekke provisjon fra selgeres lagrede betalingsmetode --
    # se SPEC.md 3.1, dette er en annen bruk enn selgernes egne Connect-kontoer)
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_CONNECT_CLIENT_ID: str | None = None

    # Vipps -- plattform-nivå defaults (selgere kobler opp sine egne,
    # lagret kryptert i databasen -- se models/seller.py)
    VIPPS_BASE_URL: str = "https://apitest.vipps.no"

    # Posten Norge / Bring
    BRING_API_KEY: str | None = None
    BRING_CUSTOMER_NUMBER: str | None = None

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

# Refuse to boot in live mode with the placeholder JWT secret still in place --
# this would let anyone forge a valid admin/selger-token.
if settings.APP_MODE == "live" and settings.JWT_SECRET == "supersecret":
    raise RuntimeError(
        "JWT_SECRET is still the default placeholder. Set a real random "
        "JWT_SECRET env var before running in live mode."
    )
