"""23-1번 쓰기 봉투 내 소비 퀴즈: 문제는 내 지출로 코드가 만들고, 모두 맞히면 하루 1번 30P."""

import pandas as pd
import pytest

from conftest import open_app
from engine import envelope, rewards, spend_quiz, store

DAY = "2026-10-03"


@pytest.fixture
def allowance():
    return store.load_allowance()


@pytest.mark.parametrize("student_id", ["S01", "S02", "S03"])
def test_five_questions_from_own_spending(allowance, student_id):
    questions = spend_quiz.daily_questions(allowance, student_id, DAY)
    assert len(questions) == spend_quiz.QUIZ_SIZE
    assert len({q["question"] for q in questions}) == spend_quiz.QUIZ_SIZE  # 같은 문제 두 번 없음
    for q in questions:
        assert q["answer"] in q["options"] and len(q["options"]) == len(set(q["options"])) >= 3


def test_same_day_same_questions_other_day_can_differ(allowance):
    first = spend_quiz.daily_questions(allowance, "S01", DAY)
    assert first == spend_quiz.daily_questions(allowance, "S01", DAY)
    days = {tuple(q["question"] for q in spend_quiz.daily_questions(allowance, "S01", f"2026-10-{d:02d}"))
            for d in range(1, 15)}
    assert len(days) > 1


def test_answers_are_computed_from_data(allowance):
    spent = envelope.spending(allowance, "S02")
    by_category = envelope.spending_by_category(allowance, "S02")
    import random
    top = spend_quiz.q_top_category(spent, by_category, random.Random(0))
    assert top["answer"] == spend_quiz.CATEGORY_LABELS[next(iter(by_category))]
    count = spend_quiz.q_count(spent, by_category, random.Random(0))
    assert count["answer"] == f"{len(spent)}번"
    biggest = spend_quiz.q_biggest(spent, by_category, random.Random(0))
    assert biggest["answer"] == spent.loc[spent["amount"].idxmin(), "memo"]


def test_no_spending_no_questions():
    empty = pd.DataFrame(columns=["tx_id", "student_id", "date", "envelope", "amount", "category", "memo"])
    assert spend_quiz.daily_questions(empty, "S01", DAY) == []


def test_all_correct():
    qs = [{"answer": "a"}, {"answer": "b"}]
    assert spend_quiz.all_correct(qs, ["a", "b"])
    assert not spend_quiz.all_correct(qs, ["a", None])
    assert not spend_quiz.all_correct([], [])


def test_points_once_per_day(allowance):
    student = next(s for s in store.load_students() if s["student_id"] == "S01")
    empty_trades = pd.DataFrame(columns=store.TRADE_COLUMNS)
    empty_missions = store.load_missions().iloc[0:0]
    records = pd.DataFrame([{"student_id": "S01", "date": DAY}, {"student_id": "S01", "date": DAY},
                            {"student_id": "S02", "date": DAY}])
    events = rewards.earn_events(student, empty_trades, empty_missions, allowance, spend_quiz=records)
    quiz = [e for e in events if e["kind"] == "소비 퀴즈"]
    assert len(quiz) == 1 and quiz[0]["points"] == rewards.SPEND_QUIZ_POINTS and quiz[0]["capped"]


def test_page_quiz_rewards_once(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "SPEND_QUIZ_PATH", tmp_path / "spend_quiz.csv")
    at = open_app("pages/2_용돈봉투.py", query={"env": "SPEND"})
    assert not at.exception
    day = envelope.latest_date(store.load_allowance())
    questions = spend_quiz.daily_questions(store.load_allowance(), "S01", day)
    for i, q in enumerate(questions, start=1):
        at.radio(key=f"spend-quiz-S01-{day}-{i}").set_value(q["answer"])
    at.run()
    assert not at.exception
    assert any("모두 맞혔어요" in s.value for s in at.success)
    assert len(store.load_spend_quiz()) == 1
    at.run()  # 다시 그려도 한 번 더 쌓이지 않는다
    assert len(store.load_spend_quiz()) == 1
