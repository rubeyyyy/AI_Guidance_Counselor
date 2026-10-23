from sqlalchemy.orm import Session

from app import main
from app.core.config import Settings, get_settings
from app.services.short_assessment import seed_short
from tests.test_chat import fake_llm  # noqa: F401
from tests.test_students import client, payload  # noqa: F401


def setup(client):
    sid = client.post('/students', json={}).json()['id']
    questions = client.get('/questionnaires/initial-v2/questions').json()
    return sid, {q['key']: q for q in questions}


def test_twenty_questions_five_required_and_optional_skips(client):
    sid, questions = setup(client)
    assert len(questions) == 20
    assert sum(q['required'] for q in questions.values()) == 5
    assert all(q['required_when'] is None for q in questions.values())
    assert not {'name', 'age', 'city', 'other_motivator', 'other_obstacle'} & questions.keys()
    url = f'/students/{sid}/assessments/initial-v2'
    required_values = {'grade': '11', 'short_term_goal': 'Explore design',
                       'long_term_aspirations': 'Not sure yet', 'soft_skills': ['Creativity'],
                       'learning_preferences': ['Hands-on']}
    for key, question in questions.items():
        assert client.put(f"{url}/answers/{question['id']}", json={'value': required_values.get(key)}).status_code == 200
    progress = client.get(url + '/progress').json()
    assert progress['total_questions'] == 20
    assert progress['required_questions'] == 5
    assert progress['answered_required_questions'] == 5
    assert progress['is_complete'] is True


def test_multi_motivation_obstacles_and_invalid_selections(client):
    sid, questions = setup(client)
    url = f'/students/{sid}/assessments/initial-v2'
    for key, choices in [('primary_motivator', ['Passion/interest', 'Financial stability', 'Other']),
                         ('biggest_obstacle', ['Financial limitations', 'Time constraints', 'Other'])]:
        assert questions[key]['response_type'] == 'multiple-choice'
        assert questions[key]['required'] is False
        endpoint = f"{url}/answers/{questions[key]['id']}"
        assert client.put(endpoint, json={'value': choices}).status_code == 200
        for bad in [choices[0], [], [choices[0], choices[0]], ['not an option'], [12]]:
            assert client.put(endpoint, json={'value': bad}).status_code == 422
        fields = {f['key']: f['value'] for f in client.get(url + '/profile').json()['fields']}
        assert fields[key] == choices
        assert client.put(endpoint, json={'value': None}).status_code == 200


def test_migration_wraps_old_choices_preserves_originals_and_cleared_answers(client, payload):
    sid, questions = setup(client)
    assert client.put(f'/students/{sid}/assessment', json=payload).status_code == 200
    url = f'/students/{sid}/assessments/initial-v2'
    fields = {f['key']: f['value'] for f in client.get(url + '/profile').json()['fields']}
    assert fields['primary_motivator'] == ['Other']
    assert fields['biggest_obstacle'] == ['Other']
    assert fields['short_term_goal'] == payload['career_goals']['short_term_goal']
    assert client.put(f"{url}/answers/{questions['primary_motivator']['id']}", json={'value': ['Helping people', 'Passion/interest']}).status_code == 200
    assert client.put(f"{url}/answers/{questions['biggest_obstacle']['id']}", json={'value': None}).status_code == 200
    with Session(main.engine) as db:
        seed_short(db)
        seed_short(db)
    fields = {f['key']: f['value'] for f in client.get(url + '/profile').json()['fields']}
    assert fields['primary_motivator'] == ['Helping people', 'Passion/interest']
    assert fields['biggest_obstacle'] is None
    old = client.get(f'/students/{sid}/assessments/initial-v1/profile').json()
    old_fields = {f['key']: f['value'] for f in old['fields']}
    assert old_fields['primary_motivator'] == 'Other'
    assert old_fields['other_motivator'] == payload['motivation']['other_motivator']
    assert len(client.get('/questionnaires/initial-v1/questions').json()) == 31


def test_default_chat_uses_short_profile_multi_answers(client, fake_llm):
    sid, questions = setup(client)
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    for key, value in [('primary_motivator', ['Helping people', 'Financial stability']),
                       ('biggest_obstacle', ['Time constraints', 'Financial limitations'])]:
        assert client.put(f"/students/{sid}/assessments/initial-v2/answers/{questions[key]['id']}", json={'value': value}).status_code == 200
    response = client.post(f'/students/{sid}/chat', json={'message': 'Help me plan my next step'})
    assert response.status_code == 200
    instructions = fake_llm.calls[-1][0]
    assert '"questionnaire_id": "initial-v2"' in instructions
    assert '"primary_motivator": ["Helping people", "Financial stability"]' in instructions
    assert '"biggest_obstacle": ["Time constraints", "Financial limitations"]' in instructions
