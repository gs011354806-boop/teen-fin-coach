"""5-1: Mistake-to-Lesson 기록 저장·불러오기 검증."""

from pathlib import Path

from conftest import open_app

from engine import store

ROOT = Path(__file__).resolve().parent.parent
PAGE = "pages/3_실수에서_배우기.py"


def record(**overrides):
    base = {"student_id": "S01", "trade_id": "T0014", "date": "2026-10-02",
            "patterns": ["몰빵", "근거 없음"], "question": "어떤 근거로 샀나요?",
            "answer": "큰 회사라서,\n그냥 샀어요", "error_type": "근거 부족",
            "reason": "이유가 막연했어요.", "concept": "INVESTMENT_JOURNAL",
            "explanation": "근거를 적어 두면 돌아볼 수 있어요.", "next_try": "사기 전에 이유를 적어요."}
    return {**base, **overrides}


def test_missing_file_is_empty(tmp_path):
    lessons = store.load_lessons(tmp_path / "lessons.csv")
    assert len(lessons) == 0 and list(lessons.columns) == store.LESSON_COLUMNS


def test_append_and_load_round_trip(tmp_path):
    path = tmp_path / "lessons.csv"
    first = store.append_lesson(record(), path=path)
    second = store.append_lesson(record(trade_id="T0010", patterns=["몰빵"]), path=path)

    lessons = store.load_lessons(path)
    assert (first, second) == ("L0001", "L0002")
    assert list(lessons.columns) == store.LESSON_COLUMNS
    assert lessons.iloc[0]["patterns"] == ["몰빵", "근거 없음"]
    assert lessons.iloc[1]["patterns"] == ["몰빵"]
    assert lessons.iloc[0]["answer"] == "큰 회사라서, 그냥 샀어요"  # 쉼표 유지, 줄바꿈은 공백


def test_append_to_header_only_file(tmp_path):
    path = tmp_path / "lessons.csv"
    path.write_text(",".join(store.LESSON_COLUMNS) + "\n", encoding="utf-8")
    assert store.append_lesson(record(), path=path) == "L0001"
    assert len(store.load_lessons(path)) == 1


def test_page_shows_saved_lesson_after_restart(tmp_path, monkeypatch):
    """앱을 새로 켠 것처럼 빈 세션으로 열어도 저장된 기록이 보인다."""
    path = tmp_path / "lessons.csv"
    store.append_lesson(record(), path=path)
    monkeypatch.setattr(store, "LESSONS_PATH", path)
    monkeypatch.setattr(store, "RULES_PATH", tmp_path / "rules.csv")

    at = open_app(PAGE)

    assert not at.exception
    assert at.main.selectbox[0].value == "T0014"  # 가장 최근 실수 매수
    assert "돌아봄" in at.main.selectbox[0].options[0]
    assert any("어떤 근거로 샀나요?" in i.value for i in at.info)
    assert any("근거 부족" in m.value for m in at.markdown)
    assert [b.label for b in at.button] == ["규칙 정하기", "다시 답해 보기"]  # 16번: 아직 규칙 없음


def test_page_without_saved_lesson_starts_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LESSONS_PATH", tmp_path / "lessons.csv")
    at = open_app(PAGE)
    assert not at.exception
    assert [b.label for b in at.button] == ["AI 코치에게 질문 받기"]


# --- 16번 대화형 후속 질문 + 나만의 규칙 ---

import pytest  # noqa: E402

from engine import detect  # noqa: E402
from llm import client  # noqa: E402


def test_old_lesson_file_without_followup_columns_still_loads(tmp_path):
    path = tmp_path / "lessons.csv"
    old = [c for c in store.LESSON_COLUMNS if not c.startswith("followup")]
    path.write_text(",".join(old) + "\n", encoding="utf-8")
    store.append_lesson({**record(), "followup_question": "왜요?", "followup_answer": "몰라요"}, path=path)
    lessons = store.load_lessons(path)
    assert list(lessons.columns) == store.LESSON_COLUMNS and lessons.iloc[0]["followup_answer"] == "몰라요"


