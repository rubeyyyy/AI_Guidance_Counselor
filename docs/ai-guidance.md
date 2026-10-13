# AI Guidance Agent v1

The counselor combines supportive system instructions, the student's latest
structured profile, recent completed conversation turns, and the current student
message. It uses `sample-initial-v1`. Profile data comes directly from
`app.services.questionnaire.profile`, the service behind the profile endpoint;
there is no HTTP request to the application itself.

## Architecture and database

- `app/services/profile_context.py`: builds a minimized profile with an explicit
  field allowlist. Retains approved interests, academic background, aspirations,
  skills, learning preferences, resources, constraints, and nulls without guessing.
- `app/services/llm.py`: a small `LLMService` protocol and OpenAI adapter. A future
  Ollama or LangChain adapter can implement `generate(instructions, messages)`;
  no dependency on those frameworks is added now.
- `app/services/guidance.py`: ownership checks, prompt construction, conversation
  persistence, bounded history, and failure handling.
- `app/api/chat.py`: Pydantic request/response models and three HTTP endpoints.

Startup creates `conversations` and `conversation_messages` using the existing
SQLAlchemy metadata initialization. Existing tables and student/assessment data
are unchanged. Conversations reference a student and questionnaire; messages
reference a conversation and record role, content, status, and UTC timestamp.
Assistant replies also reference their exact student message with a unique
`reply_to_message_id`.

Every lookup of a supplied conversation ID checks student ownership, including
before a chat write or LLM call. Another student's conversation returns 404.
This prevents accidental mixing, but **is not authentication or authorization**:
there is no login and anyone with server access can use a student ID. This remains
a local development prototype, not a system ready for real student deployment.

Messages are returned by student turn ID followed by its assistant reply, which
is deterministic even if overlapping requests finish out of order. Submit chat
requests sequentially to get a continuous dialogue; simultaneous requests each
use only turns completed when their context was built. The latest 10 completed
turns are sent by default. The complete local history remains available through
the conversation endpoint. Pending and failed turns are not replayed to the LLM.
Current input is appended exactly once.

The counselor instructions require affordable, accessible guidance, clear
uncertainty, no invented student facts or fabricated program/scholarship/statistic
details, and human counselor review before consequential educational or financial
decisions. There is no browsing or factual verification tool in this version.
Prompt instructions guide model behavior; they do not guarantee output accuracy.

## Configuration

Install dependencies in your chosen project virtual environment:

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

The ignored `.env` contains an API key entry. Enter your own key locally; never
paste it into source files, requests, screenshots, or commits. The implementation
adds a blank entry if none exists and preserves any existing key.

```dotenv
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT_SECONDS=30
GUIDANCE_MAX_OUTPUT_TOKENS=1200
GUIDANCE_HISTORY_TURNS=10
```

The model is configurable and must be available to your OpenAI project. Restart
the server after changing configuration because settings are cached. The OpenAI
adapter disables automatic retries and uses a finite timeout. No real API calls
are made during automated tests.

`GUIDANCE_PROFILE_KEYS` optionally overrides the allowlist using a JSON array of
exact question keys. When the real questionnaire is available, review its fields
and update the allowlist with the exact nonidentifying keys required for guidance.
Unlisted fields are omitted, not inferred. The context includes an omitted field
count so omitted information is not mistaken for a complete profile.

The current sample fixture has four generic keys. They have no defined career,
academic, or resource meaning; the system prompt forbids assigning such meaning.
Personalization is limited to explicit statements until real questions are loaded.

## Swagger walkthrough (fictional data only)

Start the server:

