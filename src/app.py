import os

from dotenv import load_dotenv

# ===========================
# !!! ATTENTION !!!
# KEEP THIS AT THE TOP TO ENSURE ENVIRONMENT VARIABLES ARE LOADED BEFORE ANY IMPORTS
# ===========================
load_dotenv()

from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from loguru import logger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from src.configs import DatabaseConfig
from src.entities import api_router
from src.middlewares import AuthenticationMiddleware, AuthorizationMiddleware


def run_upgrade(connection, alembic_config: Config):
    alembic_config.attributes["connection"] = connection
    command.upgrade(alembic_config, "head")


async def run_migrations():
    logger.info("Running migrations if any...")
    alembic_config = Config("alembic.ini")
    database_url = os.getenv("SQLALCHEMY_DATABASE_URI")
    if database_url:
        alembic_config.set_main_option("sqlalchemy.url", database_url)
    async with DatabaseConfig.get_engine().begin() as session:
        await session.run_sync(run_upgrade, alembic_config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting up the application...")
        await run_migrations()
        logger.info("Application started successfully...")
        yield
    except Exception as e:
        logger.exception(e)
        raise
    finally:
        logger.info("Application shutdown complete.")


app = FastAPI(lifespan=lifespan)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Paste only the raw JWT token; Swagger adds the 'Bearer ' prefix automatically.",
    }

    for path, methods in openapi_schema.get("paths", {}).items():
        if not path.startswith("/api/v1/"):
            continue
        for _, operation in methods.items():
            operation.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


app.add_middleware(AuthorizationMiddleware)
app.add_middleware(AuthenticationMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOW_ORIGINS", "http://localhost, http://127.0.0.1"
        ).split(",")
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["Health Check"])
async def check_health():
    return {"response": "Service is healthy!"}


app.include_router(api_router, prefix="/api")
