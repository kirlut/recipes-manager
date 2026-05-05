# Project Guidelines

Rules below are derived from `.specs/system_spec.md`. Refer to that spec for the full system design, data model, and business rules not captured here.

## Repository Layout

- `src/client/` — frontend app + nginx. Has its own `Dockerfile`. All nginx files live here.
- `src/server/` — Python backend. Has its own `Dockerfile`.
- `docker-compose.yml` — at repo root.
- `.env` — at repo root.

## Components & Deployment

- Three containers when deployed:
  - nginx + frontend statics (single container).
  - Python backend (separate container).
  - Postgres (separate container).
- A Docker volume for image storage is shared between the client container and the backend container.
- The backend is reachable **only** via nginx within the Docker network; it must not be exposed externally.
- nginx routing: `/api` → backend, `/uploads` → shared image volume, `/` → frontend statics.
- All base Docker images must be official packages from Docker Hub. No custom or third-party base images.
- Never bind a container to host port 80. Expose nginx on a configurable host port, default `8080`.

## Backend — `src/server`

### Code Organization (horizontal layers)

- `api/` — FastAPI endpoints. One file per entity. Use `APIRouter` and register routers via `app.include_router` in the entrypoint.
- `services/` — business logic; split by entity / core abstraction.
- `dal/` — all database access.
- Entrypoint script lives at the root of `src/server`. It reads config, initializes components, and keeps the app running.
- Class and abstraction names must follow the entity vocabulary defined in `.specs/system_spec.md` §5.1.

### Stack

- FastAPI as the web framework.
- `pydantic` for type safety and validation.
- SQLAlchemy with async support: `sqlalchemy[asyncio]` + `asyncpg`. Use SQLAlchemy **Core**, not the ORM.

### Packages & Local Run

- Use `uv` only (already installed on this machine).
- Add packages with `uv add`. Run code with `uv run`.
- Do **not** use `pip`.

### Database

- Postgres.
- `snake_case` for all table and column names.
- All `id` fields are `BIGINT`.
- Recipe and product `name` columns are indexed with `GIST` on `pg_trgm`. The `pg_trgm` extension is required. Search uses `similarity()` with a configurable threshold.
- Schema is initialized on app startup if not already present. No DB migration tooling.

### Auth & Security

- Passwords hashed with salt using `bcrypt`.
- JWT auth using HS256. Use `pyjwt` for token handling and signature checks.

### Image Uploads

- Accept JPEG and PNG only; reject other formats.
- Max file size: 5 MB.
- Stored filenames are UUID4 with the original extension preserved (e.g. `a3f1b2c4-...-.jpg`).
- Files are written to the shared Docker volume and served by nginx at `/uploads`.

### Configuration

- Env vars only, with `.env` file support.
- Configurable items: DB connection settings, HS256 JWT secret, path to the image folder (mounted to the volume).

### Logging

- Structured JSON to stdout. Use the standard library `logging` module.

## Frontend — `src/client`

- Frontend framework choice is open — pick something simple and reliable.
- Organize code according to best practices for the chosen framework.
- Layout must work and adapt automatically to both regular and mobile screens.
- List views use cursor-based pagination; the frontend implements infinite scroll on top of it.

## Out of Scope (v1)

Do not introduce: a caching layer (e.g. Redis), DB migration tooling, or external dataset import (despite the `import_source` column existing in the data model).
