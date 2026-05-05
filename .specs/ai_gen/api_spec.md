# API Specification — recipes-manager

REST API contract for the recipes-manager backend. Derived from `.specs/system_spec.md`
and the planning artifact at `.specs/ai_gen/implementation_plan.md`. All endpoints
are served by the FastAPI backend, reachable from the public internet only via
the nginx container under the `/api` prefix.

This document is the authoritative API contract. The frontend, backend, and
integration tests must match it exactly.

---

## 1. Conventions

The API follows the Zalando RESTful API Guidelines.

### 1.1 URL structure

- **Base path**: all endpoints are mounted under `/api`. nginx forwards `/api/*`
  to the backend. The backend itself does not prefix paths with `/api`; the
  prefix is added by the FastAPI router (`app.include_router(..., prefix="/api")`).
- **Resource names**: plural nouns. `products`, `recipes`, `users`,
  `nutrition-fact-types`, `shopping-list`, `uploads`.
- **Path segments**: lowercase, kebab-case where multi-word
  (`nutrition-fact-types`, `shopping-list`).
- **Resource identifiers**: integer surrogate IDs (`BIGINT` in DB).

### 1.2 Methods

| Method | Purpose |
|---|---|
| `GET` | Read |
| `POST` | Create, or non-idempotent action (copy, shopping-list calculation, login) |
| `PUT` | Full replacement of an existing resource. Idempotent. |
| `DELETE` | Remove. Idempotent. |

`PATCH` is not used in v1 — all updates are full replacements.

### 1.3 JSON conventions

- All request and response bodies are `application/json` (except image upload,
  which is `multipart/form-data`).
- JSON property names are `snake_case` matching `^[a-z_][a-z_0-9]*$`.
- Timestamps are ISO 8601 / RFC 3339 in UTC, e.g. `"2026-05-05T10:30:00Z"`.
- Enum values are lowercase strings: `"weight"`, `"volume"`.
- Floating point amounts are JSON numbers (not strings).

### 1.4 Query parameters

- Snake_case names.
- Conventional names follow Zalando: `q` for free-text search, `cursor` for
  cursor pagination, `limit` for page size.

### 1.5 Authentication

