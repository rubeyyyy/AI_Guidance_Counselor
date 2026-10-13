# Initial Student Assessment

The existing student identity and complete-document APIs are preserved. The new
workflow supports saving individual answers and resuming without submitting a
complete assessment. No login, frontend, or AI features are included.

## Database and questionnaire setup

Startup creates three additional tables: `questionnaires`, `assessment_questions`,
and `student_answers`. The students table and its legacy JSON column are unchanged.
Existing JSON is retained and is not automatically mapped into new answers.
A unique student/question pair prevents duplicate saved answers.

Startup imports `app/fixtures/sample_questionnaire.json` once. Its prompts are
explicitly SAMPLE ONLY; they are not a proposed final questionnaire.

To load the actual questions, create a JSON file with the same definition shape,
set `is_sample` to false, choose a new questionnaire ID, and validate/import it:

```python
from pathlib import Path
from app.db.session import SessionLocal, engine, init_db
from app.schemas.questionnaire import QuestionnaireDefinition
from app.services.questionnaire import load_questionnaire

init_db(engine)
definition = QuestionnaireDefinition.model_validate_json(
    Path("actual_questions.json").read_text()
)
with SessionLocal() as session:
    load_questionnaire(session, definition)
```

Stable `key` values identify profile fields. Each question has a prompt,
`response_type` (`text`, `number`, `single-choice`, `multiple-choice`), `required`,
`display_order`, and choice `options`. Use a new questionnaire ID when changing
published definitions; loading an existing ID does not overwrite questions or answers.
Definitions are ordered by display order, then ID to resolve ties.

## Endpoints

| Method | Path | Result |
| --- | --- | --- |
| POST | `/students` | Create student, 201 |
| GET | `/students/{student_id}` | Retrieve identity |
| GET | `/questionnaires/{questionnaire_id}/questions` | Ordered definitions |
| PUT | `/students/{student_id}/assessments/{questionnaire_id}/answers/{question_id}` | Save/update one answer |
| GET | `/students/{student_id}/assessments/{questionnaire_id}/answers` | Saved answers; empty list for a new assessment |
| GET | `/students/{student_id}/assessments/{questionnaire_id}/progress` | Progress |
| GET | `/students/{student_id}/assessments/{questionnaire_id}/profile` | Structured profile |

Unknown students, questionnaires, and questions return 404. Invalid inputs return
422 without overwriting saved answers. Number strings and booleans are rejected
for numeric questions. Choices must match options exactly. Multiple choices must
be nonempty and unique. Text must not be blank. `{"value": null}` clears an answer,
including required answers. Required means necessary for completion, not necessary
for saving a draft. Keep the returned student ID and questionnaire ID to resume.

## Examples

Create: `POST /students` with `{"display_name": "Sample Student"}` returns:

```json
{"display_name": "Sample Student", "id": 1, "created_at": "2026-10-12T00:00:00Z"}
```

Retrieve `/questionnaires/sample-initial-v1/questions`. An example question:

```json
{"id": 1, "key": "sample_text", "prompt": "SAMPLE: Enter a text response", "response_type": "text", "required": true, "display_order": 1, "options": []}
```

Use the actual IDs returned by the API. Save using
`PUT /students/1/assessments/sample-initial-v1/answers/1`:

```json
{"value": "My saved draft"}
```

Response:

```json
{"question_id": 1, "value": "My saved draft"}
```

Other response types use `{"value": 12}`, `{"value": "Sample A"}`, or
`{"value": ["Sample A", "Sample B"]}`. PUT again updates that answer only.
GET answers returns `[{"question_id": 1, "value": "My saved draft"}]`.

Profile after saving only the text answer:

```json
{
  "student_id": 1,
  "display_name": "Sample Student",
  "questionnaire_id": "sample-initial-v1",
  "is_sample": true,
  "fields": [
    {"key": "sample_text", "question_id": 1, "value": "My saved draft"},
    {"key": "sample_number", "question_id": 2, "value": null},
    {"key": "sample_choice", "question_id": 3, "value": null},
    {"key": "sample_choices", "question_id": 4, "value": null}
  ],
  "progress": {
    "total_questions": 4,
    "answered_questions": 1,
    "required_questions": 2,
    "answered_required_questions": 1,
    "completion_percent": 25.0,
    "is_complete": false
  }
}
```

The progress endpoint returns the `progress` object. Percentage counts all
questions; completion requires all required questions only. Profile generation
copies saved values and fills missing fields with null; it makes no inferences.
The legacy complete-document assessment is separate from this workflow.

Run `.venv/bin/python -m pytest -q` for existing and new automated tests.
