"""오늘의 뉴스 (하루 3개 · 카드 4장 · 퀴즈 · 주말 복습) — NEWS_MARKET_SPEC.md (2026-11-16, 시뮬레이션).

- 매일 07:00(재시도 07:30·08:00·09:00, 이후 1시간마다) 이후 처음 연 사람이 오늘 뉴스를 만든다 (engine/updater.py).
  못 만들면 이전 뉴스를 그대로 보여 주고 '업데이트 실패 · 이전 데이터를 보는 중'을 띄운다.
- 뉴스 출처: 정책브리핑 정책뉴스 API (같은 DATA_GO_KR_KEY). 카드 문장은 AI(news_daily), 숫자·길이·권유 표현은 코드가 검사.
- 그림은 키워드 일러스트 (실제 뉴스 사진 아님), 단어는 개념 카드(content/concepts)에서만.
- 포인트: 정답 10P(처음 푼 것만), 3문제 다 풀면 +20P, 주말 복습 정답 10P — 하루 200P 상한 안 (engine/rewards.py).
- ?mock=1 → 시안 예시 뉴스 (저장·포인트 없음).
config.NEWS_DAILY = False → 예전 '이번 주 금융 뉴스' (legacy/weekly_news_page.py).
"""

import runpy
from pathlib import Path

import streamlit as st

import config

if not config.NEWS_DAILY:
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "legacy" / "weekly_news_page.py"))
    st.stop()

from datetime import date, datetime  # noqa: E402
from html import escape  # noqa: E402

import ui_common as ui  # noqa: E402
from engine import broker, news_daily as nd, portfolio, quotes, store, updater  # noqa: E402
from llm import client as llm  # noqa: E402

student = ui.setup("오늘의 뉴스", "📰")
sid = student["student_id"]
mock = bool(st.query_params.get("mock"))
concepts = store.load_concepts()
now = updater.now_kst()
today = now.date().isoformat()
FLAGS = config.NEWS_MARKET_FLAGS
MOCK_ANSWERS = "news-mock-answers"


# ---------- 오늘 뉴스 준비 (자동 업데이트) ----------

def ask(payload, check):
    """기존 카드뉴스와 같은 규칙의 AI 생성기. 실패하면 예외 → 작업 실패로 남고 이전 뉴스를 그대로 둔다."""
    return llm.ask("news_daily", payload, default={}, check=check, raise_on_fail=True)


def run_job():
    nd.run_news_job(now, ask, concepts)


if mock:
    doc = nd.load_demo(concepts)
    status = ("ok", "오늘 오전 7:00 자동 업데이트")
else:
    if FLAGS["autoUpdate"]:
        first = updater.load_state("news")["last_success"] is None and nd.latest() is None
        if first:
            with st.spinner("오늘의 뉴스를 가져오는 중…"):
                updater.ensure_fresh("news", run_job, now)
        else:
            updater.ensure_fresh("news", run_job, now)
    elif nd.load(today) is None and "news-tried" not in st.session_state:
        st.session_state["news-tried"] = True
        try:
            with st.spinner("오늘의 뉴스를 가져오는 중…"):
                run_job()
        except Exception as e:  # 예전처럼 버튼 없이 한 번만 시도
            st.session_state["news-error"] = str(e)
    doc = nd.load(today) or nd.latest()
    job = updater.load_state("news")
    status = updater.status_label("news", job, now)
    if status[0] == "ok":
        status = ("ok", status[1].replace("업데이트됨", "자동 업데이트"))


# ---------- 기록 (시안은 세션에만) ----------

def answers():
    if mock:
        import pandas as pd
        return pd.DataFrame(st.session_state.get(MOCK_ANSWERS, {}).get("answers", []),
                            columns=store.NEWS_ANSWER_COLUMNS)
    return store.load_news_answers()


def reads():
    if mock:
        import pandas as pd
        return pd.DataFrame(st.session_state.get(MOCK_ANSWERS, {}).get("reads", []), columns=store.NEWS_READ_COLUMNS)
    return store.load_news_reads()


def mark_read(item):
    if mock:
        box = st.session_state.setdefault(MOCK_ANSWERS, {"answers": [], "reads": []})
        if not any(r["news_id"] == item["news_id"] for r in box["reads"]):
            box["reads"].append({"student_id": sid, "day": doc["day"], "news_id": item["news_id"], "date": today})
        return
    store.append_news_read(sid, doc["day"], item["news_id"], today)


