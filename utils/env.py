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
    # er kun tillatt frem til SELLER_STRICT_VERIFICATION_FROM; deretter
    # kreves BankID (egen fremtidig modul -- ikke bygget ennå).
    #
    # SELLER_STRICT_VERIFICATION_FROM satt direkte = eksplisitt, fast frist
    # (det Truls ba om 2026-08-24: 1. januar 2027). Har forrang når satt.
    #
    # LAUNCH_DATE + SELLER_EMAIL_ONLY_GRACE_DAYS er et alternativt,
    # lanseringsrelativt uttrykk for fristen (brukes kun hvis
    # SELLER_STRICT_VERIFICATION_FROM er None) -- nyttig senere hvis
    # lanseringsdatoen flytter seg og fristen skal flytte seg med den,
    # i stedet for å måtte oppdatere en fast dato manuelt.
    SELLER_STRICT_VERIFICATION_FROM: date | None = date(2027, 1, 1)
    LAUNCH_DATE: date | None = None
    SELLER_EMAIL_ONLY_GRACE_DAYS: int = 60

    # Provisjon -- fast prosentandel for alle selgere/bransjer, se SPEC.md
    # 3.3 punkt 1. MERK: 0.10 (10%) er en PLASSHOLDER, ikke en fastsatt
    # forretningsbeslutning -- eksakt sats må avklares før lansering.
    PLATFORM_COMMISSION_RATE: float = 0.10

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
    # Stripe issues a DIFFERENT signing secret for the Connect-events webhook
    # endpoint than for the main account's webhook -- see routers/stripe_connect_webhook.py.
    STRIPE_CONNECT_WEBHOOK_SECRET: str | None = None

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