Every endpoint requires a JWT bearer token **except**:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/health`

The token is sent in the `Authorization` header:

```
Authorization: Bearer <jwt>
```

Missing, malformed, or expired tokens on a protected endpoint produce
`401 Unauthorized`.

### 1.6 Content negotiation

- Request bodies: `Content-Type: application/json` for JSON endpoints,
  `multipart/form-data` for image upload.
- Successful response bodies: `Content-Type: application/json`.
- Error response bodies: `Content-Type: application/problem+json`.

The backend ignores the `Accept` header in v1; it always returns JSON for
success and Problem+JSON for errors.

---

## 2. Authentication

### 2.1 JWT

- **Algorithm**: HS256
- **Secret**: read from env var `JWT_SECRET` (required, ≥ 32 bytes recommended)
- **Library**: `pyjwt`
- **Lifetime**: 24 hours from issuance
- **Claims**:

```json
{
  "sub": "123",
  "username": "alice",
  "iat": 1714903200,
  "exp": 1714989600
}
```

`sub` is the user id as a string (per JWT convention). The backend casts it back
to int when reading. `iat` and `exp` are POSIX seconds.

### 2.2 Endpoints

#### `POST /api/auth/register`

Create a new user. No auth required.

**Request body**

```json
{
  "username": "alice",
  "password": "hunter2",
  "full_name": "Alice Smith"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `username` | string | yes | 3-50 chars, `^[a-zA-Z0-9_.-]+$` |
| `password` | string | yes | 8-200 chars; otherwise no complexity rules |
| `full_name` | string \| null | no | up to 200 chars; null/omitted both acceptable |

**Responses**

- `201 Created` — body is the new `User` representation (see §3.1). No JWT
  issued; client must call `/login` next.
- `400 Bad Request` — malformed body (e.g. password too short).
- `409 Conflict` — username already taken.

#### `POST /api/auth/login`

Exchange username + password for a JWT. No auth required.

**Request body**

```json
{
  "username": "alice",
  "password": "hunter2"
}
```

**Responses**

- `200 OK`

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_at": "2026-05-06T10:30:00Z",
  "user": { "id": 123, "username": "alice", "full_name": "Alice Smith", "created_at": "2026-05-05T09:00:00Z" }
}
```

- `401 Unauthorized` — unknown username **or** wrong password (the API does
  not differentiate, to avoid username enumeration).

#### `GET /api/auth/me`

Return the currently authenticated user. Auth required.

**Responses**

- `200 OK` — body is a `User` representation.
- `401 Unauthorized` — missing/expired/invalid token.

---

## 3. Common representations

### 3.1 `User`

```json
{
  "id": 123,
  "username": "alice",
  "full_name": "Alice Smith",
  "created_at": "2026-05-05T09:00:00Z"
}
```

`full_name` may be `null`. `pwd_hash` is never exposed.

### 3.2 `UserRef`

Compact form embedded in product/recipe responses to identify the creator.

```json
{ "id": 123, "username": "alice", "full_name": "Alice Smith" }
```

### 3.3 `NutritionFactType`

```json
{ "id": 1, "name": "Energy", "unit": "kcal" }
```

### 3.4 `ProductNutritionFact`

Embedded in product representations. No surrogate id (matches DB schema).

```json
{
  "nutrition_fact_id": 2,
  "nutrition_fact_name": "Protein",
  "unit": "g",
  "quantity_type": "weight",
  "amount": 26.0
}
```

`nutrition_fact_name` and `unit` are denormalized in responses for client
convenience. On write requests they are ignored — only `nutrition_fact_id`,
`quantity_type`, and `amount` are read.

### 3.5 `Product`

```json
{
  "id": 42,
  "name": "Chicken Breast",
  "image_filename": "a3f1b2c4-1234-5678-9abc-def012345678.jpg",
  "created_by": { "id": 123, "username": "alice", "full_name": "Alice Smith" },
  "import_source": null,
  "created_at": "2026-05-05T10:00:00Z",
  "starred_by_me": false,
  "nutrition_facts": [
    { "nutrition_fact_id": 1, "nutrition_fact_name": "Energy", "unit": "kcal", "quantity_type": "weight", "amount": 165 },
    { "nutrition_fact_id": 2, "nutrition_fact_name": "Protein", "unit": "g", "quantity_type": "weight", "amount": 31 }
  ]
}
```

- Exactly one of `created_by` / `import_source` is non-null.
- `starred_by_me` is per-request, derived from the caller's identity.
- `nutrition_facts` is included on detail responses (`GET /api/products/{id}`)
  and on creation/copy responses. List endpoints (`GET /api/products`) omit it
  to keep payloads small (see §6.4 for list item shape).
- `image_filename` may be `null`.

### 3.6 `RecipeProduct`

Embedded in recipe representations. No surrogate id.

```json
{
  "product_id": 42,
  "product_name": "Chicken Breast",
  "product_image_filename": "a3f1b2c4-...jpg",
  "quantity_type": "weight",
  "amount": 200.0
}
```

Denormalized fields (`product_name`, `product_image_filename`) are present in
responses; ignored in write requests.

### 3.7 `Recipe`

```json
{
  "id": 7,
  "name": "Grilled Chicken Bowl",
  "description": "Quick weekday dinner.",
  "image_filename": "b1c2d3e4-...png",
  "created_by": { "id": 123, "username": "alice", "full_name": "Alice Smith" },
  "import_source": null,
  "created_at": "2026-05-05T10:30:00Z",
  "starred_by_me": false,
  "products": [
    { "product_id": 42, "product_name": "Chicken Breast", "product_image_filename": "a3f1b2c4-...jpg", "quantity_type": "weight", "amount": 200 },
    { "product_id": 51, "product_name": "Brown Rice", "product_image_filename": null, "quantity_type": "weight", "amount": 100 }
  ],
  "nutrition_totals_per_serving": [
    { "nutrition_fact_id": 1, "nutrition_fact_name": "Energy", "unit": "kcal", "amount": 444 },
    { "nutrition_fact_id": 2, "nutrition_fact_name": "Protein", "unit": "g", "amount": 64.7 }
  ]
}
```

- `nutrition_totals_per_serving` is computed on the backend from the recipe's
  products and their products' nutrition facts (per-100 unit, scaled by
  recipe-product amount). See §11.
- Both `products` and `nutrition_totals_per_serving` are included on detail
  and create/copy responses; omitted on list responses.

### 3.8 `Cursor` and pagination envelope

See §5.

---

## 4. Error format

All non-2xx responses use Problem+JSON (RFC 9457).

**Content-Type**: `application/problem+json`

**Body shape**

```json
{
  "type": "https://recipes-manager.local/errors/quantity-type-mismatch",
  "title": "Quantity type does not match any product nutrition fact",
  "status": 422,
  "detail": "Product 42 has no nutrition facts for quantity_type=volume.",
  "instance": "/api/recipes",
  "extensions": {
    "product_id": 42,
    "requested_quantity_type": "volume"
  }
}
```

- `type` is a stable, dereferenceable URI within this product's error registry
  (see §4.1). Clients should match on `type`, not on `title` or `detail`.
- `title` is a short human-readable summary; safe to display.
- `status` mirrors the HTTP status code.
- `detail` is a human-readable explanation. May include user-supplied data;
  safe to display.
- `instance` is the request path that produced the error.
- `extensions` is a free-form object with machine-readable context. Keys vary
  by error type; clients should treat unknown keys as informational.

For validation errors (e.g. malformed JSON, missing required field) the
`extensions` field carries a `violations` array:

```json
{
  "type": "https://recipes-manager.local/errors/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "Request body is invalid.",
  "instance": "/api/products",
  "extensions": {
    "violations": [
      { "field": "name", "message": "field required" },
      { "field": "nutrition_facts.0.amount", "message": "must be >= 0" }
    ]
  }
}
```

### 4.1 Error type registry

Stable URIs under `https://recipes-manager.local/errors/`. The host is a
placeholder; the path component is what clients match on.