def record_answer(item, choice):
    row = {"student_id": sid, "day": doc["day"], "news_id": item["news_id"], "quiz_type": item["quiz"]["type"],
           "choice": choice, "correct": "TRUE" if choice == item["quiz"]["answer"] else "FALSE", "date": today}
    if mock:
        box = st.session_state.setdefault(MOCK_ANSWERS, {"answers": [], "reads": []})
        done = any(a["news_id"] == item["news_id"] for a in box["answers"])
        box["answers"].append({**row, "retry": "TRUE" if done else "FALSE"})
        return not done
    return store.append_news_answer(row)


# ---------- 화면 이동 ----------

def go(screen, idx=0, slide=0):
    st.session_state["news-view"] = {"screen": screen, "idx": idx, "slide": slide}


view = st.session_state.get("news-view", {"screen": "list", "idx": 0, "slide": 0})
if doc is None:
    view = {"screen": "list", "idx": 0, "slide": 0}


def stock_label(code):
    names = doc.get("stock_names") or {}
    if not names:
        names = {c: n for n, c in nd.stock_master().items()}
    return names.get(code, code)


def stock_change(code):
    if mock:
        return (doc.get("stock_quotes") or {}).get(code)
    rows = quotes.latest_rows().get(code)
    if not rows:
        return None
    q = broker.EodQuoteProvider({code: rows}, {code: code}).quote(code)
    return q["changePct"] if q else None


def open_stock(code):
    """뉴스 속 종목 칩 → 투자 탭 종목 상세 (지금 고른 모드 그대로). 시나리오 종목이 아니면 실제 시세로."""
    st.session_state["inv-screen"] = {"screen": "stock", "symbol": code}
    if code not in store.load_ticker_names():
        st.session_state["price_mode"] = "real"


def time_text(doc):
    made = datetime.fromisoformat(doc["made_at"])
    return f"{'오전' if made.hour < 12 else '오후'} {made.hour % 12 or 12}:{made.minute:02d}"


def day_title(day):
    d = date.fromisoformat(day)
    return f"{d.month}월 {d.day}일 {'월화수목금토일'[d.weekday()]}요일"


def item_image(item, slide=0):
    cat = item["images"][slide] if item.get("images") else item["categories"][0]
    uri = nd.image_uri(cat) if item.get("images") else ""
    return cat, uri


# ---------- 목록 ----------

