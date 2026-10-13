# AI Guidance Counselor — Student Backend

The new initial assessment workflow is documented in
[Initial Assessment API](docs/initial-assessment.md). It stores definitions and
partial answers separately. The complete-document APIs described below remain
available for compatibility; their questionnaire is not the final initial assessment.

The first AI guidance chat implementation uses the OpenAI API and saved assessment
profiles. See [AI Guidance and Swagger walkthrough](docs/ai-guidance.md) for setup,
endpoints, failure behavior, privacy limits, and testing with fictional students.


Student backend for a Master's capstone supporting students in under-resourced
public schools: configuration, SQLite persistence, typed questionnaire answers,
student/assessment APIs, a health endpoint, and persistent AI guidance conversations.

## Architecture

One Python package separates HTTP routes, validation, persistence, and settings:

```text
app/
├── main.py              # FastAPI application and startup/shutdown
├── api/
│   ├── health.py        # Liveness route
│   └── students.py      # Student and assessment routes
├── core/config.py       # Environment settings
├── db/
│   ├── base.py          # SQLAlchemy declarative base
│   └── session.py       # Engine, session dependency, table initialization
├── models/student.py   # Database representation
└── schemas/
    ├── assessment.py   # Seven typed questionnaire sections
    ├── health.py       # Health response
    └── student.py      # Validated student input/output
tests/                  # Scaffold and API integration tests
examples/assessment.json # Complete fictional submission
.env.example
requirements.txt
requirements-dev.txt
```

Each package also contains an `__init__.py`. Routes validate input
with Pydantic and use a request-scoped SQLAlchemy session. Database operations for
students, questionnaires, and guidance live in `app/services/`; the LLM adapter
is separate from profile construction and conversation persistence.

### Data decisions

- SQLite stores the primary student profile. The `students` table has an integer
  ID, optional display name, UTC creation timestamp, and `assessment_answers`
  JSON object. A student can exist before providing a name or assessment answers.
- JSON contains seven typed sections matching the supplied Google Form. Pydantic
  validates the complete document before persistence; clients cannot write
  arbitrary JSON through student creation. Numbers, booleans, arrays, and nested
  objects retain their types. The database stores one current assessment per
  student; no assessment history or draft saving is implemented.
- Keeping the existing JSON column avoids schema changes and unnecessary tables
  for this MVP. Fields needed for reporting can later become relational columns
  or related tables. SQL alone does not enforce the questionnaire schema, so
  future non-API writers must also validate through `Assessment`.
- Persist assessment changes by assigning a new object to
  `student.assessment_answers`. Nested in-place JSON mutations are not tracked
  by this model.
- Synchronous SQLAlchemy keeps the SQLite MVP simple. `get_db()` yields one
  session per request and closes it afterward. Write routes explicitly commit
  transactions; failed requests close their sessions without saving partial data.
- Startup uses `create_all()` to create missing tables. It does **not** migrate
  existing tables. Add Alembic migrations when the schema evolves.

Authentication, frontend, LangChain, Ollama, RAG, vector databases, and counselor
dashboard features remain outside this increment. The current guidance service
uses a provider-neutral interface with an OpenAI implementation; future adapters
can implement the same interface. Chat history is stored locally in SQLite.

## Student and assessment API

| Method and path | Behavior |
| --- | --- |
| `POST /students` | Create identity with `{}` or an optional `display_name`; returns `201` and a `Location` header |
| `GET /students/{student_id}` | Return identity (`id`, `display_name`, `created_at`); `404` if absent |
| `GET /students/{student_id}/assessment` | Return the complete questionnaire; `404` if student or assessment is absent |
| `PUT /students/{student_id}/assessment` | Save or replace a complete questionnaire; returns `200`; `404` if student is absent |

`display_name` is an optional account label. The required questionnaire name is
`basic_information.name`; the two are intentionally independent. Full assessment
answers are returned by the dedicated assessment endpoint.

Required form questions must be present for a submission. Missing required
answers, unknown fields/options, or invalid values return `422` without changing
the saved assessment. `PUT` replaces the document rather than merging it, so
omitting previously provided optional answers clears them. Repeated identical
submissions produce the same stored answers.

Example workflow (replace `1` with the ID returned by the first request):

```bash
curl -X POST http://127.0.0.1:8000/students \
  -H 'Content-Type: application/json' -d '{"display_name":"Sample"}'
curl -X PUT http://127.0.0.1:8000/students/1/assessment \
  -H 'Content-Type: application/json' --data-binary @examples/assessment.json
curl http://127.0.0.1:8000/students/1
curl http://127.0.0.1:8000/students/1/assessment
```

The example is fictional. See [assessment modeling](docs/assessment.md) for the
question mapping, optional-answer rules, and choice conventions. `/docs` exposes
all nested schemas and allowed choices.

Existing scaffold databases need no migration: the table layout is unchanged.
An empty assessment JSON object means not submitted. If old manually written
JSON does not match the questionnaire schema, assessment GET returns `409` and
leaves the data intact. A successful PUT explicitly replaces that old document.

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
the file. Student/assessment APIs and mocked tests need no API key. Live guidance
requires `OPENAI_API_KEY` in the ignored local `.env` file.

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

Tests use temporary SQLite storage to check startup, health, configuration,
student creation/retrieval, assessment persistence/replacement, optional answers,
validation failures without data loss, missing students, and legacy data handling.

Implementation references: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/),
and [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/20/orm/quickstart.html).
