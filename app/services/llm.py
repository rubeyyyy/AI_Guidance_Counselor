"""Provider boundary: future Ollama/LangChain adapters implement generate()."""
from typing import Literal, Protocol, TypedDict

from openai import APIError, OpenAI

from app.core.config import Settings, get_settings


class LLMMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMError(Exception):
    def __init__(self, code: str = "provider_unavailable", status_code: int = 502):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class LLMService(Protocol):
    def generate(self, instructions: str, messages: list[LLMMessage]) -> str: ...


class OpenAILLMService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, instructions: str, messages: list[LLMMessage]) -> str:
        key = self.settings.openai_api_key.get_secret_value().strip()
        if not key:
            raise LLMError("provider_not_configured", 503)
        try:
            # No provider-side conversation state; local SQLite is authoritative.
            with OpenAI(api_key=key, timeout=self.settings.openai_timeout_seconds,
                        max_retries=0) as client:
                response = client.responses.create(
                    model=self.settings.openai_model,
                    instructions=instructions,
                    input=messages,
                    max_output_tokens=self.settings.guidance_max_output_tokens,
                    store=False,
                )
        except APIError:
            # Never expose provider exception bodies, credentials, or profile data.
            raise LLMError() from None
        if response.status != "completed" or not response.output_text.strip():
            raise LLMError("provider_incomplete_response")
        return response.output_text.strip()


def get_llm() -> LLMService:
    return OpenAILLMService(get_settings())
