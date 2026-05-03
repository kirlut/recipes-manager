# 1. Overview
Our goal is to create a web application that users can utilize to create recipes from different products with known nutrition facts, search and view recipes, and combine recipes to generate a complete shopping list of products.

# 2. Repository-level Code Organization, Components
In the root of the repository there should be a clear separation of client and server side: folders `src/client` and `src/server`. Each one of them should have its own Dockerfile inside.
A `docker-compose.yml` file should be placed in the root of the project.

## 2.1. Components
Component-wise, when deployed this app will consist of the following components: 
- nginx + client app (statics) in a single docker container
- backend Python app in the second container (requests forwarded to it via nginx, not exposed outside of Docker network)
- volume shared between the previous two containers for image storage
- docker container with Postgres DB

# 3. UI, UX and Business Rules

## 3.1. UI
Use one of the publicly available CSS themes. Should be something light and nice-looking.

## 3.2. UX and Business Rules
- The user should first be registered. Required fields: username and password. Optional: full name. No pwd validation, no 2FA.  
- On a high level the user should have three sections: Recipes, Products and Shopping List
- Inside each of these sections there should be a clear separation of the user's own and starred recipes/products and search in the DB (by name)
- Search covers all recipes and products in the database, including those created by other users
- In the search section the user should be able to star any recipe/product from the DB, including their own. The user should be able to un-star. Starring is per-user.
- Entities "Product Nutrition Fact" and "Recipe Product" should be transparent for users: they should simply see Product with nutrition facts and Recipe with products and nutrition facts
- When viewing a recipe, total nutrition facts per serving should be displayed. These are calculated by summing each nutrition fact type across all recipe products, scaled by their amounts (per 100g or 100ml as appropriate)
- The user should be able to open (to view) any recipe and product
- The user should be able to create and edit their own recipes/products. If a recipe wasn't created by them, it should be possible to create a copy and edit it, but not a simple edit
- The user should be able to create and edit their own products. If a product wasn't created by them, it should be possible to create a copy and edit it, but not a simple edit
- Each product should have at least one nutrition fact when created
- When creating a product, the section for adding nutrition facts should first require the user to specify quantity_type (100 ml / 100 g) and only then add nutrition facts for this quantity type. The user should be able to create two separate lists of nutrition facts for both available quantity types. In view mode this separation should also be visible.  
- For the same quantity_type each nutrition fact may be added only once. For example, user must not be able to specify Protein per 100gr twice for the same product. It should be inforced both on frontend and backend.
- When a product is being linked to a recipe via Recipe Product, quantity_type should be allowed for selection only if this product has a nutrition fact associated with this quantity type. For example, if product 'Alpro Yogurt' only has nutrition facts for volume (per 100 ml), it shouldn't be allowed to add this product to a recipe and specify its amount in weight.
- All list views (own recipes, starred recipes, search results, own products, starred products) should support cursor-based pagination. The frontend should implement infinite scroll.

### 3.2.1. Behavior of Shopping List Section
In the shopping list section the user should be able to select any of their own / starred recipes, specify the number of servings for each and get a complete shopping list of products with the amount of each

# 4. Frontend App and nginx
As mentioned in section 2.1., both of these components should be placed in the same docker container

## 4.1. Frontend App
Choose the framework yourself. It should be something simple and reliable. Code should be organized according to best practices for this framework. 
The web app should work and be automatically adjustable for both regular screens and mobile.

## 4.2 nginx
It should forward `/api` to the backend app and `/uploads` to the volume with image files (the same volume should be mounted to the backend app). The root path is for frontend app statics. All nginx-related files should be placed in `src/client` folder and nginx should be a part of client Docker image / container. 

# 5. Backend App
Python REST API app. Use FastAPI as a web framework. Use `pydantic` for type safety and validations.

## 5.1. Main Data Entities and Abstractions
Below is the description of the main entities and abstractions and their interconnections that the app should operate with. This must be partially used for deciding on the exact DB schema as well as "vocabulary" for abstraction / class naming in code.

Note that this is **not** a full specification for db schema, you may decide that additional tables / columns are required.
All `id` fields below are of type `BIGINT` in Postgres. 

### 5.1.1. Nutrition Fact Type
Type of nutrition facts (e.g. `energy`, `fats` etc). 
Fields: 
- id
- name (str, unique)
- unit (str)

For example `{name: 'Energy', unit: 'kcal'}`

### 5.1.2. Product
Building block of a recipe. Represents any individual buyable food, both basic (e.g. carrot, apple) and processed (e.g. coca cola, yogurt alpro etc).
Fields: 
- id
- name (str, not unique)
- image_filename (str, not unique). Name of the image file in the file system (docker volume)
- created_by_user_id (BIGINT, optional, FK to User). Filled if created by a user.
- import_source (str, optional). Name of the dataset from where the product was imported. Mutually exclusive with created_by_user_id: exactly one of the two must be set.

### 5.1.3. Product Nutrition Fact
Special entity that links Product with Nutrition Fact Type. Has **no** id field.
Fields: 
- product_id
- nutrition_fact_id
- quantity_type. This is an enum: `volume` or `weight`. Specifies if nutrition fact is for 100 ml or for 100 g.
- amount (float)

