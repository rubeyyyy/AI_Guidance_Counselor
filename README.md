# AI Guidance Counselor — Student Backend

First increment of a Master's capstone supporting students in under-resourced
public schools: configuration, SQLite persistence, a Student model, Pydantic
schemas, and a health endpoint.

## Architecture

One Python package separates HTTP routes, validation, persistence, and settings:

```text
app/
├── main.py              # FastAPI application and startup/shutdown
├── api/health.py        # HTTP routes
├── core/config.py       # Environment settings
├── db/
│   ├── base.py          # SQLAlchemy declarative base
│   └── session.py       # Engine, session dependency, table initialization
├── models/student.py   # Database representation
└── schemas/
    ├── health.py       # Health response
    └── student.py      # Validated student input/output
tests/test_scaffold.py
.env.example
requirements.txt
requirements-dev.txt
```

Each package also contains an `__init__.py`. Future routes will validate input
with Pydantic and use a request-scoped SQLAlchemy session. Add business services
when assessment and guidance behavior requires them; separate microservices and
a repository framework are unnecessary for this MVP.

### Initial data decisions

- SQLite stores the primary student profile. The `students` table has an integer
  ID, optional display name, UTC creation timestamp, and `assessment_answers`
  JSON object. A student can exist before providing a name or assessment answers.
- JSON preserves numbers, booleans, lists, and nested objects. This is a provisional
  container, not the finalized assessment schema. The existing Google Form has
  not yet been supplied or imported. Next, define stable question keys and typed
  validation from the actual form. Fields needed for reporting can become
  relational columns or related tables.
- Persist assessment changes by assigning a new object to
  `student.assessment_answers`. Nested in-place JSON mutations are not tracked
  by this model.
- Synchronous SQLAlchemy keeps the SQLite MVP simple. `get_db()` yields one
  session per request and closes it afterward. Future write operations must
  explicitly commit transactions.
- Startup uses `create_all()` to create missing tables. It does **not** migrate
  existing tables. Add Alembic migrations when the schema evolves.

There are no student CRUD or assessment submission routes yet. Authentication,
frontend, LangChain, OpenAI, RAG, chat history, recommendations, and counselor
features are outside this increment. Later, a guidance service should consume the
structured profile through a provider-neutral interface with OpenAI and
local/Ollama adapters. A future vector store will index guidance knowledge, not
serve as the primary student database. No provider dependencies are added yet.

## Local setup

Use Python 3.11 or newer. Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and copy the
environment file with `Copy-Item .env.example .env`.

The server runs at http://127.0.0.1:8000. Interactive API documentation is at
http://127.0.0.1:8000/docs.

```bash
curl http://127.0.0.1:8000/health
```

Expected response: `{"status":"ok"}`. This is a liveness endpoint, not a continuous
database readiness probe. Startup initializes the database before serving requests.

## Configuration

Settings load from `.env` in the repository root. Environment variables override
the file. No API key is needed.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `AI Guidance Counselor - Student API` | API documentation title |
| `DATABASE_URL` | `sqlite:///./student.db` | SQLAlchemy connection URL |

The default database is created as `student.db` in the current working directory,
so run the server from the repository root. For a custom SQLite path, its parent
directory must already exist. Local environment files and SQLite databases are
excluded from Git. SQLite is the only configured/tested database for this increment;
switching databases later also requires the appropriate driver and migrations.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Tests use temporary SQLite storage to check startup, the health endpoint,
structured student persistence, input validation, and configuration precedence.

Implementation references: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/),
and [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/20/orm/quickstart.html).
