"""18번 금융 개념 물어보기: 개념 카드 안에서만 답하는지."""

import pytest

from conftest import open_app
from engine import concept_qa, store
from llm import client

PAGE = "pages/7_개념_물어보기.py"
CONCEPTS = store.load_concepts()
CHECK = concept_qa.answer_check(CONCEPTS)


def test_payload_has_only_card_text():
    p = concept_qa.payload("복리가 뭐예요?", CONCEPTS)
    assert {c["id"] for c in p["concepts"]} == set(CONCEPTS)
    assert p["special_ids"] == ["NONE", "ADVICE"]


def test_check_accepts_card_numbers_and_special_ids():
    CHECK({"concept": "COMPOUND_INTEREST", "answer": "100,000원을 연 5% 복리로 3년 두면 115,762원이 돼요."})
    CHECK({"concept": "NONE", "answer": "아직 없어요."})
    CHECK({"concept": "ADVICE", "answer": "정해 드릴 수 없어요."})


@pytest.mark.parametrize("bad", [{"concept": "TAX", "answer": "세금이에요."},
                                 {"concept": "COMPOUND_INTEREST", "answer": "연 10% 복리면 두 배가 돼요."}])
def test_check_rejects_unknown_concept_or_new_numbers(bad):
    with pytest.raises(ValueError):
        CHECK(bad)


def test_every_example_is_short():
    assert all(len(e) <= concept_qa.MAX_QUESTION_CHARS for e in concept_qa.EXAMPLES)


@pytest.fixture
def answers(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "QUESTIONS_PATH", tmp_path / "concept_questions.csv")
    replies = {"복리가 뭐예요?": {"concept": "COMPOUND_INTEREST", "answer": "이자에도 이자가 붙는 원리예요."},
               "삼성전자 사도 돼요?": {"concept": "ADVICE", "answer": "정해 드릴 수 없어요."},
               "주식 세금은 얼마예요?": {"concept": "NONE", "answer": "카드에 없어요."}}

    def ask(name, payload, default=None, check=None, **kw):
        result = replies[payload["question"]]
        check(result)
        return result

    monkeypatch.setattr(client, "ask", ask)


def ask_on_page(at, question):
    at.text_input[0].set_value(question)
    next(b for b in at.button if b.label == "물어보기").click()
    at = at.run()
    assert not at.exception, at.exception
    return at


def test_answer_shows_source_card_and_is_logged(answers):
    at = open_app(PAGE)
    next(b for b in at.button if b.label == "복리가 뭐예요?").click()  # 예시 질문 버튼
    at = at.run()
    assert any("이자에도 이자가" in i.value for i in at.info)
    assert any("출처: 개념 카드 · 복리" in m.value for m in at.markdown)
    log = store.load_questions()
    assert list(log["concept"]) == ["COMPOUND_INTEREST"] and log.iloc[0]["question"] == "복리가 뭐예요?"


def test_advice_question_gets_fixed_text(answers):
    at = ask_on_page(open_app(PAGE), "삼성전자 사도 돼요?")
    assert any(concept_qa.ADVICE_TEXT in i.value for i in at.info)
    assert not any("정해 드릴 수 없어요." in i.value for i in at.info)  # AI 문장 대신 고정 문구


def test_unknown_topic_says_no_content(answers):
    at = ask_on_page(open_app(PAGE), "주식 세금은 얼마예요?")
    assert any("아직 준비된 내용이 없어요" in w.value for w in at.warning)
    assert list(store.load_questions()["concept"]) == ["NONE"]


def test_home_has_floating_coach_button():
    """2026-11-24: 개념 물어보기는 홈 메뉴 대신 모든 화면 오른쪽 아래의 AI 코치 버튼(채팅 창)으로 연다."""
    at = open_app()
    assert any(b.key == "coach-fab-btn" for b in at.button)
    assert not any(link.proto.label == "개념 물어보기" for link in at.get("page_link"))


def test_coach_chat_answers_from_concept_cards(answers):
    """채팅 창도 개념 물어보기와 같은 규칙: 개념 카드 안에서만 답하고 기록을 남긴다."""
    import ui_common as ui
    from streamlit.testing.v1 import AppTest

    def app():
        import streamlit as st
        import ui_common as ui
        ui.ask_concept("S01", "복리가 뭐예요?")
        concepts = __import__("engine.store", fromlist=["load_concepts"]).load_concepts()
        answer, note = ui.coach_reply(ui.concept_chat("S01")[-1], concepts)
        st.write(answer)
        st.write(note)

    at = AppTest.from_function(app).run()
    assert not at.exception, at.exception
    assert any("이자에도 이자가" in m.value for m in at.markdown)
    assert any("출처: 개념 카드 · 복리" in m.value for m in at.markdown)
    assert list(store.load_questions()["concept"]) == ["COMPOUND_INTEREST"]


def test_dashboard_has_no_coach_button():
    at = open_app("pages/9_효과_측정.py")
    assert not any(b.key == "coach-fab-btn" for b in at.button)
