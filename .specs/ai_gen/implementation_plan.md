# Implementation Plan — recipes-manager

A phased build plan. Each phase fits within a single Claude Code session
(~120-150K tokens of working context after system prompt and exploration
overhead) and ends with a green test folder under `tests/phase-{N}-{name}/`.

This document is the **execution order** for the project. Read alongside
`.specs/ai_gen/api_spec.md`, `.specs/ai_gen/db_schema.md`, and
`.specs/ai_gen/testing_strategy.md`.

---

## 0. Cross-phase setup (do once before phase 1)

These steps are not phase-specific and need to happen exactly once on the
developer machine:

- **Verify tooling**: `uv --version`, `docker --version`, `node --version`
  (≥ 20), `npm --version`. All four required for the project.
- **Postgres image**: `docker pull postgres:16-alpine` (used by both
  production and test composes).
- **Frontend tooling**: nothing global — Vite/Node deps live under
  `src/client/` and are installed with `npm ci` inside the build container.

There is no global state to seed before phase 1. The first phase produces the
repo skeleton from scratch.

---

## 1. Phase sizing rationale

A Claude Code session has roughly 200K tokens of working context. After the
system prompt, project instructions (`CLAUDE.md`), repo exploration, and tool
overhead, ~120-150K tokens remain for the actual work. A safe target per
phase is:

- **2-4K LOC** of new + modified material
- **10-20** new or substantially-modified files
- **One vertical slice** of functionality so the phase ends with a runnable,
  tested artifact

Frontend phases run hotter on context (JSX is dense and components reference
each other), so the UI is split across two phases (8 and 9) plus the final
consolidation phase (10).

The last phase (10) deliberately contains **no new feature code** — only
end-to-end tests and bug fixes uncovered by them. This protects the project
from the "everything works in isolation but breaks together" failure mode.

---

## 2. Phase index

| # | Name | Stack | New code? |
|---|---|---|---|
| 1 | Infra & docker baseline | postgres + backend + nginx | yes |
| 2 | DB schema + DAL foundation | postgres + backend | yes |
| 3 | Auth (register / login / me) | postgres + backend | yes |
| 4 | Products + nutrition facts + image upload | postgres + backend | yes |
| 5 | Recipes + nutrition totals | postgres + backend | yes |
| 6 | Listing + search + pagination + starring | postgres + backend | yes |
| 7 | Shopping list | postgres + backend | yes |
| 8 | Frontend foundations + auth + products UI | full stack | yes |
| 9 | Frontend recipes + shopping list UI | full stack | yes |
| 10 | E2E consolidation + bug fixes | full stack | bug fixes only |

Each phase strictly depends on every phase before it; there is no parallel
track.

---

## Phase 1 — Infra & docker baseline

**Goal**: a deployable scaffold. `docker compose up` brings up three healthy
containers and `GET http://localhost:8080/api/health` returns 200.

### Scope

- Repository skeleton: `src/server/`, `src/client/`, root `docker-compose.yml`,
  root `.env.example`.
- Backend Dockerfile (`python:3.12-slim` base, `uv` for deps, runs the
  entrypoint).
- Backend entrypoint serves a single endpoint: `GET /health` (no `/api`
  prefix at the FastAPI level — nginx adds `/api`). The router is mounted
  with `prefix="/api"` so the externally-visible URL is `/api/health`.
- The backend connects to Postgres on startup using `POSTGRES_*` env vars and
  fails fast if the connection cannot be established.
- nginx + statics container: `nginx:alpine` base + a placeholder
  `index.html`. Routing rules: `/api → backend:8000`, `/uploads → /uploads/`
  (mounted volume), `/` → statics.
- Frontend skeleton: `src/client/web/` produced by `npm create vite@latest`
  (React + TypeScript). The Vite dev server is **not** used in production —
  the Dockerfile builds with `npm run build` and copies `dist/` into the
  nginx image.
