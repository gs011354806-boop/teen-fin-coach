"""뉴스 카드·퀴즈 + 시세 자동 업데이트 + 실전 거래 UI (invest & card_new/teengrow_news_market/NEWS_MARKET_SPEC.md)."""

import json
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import config
from conftest import open_app
from engine import broker, invest_track as it, news_daily as nd, quotes, rewards, store, updater

NEWS = "pages/12_이번_주_금융_뉴스.py"
MARKET = "pages/1_가상_주식시장.py"
MON_10 = datetime(2026, 11, 16, 10, 0)
MON_14 = datetime(2026, 11, 16, 14, 0)


# ---------- 3장 자동 업데이트 판단 ----------

def test_expected_eod_date_examples():
    assert updater.expected_eod_date(MON_10) == date(2026, 11, 12)   # 월 10:00 → 지난 목요일
    assert updater.expected_eod_date(MON_14) == date(2026, 11, 13)   # 월 14:00 → 지난 금요일
    assert updater.expected_eod_date(datetime(2026, 11, 15, 12)) == date(2026, 11, 12)  # 일요일 → 지난 목요일


def test_business_days_skip_weekend_holidays_and_dec_31():
    assert updater.is_business_day(date(2026, 11, 16))
    assert not updater.is_business_day(date(2026, 11, 15))
    assert not updater.is_business_day(date(2026, 12, 25)) and not updater.is_business_day(date(2026, 12, 31))
    assert updater.due_slot("stock_eod", datetime(2026, 12, 28, 9)) == datetime(2026, 12, 24, 13, 30)


def test_news_due_and_stale():
    assert updater.due_slot("news", datetime(2026, 11, 16, 6, 59)) == datetime(2026, 11, 15, 7, 0)
    assert updater.is_stale("news", datetime(2026, 11, 15, 8), datetime(2026, 11, 16, 7, 1))
    assert not updater.is_stale("news", datetime(2026, 11, 16, 7, 1), datetime(2026, 11, 16, 20))


def test_retry_waits_for_next_slot_then_hourly():
    fail_at = datetime(2026, 11, 16, 7, 5)
    assert not updater.should_attempt("news", None, fail_at, datetime(2026, 11, 16, 7, 20))
    assert updater.should_attempt("news", None, fail_at, datetime(2026, 11, 16, 7, 31))
    last = datetime(2026, 11, 16, 9, 10)
    assert not updater.should_attempt("news", None, last, datetime(2026, 11, 16, 9, 50))
    assert updater.should_attempt("news", None, last, datetime(2026, 11, 16, 10, 1))


def test_ensure_fresh_outcomes_and_status(tmp_path):
    path = tmp_path / "state.json"
    calls = []
    assert updater.ensure_fresh("news", lambda: calls.append(1), now=MON_10, path=path) == updater.UPDATED
    assert updater.ensure_fresh("news", lambda: calls.append(1), now=MON_14, path=path) == updater.FRESH
    assert calls == [1]
    kind, text = updater.status_label("news", updater.load_state("news", path), MON_14)
    assert kind == "ok" and text == "오늘 오전 10:00 업데이트됨"

    def boom():
        raise RuntimeError("API 실패")
    tomorrow = MON_10 + timedelta(days=1)
    assert updater.ensure_fresh("news", boom, now=tomorrow, path=path) == updater.FAILED
    assert updater.ensure_fresh("news", boom, now=tomorrow + timedelta(minutes=5), path=path) == updater.WAITING
    assert updater.status_label("news", updater.load_state("news", path), tomorrow)[1] == "업데이트 실패 · 이전 데이터를 보는 중"
    assert updater.eod_caption("2026-11-13") == "11월 13일(금) 종가 기준 · 영업일 오후 1시 30분 자동 업데이트"


# ---------- 6장 키워드 이미지 ----------

def test_every_category_has_an_svg_and_label():
    kmap = nd.load_keyword_map()
    for cat in list(kmap["categories"]) + [kmap["fallback"]]:
        assert (nd.IMAGE_DIR / f"{cat}.svg").exists(), cat
    assert len(kmap["categories"]) == 13


