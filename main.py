import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth import router as auth_router
from routers.catalog import router as catalog_router
from routers.categories import router as categories_router
from routers.checkout import router as checkout_router
from routers.commission import router as commission_router
from routers.products import router as products_router
from routers.seller_payments import router as seller_payments_router
from routers.seller_profile import router as seller_profile_router
from routers.sellers import router as sellers_router
from routers.shipping_labels import router as shipping_labels_router
from routers.shipping_brackets import router as shipping_brackets_router
from routers.stripe_connect_webhook import router as stripe_connect_webhook_router
from routers.stripe_payment import router as stripe_payment_router
from routers.stripe_webhook import router as stripe_webhook_router
from routers.vipps_payment import router as vipps_payment_router
from routers.vipps_webhook import router as vipps_webhook_router
from utils.env import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

app = FastAPI(title="NorneTorg Backend")

# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# ROUTERS
# ---------------------------------------------------------
# Databasetabeller opprettes via Alembic (`alembic upgrade head`), ikke ved
# oppstart -- se alembic/ og lessons-learned-notatet i SPEC.md om
# Vitalityboost sin schema-drift-hendelse.

app.include_router(auth_router)
app.include_router(sellers_router)
app.include_router(seller_payments_router)
app.include_router(stripe_connect_webhook_router)
app.include_router(categories_router)
app.include_router(shipping_brackets_router)
app.include_router(products_router)
app.include_router(catalog_router)
app.include_router(checkout_router)
app.include_router(stripe_payment_router)
app.include_router(stripe_webhook_router)
app.include_router(vipps_payment_router)
app.include_router(vipps_webhook_router)
app.include_router(seller_profile_router)
app.include_router(shipping_labels_router)
app.include_router(commission_router)

# ---------------------------------------------------------
# ROOT
# ---------------------------------------------------------


@app.get("/")
def root():
    return {"status": "ok", "service": "NorneTorg Backend"}