- `docker-compose.yml` declares three services (`postgres`, `backend`,
  `nginx`), one named volume `uploads`, and the configurable `${HOST_PORT:-8080}`
  binding for nginx.
- `.env.example` lists every env var with safe defaults (and a placeholder
  for `JWT_SECRET` to be filled in phase 3).

### Files created

```
.gitignore                              # py, node, .env, .venv, build artifacts
docker-compose.yml                      # 3 services + uploads volume
.env.example
src/server/Dockerfile
src/server/pyproject.toml                # uv-managed; deps: fastapi, uvicorn, asyncpg, sqlalchemy[asyncio], pydantic, pydantic-settings
src/server/uv.lock
src/server/main.py                       # FastAPI app, health router, startup hook
src/server/api/__init__.py
src/server/api/health.py                 # GET /health → {"status":"ok"}
src/server/dal/__init__.py
src/server/dal/db.py                     # async engine + connection helper
src/server/services/__init__.py
src/server/settings.py                   # pydantic-settings reading env
src/client/Dockerfile                    # multi-stage: node build → nginx:alpine
src/client/nginx/nginx.conf              # /api proxy, /uploads serving, /, gzip, no port 80 binding
src/client/web/                          # Vite scaffold (auto-generated)
src/client/web/package.json
src/client/web/vite.config.ts
src/client/web/index.html
src/client/web/src/App.tsx               # placeholder "recipes-manager"
src/client/web/src/main.tsx
tests/phase-1-infra/docker-compose.yml
tests/phase-1-infra/conftest.py
tests/phase-1-infra/test_healthcheck.py
tests/phase-1-infra/test_nginx_routing.py
tests/phase-1-infra/test_postgres_reachable.py
```

### Phase-specific setup

- Run `uv init` (or write `pyproject.toml` directly) inside `src/server/`.
  Add `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`,
  `pydantic`, `pydantic-settings`, `python-multipart`. Test extras:
  `pytest`, `pytest-asyncio`, `httpx`, `psycopg[binary]`.
- Run `npm create vite@latest web -- --template react-ts` inside `src/client/`.
- Add `.env.example` with `POSTGRES_*`, `JWT_SECRET=`, `IMAGE_DIR=/uploads`,
  `HOST_PORT=8080`, `SEARCH_SIMILARITY_THRESHOLD=0.3`. Document that the
  developer should `cp .env.example .env` and fill in `JWT_SECRET` in phase 3.

### Definition of done

- `docker compose up -d --wait` brings all three services healthy.
- `curl http://localhost:8080/api/health` returns `{"status":"ok"}`.
- `tests/phase-1-infra/` passes: `test_healthcheck.py`,
  `test_nginx_routing.py`, `test_postgres_reachable.py`. See
  `.specs/ai_gen/testing_strategy.md` §5 phase 1.

### Out of scope

- DB schema (phase 2).
- Auth (phase 3).
- Any business endpoint.

---

## Phase 2 — DB schema + DAL foundation

**Goal**: the backend creates the schema on startup, seeds nutrition fact
types, and exposes a structured-logging-ready entrypoint.

### Scope

- `src/server/dal/schema.sql` containing the full DDL from
  `.specs/ai_gen/db_schema.md` §9.
- `dal/db.py` extended with an `init_schema()` function that reads the SQL
  file and executes it within a single transaction.
- Entrypoint runs `init_schema()` on startup, before the FastAPI app starts
  serving.
- Structured JSON logging via `logging.config.dictConfig` configured at
  startup. Log records include level, logger name, message, and any extras
  passed via `logger.info(msg, extra={...})`.
- A small `dal/connections.py` (or similar) helper providing async context
  managers for both transactional and read-only DB operations using
  SQLAlchemy Core.

### Files created or modified