def test_categories_slides_hashtags_and_diversify():
    kmap = nd.load_keyword_map()
    title, body = "간편결제 스미싱 주의", "결제 링크 문자 사기가 늘었어요. 카드 결제 확인은 앱에서"
    cats = nd.pick_categories(title, body, kmap)
    assert len(cats) == 2 and nd.slide_categories(cats) == [cats[0], cats[1], cats[0], cats[1]]
    assert nd.pick_categories("오늘 날씨", "맑아요", kmap) == ["general"]
    assert nd.top_keywords(title, body, kmap)[0] in title
    assert nd.diversify([["interest", "policy"], ["interest", "prices"]]) == [["interest", "policy"], ["prices", "interest"]]
    assert nd.alt_text("security", kmap) == "금융 보안 키워드 일러스트 (실제 뉴스 사진 아님)"
    assert nd.image_uri("security").startswith("data:image/svg+xml;base64,")


# ---------- 5·7장 고르기 · 뉴스 속 종목 ----------

def news_item(i, title, body="", day="2026-11-16"):
    return {"id": f"id{i}", "title": title, "body": body, "publisher": "금융위원회", "url": f"https://x/{i}",
            "published_at": day, "teen_score": 0}


def test_dedupe_and_pick_daily_distinct_categories():
    kmap = nd.load_keyword_map()
    items = [news_item(1, "기준금리 동결 결정", "한국은행 금리"), news_item(2, "기준금리 동결 결정 발표", "금리"),
             news_item(3, "예금 금리 비교", "적금 이자"), news_item(4, "스미싱 문자 주의", "결제 링크 사기"),
             news_item(5, "수출 반도체 증가", "반도체 수출"), news_item(6, "날씨 맑음")]
    assert len(nd.dedupe(items)) == 5
    picked = nd.pick_daily(items, kmap, n=3)
    tops = [nd.pick_categories(p["title"], p["body"], kmap)[0] for p in picked]
    assert len(set(tops)) == 3 and all(p["id"] != "id6" for p in picked)  # 키워드 없는 기사는 모자랄 때만
    assert all(p["id"] != "id1" for p in nd.pick_daily(items, kmap, n=3, used_ids={"id1"}))


def test_find_mentioned_stocks_longest_name_first():
    master = {"카카오": "035720", "카카오뱅크": "323410", "삼성전자": "005930", "NAVER": "035420"}
    assert nd.find_mentioned_stocks("카카오뱅크가 새 서비스를 냈어요", master) == ["323410"]
    assert nd.find_mentioned_stocks("NAVER와 카카오, 삼성전자, 카카오뱅크", master) == ["035420", "035720", "005930"]
    assert nd.find_mentioned_stocks("반도체 수출이 늘었어요", master) == []


def test_company_names_allowed_but_advice_words_blocked():
    assert not nd.blocked("삼성전자 반도체 수출 증가")      # 2026-11-16 규칙 완화: 회사 이름만은 허용
    assert nd.blocked("이번 주 급등주 종목 추천")


# ---------- 5장 카드 · 퀴즈 생성 (AI는 가짜) ----------

def fake_fetch_items():
    raw = [("기준금리 동결, 예금 이자 그대로", "한국은행이 기준금리를 연 2.5%로 동결했어요. 예금 금리"),
           ("간편결제 스미싱 문자 주의", "결제 링크를 누르면 사기 화면이 나와요. 카드 결제 확인"),
           ("반도체 수출 늘어", "삼성전자 등 반도체 수출이 늘었어요. 수출 증가"),
           ("물가 안정 대책", "소비자물가 관리 방안")]

    def fetch(start, end, key):
        return [{"title": t, "subtitle": "", "body": b, "ministry": "금융위원회", "link": f"https://k/{i}",
                 "approved": "11/16/2026 06:00:00", "kogl": "1"} for i, (t, b) in enumerate(raw)]
    return fetch


