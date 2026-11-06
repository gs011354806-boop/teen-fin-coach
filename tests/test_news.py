"""22번 이번 주 금융 뉴스: 후보 걸러내기, AI 결과 검사, 저장, 퀴즈 포인트, 화면 (네트워크 없이)."""

from datetime import datetime

import pandas as pd
import pytest

from conftest import open_app
from engine import news, rewards, store

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=news.KST)
TICKERS = ["삼성전자", "카카오"]


def item(title, description="설명이에요", day="Thu, 05 Nov 2026 09:00:00 +0900", link="https://www.yna.co.kr/a"):
    return {"title": title, "description": description, "pubDate": day, "link": link, "originallink": link}


def fake_fetch(results):
    return lambda query, keys: results.get(query, [])


def test_candidates_filter_old_blocked_duplicate_and_tickers():
    results = {"청소년 금융": [item("<b>청소년</b> 금융교육 &quot;확대&quot;", "학교 200곳에서 시작해요"),
                               item("청소년 금융교육 확대", day="Thu, 05 Nov 2026 08:00:00 +0900"),  # 같은 제목
                               item("지난달 뉴스", day="Mon, 20 Oct 2026 09:00:00 +0900"),            # 7일 지남
                               item("이 테마주 급등주 모음"),                                          # 투자 권유
                               item("삼성전자 실적 발표")],                                            # 종목 이름
               "금융사기 예방": [item("10대 노린 중고거래 사기 주의", "피해 1,200건")]}
    cands = news.candidates(NOW, TICKERS, keys=("id", "secret"), fetch_fn=fake_fetch(results))
    assert [c["title"] for c in cands] == ['청소년 금융교육 "확대"', "10대 노린 중고거래 사기 주의"]
    assert [c["id"] for c in cands] == ["n1", "n2"] and cands[0]["press"] == "yna.co.kr"


def test_missing_keys(monkeypatch, tmp_path):
    import importlib
    real_get_keys = importlib.reload(news).get_keys  # conftest가 막아 둔 get_keys 대신 실제 함수로 확인
    monkeypatch.setattr(news, "ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    with pytest.raises(news.NewsError):
        real_get_keys()


def test_week_id_and_range():
    assert news.week_id(NOW) == "2026-W45" and news.week_range(NOW) == "11/2~11/8"


CANDS = [{"id": f"n{i}", "title": t, "description": d, "link": "l", "originallink": "o", "press": "p", "date": "2026-11-05"}
         for i, (t, d) in enumerate([("청소년 금융교육 확대", "학교 200곳에서 시작"), ("중고거래 사기 주의", "피해 1,200건"),
                                     ("예금 금리 변화", "연 3.5% 상품 등장"), ("용돈 앱 인기", "설명")], start=1)]


def good_result():
    r = {}
    for i, nid in enumerate(["n1", "n2", "n3"], start=1):
        r.update({f"card{i}_news_id": nid, f"card{i}_headline": "쉬운 제목", f"card{i}_summary": "요약이에요.",
                  f"card{i}_why": "이번 주에 확인해 봐요.", f"card{i}_concept": "GOAL_SAVING"})
        r.update({f"q{i}": "무엇일까요?", f"q{i}_options": ["가", "나", "다"], f"q{i}_answer": str(i)})
    r["card2_summary"] = "피해가 1,200건이었어요."
    return r


def test_cards_check_accepts_good_and_rejects_bad():
    concepts = store.load_concepts()
    check = news.cards_check(CANDS, concepts, TICKERS)
    check(good_result())
    for bad in ({"card1_news_id": "n9"}, {"card2_news_id": "n1"},                 # 없는 뉴스 / 같은 뉴스
                {"card1_summary": "학교 300곳이에요."},                          # 뉴스에 없는 숫자
                {"card3_concept": "SOMETHING"},                                  # 없는 개념
                {"card1_why": "삼성전자를 살펴봐요."},                            # 종목 이름
                {"q1_options": ["가", "가", "다"]}):
        with pytest.raises(ValueError):
            check({**good_result(), **bad})


def test_build_save_load_latest(tmp_path):
    doc = news.build(good_result(), CANDS, NOW)
    assert doc["week"] == "2026-W45" and len(doc["cards"]) == 3 and doc["quiz"][2]["answer"] == 3
    assert doc["cards"][1]["news"]["title"] == "중고거래 사기 주의"
    news.save(doc, tmp_path / "news_2026-W45.json")
    assert news.load("2026-W45", tmp_path) == doc and news.latest(tmp_path) == doc
    assert news.load("2026-W46", tmp_path) is None


def test_news_points_once_per_week():
    student = next(s for s in store.load_students() if s["student_id"] == "S03")
    quiz = pd.DataFrame([{"student_id": "S03", "week": "2026-W45", "date": "2026-10-04"},
                         {"student_id": "S03", "week": "2026-W45", "date": "2026-10-04"},
                         {"student_id": "S03", "week": "2026-W46", "date": "2026-10-04"}])
    events = rewards.earn_events(student, pd.DataFrame(columns=store.TRADE_COLUMNS),
                                 pd.DataFrame(columns=store.MISSION_COLUMNS), store.load_allowance(), None, quiz)
    assert [e["points"] for e in events if e["kind"] == "뉴스 퀴즈"] == [50, 50]


@pytest.fixture
def news_env(tmp_path, monkeypatch):
    monkeypatch.setattr(news, "NEWS_DIR", tmp_path)
    monkeypatch.setattr(news, "now_kst", lambda: NOW)
    path = tmp_path / "news_quiz.csv"
    path.write_text("student_id,week,date\n", encoding="utf-8")
    monkeypatch.setattr(store, "NEWS_QUIZ_PATH", path)
    return tmp_path


def test_page_without_keys_and_without_saved_news(news_env, monkeypatch):
    monkeypatch.setattr(news, "get_keys", lambda: (_ for _ in ()).throw(news.NewsError("키 없음")))
    at = open_app("pages/12_이번_주_금융_뉴스.py")
    assert not at.exception, at.exception
    assert any("아직 카드뉴스가 없어요" in i.value for i in at.info)


def test_page_shows_saved_news_and_gives_points_once(news_env):
    news.save(news.build(good_result(), CANDS, NOW))
    at = open_app("pages/12_이번_주_금융_뉴스.py")
    assert not at.exception, at.exception
    assert "쉬운 제목" in " ".join(m.value for m in at.markdown)
    for i in range(3):
        at.radio[i].set_value(i)  # 정답은 1, 2, 3번
    at = at.run()
    assert any("50P를 받았어요" in s.value for s in at.success)
    assert len(store.load_news_quiz(store.NEWS_QUIZ_PATH)) == 1
    at = at.run()
    assert len(store.load_news_quiz(store.NEWS_QUIZ_PATH)) == 1
    assert any("이미 받았어요" in s.value for s in at.success)
