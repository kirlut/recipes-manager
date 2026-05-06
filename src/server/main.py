import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import auth, health
from api.errors import register_exception_handlers
from dal import db
from logging_config import configure_logging
from settings import settings

configure_logging(settings.log_level)
logger = logging.getLogger("recipes-manager")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "startup: initializing schema",
        extra={"postgres_host": settings.postgres_host, "postgres_port": settings.postgres_port},
    )
    await db.init_schema()
    logger.info("startup: schema ready")
    try:
        yield
    finally:
        await db.dispose()


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(auth.router)