def fake_result(concept="COMPOUND_INTEREST"):
    r = {}
    for i in (1, 2, 3):
        r.update({f"n{i}_list": "뉴스 요약이에요.", f"n{i}_what_title": "무슨 일이 있었어요", f"n{i}_what": "설명이에요.",
                  f"n{i}_why_title": "왜 중요해요", f"n{i}_why": "이유예요.", f"n{i}_me_title": "나와 이어져요",
                  f"n{i}_me": "생활과 이어져요.", f"n{i}_tip": "한 번 더 생각!", f"n{i}_concept": concept,
                  f"q{i}": "알맞은 것은 무엇일까요?", f"q{i}_options": ["가", "나", "다", "라"], f"q{i}_answer": "2",
                  f"q{i}_explain": "카드에 나와요."})
    return r


def test_run_news_job_saves_three_with_images_stocks_and_word_from_concept(tmp_path):
    concepts = store.load_concepts()
    asked = []

    def ask(payload, check):
        asked.append(payload)
        result = fake_result()
        check(result)
        return result
    doc = nd.run_news_job(MON_10, ask, concepts, fetch_fn=fake_fetch_items(), news_dir=tmp_path, key="k")
    assert len(doc["items"]) == 3 and nd.load("2026-11-16", tmp_path)["day"] == "2026-11-16"
    assert [q["quiz_type"] for q in asked[0]["news"]] == ["내용 확인", "단어", "나라면?"]
    assert len({it["images"][0] for it in doc["items"]}) == 3  # 대표 그림이 겹치지 않는다
    for item in doc["items"]:
        assert item["cards"][3]["word"] == concepts["COMPOUND_INTEREST"]["name_ko"]  # 단어는 개념 파일에서
        assert len(item["cards"]) == 4 and item["quiz"]["type"] in nd.QUIZ_TYPES
    word_q = doc["items"][1]["quiz"]
    assert word_q["question"] == concepts["COMPOUND_INTEREST"]["quiz"]["질문"]  # 단어 문제 = 개념 파일 확인 문제
    semi = next(i for i in doc["items"] if "반도체" in i["title"])
    assert semi["stocks"] == ["005930"]


def test_cards_check_rejects_new_numbers_and_price_quiz():
    picked = [news_item(1, "금리 2.5%", "금리"), news_item(2, "물가", "물가"), news_item(3, "결제", "결제")]
    check = nd.cards_check(picked, store.load_concepts())
    check(fake_result())
    bad = fake_result()
    bad["n2_what"] = "물가가 3.1% 올랐어요."
    with pytest.raises(ValueError):
        check(bad)
    bad = fake_result()
    bad["q3"] = "내일 주가가 오를까요?"
    with pytest.raises(ValueError):
        check(bad)


def test_failed_job_keeps_yesterday_and_never_saves_partial(tmp_path):
    concepts = store.load_concepts()
    yesterday = {"day": "2026-11-15", "made_at": "2026-11-15T07:00", "source": "x", "items": [{"news_id": f"y{i}"} for i in range(3)]}
    nd.save(yesterday, tmp_path)
    with pytest.raises(nd.DailyNewsError):
        nd.run_news_job(MON_10, lambda p, c: {}, concepts, fetch_fn=fake_fetch_items(), news_dir=tmp_path, key="k")
    assert nd.load("2026-11-16", tmp_path) is None and nd.latest(tmp_path)["day"] == "2026-11-15"
    with pytest.raises(nd.DailyNewsError):
        nd.save({**yesterday, "day": "2026-11-16", "items": [{"news_id": "z"}]}, tmp_path)


# ---------- 9장 포인트 ----------

def answers_table(rows):
    return pd.DataFrame([dict(zip(store.NEWS_ANSWER_COLUMNS, r)) for r in rows], columns=store.NEWS_ANSWER_COLUMNS)


