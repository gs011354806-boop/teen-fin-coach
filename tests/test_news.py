"""22번 이번 주 금융 뉴스: 후보 걸러내기, AI 결과 검사, 저장, 퀴즈 포인트, 화면 (네트워크 없이)."""

from datetime import datetime

import pandas as pd
import pytest

from conftest import open_app
from engine import news, rewards, store

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=news.KST)
TICKERS = ["삼성전자", "카카오"]


def item(title, body="본문이에요", ministry="금융위원회", approved="11/05/2026 09:00:00"):
    return {"title": title, "subtitle": "", "body": body, "ministry": ministry,
            "link": "https://www.korea.kr/a", "approved": approved}


def fake_fetch(items_by_start):
    return lambda start, end, key: items_by_start.get(start, [])


def test_candidates_keep_finance_and_filter_blocked_duplicate_and_tickers():
    results = {"20261104": [item("청소년 금융교육 확대", "학교 200곳에서 시작해요"),
                            item("청소년 금융교육 확대", approved="11/04/2026 08:00:00"),       # 같은 제목
                            item("문화 축제 개최", ministry="문화체육관광부"),                   # 금융과 무관
                            item("보이스피싱 예방 안내", ministry="경찰청"),                     # 부처는 달라도 금융 낱말
                            item("이 테마주 급등주 모음"),                                      # 투자 권유
                            item("삼성전자 지원 확대"),                                         # 종목 이름
                            {**item("예금 금리 안내"), "kogl": "3"},                             # 공공누리 제1유형 아님
                            item("금융 성착취 피해 지원")]}                                     # 청소년에 맞지 않는 주제
    cands = news.candidates(NOW, TICKERS, keys="key", fetch_fn=fake_fetch(results))
    assert [c["title"] for c in cands] == ["청소년 금융교육 확대", "보이스피싱 예방 안내"]
    assert cands[0]["press"] == "금융위원회" and cands[0]["date"] == "2026-11-05" and cands[0]["id"] == "n1"


def test_parse_items_and_api_error():
    ok = ("<response><header><resultCode>0</resultCode></header><body><NewsItem><Title>예금 금리 안내</Title>"
          "<DataContents><![CDATA[<p>본문&nbsp;내용</p>]]></DataContents><MinisterCode>금융위원회</MinisterCode>"
          "<OriginalUrl>https://www.korea.kr/x</OriginalUrl><ApproveDate>11/05/2026 10:00:00</ApproveDate>"
          "</NewsItem></body></response>").encode("utf-8")
    parsed = news.parse_items(ok)
    assert parsed[0]["title"] == "예금 금리 안내" and parsed[0]["body"] == "본문 내용"
    denied = b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>"
    with pytest.raises(news.NewsError):
        news.parse_items(denied)


def test_windows_cover_three_weeks_in_three_day_chunks():
    w = news.windows(NOW)
    assert len(w) == 7 and w[0] == ("20261104", "20261106") and w[-1] == ("20261017", "20261019")


def test_missing_keys(monkeypatch, tmp_path):
    import importlib
    real_get_keys = importlib.reload(news).get_keys  # conftest가 막아 둔 get_keys 대신 실제 함수로 확인
    monkeypatch.setattr(news, "ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
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
                  f"card{i}_tag": "물가", f"card{i}_highlight": "제목", f"card{i}_fact": "새 소식이 있어요",
                  f"card{i}_learn_highlight": "물가",
                  f"card{i}_learn": "물가가 오르면 같은 돈으로 살 수 있는 게 줄어요.",
                  f"card{i}_why": "이번 주에 확인해 봐요.", f"card{i}_concept": "GOAL_SAVING",
                  f"card{i}_art": "saving", f"card{i}_number": "없음"})
        r.update({f"q{i}": "무엇일까요?", f"q{i}_options": ["가", "나", "다"], f"q{i}_answer": str(i)})
    r["card2_summary"] = "피해가 1,200건이었어요."
    r["card2_number"] = "1,200건"
    return r


