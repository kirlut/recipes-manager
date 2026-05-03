Read `.specs/system_spec.md` and `CLAUDE.md`.

This is an empty repo. I need you to produce the planning artifacts for 
this project. Do not write any implementation code.

Deliverables:

1. `.specs/ai_gen/api_spec.md` — complete REST API specification
   - Derive endpoints from the UI/UX and business rules in the spec
   - Request/response shapes, status codes, error formats, pagination contract
   - Apply Zalando RESTful API Guidelines (use context7 to retrieve them)
   - Respect the thin-frontend principle: all significant calculations (nutrition totals, shopping list aggregation etc.) are backend responsibilities

2. `.specs/ai_gen/db_schema.md` — complete Postgres schema
   - Derived from api-spec.md + section 5.1 of the system spec + business rules
   - Tables, columns, types (BIGINT for ids), constraints, indexes
   - Include pg_trgm GIST indexes for name search on recipes and products
   - Junction tables for starring, and anything else you judge necessary
   - Schema init strategy for startup (no migration tooling)

3. `.specs/ai_gen/implementation_plan.md` — phased implementation plan
   - Break the work into phases small enough that each fits a single Claude Code session with room for planning iterations. Consult Claude Code documentation (via context7) to decide on phase size in terms of number of files / tokens.
   - Each phase must end with something verifiable via `podman compose up` and automated tests (see point 4 about testing strategy)
   - For each phase, include:
     * Scope (what's built)
     * Files created/modified
     * Definition of done, including specific test deliverables from testing-strategy.md
     * Any phase-specific setup (e.g., HS256 secret generation for the auth phase)
   - Order phases so dependencies flow naturally (infra → auth → core entities → derived features → frontend → integration)
   - UI development should take at least two phases so that development of each of them may be done at a high quality level within the limits of a single session's context window.
   - The last phase should be dedicated to the final integration and consolidation of the entire system: end-to-end tests of the entire app using `pytest-playwright` covering all the main scenarios a user can do (registration, login, product and recipes creation, shopping list calculation etc). These tests should cover both UI behavior and calculations correctness. The implementation of this phase will only consist of fixing potential bugs found during the tests execution.

4. `.specs/ai_gen/testing_strategy.md` — testing approach
   - For the sake of simplicity, only integration tests should be implemented, **not** unit tests of separate classes/functions.
   - Tests for each phase of development (see point 3) should be implemented in the `tests` folder. Subfolder for each phase should be called using template `phase-{phase_num}-{phase_name}`
   - Tests should be written in Python using the `pytest` framework
   - For tests you must create custom `docker-compose.yml` files inside test folders. If you need some test-specific configuration of the environment - do it there. For example, for testing the REST API you can create a `docker-compose.yml` with the backend app bound to the host's port (this won't be the case for the final deliverable).  
   - Tests-specific `docker-compose.yml` files must be completely independent from the root-level `docker-compose.yml`.
   - Never bind Docker ports to port 80 of the host. Use configurable (8080 by default) host port for exposing nginx
   - Tests should only verify things testable via network connection. For example you can test api endpoints, healthchecks, connect to db (exposed in test-specific `docker-compose.yml`) to verify schema, etc. But you should never try to create tests requiring anything beyond a network connection to the component you're testing (e.g. manipulation of files on the host machine). 
   - The only exception from the previous requirements is the final phase (integration and consolidation) where you'll use `pytest-playwright` to test the system e2e, mimicking a real user using the app via the frontend.
   - Tests should be independent of each other and runnable one by one in any order
   - When development is done, a single script to run all the tests should be created. All information required for running tests by agents should be added to `CLAUDE.md`

5. Updated `CLAUDE.md`
   - Once all specifications mentioned above are ready, update the existing `CLAUDE.md` with the DB, tests, frontend etc. rules that are not present in this file now and were specified in the newly created specification files. 
   - Consult Claude Code documentation (via context7) on CLAUDE.md best practices (structure, recommended length etc.)

Use context7 MCP whenever you need current library docs (FastAPI, SQLAlchemy 
async, pyjwt, Zalando guidelines, chosen frontend framework, pytest, etc).

Before writing anything, explore the spec carefully and ask me clarifying 
questions about anything ambiguous or underspecified. I'd rather resolve 
ambiguity now than discover it mid-implementation.