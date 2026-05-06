# Testing Strategy — recipes-manager

How the test suite is structured, what each phase verifies, and how tests are
executed locally and from a future CI runner.

---

## 1. Stance

- **Integration tests only.** No unit tests of internal classes or functions.
  Tests interact with the running application through stable boundaries (HTTP
  API, browser UI, direct DB inspection).
- **One reason**: this codebase is small enough that integration-only coverage
  is feasible, and integration tests catch the failure modes the system
  actually has (Docker wiring, schema drift, JSON contract bugs, frontend/back
  contract mismatches) — internal refactors should never break a passing test.
- **Tests are the only acceptance signal per phase.** A phase is "done" when
  its test folder runs green against the phase's deliverable code.

---

## 2. Tooling

| Concern | Tool | Notes |
|---|---|---|
| Test runner | `pytest` | Sole runner for both API and Playwright tests. |
| Async | `pytest-asyncio` | `asyncio_mode = "auto"` in `pyproject.toml`. |
| HTTP client | `httpx` | For API tests; supports both sync and async. |
| Direct DB introspection | `psycopg[binary]` | Sync driver, simple for assertions on schema and seed data. |
| Browser automation | `pytest-playwright` | Drives Chromium against the full stack for frontend phases. |
| JWT forgery | `pyjwt` | Used in auth tests (phase 3+) to encode tokens with deliberately invalid `exp` or wrong secret. Same library the backend uses. |
| Image fixtures | tiny in-test JPEG/PNG bytes | No external assets needed. |

All test deps live under a `[project.optional-dependencies].test` section in
`pyproject.toml`. They are installed via `uv sync --extra test`.

---

## 3. Directory layout

```
tests/
├── conftest.py                        # cross-phase fixtures (rare; mostly just helpers)
├── helpers/                           # shared Python helpers (auth, image bytes, DB url)
│   ├── __init__.py
│   ├── api.py                         # API client helpers
│   ├── images.py                      # tiny valid JPEG / PNG byte blobs
│   └── db.py                          # psycopg URL parsing
├── phase-1-infra/
│   ├── docker-compose.yml             # phase-specific stack
│   ├── conftest.py                    # phase-local fixtures
│   ├── test_healthcheck.py
│   ├── test_nginx_routing.py
│   └── test_postgres_reachable.py
├── phase-2-db/
│   ├── docker-compose.yml
│   ├── conftest.py
│   ├── test_schema.py
│   └── test_seed_data.py
├── phase-3-auth/
├── phase-4-products/
├── phase-5-recipes/
├── phase-6-listing/
├── phase-7-shopping-list/
├── phase-8-frontend-products/
├── phase-9-frontend-recipes-and-shopping/
└── phase-10-e2e/
```

The `phase-{N}-{kebab-name}` numbering matches `.specs/ai_gen/implementation_plan.md`
exactly. Each phase folder is self-contained — copy-pasting it to a fresh
checkout and running its tests must work, given the implementation code from
that phase already exists.

---

## 4. Per-phase docker-compose isolation

Each `tests/phase-N-name/docker-compose.yml` is **independent** from the root
`docker-compose.yml`. Rules:

1. **Distinct project name** via the top-level `name:` key, e.g.
   `name: recipes-manager-test-phase-3-auth`. This keeps containers, networks,
   and volumes namespaced per phase. Two phase test stacks can run side by
   side without conflict.
2. **Distinct volume names** — each compose file declares its own named
   volumes; they do not share the production volume names.
3. **Distinct host ports** — every phase advertises its public port via
   `${HOST_PORT:-8080}` (default 8080). Test runs that need to parallelize must
   pass `HOST_PORT` explicitly.
4. **Never port 80** — any host-port binding uses 8080 by default. Tests must
   not hard-code 80.
5. **Image build** — compose files build images locally from `src/server` and
   `src/client` (relative path: `../../src/server`). They do not pull
   pre-built images.
6. **Health gates** — every backend / db service declares a `healthcheck:` and
   tests use `docker compose up -d --wait` (or `--wait-timeout`) so pytest
   only starts after services are healthy.
7. **Backend port exposure for API tests** — for backend-only phases (3-7),
   the test compose may bind the FastAPI service directly to a host port
   (e.g. `127.0.0.1:18000:8000`) so API tests can hit it without going
   through nginx. **The production compose still does not expose the
   backend.**
8. **No host filesystem writes** — tests must not mount or write to host
   paths beyond what compose itself does. Image upload tests verify by
   hitting nginx's `/uploads/<filename>` URL, not by checking the host
   filesystem.

### 4.1 Compose template (sketch)

