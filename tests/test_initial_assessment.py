from sqlalchemy.orm import Session

from app import main
from app.core.config import Settings, get_settings
from app.services.initial_assessment import seed_initial
from app.models.student import Student
from tests.test_chat import fake_llm  # noqa: F401
from tests.test_students import client, payload  # noqa: F401


def setup(client):
    sid = client.post('/students', json={}).json()['id']
    questions = client.get('/questionnaires/initial-v1/questions').json()
    return sid, {q['key']: q for q in questions}


def test_actual_questionnaire_schema_choices_and_validation(client):
    sid, questions = setup(client)
    assert len(questions) == 31
    assert not any('sample' in q['prompt'].lower() for q in questions.values())
    assert questions['short_term_timeline']['options'] == ['3-6 Month', '6 month - 1 Year', '1-2 Years', 'More than 2 Years']
    assert questions['other_motivator']['required_when'] == {'primary_motivator': 'Other'}
    assert questions['has_personal_laptop']['options'] == ['Yes', 'No']
    url = f'/students/{sid}/assessments/initial-v1'
    for key, bad, good in [('age', 0, 16), ('age', 16.5, 17), ('gpa', -1, 3.5),
                           ('weekly_learning_hours', 169, 4.5), ('weekly_learning_hours', -1, 0)]:
        endpoint = f"{url}/answers/{questions[key]['id']}"
        assert client.put(endpoint, json={'value': bad}).status_code == 422
        assert client.put(endpoint, json={'value': good}).status_code == 200
    profile = client.get(url + '/profile').json()
    assert profile['is_sample'] is False


def test_conditional_answers_progress_and_clearing(client):
    sid, questions = setup(client)
    url = f'/students/{sid}/assessments/initial-v1'
    def save(key, value):
        assert client.put(f"{url}/answers/{questions[key]['id']}", json={'value': value}).status_code == 200
    before = client.get(url + '/progress').json()
    save('primary_motivator', 'Other')
    after = client.get(url + '/progress').json()
    assert after['required_questions'] == before['required_questions'] + 1
    assert after['total_questions'] == before['total_questions'] + 1
    save('other_motivator', 'Support my community')
    save('primary_motivator', 'Helping people')
    profile = client.get(url + '/profile').json()
    assert 'other_motivator' not in {field['key'] for field in profile['fields']}
    save('primary_motivator', 'Other')
    fields = {field['key']: field['value'] for field in client.get(url + '/profile').json()['fields']}
    assert fields['other_motivator'] is None


def test_existing_actual_assessment_import_resume_and_non_overwrite(client, payload):
    sid, questions = setup(client)
    assert client.put(f'/students/{sid}/assessment', json=payload).status_code == 200
    url = f'/students/{sid}/assessments/initial-v1'
    fields = {f['key']: f['value'] for f in client.get(url + '/profile').json()['fields']}
    assert fields['short_term_goal'] == payload['career_goals']['short_term_goal']
    assert fields['has_personal_laptop'] == 'No'
    assert fields['soft_skills'] == ['Creativity', 'Teamwork']
    assert client.get(url + '/progress').json()['is_complete'] is True
    endpoint = f"{url}/answers/{questions['short_term_goal']['id']}"
    assert client.put(endpoint, json={'value': 'Updated goal'}).status_code == 200
    with Session(main.engine) as db:
        seed_initial(db)
        seed_initial(db)
    fields = {f['key']: f['value'] for f in client.get(url + '/profile').json()['fields']}
    assert fields['short_term_goal'] == 'Updated goal'
    assert len(client.get('/questionnaires/initial-v1/questions').json()) == 31


def test_startup_imports_preexisting_snapshot_without_restoring_cleared_answers(client, payload):
    sid, questions = setup(client)
    with Session(main.engine) as db:
        db.get(Student, sid).assessment_answers = payload
        db.commit()
        seed_initial(db)
    url = f'/students/{sid}/assessments/initial-v1'
    fields = {f['key']: f['value'] for f in client.get(url + '/profile').json()['fields']}
    assert fields['long_term_aspirations'] == payload['career_goals']['long_term_aspirations']
    assert client.put(f"{url}/answers/{questions['long_term_aspirations']['id']}", json={'value': None}).status_code == 200
    with Session(main.engine) as db:
        seed_initial(db)
    fields = {f['key']: f['value'] for f in client.get(url + '/profile').json()['fields']}
    assert fields['long_term_aspirations'] is None


def test_real_profile_used_in_chat_and_old_conversations_resume(client, fake_llm):
    sid, questions = setup(client)
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, guidance_questionnaire_id='initial-v1')
    url = f'/students/{sid}/assessments/initial-v1'
    for key, value in [('name', 'Private Full Name'), ('city', 'Private City'),
                       ('short_term_goal', 'Explore robotics'), ('has_personal_laptop', 'No')]:
        assert client.put(f"{url}/answers/{questions[key]['id']}", json={'value': value}).status_code == 200
    response = client.post(f'/students/{sid}/chat', json={'message': 'What should I try?'})
    assert response.status_code == 200
    instructions = fake_llm.calls[-1][0]
    assert 'Explore robotics' in instructions and '"is_sample": false' in instructions
    assert 'Private Full Name' not in instructions and 'Private City' not in instructions
    cid = response.json()['conversation_id']
    assert client.get(f'/students/{sid}/conversations/{cid}').json()['questionnaire_id'] == 'initial-v1'
    # A sample-era conversation is retained and can use the current real profile.
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, guidance_questionnaire_id='sample-initial-v1')
    old = client.post(f'/students/{sid}/chat', json={'message': 'Earlier conversation'}).json()['conversation_id']
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, guidance_questionnaire_id='initial-v1')
    resumed = client.post(f'/students/{sid}/chat', json={'message': 'Continue', 'conversation_id': old})
    assert resumed.status_code == 200
    assert 'Explore robotics' in fake_llm.calls[-1][0]
