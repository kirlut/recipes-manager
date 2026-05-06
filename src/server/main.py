import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import health
from dal import db
from settings import settings

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("recipes-manager")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup: pinging database at %s:%d", settings.postgres_host, settings.postgres_port)
    await db.ping()
    logger.info("startup: database reachable")
    try:
        yield
    finally:
        await db.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(health.router)