```yaml
name: recipes-manager-test-phase-N-name

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: recipes_test
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d recipes_test"]
      interval: 1s
      timeout: 3s
      retries: 30
    ports:
      - "127.0.0.1:${POSTGRES_HOST_PORT:-15432}:5432"   # only when DB-direct testing is needed
    volumes:
      - test_pgdata:/var/lib/postgresql/data

  backend:
    build: ../../src/server
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: recipes_test
      JWT_SECRET: test-secret-do-not-use-in-prod
      IMAGE_DIR: /uploads
      SEARCH_SIMILARITY_THRESHOLD: "0.3"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/health"]
      interval: 1s
      timeout: 3s
      retries: 30
    ports:
      - "127.0.0.1:${BACKEND_HOST_PORT:-18000}:8000"    # only for backend-only phases
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - test_uploads:/uploads

  nginx:
    build: ../../src/client
    ports:
      - "127.0.0.1:${HOST_PORT:-8080}:80"
    depends_on:
      backend:
        condition: service_healthy
    volumes:
      - test_uploads:/uploads:ro

volumes:
  test_pgdata:
  test_uploads:
```

For phases that don't require the frontend (3-7), the `nginx` service is
omitted; tests hit `http://127.0.0.1:18000` directly. For frontend phases
(8-10), the test compose includes nginx and a built frontend image; tests hit
`http://127.0.0.1:8080`.

---

## 5. Phase-by-phase test deliverables

The test scope per phase is driven by `.specs/ai_gen/implementation_plan.md`'s
"Definition of done". This section lists the test files and what each verifies.
Implementation in each phase must produce **at least** these files, but may
add more.

### Phase 1 — `tests/phase-1-infra/`

Stack: postgres + backend + nginx (production-shaped).

- `test_healthcheck.py` — `GET http://localhost:8080/api/health` → 200 with `{"status":"ok"}`.
- `test_nginx_routing.py` — `GET /api/<unknown>` returns 404 from the backend, confirming the `/api` proxy. (Body shape is not asserted in phase 1; the Problem+JSON middleware is introduced in phase 3, where it is verified.) `GET /uploads/missing.jpg` returns 404 from nginx (no backend involvement) — distinguishable by the `text/html` content-type of nginx's default 404 page versus the backend's JSON.
- `test_postgres_reachable.py` — connect via `psycopg` to the test compose Postgres (using its host-bound port), execute `SELECT 1`. Confirms image, env, and networking are wired.

### Phase 2 — `tests/phase-2-db/`

Stack: postgres + backend.

- `test_schema.py` — connect via `psycopg`, query `pg_extension` for `pg_trgm`, query `information_schema.tables` for the eight required tables, query `pg_indexes` for every index in §5 of the DB schema doc, verify CHECK constraints exist via `pg_constraint`.
- `test_seed_data.py` — `SELECT name, unit FROM nutrition_fact_types ORDER BY name` returns the five expected rows.

### Phase 3 — `tests/phase-3-auth/`

Stack: postgres + backend (host-bound on 18000).

- `test_register.py` — happy path, returns 201 + `User`. Duplicate username → 409 with type `/errors/conflict-username`. Short password → 400 with type `/errors/validation`.
- `test_login.py` — happy path returns JWT and `expires_at`. Wrong password → 401 (no enumeration). Unknown username → 401 (same body, no leak).
- `test_me.py` — `GET /me` with valid token returns the user; missing token → 401; expired token (forge a JWT with past `exp`) → 401; malformed token → 401.

### Phase 4 — `tests/phase-4-products/`

Stack: postgres + backend.

- `test_products_crud.py` — create with two facts, GET returns it with embedded facts, PUT replaces facts, DELETE returns 204.
- `test_products_validation.py` — empty `nutrition_facts` → 422 (`/errors/no-nutrition-facts`); duplicate `(nutrition_fact_id, quantity_type)` → 422; unknown `nutrition_fact_id` → 422 with `violations`.
- `test_products_authz.py` — User B PUT/DELETE on User A's product → 403 (`/errors/forbidden-not-owner`).
- `test_products_copy.py` — User B copies User A's product, gets a new id, owner = B, `image_filename` identical, facts identical, source product still owned by A.
- `test_uploads.py` — POST a small JPEG → 201 with `filename` ending in `.jpg`; POST a small PNG → 201 with `.png`; POST a 1-byte text file → 415; POST a 6 MB file → 413.

### Phase 5 — `tests/phase-5-recipes/`

Stack: postgres + backend.

- `test_recipes_crud.py` — create, get (with embedded products and totals), put, delete.
- `test_recipes_totals.py` — fixture: product P has facts {Energy: 165 kcal/100g, Protein: 31 g/100g}, product Q has {Energy: 130 kcal/100g, Protein: 2.7 g/100g}. Recipe R has 200g of P and 100g of Q. `GET /recipes/{r}` returns `nutrition_totals_per_serving`: Energy = 165*2 + 130*1 = 460; Protein = 31*2 + 2.7*1 = 64.7. Asserted with `pytest.approx`.
- `test_recipes_quantity_type_mismatch.py` — Product P has only weight facts. Creating a recipe with P at `quantity_type=volume` → 422 (`/errors/quantity-type-mismatch`, `extensions.product_id` = P.id).
- `test_recipes_authz.py` — non-owner PUT/DELETE → 403.
- `test_recipes_copy.py` — copy yields new recipe owned by caller, same products, totals recompute identically.

