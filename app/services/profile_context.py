"""Minimized context derived from the same service used by the profile API."""
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.questionnaire import profile

QUESTIONNAIRE_ID = "sample-initial-v1"


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
    saved = profile(db, student_id, QUESTIONNAIRE_ID)
    allowed = set(settings.guidance_profile_keys)
    fields = {field.key: minimize_value(field.value, saved.display_name)
              for field in saved.fields if field.key in allowed}
    return {
        "questionnaire_id": saved.questionnaire_id,
        "is_sample": saved.is_sample,
        "answers": fields,
        "missing_fields": [key for key, value in fields.items() if value is None],
        "omitted_field_count": len(saved.fields) - len(fields),
    }, saved.display_name