def news_list():
    ui.app_bar("오늘의 뉴스", badge=day_title(today))
    if doc is None:
        ui.update_status("fail" if status[0] == "fail" else "busy", status[1])
        st.info("아직 오늘의 뉴스가 없어요. 잠시 후 다시 열어 주세요.")
        if not mock and updater.load_state("news")["last_error"]:
            ui.muted(f"이유: {updater.load_state('news')['last_error']}")
        return
    old = doc["day"] != today
    next_text = updater.next_slot_text("news", now)
    if old and status[0] == "ok":
        status_now = ("fail", "오늘 뉴스를 아직 못 만들었어요 · 이전 뉴스를 보는 중")
    else:
        status_now = status
    ui.update_status(status_now[0], status_now[1], f"다음 업데이트 {next_text}" if next_text else None)
    if old:
        ui.muted(f"{day_title(doc['day'])}의 뉴스예요.")

    ans, rd = answers(), reads()
    prog = nd.today_progress(doc, ans, rd, sid)
    left = len(doc["items"]) - prog["quiz"]
    streak = nd.streak_days(ans, sid, today)
    head = (f"{left}개 남았어요! 다 풀면 +{config.NEWS_QUIZ_ALL_DONE_BONUS}P 보너스" if left
            else "오늘 3문제를 다 풀었어요!")
    sub = f"뉴스 공부 {streak}일째 이어가는 중" if streak else "오늘 첫 뉴스를 읽어 볼까요?"
    with ui.card("nprog"):
        st.markdown(f"<div class='say'>{ui.mascot_html(size='md')}<div><b>{escape(head)}</b>"
                    f"<div class='muted'>{escape(sub)}</div></div></div>", unsafe_allow_html=True)
        st.progress(prog["quiz"] / len(doc["items"]))
        st.markdown(f"<div class='acc-foot'><span>읽기 {prog['read']}/3 · 퀴즈 {prog['quiz']}/3</span>"
                    f"<span>오늘 받은 포인트 <b>{prog['points']}P</b> / {prog['max_points']}P</span></div>",
                    unsafe_allow_html=True)

    kmap = nd.load_keyword_map()
    for i, item in enumerate(doc["items"]):
        cat, uri = item_image(item)
        with ui.card(f"news-{i}"):
            st.markdown(ui.news_card_html(item, i + 1, len(doc["items"]), uri, nd.category_label(cat, kmap), cat,
                                          nd.alt_text(cat, kmap), time_text(doc)), unsafe_allow_html=True)
            if FLAGS["newsStockLink"] and item.get("stocks"):
                with st.container(key=f"nstocks-{i}", horizontal=True):
                    st.markdown("<span class='muted'>뉴스 속 종목</span>", unsafe_allow_html=True)
                    for code in item["stocks"]:
                        pct = stock_change(code)
                        label = stock_label(code) + ("" if pct is None else f" {pct:+.1f}%")
                        if st.button(label, key=f"nstock-{i}-{code}"):
                            open_stock(code)
                            st.switch_page(ui.MARKET)
            state = prog["status"].get(item["news_id"])
            if state is True:
                with st.container(key=f"nstate-ok-{i}", horizontal=True):
                    st.markdown(f"정답! +{config.NEWS_QUIZ_CORRECT_POINTS}P 받았어요")
                    st.button("해설 다시 보기", key=f"nbtn-{i}", on_click=go, args=("quiz", i))
            elif state is False:
                with st.container(key=f"nstate-wrong-{i}", horizontal=True):
                    st.markdown("아쉬워요 · 오답노트에 담았어요")
                    st.button("다시 풀기", key=f"nbtn-{i}", on_click=go, args=("quiz", i))
            else:
                read = item["news_id"] in prog["read_ids"]
                with st.container(key=f"nstate-new-{i}", horizontal=True):
                    st.markdown(f"{'다 읽었어요' if read else '아직 안 읽었어요'} · 퀴즈 +{config.NEWS_QUIZ_CORRECT_POINTS}P")
                    if read:
                        st.button("퀴즈 풀기", key=f"nbtn-{i}", type="primary", on_click=go, args=("quiz", i))
                    else:
                        st.button("읽으러 가기", key=f"nbtn-{i}", type="primary", on_click=go, args=("card", i, 0))

    my_stock_news()
    summary = nd.week_summary(today, ans, rd, store.load_news_reviews() if not mock else nd.empty_answers(), sid) \
        if not mock else None
    count = (len(summary["notes"]) + len(summary["words"])) if summary else 0
    with ui.card("news-review-link"):
        st.button(f"이번 주 오답노트 · 단어장 {count}개  ›", key="news-review", width="stretch",
                  on_click=go, args=("review",), disabled=mock)
    ui.muted(f"뉴스: {doc['source']} · 요약: AI(원문 링크 제공) · 이미지: 키워드 일러스트(실제 뉴스 사진 아님)"
             + (" · 뉴스 제목·숫자는 시안용 예시예요" if mock else ""))


def my_stock_news():
    """내 종목(연습·실전 보유)이 나온 오늘 뉴스."""
    held = {}
    for path in (store.TRADES_PATH, store.REAL_TRADES_PATH):
        try:
            for code, qty in portfolio.holdings(store.load_trades(path), sid).items():
                held[code] = held.get(code, 0) + qty
        except (OSError, ValueError):
            continue
    real = (store.load_invest(sid) or {}).get("real") or {}
    for code, h in (real.get("holdings") or {}).items():
        if h.get("qty"):
            held.setdefault(code, 0)
    rows = [(code, item) for item in doc["items"] for code in item.get("stocks", []) if code in held]
    if not rows or not FLAGS["newsStockLink"]:
        return
    ui.section("내 종목이 나온 뉴스")
    with ui.card("my-stock-news"):
        for code, item in rows:
            qty = held[code]
            if st.button(f"{stock_label(code)}{f' {qty}주' if qty else ''} · 오늘 뉴스 · {item['cards'][0]['title']}  ›",
                         key=f"mynews-{code}-{item['news_id']}", width="stretch"):
                open_stock(code)
                st.switch_page(ui.MARKET)


# ---------- 카드 4장 ----------

