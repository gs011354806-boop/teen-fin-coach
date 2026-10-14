"""llm/client.py 검증. 실제 Gemini는 부르지 않고 가짜 generate를 넣는다."""

import json

import pytest

from llm import client


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "LOG_PATH", tmp_path / "logs" / "llm_errors.log")
    return client.LOG_PATH


def fake(*responses):
    calls = []

    def generate(prompt):
        calls.append(prompt)
        response = responses[len(calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    generate.calls = calls
    return generate


PAYLOAD = {"patterns": ["몰빵"], "journal": "", "question": "왜 샀나요?", "answer": "그냥"}


def test_success_first_try():
    gen = fake(json.dumps({"error_type": "근거 부족", "reason": "이유가 막연했어요."}))
    result = client.ask("classify_mistake", PAYLOAD, generate=gen)
    assert result == {"error_type": "근거 부족", "reason": "이유가 막연했어요."}
    assert len(gen.calls) == 1


def test_payload_is_in_prompt():
    gen = fake(json.dumps({"question": "무엇을 보고 샀나요?"}))
    client.ask("mistake_question", {"facts": ["투자 일지를 비워 두었어요."]}, generate=gen)
    assert "투자 일지를 비워 두었어요." in gen.calls[0]
    assert "{{payload}}" not in gen.calls[0]


def test_retry_once_after_parse_failure(tmp_log):
    gen = fake("JSON 아님", json.dumps({"question": "무엇을 보고 샀나요?"}))
    assert client.ask("mistake_question", {}, generate=gen) == {"question": "무엇을 보고 샀나요?"}
    assert len(gen.calls) == 2
    assert not tmp_log.exists()


def test_default_and_log_after_two_failures(tmp_log):
    gen = fake("JSON 아님", "{}")
    result = client.ask("mistake_question", {}, generate=gen)
    assert result == client.SPECS["mistake_question"]["default"]
    assert len(gen.calls) == 2
    assert "mistake_question" in tmp_log.read_text(encoding="utf-8")


def test_custom_default():
    gen = fake("x", "y")
    default = {"explanation": "콘텐츠 정의", "next_try": "확인 질문"}
    assert client.ask("explain_concept", {}, default=default, generate=gen) == default


def test_unknown_error_type_is_failure():
    gen = fake(json.dumps({"error_type": "탐욕", "reason": "r"}),
               json.dumps({"error_type": "FOMO", "reason": "따라 샀어요."}))
    assert client.ask("classify_mistake", PAYLOAD, generate=gen)["error_type"] == "FOMO"


@pytest.mark.parametrize("bad", ["삼성전자를 파세요.", "수익률이 -11%라 잘못됐어요."])
def test_rule_breaking_text_is_failure(bad, tmp_log):
    gen = fake(json.dumps({"question": bad}), json.dumps({"question": bad}))
    result = client.ask("mistake_question", {}, generate=gen)
    assert result == client.SPECS["mistake_question"]["default"]
    assert tmp_log.exists()


@pytest.mark.parametrize("error", [client.QuotaExceededError("429"),
                                   client.ServiceUnavailableError("503")])
def test_quota_and_server_errors_are_not_retried(error):
    gen = fake(error, json.dumps({"question": "q"}))
    with pytest.raises(type(error)):
        client.ask("mistake_question", {}, generate=gen)
    assert len(gen.calls) == 1


def test_other_call_error_returns_default_without_retry(tmp_log):
    gen = fake(ConnectionError("offline"), json.dumps({"question": "q"}))
    result = client.ask("mistake_question", {}, generate=gen)
    assert result == client.SPECS["mistake_question"]["default"]
    assert len(gen.calls) == 1
    assert "offline" in tmp_log.read_text(encoding="utf-8")


def test_missing_key(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    monkeypatch.setattr(client, "ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(client.MissingKeyError):
        client.get_api_key()


# --- 실제 Gemini 호출 함수: 시간 제한·재시도 안 함 (네트워크 없이 가짜 클라이언트로) ---

class FakeModels:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        raise self.error


def fake_client(monkeypatch, error):
    from google import genai

    created = {}
    models = FakeModels(error)

    class FakeClient:
        def __init__(self, api_key, http_options):
            created["http_options"] = http_options
            self.models = models

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setattr(client, "get_api_key", lambda: "test-key")
    return created, models


def test_http_options_have_timeout_and_no_retry():
    from config import LLM_TIMEOUT_SECONDS

    options = client.http_options()
    assert options.timeout == LLM_TIMEOUT_SECONDS * 1000
    assert options.retry_options.attempts == 1


def test_timeout_becomes_service_unavailable_without_retry(monkeypatch):
    import httpx

    created, models = fake_client(monkeypatch, httpx.ReadTimeout("느림"))
    with pytest.raises(client.ServiceUnavailableError):
        client.ask("mistake_question", {}, generate=client.gemini_generate)
    assert models.calls == 1
    assert created["http_options"].retry_options.attempts == 1


@pytest.mark.parametrize("code, expected", [(429, client.QuotaExceededError),
                                            (503, client.ServiceUnavailableError)])
def test_api_errors_are_mapped(monkeypatch, code, expected):
    from google.genai import errors

    _, models = fake_client(monkeypatch, errors.APIError(code, {"error": {"message": "x"}}))
    with pytest.raises(expected):
        client.ask("mistake_question", {}, generate=client.gemini_generate)
    assert models.calls == 1


@pytest.mark.parametrize("text", ["민지야, 왜 샀어?", "서연아! 이건 왜 골랐어", "그냥 샀다."])
def test_informal_text_is_failure(text, tmp_log):
    gen = fake(json.dumps({"question": text}), json.dumps({"question": text}))
    assert client.ask("mistake_question", {}, generate=gen) == client.SPECS["mistake_question"]["default"]


@pytest.mark.parametrize("text", ["민지 님, 무엇을 보고 샀나요?", "이유를 한 줄 적어 보세요.",
                                  "좋은 흐름이에요! 이번 달도 함께해 주세요"])
def test_polite_text_passes(text):
    gen = fake(json.dumps({"question": text}))
    assert client.ask("mistake_question", {}, generate=gen) == {"question": text}


def test_category_values_are_not_checked_for_politeness():
    gen = fake(json.dumps({"error_type": "FOMO", "reason": "따라 산 것 같아요."}))
    assert client.ask("classify_mistake", {}, generate=gen)["error_type"] == "FOMO"