def test_rules_round_trip_and_latest_matching(tmp_path):
    path = tmp_path / "rules.csv"
    store.append_rule({"student_id": "S01", "date": "2026-10-02", "trade_id": "T0009",
                       "patterns": ["급등 추격"], "rule": "급등한 날은 하루 기다리기"}, path=path)
    store.append_rule({"student_id": "S01", "date": "2026-10-02", "trade_id": "T0014",
                       "patterns": ["몰빵", "근거 없음"], "rule": "한 종목은 절반까지만"}, path=path)
    rules = store.load_rules(path)
    assert list(rules["rule_id"]) == ["U0001", "U0002"]
    assert detect.latest_rule(rules, "S01", ["급등 추격"]) == "급등한 날은 하루 기다리기"
    assert detect.latest_rule(rules, "S01", ["근거 없음", "급등 추격"]) == "한 종목은 절반까지만"
    assert detect.latest_rule(rules, "S02", ["몰빵"]) is None


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LESSONS_PATH", tmp_path / "lessons.csv")
    monkeypatch.setattr(store, "RULES_PATH", tmp_path / "rules.csv")
    calls = []

    def ask(name, payload, default=None, check=None, **kw):
        calls.append((name, payload))
        answers = {"mistake_question": {"question": "어떤 근거로 사셨나요?"},
                   "followup_question": {"question": "오를 거라고 보셨네요. 무엇을 확인했다면 달라졌을까요?"},
                   "classify_mistake": {"error_type": "과신", "reason": "확신이 컸어요."},
                   "explain_concept": {"explanation": "설명이에요.", "next_try": "틀릴 이유도 적어요."}}
        return answers[name]

    monkeypatch.setattr(client, "ask", ask)
    return calls


def press(at, label):
    next(b for b in at.button if b.label == label).click()
    at = at.run()
    assert not at.exception, at.exception
    return at


def test_followup_then_classify_with_both_answers_then_rule(chat):
    at = press(open_app(PAGE), "AI 코치에게 질문 받기")
    at.text_area[0].set_value("계속 오를 것 같아서요")
    at = press(at, "답하기")
    assert any("무엇을 확인했다면" in i.value for i in at.info)
    assert [n for n, _ in chat][-1] == "followup_question"
    assert len(store.load_lessons()) == 0  # 꼬리 질문에 답하기 전엔 저장 안 함

    at.text_area[0].set_value("뉴스를 한 번 찾아봤으면 좋았을 것 같아요")
    at = press(at, "답하기")
    classify = next(p for n, p in chat if n == "classify_mistake")
    assert classify["followup_answer"] == "뉴스를 한 번 찾아봤으면 좋았을 것 같아요"
    saved = store.load_lessons().iloc[0]
    assert saved["followup_question"].startswith("오를 거라고") and saved["error_type"] == "과신"

    at.text_input[0].set_value("짧음")
    at = press(at, "규칙 정하기")
    assert at.error and len(store.load_rules()) == 0  # 공백 빼고 5자 미만
    at.text_input[0].set_value("사기 전에 뉴스 하나 확인하기")
    at = press(at, "규칙 정하기")
    rules = store.load_rules()
    assert list(rules["rule"]) == ["사기 전에 뉴스 하나 확인하기"] and rules.iloc[0]["trade_id"] == "T0014"
    assert any("나만의 규칙: 사기 전에 뉴스 하나 확인하기" in s.value for s in at.success)


def test_rule_shows_up_in_precheck(chat, tmp_path, monkeypatch):
    trades = tmp_path / "trades.csv"
    trades.write_text(store.TRADES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(store, "TRADES_PATH", trades)
    monkeypatch.setattr(store, "PRECHECK_PATH", tmp_path / "prechecks.csv")
    store.append_rule({"student_id": "S01", "date": "2026-10-02", "trade_id": "T0014",
                       "patterns": ["몰빵"], "rule": "한 종목은 절반까지만 담기"})
    monkeypatch.setattr(client, "ask", lambda name, payload, default=None, check=None, **kw:
                        chat.append((name, payload)) or {"question": "정한 규칙과 맞는지 생각해 볼까요?"})
    at = open_app("pages/1_가상_주식시장.py")
    at.number_input[0].set_value(2)
    at = press(at, "주문 넣기")
    assert any("지난번에 정한 나만의 규칙: 한 종목은 절반까지만 담기" in s.value for s in at.success)
    assert chat[-1][1]["my_rule"] == "한 종목은 절반까지만 담기"