def card_view(i, slide):
    item = doc["items"][i]
    kmap = nd.load_keyword_map()
    cat, uri = item_image(item, slide)
    label = nd.category_label(item["categories"][0], kmap)
    ui.app_bar(f"뉴스 {i + 1}/{len(doc['items'])}", on_back=lambda: go("list"))
    st.markdown(ui.slide_html(item, slide, uri, cat, nd.alt_text(cat, kmap), label, i + 1, len(doc["items"])),
                unsafe_allow_html=True)
    if slide == 3:
        mark_read(item)
    with st.container(key="slide-nav", horizontal=True):
        st.button("‹", key="slide-prev", disabled=slide == 0, on_click=go, args=("card", i, max(0, slide - 1)))
        if slide < 3:
            st.button("다음 카드", key="slide-next", type="primary", width="stretch", on_click=go,
                      args=("card", i, slide + 1))
        else:
            st.button(f"퀴즈 풀기 · +{config.NEWS_QUIZ_CORRECT_POINTS}P", key="slide-quiz", type="primary",
                      width="stretch", on_click=go, args=("quiz", i))
    st.markdown(ui.source_line(item, day_title(doc["day"]).rsplit(" ", 1)[0]), unsafe_allow_html=True)


# ---------- 퀴즈 ----------

def quiz_view(i):
    item = doc["items"][i]
    q = item["quiz"]
    key = f"news-choice-{doc['day']}-{item['news_id']}"
    ui.app_bar(f"뉴스 퀴즈 {i + 1}/{len(doc['items'])}", on_back=lambda: (go("list"), st.session_state.pop(key, None)))
    chips = "".join(f"<span class='{'on' if t == q['type'] else ''}'>{k + 1} {nd.QUIZ_TYPE_LABELS[t]}</span>"
                    for k, t in enumerate(nd.QUIZ_TYPES))
    st.markdown(f"<div class='qtypes'>{chips}</div>", unsafe_allow_html=True)
    choice = st.session_state.get(key)
    with ui.card("quiz"):
        ui.muted(item["cards"][0]["title"])
        st.markdown(f"### {q['question']}")
        for k, option in enumerate(q["options"]):
            state = ""
            if choice is not None:
                state = "ok-" if k == q["answer"] else "bad-" if k == choice else ""
            with st.container(key=f"qopt-{state}{k}"):
                tail = "  · 정답" if choice is not None and k == q["answer"] else ""
                if st.button(f"{'ABCD'[k]}  {option}{tail}", key=f"qbtn-{k}", width="stretch",
                             disabled=choice is not None):
                    first = record_answer(item, k)
                    st.session_state[key] = k
                    st.session_state["news-first"] = first
                    st.rerun()
    if choice is None:
        return
    right = choice == q["answer"]
    prog = nd.today_progress(doc, answers(), reads(), sid)
    first = st.session_state.get("news-first", False)
    if right:
        head = f"정답! +{config.NEWS_QUIZ_CORRECT_POINTS}P" if first else "정답! (다시 풀기는 0P)"
        if first and prog["quiz"] == len(doc["items"]):
            head += f" · 오늘 3문제 완주 보너스 +{config.NEWS_QUIZ_ALL_DONE_BONUS}P"
    else:
        head = "아쉬워요 · 오답노트에 담았어요" if first else "아쉬워요 · 다시 풀기는 0P예요"
    st.markdown(f"<div class='qresult qresult-{'ok' if right else 'bad'}'><b>{escape(head)}</b>"
                f"<div>{escape(q['explanation'])}</div>"
                f"<small class='muted'>오늘 뉴스 포인트 {prog['points']}P"
                + (" · 시안이라 실제로 쌓이지 않아요" if mock else " · 돼지 저금통에 쏙!") + "</small></div>",
                unsafe_allow_html=True)

    def back():
        st.session_state.pop(key, None)
        go("list")
    st.button("오늘의 뉴스로 돌아가기", type="primary", width="stretch", on_click=back)


# ---------- 주말 복습 ----------

