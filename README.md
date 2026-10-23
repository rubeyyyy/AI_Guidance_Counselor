> Authentication is now required for student data. Follow the current
> [authentication setup and migration guide](docs/authentication.md) before running
> the app. Student onboarding uses `/auth/register`, `/auth/verify-email`,
> cookie sessions, and CSRF headers.
> Registration now requires an emailed code; configure SMTP first. **Forgot password**
> sends a separate reset code and invalidates existing sessions after the change. Use synthetic or
> de-identified data only until privacy, consent, school approval, access controls,
> and security safeguards have been reviewed.

# AI Guidance Counselor — Student Backend

The initial assessment workflow uses `initial-v2`, derived from the actual supplied
questionnaire modeled in `app/schemas/assessment.py`. See
[Initial Assessment API](docs/initial-assessment.md) for individual answers, resume,
and profile behavior. The complete-document APIs remain available for compatibility.

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
- Run `python -m alembic upgrade head` before startup. Startup verifies the migration
  revision and seeds questionnaire definitions; it does not change the schema.

Authentication, email verification, and password recovery are implemented. Ollama
and counselor dashboard features remain outside this increment. The current guidance service
uses a provider-neutral interface with an OpenAI implementation; future adapters
can implement the same interface. Chat history is stored locally in SQLite.

## Student and assessment API