Each product may have a collection of Nutrition Facts. Each nutrition fact may be for weight (100 g), volume (100 ml) or both. In UI quantity_type will be used to present the list of nutrition facts as two separate lists as explained in section 3.2. Composite primary key: (product_id, nutrition_fact_id, quantity_type).

### 5.1.4. Recipe
Recipe data always represents a single serving. All multi-serving calculations (nutrition totals, shopping lists) are performed on the fly.

Fields:
- id
- name (str, not unique)
- description
- image_filename (str, not unique). Name of the image file in the file system (docker volume)
- created_by_user_id (BIGINT, optional, FK to User). Filled if created by a user.
- import_source (str, optional). Name of the dataset from where the recipe was imported. Mutually exclusive with created_by_user_id: exactly one of the two must be set.

### 5.1.5. Recipe Product
Special entity that links Recipe with Product. Has **no** id field.
Fields: 
- recipe_id
- product_id
- quantity_type (to select correct Product Nutrition Facts)
- amount (float). Depending on quantity_type will mean either grams or milliliters required for a single serving of the recipe.

Each Recipe may have a collection of Recipe Products. 

### 5.1.6. User 
Fields: 
- id
- username (unique)
- full_name
- pwd_hash

Each user may have a collection of their own recipes (either created by them, or added from publicly available ones)

### 5.1.7. Shopping List
Transient entity containing a list of products and their amounts that the user should get in order to cook selected recipes for a selected number of servings. All calculations are on the fly: multiply each recipe product's amount by the requested number of servings, then aggregate by product.

## 5.2. Packages Management
Use `uv` only. It's already installed on this machine. Add packages with `uv add` and execute code with `uv run`. Do **not** use pip. 

## 5.3. Code Organization
- Code should be organized by horizontal layers via subfolders inside `src/server` folder: 
    - api: for FastAPI endpoints. Endpoints related to different entities should be in separate files (use `APIRouter` with `app.include_router` in entrypoint script)
    - services: classes that implement business rules and compose data to be returned by endpoints. Should be split inside by entity types / core abstractions
    - dal: classes that abstract all the work with the DB. 
- The entrypoint script should be in the root of the `src/server` folder. It should read configurations, initialize all components and keep the app up and running

## 5.4. DB
- use Postgres
- during initial planning you'll be tasked to define schema (including indexes) yourself based on sections `## 3.2. UX and Business Rules` and `## 5.1. Main Data Entities and Abstractions`. 
- for recipe and product search by name, index these columns with `GIST on pg_trgm`. Extension required: `pg_trgm`. Search should be done by `similarity()` with a configurable threshold
- use snake_case for table and col names
- use SQLAlchemy with async support (`sqlalchemy[asyncio]` + `asyncpg` as the async driver). Use SQLAlchemy Core (not ORM) for queries.
- feel free to add additional junction tables not listed in this spec explicitly. For example for recipes / products starred by users.
- on startup the app should check if the DB is initialized with the relevant DB schema. If not, it should be initialized on startup.
    - The only data that should be added on initialization is data for the Nutrition Fact Types table. The data is: 
        - name: 'Energy'; unit: 'kcal'
        - name: 'Protein'; unit: 'g'
        - name: 'Net Carbs'; unit: 'g'
        - name: 'Fat'; unit: 'g'
        - name: 'Fibers'; unit: 'g'

## 5.5. Auth and Security
- Password should be hashed with salt using `bcrypt`
- Since this is a small service not designed for a huge load and security threats, it's fine to store the entire user data (login, full name and pwd hash) in a single table
- Use simple auth flow with HS256-signed JWT tokens
- Use `pyjwt` for working with JWT tokens and signature checks. 
- The backend app must only be accessible via nginx forwarding within the Docker network and is not exposed externally. 

## 5.6. Image Uploads
- Allowed formats: JPEG and PNG only. Reject other formats.
- Max file size: 5 MB.
- Stored filenames: generate a UUID4 for each uploaded file, preserving the original extension (e.g. `a3f1b2c4-...-.jpg`).
- Images are stored in the shared docker volume and served by nginx at `/uploads`.

## 5.7. Configuration
Env vars only with `.env` files support. `.env` file must be placed in the root of the repository. What to make configurable:
- DB connection settings
- Secret for HS256 signature of JWT
- Path to folder with images (mounted to the volume)

## 5.8. Logging
Structured logging in JSON format straight to stdout. Use standard py `logging`. Log shipping will be added later.

# 6. Additional Rules
- All base Docker images should be official packages from dockerhub. No other sources or custom images
- Never bind Docker ports to port 80 of the host. Use configurable (8080 by default) host port for exposing nginx

# 6. Non-goals (out of scope for v1)
- Data import from external datasets (despite the `import_source` column mentioned here)
- Email verification, password reset, social login
- Recipe rating, comments, or tags/categories
- Admin panel
- Caching layer (Redis etc.)
- Database migration tooling (schema init on startup is sufficient)

# 7. Key Validation Rules (consolidated)
These constraints are described in context within earlier sections but are listed here as a single checklist for implementation and testing:
1. Exactly one of `created_by_user_id` or `import_source` must be set on every Product and Recipe
2. Every Product must have at least one Product Nutrition Fact
3. When adding a Product to a Recipe (Recipe Product), `quantity_type` must match an existing Product Nutrition Fact `quantity_type` for that product
4. Users can only edit or delete entities they created. For entities created by others, only copy-and-edit is allowed