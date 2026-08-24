import httpx


class VippsAuthError(Exception):
    pass


class VippsAuth:
    """Verifies a seller-submitted Vipps API credential set by attempting a
    real client-credentials auth call against Vipps' own API -- we don't
    mark a seller as "connected" just because they typed something that
    looks like an API key, we confirm Vipps itself accepts it."""

    def __init__(self, client_id: str, client_secret: str, subscription_key: str, base_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.subscription_key = subscription_key
        self.base_url = base_url.rstrip("/")

    def fetch_access_token(self) -> str:
        headers = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "Ocp-Apim-Subscription-Key": self.subscription_key,
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(f"{self.base_url}/accesstoken/get", headers=headers)
        except httpx.HTTPError as e:
            raise VippsAuthError(f"Kunne ikke nå Vipps: {e}") from e

        if resp.status_code >= 400:
            raise VippsAuthError(f"Vipps avviste kredensialene (status {resp.status_code})")

        token = resp.json().get("access_token")
        if not token:
            raise VippsAuthError("Vipps svarte uten en gyldig access token")
        return token

    def get_headers(self) -> dict:
        access_token = self.fetch_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "client_id": self.client_id,
        }
