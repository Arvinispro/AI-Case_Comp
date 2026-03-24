# AI-Case_Comp Supabase Backend

Production-ready FastAPI backend with Supabase auth and profile management.

## Architecture

- FastAPI app entrypoint: app/main.py
- Auth routes: app/routes/auth.py
- Pydantic v2 models: app/models.py
- Supabase client helpers: app/services/supabase_client.py
- Auth service/business logic: app/services/auth_service.py
- Environment config: app/config.py
- SQL migration from schema: migrations/001_init_schema.sql
- Tests: tests/test_auth.py

## Schema notes from tables.sql

Used exactly as provided in migration. Notable issues found (proposed fixes, not applied automatically):

1. past_problems.lllm_conversation appears to have a typo (3x 'l').
	 - Proposed fix: rename to llm_conversation.
2. All id columns are uuid NOT NULL without defaults.
	 - Proposed fix: add DEFAULT gen_random_uuid() for safer inserts.
3. users.username is not unique.
	 - Proposed fix: add UNIQUE constraint to prevent duplicates.
4. Some nullable fields likely should be stricter (e.g., created_at NOT NULL).
	 - Proposed fix: enforce NOT NULL where appropriate.

## Setup

1) Create and activate a virtual environment (Python 3.11+).

2) Install dependencies:

```bash
pip install -r requirements.txt
```

3) Create env file:

```bash
cp .env.example .env
```

4) Fill required values in .env:

```env
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_DEFAULT_KEY=YOUR_SUPABASE_DEFAULT_KEY
SUPABASE_SERVICE_ROLE_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
JWT_SECRET=YOUR_SUPABASE_JWT_SECRET
```

## Database migration

Run the SQL in Supabase SQL Editor:

- migrations/001_init_schema.sql

Or using Supabase CLI migrations flow if you use CLI locally.

## Run server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger docs:

- http://127.0.0.1:8000/docs

## Auth API endpoints

Base path: /api/v1/auth

1) Sign up

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/sign_up \
	-H "Content-Type: application/json" \
	-d '{
		"email": "alice@example.com",
		"password": "Password123",
		"username": "alice_01"
	}'
```

2) Sign in

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/sign_in \
	-H "Content-Type: application/json" \
	-d '{
		"email": "alice@example.com",
		"password": "Password123"
	}'
```

3) Get current user

```bash
curl http://127.0.0.1:8000/api/v1/auth/current_user \
	-H "Authorization: Bearer <ACCESS_TOKEN>"
```

4) Log out

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/log_out \
	-H "Authorization: Bearer <ACCESS_TOKEN>"
```

## Run tests

```bash
pytest -q
```

The test suite includes success and common failure cases for all auth routes.