def review_view():
    reviews = store.load_news_reviews()
    summary = nd.week_summary(today, answers(), reads(), reviews, sid)
    days = summary["days"]
    first_day, last_day = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    ui.app_bar("이번 주 뉴스 공부", badge=f"{first_day.month}월 {first_day.day}일~{last_day.day}일",
               on_back=lambda: go("list"))
    with ui.card("review-week"):
        st.markdown(ui.day_circles_html(days, summary["by_day"]), unsafe_allow_html=True)
        st.markdown(ui.stat_tiles_html([("읽은 뉴스", f"{summary['read']}개"),
                                        ("정답률", "-" if summary["rate"] is None else f"{summary['rate']}%"),
                                        ("받은 포인트", f"{summary['points']}P")]), unsafe_allow_html=True)
        ui.muted("숫자는 정답 수예요(하루 3문제).")
    ui.section(f"오답노트 · {len(summary['notes'])}문제")
    with ui.card("review-notes"):
        if not summary["notes"]:
            ui.muted("이번 주에 틀린 문제가 없어요.")
        for n in summary["notes"]:
            st.markdown(f"<div class='wnote'><small>{nd.QUIZ_TYPE_LABELS[n['type']]} · {escape(n['news'])}</small>"
                        f"<b>{escape(n['question'])}</b><span>정답: {escape(n['answer'])}</span></div>",
                        unsafe_allow_html=True)
    ui.section("이번 주 모은 단어")
    with ui.card("review-words"):
        if summary["words"]:
            st.markdown("<div class='wwords'>" + "".join(f"<span title='{escape(w['meaning'])}'>{escape(w['word'])}</span>"
                                                         for w in summary["words"]) + "</div>", unsafe_allow_html=True)
        else:
            ui.muted("카드 4장을 끝까지 읽으면 오늘의 단어가 여기에 모여요.")
    qs = nd.review_questions(summary, concepts)
    with ui.card("review-quiz"):
        st.markdown(f"**주말 복습 퀴즈 {len(qs)}문제**")
        ui.muted(f"오답노트 + 단어 문제. 맞힌 문제마다 {config.NEWS_REVIEW_CORRECT_POINTS}P, 하루 200P 한도 안에서 받아요.")
        st.button("복습 시작하기", type="primary", width="stretch", disabled=not qs, on_click=go, args=("review_quiz", 0))
    total, with_news = nd.news_trades(store.load_trades(), sid, days)
    if total:
        st.markdown(f"<div class='say'>{ui.mascot_html(size='md')}<div class='say-bubble'>"
                    f"이번 주 거래 {total}건 중 {with_news}건에 뉴스 근거를 붙였어요. "
                    "다음 주엔 '왜 팔았는지'도 적어 봐요.</div></div>", unsafe_allow_html=True)


def review_quiz_view(k):
    reviews = store.load_news_reviews()
    summary = nd.week_summary(today, answers(), reads(), reviews, sid)
    qs = nd.review_questions(summary, concepts)
    week = summary["days"][0]
    if k >= len(qs):
        ui.app_bar("주말 복습 끝", on_back=lambda: go("review"))
        st.success("복습을 마쳤어요!")
        st.button("이번 주 뉴스 공부로", type="primary", width="stretch", on_click=go, args=("review",))
        return
    q = qs[k]
    ui.app_bar(f"주말 복습 {k + 1}/{len(qs)}", on_back=lambda: go("review"))
    key = f"review-choice-{week}-{q['qid']}"
    choice = st.session_state.get(key)
    with ui.card("quiz"):
        ui.muted(q["label"])
        st.markdown(f"### {q['question']}")
        for j, option in enumerate(q["options"]):
            state = "" if choice is None else ("ok-" if j == q["answer"] else "bad-" if j == choice else "")
            with st.container(key=f"qopt-{state}{j}"):
                if st.button(f"{'ABCD'[j]}  {option}", key=f"rbtn-{j}", width="stretch", disabled=choice is not None):
                    done = ((reviews["student_id"] == sid) & (reviews["week"] == week) & (reviews["qid"] == q["qid"])).any()
                    if not done:
                        store.append_news_review({"student_id": sid, "week": week, "qid": q["qid"], "choice": j,
                                                  "correct": "TRUE" if j == q["answer"] else "FALSE", "date": today})
                    st.session_state[key] = j
                    st.rerun()
    if choice is not None:
        right = choice == q["answer"]
        st.markdown(f"<div class='qresult qresult-{'ok' if right else 'bad'}'>"
                    f"<b>{'정답!' if right else '아쉬워요'}</b><div>{escape(q['explanation'])}</div></div>",
                    unsafe_allow_html=True)
        st.button("다음 문제", type="primary", width="stretch", on_click=go, args=("review_quiz", k + 1))


# ---------- 화면 고르기 ----------

if view["screen"] == "card" and doc and view["idx"] < len(doc["items"]):
    card_view(view["idx"], view["slide"])
elif view["screen"] == "quiz" and doc and view["idx"] < len(doc["items"]):
    quiz_view(view["idx"])
elif view["screen"] == "review" and not mock:
    review_view()
elif view["screen"] == "review_quiz" and not mock:
    review_quiz_view(view["idx"])
else:
    news_list()