def test_news_points_10_each_bonus_20_retry_zero_within_daily_cap():
    a = answers_table([("S01", "2026-11-16", "n1", "content", "1", "TRUE", "FALSE", "2026-11-16"),
                       ("S01", "2026-11-16", "n2", "word", "0", "FALSE", "FALSE", "2026-11-16"),
                       ("S01", "2026-11-16", "n2", "word", "1", "TRUE", "TRUE", "2026-11-16"),
                       ("S01", "2026-11-16", "n3", "apply", "2", "TRUE", "FALSE", "2026-11-16")])
    assert nd.news_points(a, "S01", "2026-11-16") == 10 + 10 + 20  # 다시 풀어 맞힌 것은 0P
    reviews = pd.DataFrame(columns=store.NEWS_REVIEW_COLUMNS)
    events = rewards.apply_daily_cap(nd.point_events(a, reviews, "S01")
                                     + [{"date": "2026-11-16", "kind": "미션", "capped": True, "label": "m", "points": 180}])
    assert sum(e["granted"] for e in events) == 200  # 하루 200P 상한
    assert (rewards.MISSION_POINTS, rewards.JOURNAL_POINTS, rewards.GOAL_BONUS_POINTS, rewards.DAILY_CAP) == (100, 20, 300, 200)


def test_store_answer_retry_flag(tmp_path):
    path = tmp_path / "a.csv"
    row = {"student_id": "S01", "day": "2026-11-16", "news_id": "n1", "quiz_type": "content", "choice": 0,
           "correct": "FALSE", "date": "2026-11-16"}
    assert store.append_news_answer(row, path) is True
    assert store.append_news_answer({**row, "choice": 1, "correct": "TRUE"}, path) is False
    assert list(store.load_news_answers(path)["retry"]) == ["FALSE", "TRUE"]


# ---------- 4-1 시세 수집 · 일정 ----------

def api_rows(code, rows):
    return {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [
        {"basDt": d.replace("-", ""), "srtnCd": code, "itmsNm": "이름", "clpr": str(c), "mkp": str(c), "hipr": str(c + 100),
         "lopr": str(c - 100), "trqu": "1000", "vs": "100", "fltRt": "1.5"} for d, c in rows]}}}}


def test_parse_keeps_ohlv_and_drops_implausible_values():
    rows = quotes.parse_items(api_rows("005930", [("2026-11-12", 50000), ("2026-11-13", 90000), ("2026-11-14", 51000)]),
                              "005930")
    assert [r["date"] for r in rows] == ["2026-11-12", "2026-11-14"]  # +80%는 버린다
    assert rows[0]["high"] == 50100 and rows[0]["volume"] == 1000 and rows[0]["change_pct"] == 1.5


def test_scheduled_quotes_fetch_once_after_1330(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "test-key")
    calls = []

    def fetch(ticker, begin, key):
        calls.append(ticker)
        return [{"date": "2026-11-13", "close": 1000}]
    kw = dict(fetch=fetch, cache_path=tmp_path / "c.json", state_path=tmp_path / "s.json", scheduled=True)
    first = quotes.load_quotes(now=MON_14.replace(tzinfo=quotes.KST), **kw)
    assert first["status"] == quotes.FRESH and len(calls) == 15
    again = quotes.load_quotes(now=(MON_14 + timedelta(hours=3)).replace(tzinfo=quotes.KST), **kw)
    assert again["status"] == quotes.CACHED and len(calls) == 15  # 다음 영업일 13:30까지 다시 부르지 않는다
    nxt = quotes.load_quotes(now=(MON_14 + timedelta(days=1)).replace(tzinfo=quotes.KST), **kw)
    assert nxt["status"] == quotes.FRESH and len(calls) == 30


# ---------- 8장 실전: 시세 출처 · 검증 ----------

def eod_provider(day="2026-11-13"):
    series = {"005930": [{"date": "2026-11-12", "close": 55800}, {"date": day, "close": 56800, "change": 1000,
                                                                   "change_pct": 1.8}]}
    return broker.EodQuoteProvider(series, {"005930": "삼성전자"})


