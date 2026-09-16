"""Network-free proof that protected values stop before the LLM contract."""

from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.privacy import PrivacyProcessor, ResponseUnmasker
from app.sessions.models import SessionState
from tests.llm.fakes import FakeLLMClient


def test_raw_protected_values_do_not_cross_fake_llm_boundary() -> None:
    original = "Show claims for member M000245. Contact me at alice@example.com."
    privacy_result = PrivacyProcessor().process(original)
    fake_llm = FakeLLMClient(text="Member T001 has 4 claims. Email stays [EMAIL].")

    llm_response = fake_llm.generate(
        LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content=privacy_result.safe_text)])
    )

    llm_visible_text = fake_llm.requests[0].messages[0].content
    assert llm_visible_text == "Show claims for member T001. Contact me at [EMAIL]."
    assert "M000245" not in llm_visible_text
    assert "alice@example.com" not in llm_visible_text

    final_text = ResponseUnmasker().unmask(llm_response.text, privacy_result.token_mappings)
    assert final_text == "Member M000245 has 4 claims. Email stays [EMAIL]."


def test_request_only_fields_are_absent_from_persisted_session_contract() -> None:
    assert "token_mapping_history" not in SessionState.model_fields
    assert "custom_context" not in SessionState.model_fields
    assert "last_token_mapping" in SessionState.model_fields