### Phase 6 — `tests/phase-6-listing/`

Stack: postgres + backend.

- `test_pagination.py` — seed 25 recipes for User A, request `scope=mine&limit=10`, follow `next` until exhausted, assert: 10 + 10 + 5 items, no overlap, no missing.
- `test_search.py` — seed products with names "Chicken Breast", "Chicken Thigh", "Beef Brisket", call `scope=search&q=chicken`, assert top results contain both Chicken items, "Beef" excluded (below threshold).
- `test_starring.py` — User B `PUT /products/{a's product}/star` → 204; `GET /products?scope=starred` for B contains it; calling PUT again still 204 (idempotent); DELETE removes it.

### Phase 7 — `tests/phase-7-shopping-list/`

Stack: postgres + backend.

- `test_shopping_list_aggregation.py` — fixture: recipe R1 has 100g Chicken + 200g Rice; recipe R2 has 150g Chicken + 50ml Olive Oil. `POST /shopping-list {items: [{R1,2}, {R2,1}]}` returns:
  - Chicken weight: 100*2 + 150*1 = 350 g
  - Rice weight: 200*2 = 400 g
  - Olive Oil volume: 50*1 = 50 ml
  Sorted by `(product_name, quantity_type)`.
- `test_shopping_list_authz.py` — User B tries to include User A's recipe (B has not starred it) → 422.
- `test_shopping_list_validation.py` — empty `items` → 400; duplicate `recipe_id` → 422; `servings <= 0` → 400.

### Phase 8 — `tests/phase-8-frontend-products/`

Stack: postgres + backend + nginx + frontend (full production-shaped on
:8080). Tests use Playwright.

- `test_register_login.py` — register via UI, log out, log in, verify auth state visible.
- `test_create_product.py` — go to "My Products", click create, fill form, upload an image (Playwright provides `page.set_input_files`), submit, see the new product in "My Products".
- `test_search_products.py` — User A creates a product; User B logs in; in "Search", types the name; result list shows it; B clicks star; "My Starred Products" contains it.
- `test_edit_own_product.py` — owner can edit; confirm new value appears.
- `test_copy_other_users_product.py` — User B opens A's product, "Edit" is disabled / not shown, "Copy" button is shown; clicking "Copy" creates a new product in B's "My Products" with the same image and facts.
- `test_infinite_scroll.py` — seed 30 products, scroll the list, assert at least three "page" worth of items load.

### Phase 9 — `tests/phase-9-frontend-recipes-and-shopping/`

Stack: full production-shaped.

- `test_create_recipe.py` — create a recipe, assert detail page shows the products list and computed totals.
- `test_recipe_totals_match_backend.py` — same fixture as phase-5 totals test, but verified through the UI: read displayed totals, compare against `pytest.approx`-expected values.
- `test_copy_recipe.py` — copy another user's recipe, edit the copy.
- `test_shopping_list.py` — select two recipes, set servings, click compute, the displayed shopping list matches manually-computed totals.

### Phase 10 — `tests/phase-10-e2e/`

Stack: full production-shaped.

- `test_user_journey.py` — a single ~30-step Playwright test:
  1. Register User A and User B (each in isolation).
  2. A creates products P1, P2, P3 with realistic nutrition facts.
  3. A creates recipe R1 using P1 and P2.
  4. B logs in.
  5. B searches for one of A's products, stars it.
  6. B copies recipe R1 → R2.
  7. B edits R2, swapping P2 for a newly-created P4.
  8. B opens "Shopping List", selects R2 with 3 servings and A's R1 (B starred R1 in step 5b? — if not, we adjust to use B's own R2 only).
  9. B computes shopping list, asserts each line item against pre-computed expected values.
  10. UI assertions on every screen confirming the data flowed correctly.

Phase 10 contains **no new feature code** — only bug fixes surfaced by the
journey test. Any failure must be fixed in the relevant earlier-phase
component, not by adding workarounds in phase 10.

---

## 6. Test independence and isolation

Every test must be runnable in any order, individually or as a suite.

Implementation guidelines:

- **Fresh DB per test, not per session.** A `truncate_all_tables` fixture
  (autouse) wipes user-generated data between tests. The five seeded
  `nutrition_fact_types` rows are preserved (or re-seeded if truncated).
- **No shared in-process state.** Each test creates its own users, products,
  recipes via the API. No top-level fixtures pre-seed application data.