def test_eod_quote_caption_and_freshness():
    p = eod_provider()
    q = p.quote("005930")
    assert q["price"] == 56800 and q["label"] == "11월 13일(금) 종가 기준 · 영업일 오후 1시 30분 자동 업데이트"
    assert p.is_fresh(q, MON_14) and p.is_fresh(q, MON_10)
    old = eod_provider("2026-11-12")
    assert not old.is_fresh(old.quote("005930"), MON_14)  # 13:30 업데이트 실패 → 실전 주문만 잠금


def test_broker_switch_needs_adapter():
    eod = eod_provider()
    assert broker.get_quote_provider(eod, source="eod") is eod
    with pytest.raises(RuntimeError):
        broker.get_quote_provider(eod, source="broker")


def test_validation_codes_table_order():
    g = it.make_guardrails(50_000, it.ETF_LARGECAP)
    q = {"changePct": 1.0}
    stock = {"type": "STOCK", "isLargeCap": True}
    reason = "실적 공시를 확인했어요 영업이익 증가"
    base = {"side": "BUY", "amount": 10_000, "reason": reason}
    v = lambda req=base, **kw: it.validate_order(req, g, kw.pop("consent", {"status": it.ACTIVE}), {"buys": 0}, q,
                                                 stock, 50_000, **kw)
    assert v(consent={"status": it.NONE}) == "NO_CONSENT"
    assert v(fresh=False) == "QUOTE_STALE"
    assert v(fresh=True, market_open=False, source="eod") is None            # eod는 장 시간 검사 안 함
    assert v(market_open=False, source="broker") == "MARKET_CLOSED"
    assert v({**base, "reserve": True}, market_open=False, source="broker") is None
    assert v(fresh=False, market_open=False, source="broker") == "MARKET_CLOSED"  # broker 장 밖: 멈춤은 잠금 사유 아님
    assert v({**base, "reason": "짧음"}) == "REASON_REQUIRED"                   # 실전 매수는 늘 근거 필수
    assert v({"side": "SELL", "qty": 1.0}) == "INSUFFICIENT_SHARES"
    for code in ("NO_CONSENT", "REVOKED", "QUOTE_STALE", "MARKET_CLOSED", "OVER_PER_ORDER", "OVER_MONTHLY",
                 "OUT_OF_SCOPE", "FOMO_CHECK_REQUIRED"):
        assert code in it.BLOCK_SCREENS


def test_real_journal_gives_existing_20p():
    state = {"real": {"orders": [{"id": "RO1", "date": "2026-11-16", "reason": "실적 공시를 확인했어요"},
                                 {"id": "RO2", "date": "2026-11-16", "reason": "그냥"}]}}
    events = rewards.real_journal_events("S01", state)
    assert [e["points"] for e in events] == [20]


# ---------- 화면 ----------

def run(at):
    at = at.run()
    assert not at.exception, at.exception
    return at


def texts(at):
    return " ".join(m.value for m in at.markdown)


def press(at, label):
    next(b for b in at.button if b.label == label).click()
    return run(at)


def test_news_list_mock_matches_mockup():
    at = open_app(NEWS, query={"mock": "1"})
    assert not at.exception, at.exception
    t = texts(at)
    for part in ["오늘 오전 7:00 자동 업데이트", "반도체 수출이 늘었어요", "기준금리가 그대로예요", "간편결제 사기가 늘고 있어요",
                 "data:image/svg+xml;base64", "읽기 0/3 · 퀴즈 0/3", "/ 50P"]:
        assert part in t, part
    labels = [b.label for b in at.button]
    assert "삼성전자 +1.8%" in labels and "SK하이닉스 +2.4%" in labels and labels.count("읽으러 가기") == 3