Student-specific routes require a verified, active session and ownership of the
requested student record. All writes require trusted Origin and CSRF headers.
See the [authentication API contract](docs/authentication.md#api-contract-and-security).

| Method and path | Behavior |
| --- | --- |
| `POST /students` | Authenticated student accounts without a profile only; normal registered accounts receive `409`. Use email-verified registration for onboarding. |
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
python3 main.py
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

## Phase 4: curated knowledge and RAG

Chat can now retrieve career reference excerpts using LangChain and a local
persistent Chroma index before calling the existing OpenAI guidance service.
SQLite remains authoritative for students and conversations. No student profiles
are indexed. The existing chat request and response schemas are unchanged; source
references appear in the saved assistant message text.

```text
knowledge_base/*.json          Curated reference documents
app/services/knowledge.py     Metadata validation, chunking, ingestion, index status
app/services/retrieval.py     Topic minimization, LangChain retrieval, evidence rules
app/api/knowledge_base.py     GET /knowledge-base/status
scripts/ingest_knowledge.py   CLI synchronization
tests/test_knowledge.py       Offline RAG and API tests
```

### Prepare documents

The three bundled documents are **SAMPLE ONLY**, original demonstration guidance.
They are not verified occupational research or official program information.
Their URLs are null; their dates indicate preparation/review of the sample,
not external source verification. They contain no verified scholarships, salary
statistics, costs, or admission requirements.

This MVP supports **JSON**, one document per file, including nested directories.
Every field below is required; unknown fields, blank text, duplicate document IDs,
invalid URLs/dates, and future dates are rejected:

```json
{
  "document_id": "sample-topic",
  "title": "SAMPLE: A career exploration exercise",
  "category": "career exploration",
  "source_organization": "PathBridge AI demonstration — not an official source",
  "source_url": null,
  "verification_date": "2026-10-21",
  "is_sample": true,
  "content": "SAMPLE ONLY: List activities you enjoy and discuss them with a counselor."
}
```

To replace samples, manually review a real official source and prepare an accurate,
appropriately licensed excerpt or summary. Record the real organization, exact
HTTP(S) source URL, actual review date, and set `is_sample` to `false`. A non-sample
document requires a URL. Metadata validation cannot establish that content is true;
the curator is responsible for verification. Include program name, location, and
applicable dates in content when relevant. Do not put student information in files.
Remove obsolete sample files when replacing them with curated evidence.

### Configure and ingest

Activate your environment and install the updated dependencies:

```bash
source env/bin/activate
python -m pip install -r requirements-dev.txt
```

Use `.venv/bin/activate` instead if that is where you created your environment.
Set these in your ignored `.env` (keep the real API key there):

```dotenv
OPENAI_API_KEY=your-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
CHROMA_PERSIST_DIRECTORY=./chroma_data
RAG_TOP_K=4
RAG_ENABLED=true
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=150
RAG_SCORE_THRESHOLD=0.35
```

From the repository root:

```bash
python -m scripts.ingest_knowledge
python3 main.py
curl http://127.0.0.1:8000/knowledge-base/status
```

Ingestion makes paid embedding calls for new/changed chunks. Example report:
`{"documents":3,"chunks":3,"chunks_added":3,"chunks_removed":0}`.
Status reports `enabled`, `initialized`, `documents`, `chunks`, and `state`.
An initialized index can be empty; an unreadable index returns `unavailable`.
Status requires no embedding request or API key and does not create a missing index.
Counts describe the collection for the configured embedding model.

Long content is split into overlapping character chunks (1000/150 by default).
Stable chunk IDs cover content and source metadata. Repeated unchanged ingestion
does not duplicate records or regenerate document embeddings. Edit files and rerun
the command to replace changed content; removed files are removed from the index.
The directory is the complete source of truth, not an incremental upload batch.
`--directory /path/to/documents` selects a different complete directory.
Invalid or empty input is rejected before modifying the index. New chunks are
embedded before old chunks are removed. Run only one ingestion process at a time,
with chat stopped during updates; synchronization is not a transaction across
the entire index. Rerun after an interrupted ingestion.

Changing `OPENAI_EMBEDDING_MODEL` selects a separate collection; ingest again before
using it. Old model collections stay on disk. The default `chroma_data/` and local
SQLite files are gitignored. If choosing another vector path inside the repository,
add that directory to `.gitignore` too.

### Test through Swagger

1. Open `http://127.0.0.1:8000/docs` and call `GET /knowledge-base/status`.
2. Create a fictional student with `POST /students`.
3. Optionally save questionnaire answers using the existing questionnaire routes.
4. Call `POST /students/{student_id}/chat` with
   `{"message":"How can I explore programming with limited equipment?"}`.
5. Inspect `assistant_message.content` for relevant sample references such as
   `[sample-programming]`, its title, and the explicit sample/evidence limitation.
6. Continue with the returned `conversation_id`; the conversation routes retain
   both messages and references as before.

Chat uses the real `initial-v2` profile by default (`GUIDANCE_QUESTIONNAIRE_ID`).
Existing valid complete assessments are carried into this profile on startup and
when submitted through the complete-assessment API. Old conversations remain accessible.

Set `RAG_ENABLED=false` and restart to disable retrieval and query embeddings.
Chat still works using its existing profile/history and general guidance rules.
An empty index, unsupported query topic, retrieval error, or no match above the
threshold likewise falls back to general guidance, with instructions to explicitly
acknowledge missing verified evidence.

### Privacy and limitations

- Embedding queries contain only reviewed topic labels from a fixed vocabulary
  in `retrieval.py`, extracted from the question and selected non-sample interest
  or career-goal fields. Raw questions, names, contact information, financial or
  accessibility fields, and conversation history never enter embedding queries.
  Retrieved reference chunks alone are persisted in Chroma. The existing LLM
  still receives its minimized profile and conversation context as before.
- Controlled topics reduce privacy exposure but lose specificity. Unsupported
  topics return no evidence. Extend the vocabulary when expanding the collection.
- Retrieval uses cosine similarity, configurable top-k, and a relevance threshold.
  Similarity does not establish correctness or sufficient support. The model is
  instructed to cite only supporting documents with exact IDs, titles, and URLs;
  samples cannot support verified program-specific facts. Citation correctness
  and factual grounding remain prompt-based, not a formal guarantee or automated
  claim verifier. A human counselor should review consequential decisions.
- Retrieval does not add scraping, live browsing, automatic freshness checking,
  or profile embeddings. Curators must review and update sources. Authentication
  and the frontend are implemented in their respective layers.
- A broad retrieval failure returns general guidance; the status route reports
  local index availability, not OpenAI service health or source freshness.

### Offline validation

```bash
python -m pytest -q
```

Tests use deterministic mock embeddings, real temporary Chroma/SQLite persistence,
and mocked guidance responses. They need no paid API calls. Integration follows
the [LangChain Chroma interface](https://reference.langchain.com/python/langchain-chroma/vectorstores/Chroma)
and [OpenAI embeddings adapter](https://reference.langchain.com/python/langchain-openai/embeddings/base/OpenAIEmbeddings).

## Student frontend

`frontend/` contains React, Vite, TypeScript, and Tailwind CSS. It uses the existing
FastAPI routes; no new recommendation endpoints or backend profile logic are added.
The frontend uses the real `initial-v2` questionnaire. Backend startup seeds its
20-question revision with 5 required and 15 optional answers and carries forward saved complete
assessments without overwriting individually edited answers. CORS is configurable.

### Run locally

Use Node.js 22.12+ (Node 24 is also supported) and Python from your existing
environment. Start FastAPI in one terminal from the repository root:

```bash
source env/bin/activate
python3 main.py
```

Use `.venv/bin/activate` instead if applicable. In a second terminal:

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Open `http://127.0.0.1:5173`. Vite uses port 5173 strictly; it will report an error
if the port is occupied rather than silently switching to an origin outside CORS.

`frontend/.env` contains only public frontend configuration:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Restart Vite after changing environment settings. Never put `OPENAI_API_KEY` or any
other secret in a `VITE_` variable: these are included in browser code. All model
and retrieval calls stay on FastAPI. The UI makes no direct OpenAI requests.

FastAPI allows `http://localhost:5173` and `http://127.0.0.1:5173` by default. To
override, set a JSON array in the **backend root `.env`** and restart FastAPI:

```dotenv
CORS_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
```

CORS allows GET, POST, and PUT with Content-Type and X-CSRF-Token, with browser
credentials for explicit configured origins. Authentication and ownership checks
are enforced separately on the server. Configure SMTP and migrate the database
using the [setup guide](docs/authentication.md) before testing registration.

### Test the student journey

1. On the welcome dashboard, create an account and enter the emailed verification
   code, or select Returning student to sign in. Refresh restores your cookie
   session; no student ID entry is needed. Forgot password sends a separate code
   to recover an existing account. SMTP must be configured for actual delivery.
2. Open Initial assessment. Questions are loaded dynamically from
   `/questionnaires/initial-v2/questions`; none are hardcoded in React.
   Text, number, radio, and checkbox controls match backend question types.
3. Use Save & next to persist each answer. Optional Skip sends `null` and clears
   any previous answer to that question. Back preserves unsaved edits only while
   the assessment view remains mounted. Leaving the page discards unsaved edits.
4. Return to the assessment to resume at the first unanswered question. The progress
   bar uses the backend progress endpoint; optional unanswered questions do not
   prevent completion of required questions.
5. Open My profile to inspect actual saved fields. Edit assessment returns to the
   question workflow. Missing fields stay missing. Other follow-up questions
   are no longer separate questions. Motivation and obstacles both accept multiple selections.
6. Open AI counselor, send a question, start another conversation, and select a
   previous conversation to continue. The existing API key/model setup is required
   for live replies. Existing RAG settings control source retrieval.
7. Source IDs and links within replies are retained. Markdown is
   rendered without raw HTML or unsafe URL schemes. The frontend does not assert
   that a model-supplied citation is verified.
8. Explore pathways shows saved assistant messages alongside their original
   questions. It is a conversation notebook, not structured career rankings.

When the provider fails after saving a student message, the UI uses the error's
conversation ID to reload saved history and mark the unavailable reply. On a
network failure the save outcome may be unknown; inspect conversation history
before resending. Requests are never automatically retried, avoiding duplicate
student writes or paid model calls.

### Frontend structure and validation

```text
frontend/
├── src/api/            Typed API contracts, request client, sanitized errors
├── src/components/     Status/error messages and safe Markdown rendering
├── src/views/          Welcome, assessment, profile, counselor, exploration
├── src/test/           Mocked HTTP student workflow tests
├── src/App.tsx         Navigation and in-memory student selection
├── src/styles.css     Tailwind import, responsive layout, accessible controls
├── vite.config.ts     React, Tailwind, and Vitest setup
└── .env.example        Public FastAPI base URL only
```

```bash
cd frontend
npm run build
npm run lint
npm test
```

Frontend tests mock HTTP responses and cover registration, email codes, sign-in,
password recovery, session restoration, dynamic question
loading, each answer type, edits, resume, saved progress, profile display, chat
and history, source rendering, provider failure recovery, and API errors. They make
no paid model calls. Backend regression tests remain `python -m pytest -q`.

The build writes `frontend/dist/`. `npm run preview` serves the built application
locally, including student entry. It uses the configured API base URL; add its
origin (normally `http://127.0.0.1:4173`) to CORS_ORIGINS when using preview.
The application has normal student-facing wording in both development and builds.

### Privacy and current API gaps

Loaded answers and account state live only in React memory. There is no use of
localStorage, sessionStorage, or browser database storage for credentials or student
records. Refresh restores a verified user's session through `/auth/me`; saved
answers and history remain in SQLite. API responses use `Cache-Control: no-store`.

Authentication uses HttpOnly cookie sessions, CSRF protection, email verification,
and server-side role and ownership checks. The student ID selector and development
preview text have been removed. Password recovery revokes previous sessions.
Real email delivery requires private SMTP settings. Existing pre-verification
accounts must use Forgot password once to verify email ownership.

Before using real student records, complete the school, privacy, consent, and
security review described in the [rollout limitations](docs/authentication.md#tests-and-pilot-limitations).
Removing preview wording does not establish deployment readiness. The app has not
been deployed or tested against a real SMTP provider by these automated tests.

Current API limitations are surfaced rather than simulated:

- `initial-v2` covers the supplied questionnaire's seven sections. Choice labels
  and field validation come from the existing Pydantic schema. Technical skills
  use the original free-text field; existing structured skills are preserved in
  the complete-assessment snapshot and represented as text when imported.
- Complete-assessment PUT imports its validated fields into the resumable profile.
  Individual draft edits are authoritative for the frontend and guidance; they do
  not replace the historical complete-document snapshot. Startup imports only
  missing answer rows, so saved edits and explicitly cleared answers survive restarts.
- `sample-initial-v1` remains available only for compatibility with older clients
  and tests. It is not used by the student interface or default AI profile.
- No recommendations, structured source list, or machine-readable verification
  status is returned. The UI displays original guidance and source references.
- Conversation lists have IDs and timestamps, not generated titles or pagination.
  Exploration loads existing conversation details; large histories will need a
  paginated backend API in a future phase.

Build integration uses the [Vite guide](https://vite.dev/guide/) and
[Tailwind Vite plugin](https://tailwindcss.com/docs/installation/using-vite).

### Shorter initial assessment (initial-v2)

The student assessment has exactly 20 questions: 5 required and 15 optional.
Required answers are grade/year, short-term goal, long-term aspirations, soft
skills, and learning preferences. All other questions can be skipped. Motivation
and obstacles use multiple-choice checkboxes with the existing option labels.
Other remains a choice without extra follow-up questions, so the total stays 20.

The revision removes name, age, city, long-term timeline, four awareness questions,
separate Other explanations, and the clubs/projects question from the assessment.
Original initial-v1 questions and answers remain available. On startup, retained
v1 answers are copied into initial-v2 only where no v2 answer exists; old single
motivation/obstacle choices become one-item lists. Existing v2 edits and explicitly
cleared answers are never overwritten by startup. Complete-document PUT continues
to accept its original schema and explicitly replaces retained profile answers,
converting these two single-choice fields to lists. Frontend and default guidance
use initial-v2. No schema change is made to the original complete-document API.
