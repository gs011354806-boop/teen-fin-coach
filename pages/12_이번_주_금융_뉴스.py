"""22번 이번 주 금융 뉴스 (카드뉴스 3장 + 퀴즈 3문제).

한 주에 처음 연 사람이 만들면(정책브리핑 정책뉴스 API → AI 카드화) data/real/news_<주차>.json에 저장되고,
그 주에는 모두 같은 카드뉴스를 본다. 못 만들면 가장 최근 저장본을 보여 준다.
퀴즈를 모두 맞히면 주에 한 번 포인트 (engine/rewards.py, 하루 상한 안에서).
"""

import streamlit as st

import ui_common as ui
from engine import envelope, news, rewards, store

student = ui.setup("이번 주 금융 뉴스", "📰")
student_id = student["student_id"]
concepts = store.load_concepts()
now = news.now_kst()
week = news.week_id(now)


def make_this_week():
    """이번 주 카드뉴스를 만들어 저장한다. 못 만들면 이유 문자열을 돌려준다."""
    try:
        ticker_names = list(store.load_ticker_names().values())
        cands = news.candidates(now, ticker_names)
    except news.NewsError as e:
        return str(e)
    if len(cands) < news.CARD_COUNT:
        return "이번 주에 고를 만한 뉴스가 부족해요"
    with st.spinner("AI 코치가 이번 주 뉴스를 카드뉴스로 정리하고 있어요..."):
        result = ui.ask_ai("news_cards", news.payload(cands, concepts), student_id, demo_key=week,
                           default={}, check=news.cards_check(cands, concepts, ticker_names))
    if not result:
        return "AI가 카드뉴스를 만들지 못했어요"
    news.save(news.build(result, cands, now))
    return None


doc = news.load(week)
note_key = f"news-failed-{week}"
if doc is None and note_key not in st.session_state:
    st.session_state[note_key] = make_this_week()
    doc = news.load(week)
stale = doc is None
if stale:
    doc = news.latest()

ui.app_bar("이번 주 금융 뉴스", badge="AI 카드뉴스")
if doc is None:
    st.info("아직 카드뉴스가 없어요. 잠시 후 다시 열어 주세요.")
    if st.session_state.get(note_key):
        ui.muted(f"이유: {st.session_state[note_key]}")
    st.stop()
ui.muted(f"{doc['range']} 주의 카드뉴스 (최근 3주 정책뉴스에서 골랐어요) · 출처: {doc['source']} · AI가 정책뉴스 제목과 본문 앞부분만으로 정리했어요. 자세한 내용은 원문에서 확인해요.")
if stale:
    st.warning("이번 주 카드뉴스를 아직 만들지 못해서 가장 최근 카드뉴스를 보여 줘요.")

for i, card in enumerate(doc["cards"], start=1):
    with ui.card(f"news-{i}"):
        art, tone = news.cover(card)
        ui.news_cover(art, tone, card["headline"], card.get("number", ""), f"{i}/{len(doc['cards'])} · {card['news']['press']}")
        ui.muted(f"{card['news']['date']} · 정책브리핑")
        st.write(card["summary"])
        if card.get("learn"):  # 예전 저장본에는 없다
            st.success(f"📘 이 뉴스로 배우는 금융: {card['learn']}")
        st.info(f"나에게는? {card['why']}")
        if card["concept"] in concepts:
            ui.muted(f"관련 개념: {concepts[card['concept']]['name_ko']} · {concepts[card['concept']]['sections']['한 줄 정의']}")
        st.markdown(f"[원문 보기: {card['news']['title']}]({card['news']['link']})")

ui.section("이번 주 뉴스 퀴즈")
done_before = store.load_news_quiz()
already = ((done_before["student_id"] == student_id) & (done_before["week"] == doc["week"])).any()
with ui.card("news-quiz"):
    ui.muted(f"3문제를 모두 맞히면 {rewards.NEWS_POINTS}P를 받아요 (주마다 1번).")
    solved = 0
    for i, q in enumerate(doc["quiz"], start=1):
        choice = st.radio(f"{i}. {q['question']}", range(len(q["options"])), index=None,
                          format_func=lambda k, q=q: f"{'①②③'[k]} {q['options'][k]}",
                          key=f"news-quiz-{student_id}-{doc['week']}-{i}")
        if choice is not None:
            if choice + 1 == q["answer"]:
                solved += 1
                st.success("맞았어요!")
            else:
                st.warning("카드뉴스를 다시 읽어 볼까요?")

if solved == len(doc["quiz"]):
    if already:
        st.success("이번 주 뉴스 퀴즈 포인트는 이미 받았어요. 다음 주 카드뉴스도 기대해 주세요!")
    else:
        today = envelope.latest_date(store.load_allowance())
        store.append_news_quiz(student_id, doc["week"], today)
        events = rewards.apply_daily_cap(rewards.earn_events(
            student, store.load_trades(), store.load_missions(), store.load_allowance(),
            store.load_game_reviews(), store.load_news_quiz(), store.load_spend_quiz()))
        granted = next((e["granted"] for e in events if e["kind"] == "뉴스 퀴즈"
                        and e["label"].endswith(f"({doc['week']})")), 0)
        st.balloons()
        st.success(f"🎉 모두 맞혔어요! {granted}P를 받았어요." if granted else
                   f"🎉 모두 맞혔어요! 오늘 받을 수 있는 포인트(하루 {rewards.DAILY_CAP}P)를 다 받아서 이번엔 0P예요.")