```
src/server/dal/schema.sql               # NEW — full DDL
src/server/dal/db.py                    # MODIFIED — add init_schema()
src/server/dal/connections.py           # NEW — context managers for tx / read-only
src/server/main.py                      # MODIFIED — call init_schema() before serving; configure logging
src/server/logging_config.py            # NEW — JSON formatter + dictConfig
src/server/settings.py                  # MODIFIED — add LOG_LEVEL, validate POSTGRES_* required
tests/phase-2-db/docker-compose.yml
tests/phase-2-db/conftest.py
tests/phase-2-db/test_schema.py
tests/phase-2-db/test_seed_data.py
```

### Phase-specific setup

- The test compose binds Postgres to a host port (e.g. 15432) so
  `psycopg`-based assertions can run from the test process.
- No env-var generation needed (`JWT_SECRET` is still unused in phase 2).

### Definition of done

- `docker compose up -d --wait` brings the schema to a state matching the DB
  schema doc.
- Restarting the backend twice is idempotent (no errors, no duplicate seed
  rows).
- `tests/phase-2-db/` passes: schema introspection assertions and seed-data
  assertion.

### Out of scope

- Any application table (users, products, recipes) is created but **not yet**
  written to. Endpoints touching them are still phase 3+.

---

## Phase 3 — Auth (register / login / me)

**Goal**: a user can register, log in, get a 24-hour JWT, and call a
protected endpoint with it.

### Scope

- `services/auth.py` — bcrypt verify/hash, JWT encode/decode, `expires_at`
  derivation.
- `dal/users.py` — `create_user`, `get_user_by_username`, `get_user_by_id`.
- `api/auth.py` — `POST /auth/register`, `POST /auth/login`, `GET /auth/me`.
  Mounted at `/api` in `main.py`.
- A reusable FastAPI dependency `current_user` that decodes the JWT from
  `Authorization: Bearer …` and loads the user from DB; raises 401 on any
  failure.
- Problem+JSON error response middleware. Any `HTTPException` (or custom
  `AppError`) returns `application/problem+json` per the API spec §4.
- Pydantic models for request/response shapes (snake_case property names).

### Files created or modified

```
src/server/services/auth.py             # NEW — bcrypt, jwt encode/decode
src/server/dal/users.py                 # NEW — user CRUD
src/server/api/auth.py                  # NEW — 3 endpoints
src/server/api/dependencies.py          # NEW — current_user dependency
src/server/api/errors.py                # NEW — Problem+JSON exception handlers
src/server/api/schemas/auth.py          # NEW — pydantic models
src/server/api/schemas/users.py         # NEW — User, UserRef
src/server/main.py                      # MODIFIED — register router + exception handlers
src/server/settings.py                  # MODIFIED — JWT_SECRET, JWT_TTL_HOURS=24, BCRYPT_COST=12
src/server/pyproject.toml               # MODIFIED — add pyjwt, bcrypt
tests/phase-3-auth/docker-compose.yml
tests/phase-3-auth/conftest.py
tests/phase-3-auth/test_register.py
tests/phase-3-auth/test_login.py
tests/phase-3-auth/test_me.py
```

### Phase-specific setup

- **Generate a JWT secret** for local dev:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
  Place the output in `.env` under `JWT_SECRET=`. Update `.env.example` with
  a comment instructing the next developer to run the same command.
- The test compose passes `JWT_SECRET=test-secret-do-not-use-in-prod`. Tests
  forge tokens with the same secret to exercise expired/malformed cases.

### Definition of done

- All three endpoints return the shapes specified in
  `.specs/ai_gen/api_spec.md` §2.
- All error cases return Problem+JSON with the documented `type` URIs.
- `tests/phase-3-auth/` passes.

### Out of scope

- Password reset, email verification, social login (out for v1 entirely).
- Token refresh (single 24h token; no refresh endpoint).
- User profile editing.

---

## Phase 4 — Products + nutrition facts + image upload

**Goal**: full product lifecycle (create, read, update, delete, copy) plus
image upload. Listing and search are deferred to phase 6.

### Scope

- `dal/products.py` with helpers for: insert product + facts atomically,
  fetch product with embedded facts, replace product + facts atomically,
  delete product (raise on referenced-by-recipes), copy product.
