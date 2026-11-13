"""21번 자산 키우기 게임: 단어·출제·코인·복습·AI 검사·화면."""

import pytest

from conftest import open_app
from engine import detect, game, store

PAGE = "pages/11_자산_키우기_게임.py"


def test_every_word_links_to_existing_concept_and_is_short():
    concepts = store.load_concepts()
    assert all(w["concept"] in concepts for w in game.BY_WORD.values())
    assert sum(w["good"] for w in game.BY_WORD.values()) == 13 and len(game.BY_WORD) == 25
    assert all(len(w.replace(" ", "")) <= 8 for w in game.BY_WORD)
    names = set(store.load_ticker_names().values())
    assert not any(n in w for w in game.BY_WORD for n in names)  # 종목 이름 없음


def test_deck_is_balanced_deterministic_and_boosted():
    a = game.deck(["DIVERSIFICATION"], "S01-1")
    assert a == game.deck(["DIVERSIFICATION"], "S01-1")
    assert sum(w["good"] for w in a) == game.DECK_SIZE // 2
    plain = game.deck([], "x", size=4000)
    boosted = game.deck(["DIVERSIFICATION"], "x", size=4000)
    share = lambda d: sum(game.BY_WORD[w["word"]]["concept"] == "DIVERSIFICATION" for w in d)
    assert share(boosted) > share(plain) * 1.5


def test_boost_follows_repeated_mistakes():
    students = {s["student_id"]: s for s in store.load_students()}
    args = (store.load_trades(), store.load_prices(), store.load_allowance())
    assert "DIVERSIFICATION" in game.boost_concepts(students["S01"], *args)  # 몰빵형 민지
    assert "GOAL_SAVING" in game.boost_concepts(students["S02"], *args)      # 저축 실패형 준호
    assert game.boost_concepts(students["S03"], *args) == []                 # 균형형 서연


def test_coins_summary_and_review():
    r = game.summary(["분산투자", "몰빵", "복리", "몰빵", "없는 단어"], ["비상금", "몰빵"])
    assert r["coins"] == 10000 + 1000 * 2 - 1500 * 2
    assert r["good"] == ["분산투자", "복리"] and r["bad"] == {"몰빵": 2}
    assert r["missed"] == ["비상금"]  # 나쁜 단어는 놓쳐도 '놓침'이 아니다
    assert game.summary(["복리"], ["복리", "비상금"])["missed"] == ["비상금"]  # 한 번이라도 받았으면 놓침 아님
    assert not r["passed"] and r["review"] == ["DIVERSIFICATION", "EMERGENCY_FUND"]
    assert game.summary(["복리"] * 5, [])["passed"]


def test_facts_link_game_and_real_behavior():
    minji = next(s for s in store.load_students() if s["student_id"] == "S01")
    facts = game.facts(game.summary(["몰빵", "몰빵"], []), detect.detect(store.load_trades(), store.load_prices(), minji))
    assert "나쁜 습관 '몰빵'을 2번 받았어요." in facts
    assert any("비중이" in f for f in facts)


def test_quiz_check_rejects_new_numbers_and_same_answers():
    concept = store.load_concepts()["DIVERSIFICATION"]
    check = game.quiz_check(concept)
    ok = {"q1": "분산투자는 무엇일까요?", "q1_options": ["나눠 담기", "몰아 담기", "안 담기"], "q1_answer": "1",
          "q2": "한 곳에 문제가 생기면 어떻게 될까요?", "q2_options": ["전체가 덜 흔들려요", "다 잃어요", "두 배"], "q2_answer": "2"}
    check(ok)
    with pytest.raises(ValueError):
        check({**ok, "q2_answer": "1"})
    with pytest.raises(ValueError):
        check({**ok, "q1_options": ["30% 넣기", "몰아 담기", "안 담기"]})
    assert game.ai_quiz_items({"q1": ""}) == []
    assert game.card_quiz(concept)["answer"] in (1, 2, 3)


@pytest.fixture
def reviews(tmp_path, monkeypatch):
    path = tmp_path / "game_reviews.csv"
    path.write_text("student_id,date,concept\n", encoding="utf-8")
    monkeypatch.setattr(store, "GAME_REVIEWS_PATH", path)
    return path


def test_page_waits_for_game_then_shows_review_after_low_score(reviews, monkeypatch):
    import config

    monkeypatch.setattr(config, "ISLAND_GAME", False)  # 2026-11-13부터 기본은 자산섬. 예전 게임은 스위치를 끄면 나온다
    at = open_app(PAGE)
    assert not at.exception, at.exception
    assert not at.metric  # 게임 결과 전에는 결과가 없다
    state = at.session_state["game-S01"]
    state["result"] = game.summary(["몰빵", "몰빵"], ["비상금"])
    state["coach"] = "테스트 한마디예요."
    state["quiz"] = [game.card_quiz(store.load_concepts()["DIVERSIFICATION"])]
    at = at.run()
    assert at.metric[0].value == "🪙 7,000"
    retry = next(b for b in at.button if b.label == "다시 도전")
    assert retry.disabled  # 복습 문제를 맞히기 전에는 다시 도전 못 함
    at.radio[0].set_value(state["quiz"][0]["answer"] - 1).run()
    assert not next(b for b in at.button if b.label == "다시 도전").disabled
    assert any("30P를 받았어요" in m.value for m in at.success)
    saved = store.load_game_reviews(reviews)
    assert list(saved["concept"]) == ["DIVERSIFICATION"] and len(saved) == 1
    at.run()  # 다시 그려도 두 번 기록하지 않는다
    assert len(store.load_game_reviews(reviews)) == 1


def test_review_points_once_per_concept_per_day_and_capped():
    import pandas as pd
    from engine import rewards

    student = next(s for s in store.load_students() if s["student_id"] == "S03")
    empty_trades = pd.DataFrame(columns=store.TRADE_COLUMNS)
    empty_missions = pd.DataFrame(columns=store.MISSION_COLUMNS)
    reviews = pd.DataFrame([{"student_id": "S03", "date": "2026-10-02", "concept": "DIVERSIFICATION"},
                            {"student_id": "S03", "date": "2026-10-02", "concept": "DIVERSIFICATION"},
                            {"student_id": "S03", "date": "2026-10-02", "concept": "FOMO"},
                            {"student_id": "S01", "date": "2026-10-02", "concept": "FOMO"}])
    events = rewards.earn_events(student, empty_trades, empty_missions, store.load_allowance(), reviews)
    review_events = [e for e in events if e["kind"] == "복습"]
    assert [e["points"] for e in review_events] == [30, 30]
    assert review_events[0]["label"] == "1분 복습 완료: 분산투자"
    many = pd.DataFrame([{"student_id": "S03", "date": "2026-10-02", "concept": c}
                         for c in store.load_concepts()])  # 10개 → 하루 상한 200P
    granted = rewards.apply_daily_cap(rewards.earn_events(student, empty_trades, empty_missions,
                                                          store.load_allowance(), many))
    assert sum(e["granted"] for e in granted if e["kind"] == "복습") == rewards.DAILY_CAP