| URI suffix | HTTP | Meaning |
|---|---|---|
| `/validation` | 400 | Malformed request body or query parameters |
| `/invalid-cursor` | 400 | Pagination cursor cannot be decoded |
| `/unauthorized` | 401 | Missing, expired, or invalid JWT |
| `/forbidden-not-owner` | 403 | Caller is not the owner of the resource being modified |
| `/not-found` | 404 | Resource does not exist (or caller cannot see it) |
| `/conflict-username` | 409 | Username already taken on register |
| `/payload-too-large` | 413 | Image upload exceeds 5 MB |
| `/unsupported-media-type` | 415 | Image upload is not JPEG or PNG |
| `/quantity-type-mismatch` | 422 | Recipe-product quantity_type has no matching product nutrition fact |
| `/no-nutrition-facts` | 422 | Product creation/update would leave product with zero nutrition facts |
| `/duplicate-nutrition-fact` | 422 | Same `(nutrition_fact_id, quantity_type)` listed twice for one product |
| `/duplicate-recipe-product` | 422 | Same `product_id` listed twice in a recipe |
| `/owner-import-source-conflict` | 422 | Both `created_by_user_id` and `import_source` would be set (server-side invariant; should not be reachable from client) |
| `/internal` | 500 | Unhandled server error |

---

## 5. Pagination

All list endpoints use opaque cursor-based pagination.

### 5.1 Request

| Param | Type | Default | Notes |
|---|---|---|---|
| `cursor` | string \| omitted | first page | Opaque base64url string returned by a previous response. |
| `limit` | integer | 20 | Range 1-100. Out-of-range → 400. |

### 5.2 Response envelope

```json
{
  "items": [ /* … */ ],
  "self": "/api/products?scope=mine&limit=20",
  "next": "/api/products?scope=mine&cursor=eyJ...&limit=20"
}
```

- `items` — array of zero or more resource representations. Order is endpoint-specific.
- `self` — the URL that produced this response (for client logging / re-fetch).
- `next` — URL of the next page. **Absent** when this is the last page.
- `prev` — not provided in v1 (frontend uses infinite scroll forward only).

### 5.3 Cursor contents (informative)

Cursors are opaque to clients. Internally they encode:

- For chronological lists (`scope=mine`, `scope=starred`):
  `base64url({"k": "created_at_id", "v": ["2026-05-05T10:00:00Z", 42]})`
  paginating by `(created_at DESC, id DESC)`.
- For search (`scope=search`):
  `base64url({"k": "sim_id", "v": [0.42, 17]})`
  paginating by `(similarity DESC, id ASC)`.

A client passing a cursor whose `k` does not match the endpoint's expected
sort produces `400` with type `/errors/invalid-cursor`.