- **Auth tokens scoped to tests.** A `make_user` fixture takes a username and
  returns a registered+logged-in client. Tokens are not shared across tests.
- **Image bytes are inline.** `tests/helpers/images.py` exposes `JPEG_BYTES`
  and `PNG_BYTES` — small valid byte blobs for upload tests. No reference to
  files on disk.
- **DB-direct tests use a separate fixture** — `pg_conn` opens a `psycopg`
  connection via `POSTGRES_HOST_PORT` and is closed after the test.

---

## 7. Truncation fixture (sketch)

```python
# tests/helpers/db.py
import os
import psycopg

TABLES_TO_TRUNCATE = [
    "recipe_stars",
    "product_stars",
    "recipe_products",
    "product_nutrition_facts",
    "recipes",
    "products",
    "users",
]

def db_url() -> str:
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    user = os.environ["POSTGRES_USER"]
    pwd = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def truncate_all() -> None:
    with psycopg.connect(db_url()) as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE;")
        conn.commit()
```

```python
# tests/phase-N/conftest.py
import pytest
from tests.helpers.db import truncate_all

@pytest.fixture(autouse=True)
def _clean_db():
    truncate_all()
    yield
```

`nutrition_fact_types` is intentionally **not** in the truncation list — the
five seeded rows are preserved. If a test requires checking that the seed runs
on init, it does that against a freshly-`compose up`'d stack rather than via
truncation.

---

## 8. `run-all-tests.sh`

A single entrypoint at the repo root. Purpose: run the entire suite from a
clean machine (after `uv sync --extra test`) and report pass/fail.

```bash
#!/usr/bin/env bash
set -euo pipefail

# Compose runtime: "docker compose" or "podman compose". Override with
#   COMPOSE="podman compose" ./run-all-tests.sh
COMPOSE="${COMPOSE:-docker compose}"

PHASES=(
  phase-1-infra
  phase-2-db
  phase-3-auth
  phase-4-products
  phase-5-recipes
  phase-6-listing
  phase-7-shopping-list
  phase-8-frontend-products
  phase-9-frontend-recipes-and-shopping
  phase-10-e2e
)

KEEP_GOING=0
if [[ "${1:-}" == "--keep-going" ]]; then
  KEEP_GOING=1
fi

failed=()

for phase in "${PHASES[@]}"; do
  echo "=== $phase ==="
  pushd "tests/$phase" >/dev/null

  $COMPOSE up -d --wait

  if uv run pytest -v ; then
    echo "PASS: $phase"
  else
    echo "FAIL: $phase"
    failed+=("$phase")
  fi

  $COMPOSE down -v
  popd >/dev/null

  if [[ ${#failed[@]} -gt 0 && $KEEP_GOING -eq 0 ]]; then
    echo "Stopping at first failure. Use --keep-going to continue."
    break
  fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
  echo "Failed phases: ${failed[*]}"
  exit 1
fi

echo "All phases passed."
```

The script:
- Starts each phase's stack, runs its pytest, tears the stack down (with
  volumes) before moving on.
- Defaults to fail-fast; `--keep-going` runs every phase and reports a final
  summary.
- Works with either `docker compose` or `podman compose`. Default is
  `docker compose`; override with `COMPOSE="podman compose" ./run-all-tests.sh`.
- Requires `uv` on `PATH`. The frontend phases additionally require
  `playwright install chromium` to have been run once after dependency
  installation.

This script's location and invocation are documented in `CLAUDE.md`.

---

## 9. Browser installation for Playwright phases

Phases 8, 9, and 10 require a Chromium browser. Installed once per machine
via:

```bash
uv run playwright install chromium
```

This is documented in CLAUDE.md and in each Playwright phase's README/conftest
prelude. Tests run with the browser headless by default; setting
`HEADLESS=0` in the environment runs headed for debugging.

---

## 10. CI considerations (informative)

CI is not part of v1, but the structure is CI-ready:

- Each phase folder is independently runnable, so CI can shard by phase.
- All test fixtures are produced by the test code itself; no external
  resources, no network egress required beyond Docker Hub for base images.
- Test compose files use `healthcheck:` so CI doesn't need to sleep.

A future CI configuration would invoke `./run-all-tests.sh --keep-going` and
publish each phase's pytest output as a separate artifact.

---

## 11. What is intentionally **not** tested

- **Internal helpers.** No test directly imports `services/*` or `dal/*`.
- **Logging output.** Beyond confirming the process starts, log content is not
  asserted.
- **Database performance / EXPLAIN plans.** Index correctness is verified by
  presence; query plans are not.
- **Concurrent writes.** v1 is single-tenant per resource; there are no
  concurrency tests.
- **Security beyond happy path.** Brute-force protection, rate-limiting, CSP
  headers, etc. are out of scope. Auth tests verify the contract (401/403),
  not adversarial behavior.
