# Assessment data model

`Student` remains the relational identity record. Its `assessment_answers` JSON
column stores a single current questionnaire, validated by the Pydantic
`Assessment` schema. Seven nested models separate the form's sections. This
matches the current use case of reading/writing a whole assessment without
introducing joins or a second schema migration. No vector database is involved.

## Question mapping

| Section | Fields and types |
| --- | --- |
| Basic information | `name`: text; `age`: positive integer; `grade`: text; `city`: text; `current_program`: text; `gpa`: nonnegative finite number |
| Career goals | `short_term_goal`: text; `short_term_timeline`: choice; `long_term_aspirations`: text; `long_term_timeline`: choice; `confidence`: choice |
| Career awareness | `knows_tutoring_resources`, `knows_how_to_find_internship`, `knows_job_training_resources`, `has_talked_to_career_adult`, `knows_required_education`: each `Yes`, `No`, or `Somewhat` |
| Motivation | `career_interest_reason`: text; `primary_motivator`: choice; `other_motivator`: conditional text |
| Skills | `soft_skills`: multiple choices; `technical_skills`: optional array of `{name, proficiency}`; `technical_skills_raw`: optional original answer |
| Experience | `related_experiences`, `certifications`, `clubs_competitions_projects`: optional text |
| Support/resources | `socioeconomic_factors`: multiple choices; `has_personal_laptop`, `has_reliable_internet`: booleans; `biggest_obstacle`: choice; `other_obstacle`: conditional text; `weekly_learning_hours`: finite number from 0 to 168; `learning_preferences`: multiple choices |

All fields marked required in the source form remain required on assessment
submission. Student creation happens first and does not require these answers.
The API accepts JSON numbers and booleans, not numeric strings or `"Yes"`/`"No"`
for laptop/internet access. Any future form importer must explicitly convert
those source answers; no Google Form integration is included here.

## Modeling choices

- Grade stays text because the form does not constrain it to an integer; values
  such as `11`, `11th`, or `First year` can all be represented as strings. Current
  program is also unconstrained text.
- GPA is numeric but has no assumed upper bound: the form supplies neither a
  grading scale nor weighted/unweighted status. The API does not infer either or
  normalize GPA. Add those questions before comparing GPAs across institutions.
- Short- and long-term timelines have distinct allowed values matching their
  respective form questions. They are ranges, not invented dates.
- Choice strings retain the form's labels, including capitalization, except
  technical proficiency is standardized to `Basic`, `Intermediate`, `Advanced`,
  and the obstacle's `Other:` becomes `Other` plus a text field.
- Required checkbox fields are nonempty arrays and reject duplicate selections.
  Socioeconomic factors preserve the original combined checkbox question: income
  categories, first-generation status, work, and caring responsibilities remain
  selectable together. No exclusive-income rule is invented for a checkbox form.
- Soft skills have no proficiency because the form did not collect it. Technical
  skills each have a name and nullable proficiency. Unknown proficiency stays
  null rather than being inferred. Multiple technical skills are supported.
- `technical_skills_raw` preserves a free-text technical-skills answer when exact
  interpretation is unavailable. It can be supplied alone or alongside structured
  skills. The API does not parse this text or claim the two representations agree;
  the submitting client is responsible for any explicit structured conversion.
- Experience and certification answers remain optional text because that is what
  the form collects. Converting prose into inferred lists could lose context.
- Optional text accepts omission, null, or blank input (blank becomes null).
  Optional technical skills accept omission/null (not supplied) or `[]` (explicitly
  none). The whole experience section may be omitted/null. Required text cannot
  be blank, and required booleans distinguish `false` from missing.
- Selecting `Other` requires nonblank companion text. Companion text with a
  different selection is rejected so contradictory answers are not silently saved.
- Weekly hours allow fractions and zero, up to the physical limit of 168 per week.
- Special needs were mentioned in the initial project overview but are not in the
  actual supplied form, so no additional required question was invented.

## Persistence boundaries

`PUT` validates the whole assessment, serializes it to JSON-compatible values,
replaces the stored object, and commits once. This avoids SQLAlchemy's limitation
with tracking nested in-place JSON changes. See the
[SQLAlchemy JSON documentation](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.JSON).
The section validators follow [Pydantic's validation model](https://docs.pydantic.dev/latest/concepts/validators/).

There is no draft/completion flag: absent assessment means not submitted, and a
saved assessment has passed the required-question validation. Future draft saving,
assessment versions/history, or cross-student reporting should get explicit schema
changes rather than silently changing these endpoint semantics.
