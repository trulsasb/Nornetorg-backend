import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth import router as auth_router
from routers.sellers import router as sellers_router
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

# ---------------------------------------------------------
# ROOT
# ---------------------------------------------------------


@app.get("/")
def root():
    return {"status": "ok", "service": "NorneTorg Backend"}
