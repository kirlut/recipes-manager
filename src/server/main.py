import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import auth, health, nutrition_fact_types, products, uploads
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
    os.makedirs(settings.image_dir, exist_ok=True)
    logger.info(
        "startup: schema ready",
        extra={"image_dir": settings.image_dir},
    )
    try:
        yield
    finally:
        await db.dispose()


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(nutrition_fact_types.router)
app.include_router(products.router)
app.include_router(uploads.router)
