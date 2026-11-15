"""OpenAI 호출 + JSON 파싱 + 재시도. LLM 호출은 이 파일에서만 한다.

- 파싱 실패(또는 규칙 위반 문장) → 1회 재시도, 또 실패하면 기본 문구 + logs/llm_errors.log 기록
- 429 → QuotaExceededError (자동 재시도 안 함)
- 5xx(서버 과부하 등)·응답 시간 초과 → ServiceUnavailableError (자동 재시도 안 함)
- 키 없음 → MissingKeyError
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from config import LLM_TIMEOUT_SECONDS, MODEL_NAME, REASONING_EFFORT
from engine.detect import ERROR_TYPES
from engine.news import ART as NEWS_ART

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
ENV_PATH = ROOT / ".env"
LOG_PATH = ROOT / "logs" / "llm_errors.log"

# 규칙 3(종목 권유), 4(수익률 평가)를 어기는 표현이 나오면 실패로 본다.
BANNED_PHRASES = ["사세요", "파세요", "매수하세요", "매도하세요", "사는 게 좋", "파는 게 좋",
                  "매수해 보세요", "매도해 보세요", "매수하는 방법", "매도하는 방법",
                  "사지 마세요", "팔지 마세요", "사지 않는 게 좋", "멈추세요",
                  "수익률", "손실이 났", "이익이 났"]

# 학생·부모에게 보여 줄 문장은 존댓말이어야 한다. 반말 호칭("민지야,")이나 존댓말 어미가 없으면 실패로 본다.
# 반말 호칭은 문장 첫머리의 짧은 이름 + 야/아 ("민지야,"). 문장 중간의 "나눠 담아,"는 호칭이 아니다.
INFORMAL_CALL = re.compile(r"(^|[.!?]\s+)[가-힣]{1,3}(야|아)\s*[,!~]")
POLITE_ENDING = re.compile(r"(요|니다|세요|까요)\s*[.?!~]*\s*$|(요|니다)\s*[.?!~]")


def check_polite(text):
    if INFORMAL_CALL.search(text) or not POLITE_ENDING.search(text):
        raise ValueError(f"존댓말 아님: {text[:40]}")


SPECS = {
    "mistake_question": {
        "required": ["question"],
        "allowed": {},
        "default": {"question": "이 종목을 살 때 무엇을 보고 결정했나요? 한 줄로 적어 볼까요?"},
    },
    "followup_question": {
        "required": ["question"],
        "allowed": {},
        "default": {"question": "그때 무엇을 하나만 확인했다면 판단이 달라졌을까요? 한 줄로 적어 볼까요?"},
    },
    "classify_mistake": {
        "required": ["error_type", "reason"],
        "allowed": {"error_type": ERROR_TYPES},
        "default": {"error_type": "해당 없음", "reason": ""},
    },
    "explain_concept": {
        "required": ["explanation", "next_try"],
        "allowed": {},
        "default": {"explanation": "", "next_try": ""},
    },
    "diagnose_week": {
        "required": ["summary"],
        "lists": {"good": (1, 2), "practice": (1, 2)},
        "allowed": {},
        "default": {"summary": "", "good": [], "practice": []},
    },
    "weekly_mission": {
        "required": ["text"],
        "allowed": {},
        "default": {"text": ""},
    },
    "replay_comment": {
        "required": ["comment"],
        "allowed": {},
        "default": {"comment": ""},
    },
    "precheck_question": {
        "required": ["question"],
        "allowed": {},
        "default": {"question": "이 매수를 하려는 이유를 한 줄로 더 적어 볼까요?"},
    },
    "growth_review": {
        "required": ["story", "next"],
        "allowed": {},
        "default": {"story": "", "next": ""},
    },
    "concept_answer": {
        "required": ["concept", "answer"],
        "allowed": {},
        "plain": ["concept"],  # 개념 id라 존댓말 검사 대상이 아님 (허용 값은 화면의 check가 본다)
        "default": {"concept": "NONE", "answer": "아직 준비된 내용이 없어요."},
    },
    "game_coach": {
        "required": ["message"],
        "allowed": {},
        "default": {"message": ""},
    },
    "game_quiz": {
        "required": ["q1", "q1_answer", "q2", "q2_answer"],
        "lists": {"q1_options": (3, 3), "q2_options": (3, 3)},
        "allowed": {"q1_answer": ["1", "2", "3"], "q2_answer": ["1", "2", "3"]},
        "default": {"q1": "", "q1_answer": "", "q2": "", "q2_answer": "", "q1_options": [], "q2_options": []},
    },
    "news_cards": {  # 22번: 카드 3장 + 퀴즈 3문제 (중첩 대신 평평한 키)
        "required": [f"card{i}_{k}" for i in (1, 2, 3) for k in ("news_id", "tag", "headline", "highlight", "number", "fact", "summary",
                                                      "learn", "learn_highlight", "why", "concept", "art")]
                    + [f"q{i}{k}" for i in (1, 2, 3) for k in ("", "_answer")],
        "lists": {f"q{i}_options": (3, 3) for i in (1, 2, 3)},
        "allowed": {**{f"q{i}_answer": ["1", "2", "3"] for i in (1, 2, 3)},
                    **{f"card{i}_art": list(NEWS_ART) for i in (1, 2, 3)}},
        "plain": [f"card{i}_{k}" for i in (1, 2, 3)
                  for k in ("news_id", "tag", "headline", "highlight", "number", "fact", "learn_highlight", "concept")],
        "default": {},
    },
    "news_daily": {  # 오늘의 뉴스 3개 × 카드 3장 문장 + 퀴즈 3문제 (NEWS_MARKET_SPEC.md 5장, news_cards와 같은 규칙)
        "required": [f"n{i}_{k}" for i in (1, 2, 3)
                     for k in ("list", "what_title", "what", "why_title", "why", "me_title", "me", "tip", "concept")]
                    + [f"q{i}{k}" for i in (1, 2, 3) for k in ("", "_answer", "_explain")],
        "lists": {f"q{i}_options": (4, 4) for i in (1, 2, 3)},
        "allowed": {f"q{i}_answer": ["1", "2", "3", "4"] for i in (1, 2, 3)},
        "plain": [f"n{i}_{k}" for i in (1, 2, 3) for k in ("tip", "concept")],
        "default": {},
    },
    "mydata_welcome": {
        "required": ["message"],
        "allowed": {},
        "default": {"message": "마이데이터를 연결해 줘서 고마워요. 이번 주 연습할 것부터 함께 해 봐요."},
    },
    "parent_mission": {
        "required": ["text"],
        "allowed": {},
        "default": {"text": ""},
    },
}


class LLMError(Exception):
    """AI에서 쓸 만한 답을 받지 못한 모든 경우의 부모 클래스 (시연 모드가 한 번에 잡는다)."""


class MissingKeyError(LLMError):
    pass


class QuotaExceededError(LLMError):
    pass


class ServiceUnavailableError(LLMError):
    pass


class AnswerRejectedError(LLMError):
    """두 번 물어도 형식·규칙에 맞는 답이 오지 않음 (raise_on_fail=True일 때만)."""


def get_api_key():
    load_dotenv(ENV_PATH)
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise MissingKeyError(".env.example을 .env로 복사하고 OPENAI_API_KEY에 키를 넣어 주세요.")
    return key


def make_client(timeout_seconds=LLM_TIMEOUT_SECONDS):
    """응답 대기 시간 제한과 '재시도 안 함'(max_retries=0)을 명시한다. 라이브러리 기본값이 바뀌어도 같게 동작하도록."""
    from openai import OpenAI

    # 응답 압축은 gzip만 받는다. 오래된 Brotli 패키지(1.0.x)가 깔린 컴퓨터에서 응답을 못 읽는 문제를 피한다.
    return OpenAI(api_key=get_api_key(), timeout=timeout_seconds, max_retries=0,
                  default_headers={"Accept-Encoding": "gzip, deflate"})


def openai_generate(prompt, timeout_seconds=LLM_TIMEOUT_SECONDS):
    import openai

    client = make_client(timeout_seconds)
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME, messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, reasoning_effort=REASONING_EFFORT)
    except openai.APITimeoutError as e:
        raise ServiceUnavailableError(f"AI 응답 시간 초과({timeout_seconds}초)") from e
    except openai.RateLimitError as e:
        raise QuotaExceededError("AI 사용 한도 초과, 잠시 후 다시 시도") from e
    except (openai.InternalServerError, openai.APIConnectionError) as e:
        raise ServiceUnavailableError(f"AI 서버 응답 없음({e!r})") from e
    return response.choices[0].message.content


def render(prompt_name, payload):
    template = (PROMPTS_DIR / f"{prompt_name}.md").read_text(encoding="utf-8")
    return template.replace("{{payload}}", json.dumps(payload, ensure_ascii=False, indent=2))


def parse(text, spec, check=None):
    """JSON을 읽고 필수 키, 목록 키, 허용 값, 금지 표현, 추가 확인(check)을 본다. 문제가 있으면 ValueError."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    for key in spec["required"]:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"필수 키 없음: {key}")
    for key, (low, high) in spec.get("lists", {}).items():
        items = data.get(key)
        if (not isinstance(items, list) or not low <= len(items) <= high
                or not all(isinstance(i, str) and i.strip() for i in items)):
            raise ValueError(f"목록 키 형식 오류: {key}")
    for key, values in spec["allowed"].items():
        if data[key] not in values:
            raise ValueError(f"허용되지 않은 값: {key}={data[key]}")
    result = {key: data[key].strip() for key in spec["required"]}
    result.update({key: [i.strip() for i in data[key]] for key in spec.get("lists", {})})
    texts = [v for v in result.values() if isinstance(v, str)]
    texts += [i for v in result.values() if isinstance(v, list) for i in v]
    found = [p for p in BANNED_PHRASES if any(p in t for t in texts)]
    if found:
        raise ValueError(f"금지 표현: {found}")
    for key in spec["required"]:
        if key not in spec["allowed"] and key not in spec.get("plain", []):  # 분류 값(FOMO 등)이 아닌 문장만 검사
            check_polite(result[key])
    if check:
        check(result)
    return result


