from celery import Celery

from utils.env import settings

celery_app = Celery(
    "nornetorg",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Oslo",
    enable_utc=True,
)

# Ingen tasks ennå -- lagt til etter hvert som modulene som trenger dem
# bygges: fraktberegning (Modul 9), provisjonstrekk/dunning (Modul 10),
# selgervarsling, periodisk statistikk.