def test_cards_then_quiz_then_points_in_mock():
    at = open_app(NEWS, query={"mock": "1"})
    at = press(at, "읽으러 가기")
    t = texts(at)
    assert "키워드 이미지 · 실제 뉴스 사진 아님" in t and "1 · 무슨 일?" in t and "#반도체" in t
    for _ in range(3):
        at = press(at, "다음 카드")
    t = texts(at)
    assert "4 · 오늘의 단어" in t and "분산투자" in t
    at = press(at, "퀴즈 풀기 · +10P")
    assert "1 내용 확인" in texts(at)
    at = press(at, "B  반도체 수출")
    assert "정답! +10P" in texts(at)
    at = press(at, "오늘의 뉴스로 돌아가기")
    assert "퀴즈 1/3" in texts(at) and "오늘 받은 포인트 <b>10P</b>" in texts(at)
    assert not store.NEWS_ANSWERS_PATH.exists()  # 시안은 저장하지 않는다


def test_real_news_page_without_api_shows_failure_status():
    at = open_app(NEWS)
    assert not at.exception, at.exception
    assert "아직 오늘의 뉴스가 없어요" in " ".join(i.value for i in at.info)
    assert updater.load_state("news")["last_error"]  # 실패를 남기고 다음 재시도 칸까지 기다린다


def test_saved_news_page_quiz_records_answer_and_points(monkeypatch):
    concepts = store.load_concepts()
    today = updater.now_kst().date().isoformat()
    doc = nd.load_demo(concepts)
    doc["day"] = today
    nd.save(doc)
    updater.save_state("news", {"last_success": updater.now_kst(), "last_attempt": None, "last_error": None})
    at = open_app(NEWS)
    assert "기준금리가 그대로예요" in texts(at)
    at.session_state["news-view"] = {"screen": "quiz", "idx": 2, "slide": 0}
    at = run(at)
    at = press(at, "C  링크는 누르지 않고 게임 앱을 직접 열어 확인한다")
    a = store.load_news_answers()
    assert list(a["correct"]) == ["TRUE"] and list(a["quiz_type"]) == ["apply"]
    events = rewards.daily_news_events("S01")
    assert [e["points"] for e in events] == [10]


def test_stock_detail_practice_switch_to_real_without_consent_shows_no_consent():
    at = open_app(MARKET, query={"mock": "1"})
    at = press(at, "누리바이오 보기")
    assert "11월 13일(금) 종가 기준" in texts(at)
    at.segmented_control(key="stock-mode-NR01").set_value("● 실전 · 부모님 동의")
    at = run(at)
    assert "NO_CONSENT" in texts(at) and any(b.label == "부모님께 동의 요청하기" for b in at.button)


def test_real_stock_detail_shows_eod_and_guardrails():
    at = open_app(MARKET, query={"mock": "real"})
    at = press(at, "한빛전자 더 사기")
    t = texts(at)
    for part in ["실제 돈으로 거래해요", "전날 종가", "11월 13일(금) 종가 기준", "실전도 지금은 연습과 같은 전날 종가",
                 "부모님이 정한 안전장치", "20,000원 남음 / 50,000원", "25,000원까지", "이 종목 가능", "항상 막혀 있어요"]:
        assert part in t, part


def test_blocked_screen_out_of_scope_button():
    at = open_app(MARKET, query={"mock": "real"})
    at.session_state["inv-block"] = {"code": "OUT_OF_SCOPE", "symbol": "NR01"}
    at.session_state["inv-screen"] = {"screen": "blocked", "symbol": "NR01"}
    at = run(at)
    assert "OUT_OF_SCOPE" in texts(at) and any(b.label == "연습 모드에서 보기" for b in at.button)


def test_flags_off_keep_old_screens(monkeypatch):
    monkeypatch.setattr(config, "NEWS_DAILY", False)
    monkeypatch.setattr(config, "NEWS_MARKET_FLAGS", {k: False for k in config.NEWS_MARKET_FLAGS})
    at = open_app(NEWS)
    assert not at.exception and at.title[0].value == "이번 주 금융 뉴스"
    at = open_app(MARKET, query={"mock": "1"})
    at = press(at, "누리바이오 보기")
    assert not any(getattr(e, "key", "") == "stock-mode-NR01" for e in at.get("segmented_control"))