### 5.4 Stability

Cursors remain valid across server restarts and configuration changes within
the same major schema version. They may be invalidated by:

- Deletion of the row at the cursor boundary (the next page may skip an item).
- Schema-changing migrations.

Clients must treat cursors as ephemeral. Persisting a cursor across long time
intervals is unsupported.

---

## 6. Products

A `Product` is a buyable food with one or more nutrition facts. It is
created either by a user (`created_by_user_id`) or imported from a dataset
(`import_source`); never both. v1 only supports user-created products
(import is a non-goal), but the schema supports both for forward
compatibility.

### 6.1 `POST /api/products`

Create a new product owned by the caller. Auth required.

**Request body**

```json
{
  "name": "Chicken Breast",
  "image_filename": "a3f1b2c4-1234-5678-9abc-def012345678.jpg",
  "nutrition_facts": [
    { "nutrition_fact_id": 1, "quantity_type": "weight", "amount": 165 },
    { "nutrition_fact_id": 2, "quantity_type": "weight", "amount": 31 }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | 1-200 chars after trimming |
| `image_filename` | string \| null | no | Must reference a file previously returned by `POST /api/uploads/images`. The backend does **not** verify file existence on the volume in v1. |
| `nutrition_facts` | array | yes | At least one entry. No `(nutrition_fact_id, quantity_type)` duplicates. |
| `nutrition_facts[].nutrition_fact_id` | integer | yes | Must reference an existing `nutrition_fact_types.id`. |
| `nutrition_facts[].quantity_type` | `"weight"` \| `"volume"` | yes | |
| `nutrition_facts[].amount` | number | yes | `>= 0`. |

**Responses**

- `201 Created` — body is the new `Product` (with embedded facts and `starred_by_me=false`). `Location: /api/products/{id}` header set.
- `400 Bad Request` — malformed body (`type=/errors/validation`).
- `401 Unauthorized`.
- `422 Unprocessable Entity` —
  - `type=/errors/no-nutrition-facts` if `nutrition_facts` is empty.
  - `type=/errors/duplicate-nutrition-fact` if duplicates.
  - `type=/errors/validation` with violations referencing unknown `nutrition_fact_id`.

### 6.2 `GET /api/products/{id}`

Fetch a product by id. Auth required.

**Responses**

- `200 OK` — `Product` representation including `nutrition_facts` and `starred_by_me`.
- `404 Not Found` — no such product.

### 6.3 `PUT /api/products/{id}`

Replace a product. Owner only. Auth required.

Body shape identical to `POST /api/products`. The replacement is full —
nutrition facts not present in the request are removed, present ones
upserted.

**Responses**

- `200 OK` — updated `Product`.
- `400`, `422` — same as `POST`.
- `403 Forbidden` (`type=/errors/forbidden-not-owner`) — caller is not the
  owner. Imported products (`import_source` set) are not owned by anyone and
  cannot be edited; the same 403 applies.
- `404 Not Found`.

### 6.4 `DELETE /api/products/{id}`

Delete a product. Owner only. Auth required.

**Behavior**

- Cascades to `product_nutrition_facts` and `product_stars`.
- Does **not** cascade to `recipe_products`. If the product is used by any
  recipe, deletion is rejected (409). The user must remove the product from
  recipes first.
- The image file referenced by `image_filename` is **not** deleted from the
  volume (other entities may reference it; cleanup is out-of-scope for v1).

**Responses**

- `204 No Content`.
- `403 Forbidden`, `404 Not Found`.
- `409 Conflict` (`type=/errors/conflict`, with `extensions.recipe_count` indicating how many recipes reference this product).

### 6.5 `POST /api/products/{id}/copy`

Create a new product owned by the caller, cloning the source product's name,
`image_filename`, and nutrition facts. Auth required. Any user can copy any
product.

**Request body**: empty (or `{}`).

**Responses**

- `201 Created` — new `Product` with `created_by` = caller, `import_source` = null,
  and `image_filename` identical to the source (no file duplication).
- `404 Not Found` — source does not exist.

The newly copied product is **not** automatically starred.

### 6.6 `GET /api/products`

List products. Auth required. Returns the paginated envelope (§5).

**Query parameters**

| Param | Type | Required | Notes |
|---|---|---|---|
| `scope` | `"mine"` \| `"starred"` \| `"search"` | yes | Missing or invalid → 400. |
| `q` | string | required when `scope=search` | 1-200 chars. Used for `pg_trgm` similarity search on `name`. |
| `cursor`, `limit` | see §5 | no | |

**List item shape** (omits `nutrition_facts`):

```json
{
  "id": 42,
  "name": "Chicken Breast",
  "image_filename": "a3f1b2c4-...jpg",
  "created_by": { "id": 123, "username": "alice", "full_name": "Alice Smith" },
  "import_source": null,
  "created_at": "2026-05-05T10:00:00Z",
  "starred_by_me": false
}
```

**Sort order**

- `scope=mine` and `scope=starred`: `created_at DESC, id DESC`.
- `scope=search`: `similarity(name, q) DESC, id ASC`. Only items with similarity ≥ `SEARCH_SIMILARITY_THRESHOLD` (default 0.3, env-tunable) are returned.

**Responses**

- `200 OK` — envelope.
- `400 Bad Request` — missing/invalid `scope`, missing `q` for search, invalid `cursor`, `limit` out of range.

---

## 7. Recipes

A `Recipe` represents a single serving. The backend computes per-serving and
multi-serving aggregates on demand.

### 7.1 `POST /api/recipes`

Create a recipe. Auth required.

**Request body**

```json
{
  "name": "Grilled Chicken Bowl",
  "description": "Quick weekday dinner.",
  "image_filename": "b1c2d3e4-...png",
  "products": [
    { "product_id": 42, "quantity_type": "weight", "amount": 200 },
    { "product_id": 51, "quantity_type": "weight", "amount": 100 }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | 1-200 chars. |
| `description` | string \| null | no | Up to 5000 chars. |
| `image_filename` | string \| null | no | See `Product`. |
| `products` | array | yes | May be empty (a recipe with no products is allowed; its nutrition totals are all zero). No duplicate `product_id`. |
| `products[].product_id` | integer | yes | Must reference an existing product. |
| `products[].quantity_type` | `"weight"` \| `"volume"` | yes | Must match an existing `product_nutrition_facts(product_id, quantity_type)` row. |
| `products[].amount` | number | yes | `> 0`. |

**Responses**

- `201 Created` — `Recipe` with embedded `products` and `nutrition_totals_per_serving`.
- `400 Bad Request` — malformed body.
- `422 Unprocessable Entity` —
  - `/errors/duplicate-recipe-product` for duplicate `product_id`s.
  - `/errors/quantity-type-mismatch` (`extensions.product_id`, `extensions.requested_quantity_type`) when the product has no facts for that quantity_type.
  - `/errors/validation` with violations for unknown `product_id`s.

### 7.2 `GET /api/recipes/{id}`

Fetch a recipe. Auth required.

**Responses**

- `200 OK` — full `Recipe` with `products` and `nutrition_totals_per_serving`.
- `404 Not Found`.

### 7.3 `PUT /api/recipes/{id}`

Replace a recipe. Owner only. Auth required. Body identical to `POST`.

**Responses**: same as `POST`, plus `403 Forbidden`, `404 Not Found`.

### 7.4 `DELETE /api/recipes/{id}`

Delete a recipe. Owner only.

- Cascades to `recipe_products` and `recipe_stars`.
- Image file untouched.

**Responses**: `204 No Content`, `403`, `404`.

### 7.5 `POST /api/recipes/{id}/copy`

Clone a recipe to the caller. Same semantics as `POST /api/products/{id}/copy`:
new owner, same `image_filename` (no duplication), `import_source=null`,
cloned `recipe_products`. Returns `201 Created` with the new `Recipe`.

### 7.6 `GET /api/recipes`

List recipes. Mirrors `GET /api/products` exactly:

| Param | Type | Required |
|---|---|---|
| `scope` | `"mine"` \| `"starred"` \| `"search"` | yes |
| `q` | string | required if `scope=search` |
| `cursor`, `limit` | see §5 | no |

**List item shape** (omits `products` and `nutrition_totals_per_serving`):

```json
{
  "id": 7,
  "name": "Grilled Chicken Bowl",
  "image_filename": "b1c2d3e4-...png",
  "created_by": { "id": 123, "username": "alice", "full_name": "Alice Smith" },
  "import_source": null,
  "created_at": "2026-05-05T10:30:00Z",
  "starred_by_me": false
}
```

Sort order and responses identical to `GET /api/products`.

---

## 8. Starring

Starring is per-user. A user can star their own items. Starring is idempotent:
re-starring is a no-op.

### 8.1 Recipes

- `PUT /api/recipes/{id}/star` — star the recipe for the caller.
  - `204 No Content` — newly starred or already starred (idempotent).
  - `404 Not Found` — recipe does not exist.
- `DELETE /api/recipes/{id}/star` — unstar.
  - `204 No Content` — was starred (now removed) or wasn't starred (idempotent).
  - `404 Not Found` — recipe does not exist.

### 8.2 Products

Symmetric to recipes:

- `PUT /api/products/{id}/star`
- `DELETE /api/products/{id}/star`

Both `204 No Content` on success, `404 Not Found` if the product doesn't exist.

---

## 9. Shopping list

Shopping list is computed on-the-fly. Not persisted.

### 9.1 `POST /api/shopping-list`

Aggregate products across selected recipes scaled by serving counts.

**Request body**

```json
{
  "items": [
    { "recipe_id": 7, "servings": 2 },
    { "recipe_id": 9, "servings": 1.5 }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `items` | array | yes | At least one entry. Duplicate `recipe_id` → 422. |
| `items[].recipe_id` | integer | yes | Caller must own or have starred this recipe. Otherwise 422. |
| `items[].servings` | number | yes | `> 0`. Fractional allowed. |

**Authorization rule**: a recipe can be requested if it is owned by the caller
**or** starred by the caller. Otherwise 422 (`/errors/validation` with a
violation explaining the recipe is not accessible). This matches the spec's
"select any of their own / starred recipes".

**Response — `200 OK`**

```json
{
  "items": [
    {
      "product_id": 42,
      "product_name": "Chicken Breast",
      "product_image_filename": "a3f1b2c4-...jpg",
      "quantity_type": "weight",
      "unit": "g",
      "total_amount": 400
    },
    {
      "product_id": 51,
      "product_name": "Brown Rice",
      "product_image_filename": null,
      "quantity_type": "weight",
      "unit": "g",
      "total_amount": 250
    },
    {
      "product_id": 60,
      "product_name": "Olive Oil",
      "product_image_filename": null,
      "quantity_type": "volume",
      "unit": "ml",
      "total_amount": 30
    }
  ]
}
```

**Aggregation rule**: items are grouped by `(product_id, quantity_type)`.
Different quantity_types of the same product produce separate rows since the
units are not commensurable. `unit` is `"g"` for `quantity_type=weight` and
`"ml"` for `quantity_type=volume`.

**Sort order**: `product_name ASC, quantity_type ASC` for deterministic output.

**Errors**

- `400` — malformed body.
- `422` — duplicate `recipe_id`, unknown recipe, recipe not accessible (not owned, not starred).

---

## 10. Image uploads

### 10.1 `POST /api/uploads/images`

Upload an image. Auth required.

**Request**: `multipart/form-data` with a single file part named `file`.

**Validation**

- MIME type detected by reading the file header (not the `Content-Type` of the part). Allowed: `image/jpeg`, `image/png`. The original filename is otherwise ignored except to derive the extension.
- Max size: 5 MB. The backend rejects with 413 as soon as the limit is exceeded; it does not buffer the entire file first.

**Responses**

- `201 Created`

```json
{ "filename": "a3f1b2c4-1234-5678-9abc-def012345678.jpg" }
```

The file is written to the shared volume under `IMAGE_DIR` with this exact
filename. Subsequent product/recipe writes reference this filename in
`image_filename`.

- `413 Payload Too Large` (`/errors/payload-too-large`).
- `415 Unsupported Media Type` (`/errors/unsupported-media-type`).

### 10.2 Serving images

Image bytes are served by nginx, not the backend. The frontend renders images
using URLs of the form `/uploads/<filename>`. The backend has no `GET` endpoint
for image bytes.

---

## 11. Nutrition fact types

### 11.1 `GET /api/nutrition-fact-types`

Return the seeded list of nutrition fact types. Read-only. Auth required.

**Response — `200 OK`**

```json
{
  "items": [
    { "id": 1, "name": "Energy", "unit": "kcal" },
    { "id": 2, "name": "Protein", "unit": "g" },
    { "id": 3, "name": "Net Carbs", "unit": "g" },
    { "id": 4, "name": "Fat", "unit": "g" },
    { "id": 5, "name": "Fibers", "unit": "g" }
  ]
}
```

This list is small and bounded; it is **not** paginated. The `items` envelope
is preserved for consistency with other list endpoints.

---

## 12. Health

### 12.1 `GET /api/health`

No auth required. Returns 200 if the process is up and able to reach the
database.

**Response — `200 OK`**

```json
{ "status": "ok" }
```

If the database is unreachable, returns `503 Service Unavailable` with
Problem+JSON.

---

## 13. Nutrition totals calculation (informative)

For a recipe with `n` recipe-products `(p_i, q_i, a_i)` where `p_i` is the
product, `q_i ∈ {weight, volume}`, and `a_i` is the recipe-product amount:

```
For each nutrition_fact_type t:
  total_t = sum_{i=1..n} (
    pnf(p_i, t, q_i).amount × (a_i / 100)
  )
```

where `pnf(p_i, t, q_i)` is the product-nutrition-fact row for product `p_i`,
nutrition fact type `t`, and quantity type `q_i`. If no such row exists for
`(p_i, t, q_i)`, that product contributes `0` for `t`. (This is reachable in
practice: a product may have an Energy fact under `weight` but not Protein;
the missing Protein simply contributes 0.)

`nutrition_totals_per_serving` in `GET /api/recipes/{id}` is the array of
non-zero totals computed for one serving, in the same order as
`nutrition_fact_types` (Energy, Protein, Net Carbs, Fat, Fibers). Zero totals
are omitted.

For the shopping list (per §9), totals are computed similarly but aggregated
by product (not nutrition fact) and scaled by `servings`:

```
For each (product_id, quantity_type):
  total_amount = sum_{recipe in selection, rp in recipe.products
                     where rp.product_id = product_id and rp.quantity_type = quantity_type}
    rp.amount × selection.servings_for(recipe)
```

---

## 14. Status code matrix

| Code | When |
|---|---|
| 200 | Successful read or replacement. |
| 201 | Successful create or copy. `Location` header points to the new resource. |
| 204 | Successful delete or starring action. No body. |
| 400 | Malformed request body, missing required query parameter, invalid `scope`, invalid `cursor`, `limit` out of range. |
| 401 | Missing/expired/invalid JWT. Login with bad credentials. |
| 403 | Auth ok but caller is not the owner of the resource being modified. |
| 404 | Resource does not exist. |
| 409 | Username already taken on register; deleting a product that is still referenced by recipes. |
| 413 | Image upload > 5 MB. |
| 415 | Image upload is not JPEG or PNG. |
| 422 | Semantic validation failure (quantity-type mismatch, no nutrition facts, duplicates, recipe not accessible for shopping list). |
| 500 | Unhandled server error (logged with stack trace; body omits internal detail). |
| 503 | Health endpoint when database unreachable. |

---

## 15. Authorization summary

| Endpoint | Anonymous | Authenticated | Owner-only |
|---|---|---|---|
| `POST /auth/register` | yes | — | — |
| `POST /auth/login` | yes | — | — |
| `GET /auth/me` | — | yes | — |
| `GET /health` | yes | — | — |
| `GET /nutrition-fact-types` | — | yes | — |
| `GET /products`, `GET /products/{id}` | — | yes | — |
| `POST /products`, `POST /products/{id}/copy` | — | yes | — |
| `PUT /products/{id}`, `DELETE /products/{id}` | — | — | yes |
| `PUT /products/{id}/star`, `DELETE /products/{id}/star` | — | yes | — |
| `GET /recipes`, `GET /recipes/{id}` | — | yes | — |
| `POST /recipes`, `POST /recipes/{id}/copy` | — | yes | — |
| `PUT /recipes/{id}`, `DELETE /recipes/{id}` | — | — | yes |
| `PUT /recipes/{id}/star`, `DELETE /recipes/{id}/star` | — | yes | — |
| `POST /shopping-list` | — | yes (recipes must be owned or starred) | — |
| `POST /uploads/images` | — | yes | — |

A v1 user can never modify another user's data and can never modify imported
content. The only mutation a non-owner can perform on someone else's resource
is starring.
