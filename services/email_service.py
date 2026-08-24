import logging

logger = logging.getLogger("nornetorg.email")


class EmailService:
    """Stub -- logger e-poster i stedet for å sende dem. Ingen e-postleverandør
    (SendGrid e.l.) er koblet til ennå; dette holder Modul 2 fokusert på selve
    autentiseringslogikken. Byttes ut med en ekte implementasjon (samme
    grensesnitt) når prosjektet trenger faktisk utgående e-post."""

    async def send(self, to_email: str, subject: str, body: str) -> None:
        logger.info("EMAIL (stub) to=%s subject=%r\n%s", to_email, subject, body)


def build_verification_email(store_name: str, verification_url: str) -> tuple[str, str]:
    subject = f"Bekreft e-posten din for {store_name} på NorneTorg"
    body = (
        f"Takk for at du registrerte {store_name} på NorneTorg.\n\n"
        f"Bekreft e-postadressen din ved å åpne denne lenken:\n{verification_url}\n\n"
        "Lenken er gyldig i 24 timer."
    )
    return subject, body


def build_commission_draw_failed_email(
    store_name: str, amount: float, attempt: int, max_attempts: int, will_suspend: bool
) -> tuple[str, str]:
    subject = f"Provisjonstrekk feilet for {store_name} ({attempt}/{max_attempts})"
    body = (
        f"Vi klarte ikke å trekke {amount:.2f} kr i utestående provisjon fra betalingsmetoden registrert for "
        f"{store_name}.\n\nDette var forsøk {attempt} av {max_attempts}."
    )
    if will_suspend:
        body += (
            "\n\nSiden dette var det siste forsøket, er Vipps nå midlertidig deaktivert som betalingsmetode for "
            "butikken din inntil utestående beløp er gjort opp. Stripe-salg er ikke påvirket."
        )
    else:
        body += "\n\nVi prøver igjen automatisk. Sørg for at betalingsmetoden er gyldig for å unngå avbrudd."
    return subject, body


def build_invitation_email(seller_store_name: str, accept_url: str) -> tuple[str, str]:
    subject = f"Du er invitert til å bli ansatt hos {seller_store_name} på NorneTorg"
    body = (
        f"Du har blitt invitert til å administrere {seller_store_name} på NorneTorg.\n\n"
        f"Godta invitasjonen og sett et passord her:\n{accept_url}\n\n"
        "Lenken er gyldig i 7 dager."
    )
    return subject, body
