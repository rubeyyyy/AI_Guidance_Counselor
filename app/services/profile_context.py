"""Minimized context derived from the same service used by the profile API."""
import re
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.questionnaire import profile

from app.services.short_assessment import QUESTIONNAIRE_ID
from app.models.pathway import PathwayPlan


def minimize_text(text: str, display_name: str | None) -> str:
    """Best-effort minimization, NOT a complete de-identification system."""
    if display_name:
        text = re.sub(re.escape(display_name), "[name omitted]", text, flags=re.IGNORECASE)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email omitted]", text)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)", "[phone omitted]", text)
    return text


def minimize_value(value: Any, display_name: str | None) -> Any:
    if isinstance(value, str):
        return minimize_text(value, display_name)
    if isinstance(value, list):
        return [minimize_value(item, display_name) for item in value]
    return value


def build_profile_context(db: Session, student_id: int, settings: Settings) -> tuple[dict, str | None]:
    saved = profile(db, student_id, settings.guidance_questionnaire_id)
    allowed = set(settings.guidance_profile_keys)
    fields = {field.key: minimize_value(field.value, saved.display_name)
              for field in saved.fields if field.key in allowed}
    context = {
        "questionnaire_id": saved.questionnaire_id,
        "is_sample": saved.is_sample,
        "answers": fields,
        "missing_fields": [key for key, value in fields.items() if value is None],
        "omitted_field_count": len(saved.fields) - len(fields),
    }
    plan = db.get(PathwayPlan, student_id)
    if plan:
        current_answers = {field.key: field.value for field in saved.fields}
        fingerprint = hashlib.sha256(json.dumps(current_answers, sort_keys=True).encode()).hexdigest()
        context['saved_pathway'] = {
            'assessment_changed': saved.questionnaire_id != QUESTIONNAIRE_ID or plan.data['fingerprint'] != fingerprint,
            'pace': minimize_value(plan.data['pace'], saved.display_name),
            'steps': [{key: minimize_value(step[key], saved.display_name)
                       for key in ('horizon', 'title', 'action', 'evidence', 'timing', 'status')}
                      for step in plan.data['steps']],
        }
    return context, saved.display_name
