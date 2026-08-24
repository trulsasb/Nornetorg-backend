from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from utils.env import settings

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
# Ingen rutere ennå -- Modul 2 (bruker-/selgerautentisering) legger til de
# første. Databasetabeller opprettes via Alembic (`alembic upgrade head`),
# ikke ved oppstart -- se alembic/ og lessons-learned-notatet i SPEC.md
# om Vitalityboost sin schema-drift-hendelse.

# ---------------------------------------------------------
# ROOT
# ---------------------------------------------------------


@app.get("/")
def root():
    return {"status": "ok", "service": "NorneTorg Backend"}