def test_cards_check_accepts_good_and_rejects_bad():
    concepts = store.load_concepts()
    check = news.cards_check(CANDS, concepts, TICKERS)
    check(good_result())
    for bad in ({"card1_news_id": "n9"}, {"card2_news_id": "n1"},                 # 없는 뉴스 / 같은 뉴스
                {"card1_summary": "학교 300곳이에요."},                          # 뉴스에 없는 숫자
                {"card3_concept": "SOMETHING"},                                  # 없는 개념
                {"card1_concept": "NONE", "card2_concept": "NONE", "card3_concept": "NONE"},  # 개념 연결이 하나도 없음
                {"card2_learn": "이자가 5% 늘어요."},                            # 배우는 금융에 뉴스 밖 숫자
                {"card1_number": "300곳"},                                       # 표지 숫자가 뉴스에 없음
                {"card3_number": "많이"},                                         # 표지 숫자에 숫자가 없음
                {"card1_highlight": "없는말"},                                     # 형광펜 낱말이 제목에 없음
                {"card2_learn_highlight": "엉뚱"},                                 # 강조 낱말이 배우는 금융에 없음
                {"card1_headline": "가" * 27},                                     # 표지 제목이 너무 김
                {"card3_why": "나" * 49},                                         # 한 줄이 너무 김
                {"card2_tag": "띄어 쓴 태그"},                                     # 해시태그 형식
                {"card1_fact": "학교 999곳이에요"},                                # 무슨 일? 에 뉴스 밖 숫자
                {"card1_why": "삼성전자를 살펴봐요."},                            # 종목 이름
                {"q1_options": ["가", "가", "다"]}):
        with pytest.raises(ValueError):
            check({**good_result(), **bad})


def test_build_save_load_latest(tmp_path):
    doc = news.build(good_result(), CANDS, NOW)
    assert doc["week"] == "2026-W45" and len(doc["cards"]) == 3 and doc["quiz"][2]["answer"] == 3
    assert doc["cards"][1]["news"]["title"] == "중고거래 사기 주의" and doc["cards"][0]["learn"]
    assert doc["cards"][0]["number"] == "" and doc["cards"][1]["number"] == "1,200건"
    assert doc["cards"][0]["tag"] == "물가" and doc["cards"][0]["highlight"] == "제목"
    assert news.cover(doc["cards"][0]) == news.ART["saving"]
    assert news.cover({"concept": "NEEDS_VS_WANTS"}) == news.ART["shopping"]  # 예전 저장본: 개념으로
    assert news.cover({}) == news.ART["learn"]
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
    html = " ".join(m.value for m in at.markdown)
    assert "ig-carousel" in html and "<mark>제목</mark>" in html and "#물가" in html  # 넘기는 4장 카드뉴스
    for i in range(3):
        at.radio[i].set_value(i)  # 정답은 1, 2, 3번
    at = at.run()
    assert any("50P를 받았어요" in s.value for s in at.success)
    assert len(store.load_news_quiz(store.NEWS_QUIZ_PATH)) == 1
    at = at.run()
    assert len(store.load_news_quiz(store.NEWS_QUIZ_PATH)) == 1
    assert any("이미 받았어요" in s.value for s in at.success)


def test_candidates_put_teen_related_news_first():
    results = {"20261104": [item("은행 경영진 인사 기준 강화", ministry="금융위원회", approved="11/06/2026 09:00:00")],
               "20261101": [item("청소년 용돈 사기 주의", "10대 학생 대상 피싱", approved="11/02/2026 09:00:00")]}
    cands = news.candidates(NOW, TICKERS, keys="key", fetch_fn=fake_fetch(results))
    assert cands[0]["title"] == "청소년 용돈 사기 주의"  # 더 오래됐어도 청소년 관련 점수가 높으면 먼저
    assert cands[0]["teen_score"] > cands[1]["teen_score"]