- `dal/images.py` (or similar) for writing uploaded bytes to `IMAGE_DIR`
  with a UUID4 filename, MIME sniffing for JPEG/PNG, size validation.
- `services/products.py` — orchestrate validation (≥ 1 fact, no
  `(fact_id, qty)` duplicates, unknown fact IDs), enforce ownership on
  PUT/DELETE.
- `api/products.py` — `POST`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`,
  `POST /{id}/copy`.
- `api/uploads.py` — `POST /uploads/images`.
- `api/nutrition_fact_types.py` — `GET /nutrition-fact-types` (small but
  belongs to this phase since products depend on the data).
- Pydantic schemas for product create/read.

### Files created or modified

```
src/server/dal/products.py
src/server/dal/images.py                # disk write + UUID filename
src/server/dal/nutrition_fact_types.py  # simple SELECT
src/server/services/products.py
src/server/services/images.py           # validation + filename generation
src/server/services/nutrition_fact_types.py
src/server/api/products.py
src/server/api/uploads.py
src/server/api/nutrition_fact_types.py
src/server/api/schemas/products.py
src/server/api/schemas/uploads.py
src/server/api/schemas/nutrition_fact_types.py
src/server/main.py                      # MODIFIED — register new routers, ensure IMAGE_DIR exists at startup
src/server/settings.py                  # MODIFIED — IMAGE_DIR, IMAGE_MAX_BYTES=5*1024*1024
src/server/pyproject.toml               # MODIFIED — add python-magic-bin or rely on header sniffing helper
tests/phase-4-products/docker-compose.yml
tests/phase-4-products/conftest.py
tests/phase-4-products/test_products_crud.py
tests/phase-4-products/test_products_validation.py
tests/phase-4-products/test_products_authz.py
tests/phase-4-products/test_products_copy.py
tests/phase-4-products/test_uploads.py
```

### Phase-specific setup

- The `IMAGE_DIR` is created at startup if missing
  (`os.makedirs(settings.IMAGE_DIR, exist_ok=True)`).
- MIME sniffing: read the first 32 bytes of the uploaded file. JPEG starts
  with `FF D8 FF`, PNG with `89 50 4E 47 0D 0A 1A 0A`. No external binary
  needed.

### Definition of done

- Endpoints behave per `.specs/ai_gen/api_spec.md` §6 and §10.
- `tests/phase-4-products/` passes (CRUD, validation, authz, copy, upload).

### Out of scope

- Listing endpoint (`GET /products` without an id) — phase 6.
- Searching products — phase 6.
- Starring products — phase 6.

---

## Phase 5 — Recipes + nutrition totals

**Goal**: full recipe lifecycle plus on-the-fly nutrition total computation.

### Scope

- `dal/recipes.py` — insert recipe + recipe_products atomically, fetch with
  embedded products, replace, delete, copy.
- `services/recipes.py` — compute `nutrition_totals_per_serving` (per the
  formula in `.specs/ai_gen/api_spec.md` §13), validate
  `quantity_type` against `product_nutrition_facts`, enforce ownership on
  PUT/DELETE, enforce no-duplicate-product rule.
- `api/recipes.py` — `POST`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`,
  `POST /{id}/copy`.
- Pydantic schemas for recipes.

### Files created or modified

```
src/server/dal/recipes.py
src/server/services/recipes.py
src/server/api/recipes.py
src/server/api/schemas/recipes.py
src/server/main.py                      # MODIFIED — register recipes router
tests/phase-5-recipes/docker-compose.yml
tests/phase-5-recipes/conftest.py
tests/phase-5-recipes/test_recipes_crud.py
tests/phase-5-recipes/test_recipes_totals.py
tests/phase-5-recipes/test_recipes_quantity_type_mismatch.py
tests/phase-5-recipes/test_recipes_authz.py
tests/phase-5-recipes/test_recipes_copy.py
```

