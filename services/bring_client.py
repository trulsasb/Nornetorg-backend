from dataclasses import dataclass

import httpx

from utils.env import settings


class BringClientError(Exception):
    pass


@dataclass
class Address:
    name: str
    address_line: str
    postal_code: str
    city: str
    country: str = "NO"


@dataclass
class BookedShipment:
    bring_shipment_id: str
    tracking_number: str
    label_url: str
    postage_cost: float


class BringClient:
    """Thin wrapper around Bring's Booking API for buying postage and
    generating a shipping label -- see SPEC.md 3.2/4.4.

    IMPORTANT: the exact request/response shape, endpoint paths, and auth
    header names below are a reasonable placeholder based on Bring's
    publicly documented Booking API conventions (X-MyBring-API-Uid /
    X-MyBring-API-Key auth, POST /booking/api/booking), NOT verified
    against a live account -- SPEC.md 3.2 explicitly calls this out.
    Verify against Bring's current documentation and a real sandbox
    account before this ever runs against production."""

    BASE_URL = "https://api.bring.com"

    def __init__(self, api_key: str, customer_number: str):
        self.api_key = api_key
        self.customer_number = customer_number

    def book_shipment(
        self,
        sender: Address,
        recipient: Address,
        bring_product_code: str,
        weight_g: int,
    ) -> BookedShipment:
        if not self.api_key or not self.customer_number:
            raise BringClientError("Bring er ikke konfigurert")

        headers = {
            "X-MyBring-API-Uid": self.customer_number,
            "X-MyBring-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        body = {
            "customerNumber": self.customer_number,
            "product": bring_product_code,
            "weightInGrams": weight_g,
            "sender": {
                "name": sender.name,
                "addressLine": sender.address_line,
                "postalCode": sender.postal_code,
                "city": sender.city,
                "countryCode": sender.country,
            },
            "recipient": {
                "name": recipient.name,
                "addressLine": recipient.address_line,
                "postalCode": recipient.postal_code,
                "city": recipient.city,
                "countryCode": recipient.country,
            },
        }

        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(f"{self.BASE_URL}/booking/api/booking", headers=headers, json=body)
        except httpx.HTTPError as e:
            raise BringClientError(f"Kunne ikke nå Bring: {e}") from e

        if resp.status_code >= 400:
            raise BringClientError(f"Bring avviste bestillingen (status {resp.status_code}): {resp.text}")

        data = resp.json()
        try:
            return BookedShipment(
                bring_shipment_id=data["shipmentId"],
                tracking_number=data["trackingNumber"],
                label_url=data["labelUrl"],
                postage_cost=float(data["price"]),
            )
        except (KeyError, ValueError, TypeError) as e:
            raise BringClientError(f"Uventet svarformat fra Bring: {e}") from e


def get_bring_client() -> BringClient:
    return BringClient(api_key=settings.BRING_API_KEY, customer_number=settings.BRING_CUSTOMER_NUMBER)
