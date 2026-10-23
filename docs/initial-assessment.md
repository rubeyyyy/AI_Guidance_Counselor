# Initial Student Assessment

The active student questionnaire is **initial-v2: 20 questions, 5 required and
15 optional**. The frontend fetches its questions dynamically. Motivation and
obstacles are multiple-choice checkboxes (select all that apply). Other does not
add extra questions. Optional questions can be skipped with null.

Required: grade/year, short-term goal, long-term aspirations, soft skills, and
learning preferences. Retained optional topics include current program, GPA,
timeline, confidence, career-education awareness, interest reason, motivation,
technical skills, experience, certifications, circumstances, laptop/internet
access, obstacles, weekly learning hours.

Endpoints use /questionnaires/initial-v2/questions and
/students/{student_id}/assessments/initial-v2/{answers,progress,profile}.
Save individual answers with PUT to answers/{question_id}. Use the returned IDs.
Numbers and choice selections retain backend validation. Motivation and obstacles
require nonempty lists of unique allowed strings, or null to skip. Strings alone,
unknown choices, and duplicate selections return 422.

Startup seeds the revision without modifying published initial-v1 questions or
answers. Retained v1 answers are copied only when a v2 row is absent. Single
motivation/obstacle choices become one-item lists. Already edited or explicitly
cleared v2 answers survive restarts. Original fields removed from the shorter form
remain stored in v1; they are not discarded or silently reinterpreted.

The complete-assessment API keeps its existing nested schema. Its PUT imports
retained fields into both versions, with explicit scalar-to-list conversion for
v2. Individual draft edits remain independent of that complete-document snapshot.

Chat uses initial-v2 by default (GUIDANCE_QUESTIONNAIRE_ID=initial-v2), including
the selected motivation and obstacle lists. Existing conversations can continue
with the current profile. Neither student profiles nor answers are embedded.