### Phase-specific setup

- None beyond what previous phases provide.

### Definition of done

- All endpoints in `.specs/ai_gen/api_spec.md` §7 work.
- `nutrition_totals_per_serving` matches the formula exactly. The phase-5
  totals test asserts the worked example from the API spec / test strategy
  doc.
- `tests/phase-5-recipes/` passes.

### Out of scope

- Recipe listing/search — phase 6.
- Recipe starring — phase 6.

---

## Phase 6 — Listing + search + pagination + starring

**Goal**: all list endpoints, cursor pagination, `pg_trgm` search, and
star/unstar for both recipes and products.

### Scope

- `api/listing.py` (or extend per-resource files) — `GET /products`,
  `GET /recipes` with `scope=mine|starred|search`, `q`, `cursor`, `limit`.
- `services/cursor.py` — opaque cursor encode/decode (base64url over a
  small JSON envelope `{"k": "...", "v": [...]}`); `400` with type
  `/errors/invalid-cursor` on decode failure.
- `dal/products.py`, `dal/recipes.py` — extended with three list query
  builders (mine, starred, search) using SQLAlchemy Core.
- `dal/stars.py` — insert/delete in `recipe_stars` and `product_stars`
  tables, idempotent (`ON CONFLICT DO NOTHING` for insert, plain DELETE).
- `services/stars.py` — orchestrate idempotent star/unstar.
- `api/stars.py` (or per-resource sub-routers) —
  `PUT /products/{id}/star`, `DELETE /products/{id}/star`,
  `PUT /recipes/{id}/star`, `DELETE /recipes/{id}/star`.