```bash
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs. For each endpoint, click **Try it out**, enter
parameters/body, then **Execute**.

1. Create a fictional student with `POST /students`:

   ```json
   {"display_name": "Demo Student"}
   ```

   Keep the returned `id` (examples below assume `1`).

2. Retrieve questions with
   `GET /questionnaires/sample-initial-v1/questions`. Use the returned question
   ID for the sample text question to save an explicit fictional statement:
   `PUT /students/1/assessments/sample-initial-v1/answers/{question_id}`:

   ```json
   {"value": "I enjoy programming and prefer hands-on learning. I have limited internet access and a small budget."}
   ```

   Other answers may remain missing. Check the profile endpoint to see them as null.

3. Start a conversation with `POST /students/1/chat`:

   ```json
   {"message": "What affordable ways can I explore a career in technology?"}
   ```

   The response has this shape; IDs, timestamps, and generated text vary:

   ```json
   {
     "conversation_id": 1,
     "student_message": {
       "id": 1,
       "role": "user",
       "content": "What affordable ways can I explore a career in technology?",
       "status": "completed",
       "reply_to_message_id": null,
       "created_at": "2026-10-12T12:00:00Z"
     },
     "assistant_message": {
       "id": 2,
       "role": "assistant",
       "content": "Example only: consider a small hands-on project using resources you already have, and discuss your education plan with a human counselor.",
       "status": "completed",
       "reply_to_message_id": 1,
       "created_at": "2026-10-12T12:00:01Z"
     }
   }
   ```

4. Continue the same conversation by including its ID:

   ```json
   {"message": "Can you suggest a first project I can work on offline?", "conversation_id": 1}
   ```

   Omitting `conversation_id` or using null starts a new conversation.

5. Use `GET /students/1/conversations` to list sessions. Use
   `GET /students/1/conversations/1` to retrieve all saved messages in turn order.
   These endpoints work without an API key. Saved sessions survive server restarts.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/students/{student_id}/chat` | Create/continue a conversation and request guidance |
| GET | `/students/{student_id}/conversations` | List this student's conversations |
| GET | `/students/{student_id}/conversations/{conversation_id}` | Retrieve this student's ordered conversation |

## Failure behavior

The student message is committed with `pending` status before contacting OpenAI.
Success atomically stores the assistant message and marks the student message
`completed`. API connection errors, timeouts, rate limits, credential failures,
and other provider API errors mark the student message `failed` and return 502.
Blank or incomplete model responses also return 502 without storing a partial
assistant reply. Missing local API key returns 503. Provider exception details
and secrets are not returned or logged by these services.

An error response includes the saved conversation and message IDs:

```json
{
  "detail": {
    "code": "provider_unavailable",
    "message": "Guidance is unavailable. Your message was saved; try again in this conversation.",
    "conversation_id": 1,
    "student_message_id": 1
  }
}
```

Fix configuration or wait for provider recovery, then submit the message again
with that `conversation_id`. This creates a new turn; the failed original remains
in the local transcript. No automatic retry endpoint is implemented. If the
process stops during a call, its pending student message remains saved; it can be
retrieved and manually resubmitted. A provider call and local SQLite commit cannot
be one transaction, so a crash after generation may leave a pending turn without
the generated reply. Never assume a pending message received guidance.

Invalid requests return 422 before saving. Missing students or conversations
return 404 without making an LLM call.

## Privacy boundaries

**Do not use real student data with an external provider without appropriate
authorization and privacy safeguards**, especially for minors. Use fictional
data for this capstone prototype. Before any real deployment, the responsible
school/institution must establish the necessary authorization, provider data
handling arrangements, access controls, retention/deletion policy, and safeguards
for student and family information.

The context excludes student ID, display name, question IDs, and nonallowlisted
profile values. It preserves only approved guidance-relevant fields. Known display
names, email-like text, and phone-like strings are redacted from selected profile
values and outbound conversation messages. The original messages remain in local
SQLite so the student transcript is not silently modified.

This is best-effort minimization, **not reliable anonymization**. Free text can
still contain names, locations, school details, health information, or other
sensitive data. The pattern-based phone filter may also over-redact number-like
text. Do not rely on it as the sole privacy safeguard. Never put identifying or
sensitive details into demonstration answers or chat messages.

OpenAI requests use `store=False` and no provider-hosted conversation ID. This
disables response application-state storage but does not itself guarantee zero
retention; provider abuse-monitoring handling can still apply. Review the official
[OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
before any authorized real-data integration. API usage follows the official
[Responses API reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

## Automated validation

```bash
python -m pytest -q
```

Tests use temporary SQLite databases, fake LLM responses, and mocked OpenAI SDK
objects. They cover creation, continuation, persisted ordered messages, refreshed
profile context, history bounds, student isolation, validation, minimization,
missing values, missing credentials, provider errors, and incomplete responses.
No API key or paid API call is required.
