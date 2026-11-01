import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import main
from app.core.config import Settings
from app.models.pathway import PathwayPlan
from app.schemas.pathway import GeneratedPathway
from app.services.llm import LLMError, OpenAILLMService, get_llm
from app.services import llm as llm_module
from app.services.profile_context import build_profile_context
from tests.test_students import client  # noqa: F401
from tests.test_auth import secure_client, headers, register  # noqa: F401


def plan_content(minutes=0):
    return dict(pace='Use the reported time budget; confirm any missing availability.',
                adaptations=['Use an offline paper prototype if equipment is unavailable.'],
                steps=[dict(horizon=horizon, title=title, action='Sketch and test a paper mechanism, then record feedback.',
                            why='You want to explore robotics and prefer hands-on learning.',
                            evidence='A sketch with test notes.', timing='After the preceding milestone', weekly_minutes=minutes)
                       for horizon, title in [('short', 'Define a first outcome'), ('short', 'Try an interest experiment'),
                                              ('long', 'Compare routes'), ('long', 'Build a project')]])


@pytest.fixture
def ai(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not call the live OpenAI API')
    monkeypatch.setattr(llm_module, 'OpenAI', forbidden)
    fake = MagicMock()
    fake.generate_json.return_value = json.dumps(plan_content())
    main.app.dependency_overrides[get_llm] = lambda: fake
    return fake


def completed_student(client, **optional):
    sid = client.post('/students', json={'display_name': 'Private Student'}).json()['id']
    qs = {q['key']: q for q in client.get('/questionnaires/initial-v2/questions').json()}
    answers = dict(grade='High School', short_term_goal='Try robotics', long_term_aspirations='Design robots',
                   soft_skills=['Teamwork'], learning_preferences=['Hands-on'])
    answers.update(optional)
    for key, value in answers.items():
        result = client.put(f"/students/{sid}/assessments/initial-v2/answers/{qs[key]['id']}", json={'value': value})
        assert result.status_code == 200, result.text
    return sid, qs


def create(client, sid):
    result = client.post(f'/students/{sid}/pathway/generate')
    assert result.status_code == 200, result.text
    return result.json()


def test_plan_requires_completed_assessment(client, ai):
    sid = client.post('/students', json={}).json()['id']
    for endpoint in ('generate', 'rebuild'):
        assert client.post(f'/students/{sid}/pathway/{endpoint}').status_code == 409
    assert client.get(f'/students/{sid}/pathway').status_code == 409
    assert client.get('/students/999/pathway').status_code == 404
    ai.generate_json.assert_not_called()


def test_ai_plan_uses_minimized_assessment_and_persists_without_repeated_calls(client, ai):
    sid, _ = completed_student(client, weekly_learning_hours=0, has_personal_laptop='No', has_reliable_internet='No',
                               related_experiences='Private Student built a toy; contact student@example.org')
    url = f'/students/{sid}/pathway'
    assert client.get(url).status_code == 404
    ai.generate_json.assert_not_called()
    plan = create(client, sid)
    assert plan['generated_by'] == 'ai' and plan['model']
    assert plan['short_term_goal'] == 'Try robotics'
    assert plan['long_term_aspiration'] == 'Design robots'
    instructions, messages, schema = ai.generate_json.call_args.args
    context = json.loads(messages[0]['content'].split('\n', 1)[1])
    assert context['has_personal_laptop'] == 'No' and context['weekly_learning_hours'] == 0
    assert context['learning_preferences'] == ['Hands-on']
    assert context['current_program'] is None
    assert 'Private Student' not in str(messages) and 'student@example.org' not in str(messages)
    assert 'untrusted' in instructions and schema['additionalProperties'] is False
    assert {s['horizon'] for s in plan['steps']} == {'short', 'long'}
    step_id = plan['steps'][0]['id']
    updated = client.put(url + f'/steps/{step_id}', json={'status': 'completed', 'notes': 'Built a paper robot'})
    assert updated.status_code == 200
    stored = client.get(url).json()
    assert stored['steps'][0]['status'] == 'completed' and stored['steps'][0]['notes'] == 'Built a paper robot'
    assert create(client, sid)['steps'][0]['status'] == 'completed'
    assert ai.generate_json.call_count == 1
    assert client.put(url + '/steps/missing', json={'status': 'completed'}).status_code == 404
    assert client.put(url + f'/steps/{step_id}', json={'status': 'invalid'}).status_code == 422
    assert client.put(url + f'/steps/{step_id}', json={'status': 'completed', 'notes': 'x' * 2001}).status_code == 422
    other, _ = completed_student(client)
    assert all(s['status'] == 'not_started' for s in create(client, other)['steps'])


def test_changed_assessment_and_explicit_rebuild(client, ai):
    sid, qs = completed_student(client)
    url = f'/students/{sid}/pathway'
    original = create(client, sid)
    step_id = original['steps'][0]['id']
    client.put(url + f'/steps/{step_id}', json={'status': 'in_progress', 'notes': 'Keep this'})
    client.put(f"/students/{sid}/assessments/initial-v2/answers/{qs['short_term_goal']['id']}", json={'value': 'Explore art'})
    changed = client.get(url).json()
    assert changed['assessment_changed'] is True
    assert changed['short_term_goal'] == original['short_term_goal']
    assert changed['steps'][0]['notes'] == 'Keep this'
    assert client.put(url + f'/steps/{step_id}', json={'status': 'completed'}).status_code == 409
    rebuilt = client.post(url + '/rebuild').json()
    assert rebuilt['short_term_goal'] == 'Explore art' and not rebuilt['assessment_changed']
    assert all(s['status'] == 'not_started' and not s['notes'] for s in rebuilt['steps'])
    assert rebuilt['steps'][0]['id'] != step_id
    assert 'Explore art' in str(ai.generate_json.call_args.args[1])


@pytest.mark.parametrize('failure', [LLMError('provider_not_configured', 503), LLMError(), 'not JSON', '{}', json.dumps(plan_content(1))])
def test_failed_or_over_budget_generation_preserves_existing_work(client, ai, failure):
    sid, _ = completed_student(client, weekly_learning_hours=0)
    url = f'/students/{sid}/pathway'
    plan = create(client, sid)
    step_id = plan['steps'][0]['id']
    client.put(url + f'/steps/{step_id}', json={'status': 'completed', 'notes': 'Keep this'})
    before = client.get(url).json()
    if isinstance(failure, Exception):
        ai.generate_json.side_effect = failure
    else:
        ai.generate_json.return_value = failure
    result = client.post(url + '/rebuild')
    assert result.status_code in (502, 503)
    assert client.get(url).json() == before


def test_missing_provider_does_not_create_fake_plan(client, ai):
    sid, _ = completed_student(client)
    ai.generate_json.side_effect = LLMError('provider_not_configured', 503)
    assert client.post(f'/students/{sid}/pathway/generate').status_code == 503
    assert client.get(f'/students/{sid}/pathway').status_code == 404


def test_assessment_edit_during_generation_is_rejected(client, ai):
    sid, qs = completed_student(client)
    def change(*args):
        client.put(f"/students/{sid}/assessments/initial-v2/answers/{qs['short_term_goal']['id']}", json={'value': 'Explore art'})
        return json.dumps(plan_content())
    ai.generate_json.side_effect = change
    assert client.post(f'/students/{sid}/pathway/generate').status_code == 409
    assert client.get(f'/students/{sid}/pathway').status_code == 404


def test_legacy_plan_is_preserved_until_explicit_ai_rebuild(client, ai):
    sid, _ = completed_student(client)
    create(client, sid)
    with Session(main.engine) as db:
        row = db.get(PathwayPlan, sid)
        row.data = {k: v for k, v in row.data.items() if k != 'generated_by'}
        db.commit()
    assert client.get(f'/students/{sid}/pathway').json()['generated_by'] == 'rules'
    assert ai.generate_json.call_count == 1
    assert client.post(f'/students/{sid}/pathway/rebuild').json()['generated_by'] == 'ai'


def test_pathway_ownership_and_csrf(secure_client):
    client, _ = secure_client
    sid = register(client).json()['user']['student_id']
    assert client.get(f'/students/{sid}/pathway').status_code == 409
    assert client.get('/students/999/pathway').status_code == 404
    for endpoint in ('generate', 'rebuild'):
        assert client.post(f'/students/999/pathway/{endpoint}', headers=headers(client)).status_code == 404
        assert client.post(f'/students/{sid}/pathway/{endpoint}').status_code == 403
    assert client.put('/students/999/pathway/steps/make-space', json={'status': 'completed'}, headers=headers(client)).status_code == 404
    assert client.put(f'/students/{sid}/pathway/steps/make-space', json={'status': 'completed'}).status_code == 403


def test_structured_provider_request_and_failure_handling(monkeypatch):
    sdk = MagicMock()
    sdk.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(plan_content()))
    factory = MagicMock()
    factory.return_value.__enter__.return_value = sdk
    monkeypatch.setattr(llm_module, 'OpenAI', factory)
    service = OpenAILLMService(Settings(_env_file=None, openai_api_key='test-key'))
    schema = GeneratedPathway.model_json_schema()
    result = service.generate_json('Instructions', [], schema)
    assert GeneratedPathway.model_validate_json(result)
    request = sdk.responses.create.call_args.kwargs
    assert request['store'] is False and request['max_output_tokens'] == 6000
    assert request['text']['format'] == dict(type='json_schema', name='student_pathway', strict=True, schema=schema)
    sdk.responses.create.return_value = SimpleNamespace(status='incomplete', output_text='{}')
    with pytest.raises(LLMError):
        service.generate_json('Instructions', [], schema)


def test_structured_plan_requires_both_horizons_and_meaningful_content():
    plan = plan_content()
    for step in plan['steps']:
        step['horizon'] = 'short'
    with pytest.raises(ValidationError):
        GeneratedPathway.model_validate(plan)
    plan = plan_content()
    plan['steps'][0]['action'] = '   '
    with pytest.raises(ValidationError):
        GeneratedPathway.model_validate(plan)


def test_counselor_context_includes_saved_plan_and_progress(client, ai):
    sid, _ = completed_student(client)
    plan = create(client, sid)
    client.put(f"/students/{sid}/pathway/steps/{plan['steps'][0]['id']}", json={'status': 'completed', 'notes': 'Private reflection'})
    with Session(main.engine) as db:
        context, _ = build_profile_context(db, sid, Settings(_env_file=None, guidance_questionnaire_id='initial-v2'))
    assert context['saved_pathway']['assessment_changed'] is False
    assert context['saved_pathway']['steps'][0]['status'] == 'completed'
    assert context['saved_pathway']['steps'][0]['action'] == plan['steps'][0]['action']
    assert 'Private reflection' not in str(context)