- Backfill `starred_by_me` in product/recipe responses (one extra
  `EXISTS` subquery for the caller's user_id).
- `services/products.py`, `services/recipes.py` — read
  `SET LOCAL pg_trgm.similarity_threshold = ...` per request when running a
  `scope=search` query, sourced from `SEARCH_SIMILARITY_THRESHOLD`.

### Files created or modified

```
src/server/services/cursor.py
src/server/dal/stars.py
src/server/dal/products.py              # MODIFIED — list queries, starred_by_me
src/server/dal/recipes.py               # MODIFIED — list queries, starred_by_me
src/server/services/stars.py
src/server/services/products.py         # MODIFIED — list orchestration, search threshold
src/server/services/recipes.py          # MODIFIED — same
src/server/api/products.py              # MODIFIED — add list + star endpoints
src/server/api/recipes.py               # MODIFIED — same
src/server/api/schemas/pagination.py    # NEW — Page envelope, cursor types
tests/phase-6-listing/docker-compose.yml
tests/phase-6-listing/conftest.py
tests/phase-6-listing/test_pagination.py
tests/phase-6-listing/test_search.py
tests/phase-6-listing/test_starring.py
```

### Phase-specific setup

- None beyond previous phases. `SEARCH_SIMILARITY_THRESHOLD` already in
  `.env.example` from phase 1; tests pass `0.3` explicitly to assert the
  threshold gate in `test_search.py`.

### Definition of done

- Pagination terminates correctly with no overlap and no missing items.
- Search ranks by similarity and respects the threshold.
- Star/unstar idempotent and visible via `scope=starred`.
- `starred_by_me` flag is correct on all detail and list responses.
- `tests/phase-6-listing/` passes.

### Out of scope

- Shopping list — phase 7.
- Frontend.

---

## Phase 7 — Shopping list

**Goal**: backend computes shopping lists across selected recipes and
servings.

### Scope

- `services/shopping_list.py` — accepts `[{recipe_id, servings}]`, validates
  every recipe is owned-or-starred by caller, fetches all
  `recipe_products` rows in a single query, aggregates by
  `(product_id, quantity_type)`, joins to `products` for name/image, sorts
  by `(product_name, quantity_type)`.
- `api/shopping_list.py` — `POST /shopping-list`.
- Pydantic schemas for the request and response.

### Files created or modified

```
src/server/services/shopping_list.py
src/server/dal/shopping_list.py         # single aggregation query
src/server/api/shopping_list.py
src/server/api/schemas/shopping_list.py
src/server/main.py                      # MODIFIED — register router
tests/phase-7-shopping-list/docker-compose.yml
tests/phase-7-shopping-list/conftest.py
tests/phase-7-shopping-list/test_shopping_list_aggregation.py
tests/phase-7-shopping-list/test_shopping_list_authz.py
tests/phase-7-shopping-list/test_shopping_list_validation.py
```

### Phase-specific setup

- None.

### Definition of done

- Aggregation matches the formula in `.specs/ai_gen/api_spec.md` §13 exactly.
- Caller cannot include a recipe they don't own and haven't starred.
- `tests/phase-7-shopping-list/` passes.

### Out of scope

- Frontend shopping list UI — phase 9.
- Persisting shopping lists — never (out of scope for v1).

---

## Phase 8 — Frontend foundations + auth + products UI

**Goal**: a working browser experience for register, login, and the entire
products section. Listing/search/starring/copying products all work end-to-end.

### Scope

- Replace the Vite scaffold with a real app structure under
  `src/client/web/src/`.
- Routing via `react-router-dom`. Routes:
  `/login`, `/register`, `/` (redirect to `/products`),
  `/products` (with sub-tabs: My / Starred / Search),
  `/products/new`, `/products/:id`, `/products/:id/edit`.
- Data fetching via `@tanstack/react-query`. A typed `apiClient` wraps
  `fetch` with the bearer token from `localStorage`.
- Tailwind CSS + DaisyUI for styling. Use a single light DaisyUI theme.
- Mobile-friendly layout: a top app bar with current section and a
  hamburger menu on small screens; full sidebar on `md+`.
- Auth flow: `/login` and `/register` post to the backend, store the
  resulting token in `localStorage` under key `auth_token`, store user info
  in a React Query cache. A 401 response from any API call clears the token
  and bounces to `/login`.
- Products section:
  - List views with infinite-scroll (intersection observer) for My, Starred,
    Search.
  - Search input with debounce (300 ms).
  - Detail page showing image, nutrition facts grouped by `quantity_type`,
    creator info, star button. If caller is owner: Edit and Delete buttons.
    If not: Copy button.
  - Create / Edit form with image upload (uploaded synchronously to
    `/api/uploads/images`, then the resulting filename is included in the
    create/update body). Two collapsible sub-forms for weight facts and
    volume facts. Per-form: select `nutrition_fact_id` (from
    `/api/nutrition-fact-types`), enter `amount`. Validate non-negative,
    no duplicates, ≥ 1 fact total before allowing submit.
- 404 / generic-error fallback components reading Problem+JSON `title` /
  `detail` / `extensions.violations`.

### Files created or modified

```
src/client/web/package.json             # MODIFIED — react-router-dom, @tanstack/react-query, tailwindcss, daisyui, postcss, autoprefixer
src/client/web/tailwind.config.js
src/client/web/postcss.config.js
src/client/web/src/main.tsx             # MODIFIED — QueryClientProvider, BrowserRouter
src/client/web/src/App.tsx              # MODIFIED — routing
src/client/web/src/index.css            # tailwind directives
src/client/web/src/api/client.ts
src/client/web/src/api/types.ts         # mirror of API spec types in TS
src/client/web/src/api/auth.ts
src/client/web/src/api/products.ts
src/client/web/src/api/uploads.ts
src/client/web/src/api/nutritionFactTypes.ts
src/client/web/src/auth/AuthContext.tsx
src/client/web/src/auth/useAuth.ts
src/client/web/src/components/Layout.tsx
src/client/web/src/components/InfiniteList.tsx
src/client/web/src/components/ImageUpload.tsx
src/client/web/src/components/ErrorBanner.tsx
src/client/web/src/pages/Login.tsx
src/client/web/src/pages/Register.tsx
src/client/web/src/pages/products/ProductsList.tsx       # tabs: mine|starred|search
src/client/web/src/pages/products/ProductDetail.tsx
src/client/web/src/pages/products/ProductForm.tsx        # used by new + edit
tests/phase-8-frontend-products/docker-compose.yml       # full prod-shaped stack
tests/phase-8-frontend-products/conftest.py
tests/phase-8-frontend-products/test_register_login.py
tests/phase-8-frontend-products/test_create_product.py
tests/phase-8-frontend-products/test_search_products.py
tests/phase-8-frontend-products/test_edit_own_product.py
tests/phase-8-frontend-products/test_copy_other_users_product.py
tests/phase-8-frontend-products/test_infinite_scroll.py
```

### Phase-specific setup

- Install Playwright browser:
  ```bash
  uv run playwright install chromium
  ```
  Document this in CLAUDE.md.
- Inside `src/client/web/`: `npm install` to update lockfile after adding
  Tailwind, DaisyUI, react-router-dom, @tanstack/react-query.
- Configure DaisyUI in `tailwind.config.js` with a single light theme (e.g.
  `"light"`).

### Definition of done

- A user can register, log in, create a product (with an image), find it
  via search, star it, edit it. Another user can find it, star it, copy it.
- Infinite scroll loads additional pages without re-rendering the entire
  list.
- `tests/phase-8-frontend-products/` passes.

### Out of scope

- Recipes UI — phase 9.
- Shopping list UI — phase 9.

---

## Phase 9 — Frontend recipes + shopping list UI

**Goal**: complete UX. Users can manage recipes (with embedded products and
on-the-fly totals display) and compute shopping lists across multiple
recipes.

### Scope

- Recipes section: routes
  `/recipes` (My / Starred / Search tabs),
  `/recipes/new`, `/recipes/:id`, `/recipes/:id/edit`.
- Recipe detail view: shows products list, computed
  `nutrition_totals_per_serving` (rendered as a small table with units),
  star/copy/edit/delete actions per ownership.
- Recipe create/edit form: name, description, image, plus a "products"
  sub-form with an autocomplete picker over the products listing API
  (re-uses the products search endpoint), choice of `quantity_type` (only
  the values supported by that product based on its facts), `amount`.
- Shopping list section: route `/shopping-list`. UI:
  1. Top: list of selected recipes with `servings` inputs (defaults 1).
  2. "Add recipe" button opens a modal listing the user's own recipes plus
     starred recipes (from the listing API).
  3. "Compute" button posts to `/api/shopping-list` and renders the result
     as a sortable table (product, quantity_type, amount, unit).
  4. Items remain displayed until the user changes the selection — no
     persistence.

### Files created or modified

```
src/client/web/src/api/recipes.ts
src/client/web/src/api/shoppingList.ts
src/client/web/src/components/ProductPicker.tsx          # autocomplete over /api/products?scope=search
src/client/web/src/components/QuantityTypeRadio.tsx
src/client/web/src/components/RecipePicker.tsx           # modal listing mine+starred
src/client/web/src/pages/recipes/RecipesList.tsx
src/client/web/src/pages/recipes/RecipeDetail.tsx
src/client/web/src/pages/recipes/RecipeForm.tsx
src/client/web/src/pages/recipes/NutritionTotalsTable.tsx
src/client/web/src/pages/shopping-list/ShoppingListPage.tsx
src/client/web/src/App.tsx                              # MODIFIED — register new routes + nav
src/client/web/src/components/Layout.tsx                # MODIFIED — add Recipes + Shopping List nav entries
tests/phase-9-frontend-recipes-and-shopping/docker-compose.yml
tests/phase-9-frontend-recipes-and-shopping/conftest.py
tests/phase-9-frontend-recipes-and-shopping/test_create_recipe.py
tests/phase-9-frontend-recipes-and-shopping/test_recipe_totals_match_backend.py
tests/phase-9-frontend-recipes-and-shopping/test_copy_recipe.py
tests/phase-9-frontend-recipes-and-shopping/test_shopping_list.py
```

### Phase-specific setup

- None new (Playwright browser installed in phase 8).

### Definition of done

- All recipe and shopping-list user flows work end-to-end in the browser.
- Frontend-displayed totals match backend computations (asserted directly
  in `test_recipe_totals_match_backend.py`).
- `tests/phase-9-frontend-recipes-and-shopping/` passes.

### Out of scope

- Anything not specified in `.specs/system_spec.md`.

---

## Phase 10 — Final integration + E2E consolidation

**Goal**: prove the full system works as one. **No new feature code.** Only
fixes for issues surfaced by the E2E test, and the single suite-runner
script.

### Scope

- `tests/phase-10-e2e/` — a single comprehensive Playwright user-journey
  test (see `.specs/ai_gen/testing_strategy.md` §5 phase 10).
- `run-all-tests.sh` at repo root, per `.specs/ai_gen/testing_strategy.md` §8.
- Final pass on `CLAUDE.md` to confirm test commands, env vars, and
  Playwright install steps are documented.

If phase 10 surfaces a defect:

- Diagnose it in the relevant earlier-phase component.
- Fix it there. Add or extend the relevant phase's test to cover the
  regression.
- Re-run `./run-all-tests.sh` until green.

### Files created or modified

```
run-all-tests.sh
tests/phase-10-e2e/docker-compose.yml
tests/phase-10-e2e/conftest.py
tests/phase-10-e2e/test_user_journey.py
CLAUDE.md                               # MODIFIED — final pass on testing section
# plus any earlier-phase files touched by bug fixes
```

### Phase-specific setup

- Verify `playwright install chromium` was run on the machine.

### Definition of done

- `./run-all-tests.sh` (no args) exits 0.
- `./run-all-tests.sh --keep-going` exits 0 and reports every phase as
  passing.
- The phase-10 user journey covers, at minimum: register two users, each
  creating products and a recipe, one user copying the other's recipe,
  starring across users, and computing a multi-recipe shopping list with
  numeric assertions.

### Out of scope

- New endpoints.
- Schema changes.
- Frontend feature additions.

If something feels missing during phase 10, file it as a follow-up rather
than expanding this phase's scope.

---

## 3. Phase boundaries and dependency contract

| Phase | Adds | Depends on |
|---|---|---|
| 1 | Repo skeleton, healthcheck | — |
| 2 | DB schema, init_schema, JSON logging | 1 |
| 3 | Users, JWT, register/login/me | 2 |
| 4 | Products, nutrition facts, image upload, nutrition_fact_types | 3 |
| 5 | Recipes, recipe_products, totals | 4 |
| 6 | Listing, search, pagination, starring | 5 |
| 7 | Shopping list | 6 |
| 8 | Frontend foundations + products UI | 7 |
| 9 | Frontend recipes + shopping-list UI | 8 |
| 10 | E2E + bug fixes + run-all-tests.sh | 9 |

Cross-phase rule: a phase MUST NOT modify code outside its own scope unless
fixing a bug surfaced by its own tests. If a phase reveals that an
earlier-phase API was insufficient (e.g. needs an extra field), the phase
extends it minimally and updates **both** the relevant spec doc
(`api_spec.md` or `db_schema.md`) and `CLAUDE.md` in the same change.

---

## 4. What "done" means for the whole project

- All 10 phase test suites pass via `./run-all-tests.sh`.
- `CLAUDE.md` is current and a fresh agent session can read it + the four
  spec docs and pick up any phase.
- A non-developer user can `cp .env.example .env`, fill in `JWT_SECRET`,
  `docker compose up -d`, browse to `http://localhost:8080`, register,
  create products and recipes, generate a shopping list.
- No code paths reference `import_source` for client-driven mutation (that
  field exists only for forward compatibility with future imports, which
  remain out of scope).
