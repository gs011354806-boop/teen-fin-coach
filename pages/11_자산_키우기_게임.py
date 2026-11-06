"""21번 자산 키우기 게임.

떨어지는 단어 중 좋은 습관만 바구니로 받는다 → 결과 + AI 코치 한마디(실제 가상투자 행동과 연결)
→ 코인이 기준보다 적으면 1분 복습(개념 카드 + AI 퀴즈 2 + 카드 확인 문제 1)을 마쳐야 다시 도전.
계산(출제·코인·복습 개념)은 engine/game.py, AI는 문장과 퀴즈 문장만 만든다. 코인은 게임 안 점수다.
"""

import streamlit as st

import ui_common as ui
from engine import detect, envelope, game, rewards, store
from engine.growth import numbers_check

student = ui.setup("자산 키우기 게임", "🧺")
student_id = student["student_id"]
trades, prices, allowance = store.load_trades(), store.load_prices(), store.load_allowance()
concepts = store.load_concepts()
state = st.session_state.setdefault(f"game-{student_id}",
                                    {"round": 1, "result": None, "coach": None, "quiz": None})


def next_round():
    state.update(round=state["round"] + 1, result=None, coach=None, quiz=None, rewarded=None)


ui.app_bar("자산 키우기 게임", badge="AI 코치")
ui.muted(f"좋은 습관 단어는 바구니로 받고, 나쁜 습관 단어는 피해요. 코인은 게임 안 점수예요. "
         f"🪙 {game.PASS_COINS:,} 이상이면 바로 다시 도전하고, 적으면 1분 복습 뒤에 다시 도전해요.")

if state["result"] is None:
    boosted = game.boost_concepts(student, trades, prices, allowance)
    with ui.card("game"):
        value = ui.catch_game(game.deck(boosted, f"{student_id}-{state['round']}"), state["round"],
                              game.DURATION_SECONDS, game.START_COINS, game.GOOD_COINS, game.BAD_COINS)
    if boosted:
        ui.muted("내 연습에 맞춰 '" + "', '".join(concepts[c]["name_ko"] for c in boosted)
                 + "' 관련 단어가 더 자주 떨어져요.")
    if value and value.get("round") == state["round"]:
        state["result"] = game.summary(value.get("caught", []), value.get("missed", []))
        st.rerun()
    st.stop()

result = state["result"]
ui.section("결과")
with ui.card("game-result"):
    st.metric("모은 자산", f"🪙 {result['coins']:,}")
    if result["good"]:
        ui.muted("받은 좋은 습관")
        ui.chips(result["good"], "good")
    if result["bad"]:
        ui.muted("받아 버린 나쁜 습관")
        ui.chips([f"{w} ×{n}" if n > 1 else w for w, n in result["bad"].items()], "practice")
    for w in list(result["bad"]) + result["missed"][:2]:
        verb = "받았어요" if w in result["bad"] else "놓쳤어요"
        st.write(f"- **{w}** {verb} · {game.BY_WORD[w]['reason']}")

ui.section("AI 코치 한마디")
with ui.card("game-coach"):
    if state["coach"] is None:
        sentences = game.facts(result, detect.detect(trades, prices, student))
        with st.spinner("AI 코치가 결과를 보고 있어요..."):
            state["coach"] = ui.ask_ai(
                "game_coach", game.coach_payload(student, result, sentences), student_id,
                default=game.default_coach(result),
                check=lambda r: numbers_check(sentences)({"story": r["message"], "next": ""}))["message"]
    st.info(state["coach"])

if result["passed"]:
    st.success(f"🪙 {game.PASS_COINS:,} 이상 모았어요!")
    st.button("다시 도전", type="primary", width="stretch", on_click=next_round)
    st.stop()

ui.section("1분 복습")
concept = concepts[result["review"][0]] if result["review"] else concepts["DIVERSIFICATION"]
with ui.card("game-review"):
    ui.muted(f"🪙 {game.PASS_COINS:,}보다 적게 모았어요. 놓친 습관을 1분만 복습하면 다시 도전할 수 있어요.")
    st.markdown(f"**{concept['name_ko']}** · {concept['sections']['한 줄 정의']}")
    st.markdown(concept["sections"]["다음엔 이렇게 확인해 보세요"])

    if state["quiz"] is None:
        with st.spinner("AI 코치가 복습 문제를 만들고 있어요..."):
            made = ui.ask_ai("game_quiz", game.quiz_payload(concept), student_id, demo_key=concept["concept"],
                             default=ui.llm.SPECS["game_quiz"]["default"], check=game.quiz_check(concept))
        state["quiz"] = game.ai_quiz_items(made) + [game.card_quiz(concept)]

    solved = 0
    for i, q in enumerate(state["quiz"], start=1):
        choice = st.radio(f"{i}. {q['question']}", range(len(q["options"])), index=None,
                          format_func=lambda k, q=q: f"{'①②③'[k]} {q['options'][k]}",
                          key=f"game-quiz-{student_id}-{state['round']}-{i}")
        if choice is not None:
            if choice + 1 == q["answer"]:
                solved += 1
                st.success("맞았어요!")
            else:
                st.warning("다시 한 번 생각해 볼까요?")

done = solved == len(state["quiz"])
if not done:
    ui.muted(f"문제 {len(state['quiz'])}개를 모두 맞히면 {rewards.REVIEW_POINTS}P를 받고 다시 도전할 수 있어요.")
elif not state.get("rewarded"):  # 복습을 다 맞힌 순간 한 번만 기록 → 포인트는 기록에서 계산 (하루 상한 안에서)
    today = envelope.latest_date(allowance)
    already = store.load_game_reviews()
    duplicate = ((already["student_id"] == student_id) & (already["date"] == today)
                 & (already["concept"] == concept["concept"])).any()
    if not duplicate:
        store.append_game_review(student_id, today, concept["concept"])
    events = rewards.apply_daily_cap(rewards.earn_events(student, trades, store.load_missions(), allowance,
                                                         store.load_game_reviews()))
    granted = next((e["granted"] for e in reversed(events) if e["kind"] == "복습"
                    and e["label"].endswith(concept["name_ko"]) and e["date"] == today), 0)
    state["rewarded"] = ("이미 오늘 이 개념 복습 포인트를 받았어요." if duplicate
                         else f"🎉 1분 복습 완료! {granted}P를 받았어요." if granted
                         else "🎉 1분 복습 완료! 오늘 받을 수 있는 포인트(하루 "
                         f"{rewards.DAILY_CAP}P)를 다 받아서 이번엔 0P예요.")
if done:
    st.success(state["rewarded"])
st.button("다시 도전", type="primary", width="stretch", disabled=not done, on_click=next_round)

if len(result["review"]) > 1:
    with ui.card("game-review-more"):
        ui.concept_card(concepts[result["review"][1]], key=f"game-more-{state['round']}",
                        intro="함께 보면 좋은 개념이에요")
