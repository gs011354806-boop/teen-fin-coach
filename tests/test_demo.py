"""시연 모드 검증: 저장 응답 파일이 규칙을 지키는지, AI가 실패하면 화면이 저장 응답으로 넘어가는지."""

import json
import re

import pytest

from conftest import open_app
from engine import store
from llm import client

LESSON = "pages/3_실수에서_배우기.py"
MISSION = "pages/4_이번_주_미션.py"

DEMO = {"students": {"S01": {
    "answers": {"T0014": "큰 회사라서 계속 오를 것 같았어요."},
    "followup_answers": {"T0014": "틀릴 수도 있다는 생각은 안 해 봤어요."},
    "responses": {
        "mistake_question": {"T0014": {"question": "민지 님, 이번에는 어떤 근거로 사셨나요?"}},
        "followup_question": {"T0014": {"question": "큰 회사라서 오를 거라고 보셨네요. 틀릴 수도 있다면 어떤 경우일까요?"}},
        "classify_mistake": {"T0014": {"error_type": "과신", "reason": "오를 거라고 굳게 믿으셨어요."}},
        "explain_concept": {"T0014|과신": {"explanation": "저장된 설명이에요.",
                                          "next_try": "틀릴 수 있는 이유를 먼저 적어 보세요."}},
        "diagnose_week": {"2026-09-07": {"good": ["꾸준히 모으기"], "practice": ["근거 없는 매수"],
                                         "summary": "저장된 진단이에요."}},
    },
}}}


# --- 실제 저장 응답 파일 ---

def saved_file():
    if not store.DEMO_PATH.exists():
        pytest.skip("demo_responses.json 없음 (python data/make_demo_responses.py로 만든다)")
    return store.load_demo()


def test_saved_responses_follow_the_same_rules_as_ai():
    for student_id, entry in saved_file()["students"].items():
        for prompt_name, by_key in entry["responses"].items():
            for key, response in by_key.items():
                client.validate(prompt_name, response)  # 존댓말·금지 표현·허용 값


def test_saved_mission_texts_keep_goal_numbers():
    for entry in saved_file()["students"].values():
        for phrase, response in entry["responses"].get("weekly_mission", {}).items():
            for number in re.findall(r"\d[\d,]*(?:%|원|자)", phrase):
                assert number in response["text"], (phrase, response["text"])


def test_saved_keys_match_data():
    data = saved_file()["students"]["S01"]
    trade_ids = set(store.load_trades()["trade_id"])
    assert set(data["answers"]) <= trade_ids
    assert set(data["responses"]["mistake_question"]) <= trade_ids
    assert set(data["responses"]["classify_mistake"]) <= set(data["answers"])


# --- 화면: AI가 실패하면 시연 모드는 저장 응답, 아니면 멈춤 ---

@pytest.fixture
def failing_ai(tmp_path, monkeypatch):
    """AI는 항상 한도 초과. 저장 응답과 기록 파일은 임시 파일로."""
    path = tmp_path / "demo_responses.json"
    path.write_text(json.dumps(DEMO, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(store, "DEMO_PATH", path)
    monkeypatch.setattr(store, "LESSONS_PATH", tmp_path / "lessons.csv")
    monkeypatch.setattr(store, "RULES_PATH", tmp_path / "rules.csv")
    monkeypatch.setattr(store, "MISSIONS_PATH", tmp_path / "missions.csv")
    monkeypatch.setattr(store, "COACHING_PATH", tmp_path / "coaching_weeks.csv")
    calls = []

    def ask(name, payload, **kwargs):
        calls.append(kwargs)
        raise client.QuotaExceededError("429")

    monkeypatch.setattr(client, "ask", ask)
    return calls


def open_with_demo(page, on):
    at = open_app(page)
    at.session_state["demo_mode"] = on
    return at.run()


def click(at, label):
    next(b for b in at.button if b.label == label).click()
    at = at.run()
    assert not at.exception, at.exception
    return at


def test_demo_off_stops_with_notice(failing_ai):
    at = click(open_with_demo(LESSON, False), "AI 코치에게 질문 받기")
    assert any("한도 초과" in w.value for w in at.warning)
    assert not at.info  # 질문이 나오지 않음


def test_demo_on_lesson_uses_saved_responses(failing_ai):
    at = click(open_with_demo(LESSON, True), "AI 코치에게 질문 받기")
    assert any("어떤 근거로 사셨나요" in i.value for i in at.info)
    assert failing_ai[-1]["timeout"] and failing_ai[-1]["raise_on_fail"]  # 짧게 기다리고 실패를 알림

    assert at.text_area[0].value == "큰 회사라서 계속 오를 것 같았어요."  # 예시 답이 미리 채워짐
    at = click(at, "답하기")
    assert any("틀릴 수도 있다면" in i.value for i in at.info)  # 저장된 꼬리 질문
    assert at.text_area[0].value == "틀릴 수도 있다는 생각은 안 해 봤어요."
    at = click(at, "답하기")
    text = " ".join(m.value for m in at.markdown)
    assert "과신" in text and "저장된 설명이에요." in text


def test_demo_on_other_answer_does_not_use_saved_classification(failing_ai):
    at = click(open_with_demo(LESSON, True), "AI 코치에게 질문 받기")
    at.text_area[0].set_value("유튜브에서 좋다고 해서요")
    at = click(at, "답하기")
    assert any(client.SPECS["followup_question"]["default"]["question"] in i.value for i in at.info)
    at.text_area[0].set_value("잘 모르겠어요")
    at = click(at, "답하기")
    text = " ".join(m.value for m in at.markdown)
    assert "과신" not in text  # 답이 다르면 저장된 분류를 쓰지 않고 기본 문구
    assert "이때 보인 모습을 함께 살펴봐요." in text


@pytest.mark.usefixtures("legacy_mission_tab")
def test_demo_on_mission_uses_saved_diagnosis(failing_ai):
    at = click(open_with_demo(MISSION, True), "1주차 (9/7~9/13) 기록으로 진단 받기")
    assert any("저장된 진단이에요." in m.value for m in at.markdown)
    at = click(at, "미션 받기")  # 저장 응답이 없는 미션 문장 → 코드가 만든 기본 문장
    assert any("10자" in s.value for s in at.success)


def test_demo_on_without_saved_falls_back_to_default(failing_ai):
    at = open_app(LESSON)
    at.session_state["demo_mode"] = True
    at.sidebar.selectbox[0].select("준호 (중3)")  # 준호는 저장 응답이 없다
    at = click(at.run(), "AI 코치에게 질문 받기")
    assert any(client.SPECS["mistake_question"]["default"]["question"] in i.value for i in at.info)