def validate(prompt_name, data, check=None):
    """이미 dict인 응답(시연용 저장 응답 등)을 AI 응답과 똑같은 규칙으로 검사한다."""
    return parse(json.dumps(data, ensure_ascii=False), SPECS[prompt_name], check)


def log_error(prompt_name, errors):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {prompt_name} "
                f"{json.dumps(errors, ensure_ascii=False)}\n")


def ask(prompt_name, payload, default=None, check=None, generate=None, timeout=None,
        raise_on_fail=False):
    """프롬프트를 채워 LLM에 묻고 dict를 돌려준다. 실패하면 기본 문구를 돌려준다.

    check: 결과 dict를 받아 문제가 있으면 ValueError를 내는 함수 (파싱 실패와 똑같이 재시도).
    timeout: 이번 호출만 다른 대기 시간(초)을 쓸 때.
    raise_on_fail: 기본 문구 대신 AnswerRejectedError를 낸다 (시연 모드가 저장 응답으로 바꾸도록)."""
    if generate is None:
        def generate(text):
            return openai_generate(text, timeout or LLM_TIMEOUT_SECONDS)
    spec = SPECS[prompt_name]
    prompt = render(prompt_name, payload)
    errors = []
    for _ in range(2):
        try:
            text = generate(prompt)
        except LLMError:
            raise
        except Exception as e:  # 네트워크 등: 재시도하지 않고 기본 문구
            errors.append(f"호출 실패: {e!r}")
            break
        try:
            return parse(text, spec, check)
        except (ValueError, TypeError) as e:
            errors.append(f"{e} | 응답: {str(text)[:300]}")
    log_error(prompt_name, errors)
    if raise_on_fail:
        raise AnswerRejectedError("; ".join(errors))
    return dict(default if default is not None else spec["default"])
