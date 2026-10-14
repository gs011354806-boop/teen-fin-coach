"""① Mistake-to-Lesson: 감지 → 질문 → 분류 → 개념 설명."""

import re

import streamlit as st

import ui_common as ui
from engine import detect, portfolio, store
from llm import client as llm
from ui_common import run_llm

ERROR_LABELS = {"FOMO": "놓칠까 봐 따라 사기(FOMO)", "과신": "과신", "근거 부족": "근거 부족"}
ANSWER_MARKS = "①②③④⑤"

student = ui.setup("실수에서 배우기", "🔍")
names = store.load_ticker_names()
prices = store.load_prices()
detections = detect.detect(store.load_trades(), prices, student)
lessons = store.load_lessons()
lessons = lessons[lessons["student_id"] == student["student_id"]]
reviewed = set(lessons["trade_id"])
moments = detect.mistakes(detections)

ui.app_bar("실수에서 배우기", badge="AI 코치")
ui.muted("결과(올랐는지, 내렸는지)가 아니라 살 때의 판단 과정을 함께 돌아봐요.")

if not moments:
    st.success("다시 살펴볼 매수가 없어요. 지금처럼 근거를 적고 나눠 담아 보세요.")
    st.stop()

by_id = {m["trade_id"]: m for m in moments}
trade_id = ui.card("pick").selectbox(
    "돌아볼 매수", list(by_id),
    format_func=lambda tid: (f"{by_id[tid]['date']} {names[by_id[tid]['ticker']]} "
                             f"{by_id[tid]['qty']}주 매수 · {', '.join(by_id[tid]['patterns'])}"
                             + (" · 돌아봄" if tid in reviewed else "")))
moment = by_id[trade_id]
past = detect.past_same_pattern(detections, trade_id)
state = st.session_state.setdefault("lessons", {}).setdefault(
    (student["student_id"], trade_id), {})
saved = lessons[lessons["trade_id"] == trade_id]
if not state and len(saved):  # 앱을 다시 켜도 이 매수의 가장 최근 기록을 보여 준다
    last = saved.iloc[-1]
    state.update({key: last[key] for key in ["question", "answer", "error_type", "reason",
                                              "concept", "explanation", "next_try"]},
                 saved_on=last["date"])

ui.section("이때 이런 모습이 보였어요")
facts = ui.card("facts")
for sentence in detect.fact_sentences(moment, names[moment["ticker"]]):
    facts.write(f"- {sentence}")
if past:
    facts.write(f"- 전에도 비슷한 모습이 {len(past)}번 있었어요: "
                + ", ".join(f"{p['date']} {names[p['ticker']]}" for p in past))

ui.section("1. 질문")
if "question" not in state:
    if st.button("AI 코치에게 질문 받기", type="primary", width="stretch"):
        with st.spinner("질문을 만들고 있어요..."):
            payload = detect.question_payload(student, moment, past, names)
            state["question"] = run_llm(lambda: llm.ask("mistake_question", payload))["question"]
        st.rerun()
    st.stop()

st.info(state["question"])

ui.section("2. 내 생각 적기")
if "error_type" not in state:
    with ui.card("answer"), st.form("answer", border=False):
        answer = st.text_area("그때 왜 샀는지 솔직하게 적어 보세요.")
        submitted = st.form_submit_button("답하기", type="primary", width="stretch")
    if submitted:
        if not answer.strip():
            st.error("한 줄이라도 적어 주세요.")
            st.stop()
        with st.spinner("생각을 정리하고 있어요..."):
            classified = run_llm(lambda: llm.ask(
                "classify_mistake", detect.classify_payload(moment, state["question"], answer)))
            concept_name = detect.pick_concept(classified["error_type"], moment["patterns"])
            concept = store.load_concepts()[concept_name]
            sections = concept["sections"]
            first_check = re.sub(r"^\d+\.\s*", "",
                                 sections["다음엔 이렇게 확인해 보세요"].splitlines()[0])
            explained = run_llm(lambda: llm.ask(
                "explain_concept",
                detect.explain_payload(student, moment, classified["error_type"], answer, concept),
                default={"explanation": sections["한 줄 정의"], "next_try": first_check}))
        record = {"student_id": student["student_id"], "trade_id": trade_id,
                  "date": portfolio.latest_date(prices), "patterns": moment["patterns"],
                  "question": state["question"], "answer": answer, "concept": concept_name,
                  **classified, **explained}
        store.append_lesson(record)
        state.update(answer=" ".join(answer.split()), concept=concept_name,
                     saved_on=record["date"], **classified, **explained)
        st.rerun()
    st.stop()

with ui.card("result"):
    st.write(f"> {state['answer']}")
    if state["error_type"] in ERROR_LABELS:
        st.write(f"이번 판단은 **{ERROR_LABELS[state['error_type']]}**에 가까워 보여요.")
    elif state["reason"]:
        st.write("이유를 잘 적었어요. 그래도 이때 보인 모습을 한 번 더 살펴봐요.")
    else:  # 분류에 실패해 기본값이 온 경우: 판단을 단정하지 않는다
        st.write("이때 보인 모습을 함께 살펴봐요.")
    if state["reason"]:
        ui.muted(state["reason"])

concept = store.load_concepts()[state["concept"]]
ui.section(f"3. 배워 보기: {concept['name_ko']}")
with ui.card("concept"):
    st.write(state["explanation"])
    st.success(f"다음엔 이렇게 해 봐요: {state['next_try']}")
    st.markdown(concept["sections"]["다음엔 이렇게 확인해 보세요"])

ui.section("확인 문제")
with ui.card("quiz"):
    quiz = concept["quiz"]
    choice = st.radio(quiz["질문"], range(len(quiz["보기"])), index=None,
                      format_func=lambda i: f"{ANSWER_MARKS[i]} {quiz['보기'][i]}")
    if choice is not None:
        if ANSWER_MARKS[choice] == quiz["정답"]:
            st.success("맞았어요!")
        else:
            st.warning("다시 한 번 생각해 볼까요?")

ui.muted(f"{state['saved_on']}에 기록했어요."
         + (f" 이 매수는 지금까지 {len(saved)}번 돌아봤어요." if len(saved) > 1 else ""))
if st.button("다시 답해 보기", width="stretch"):
    st.session_state["lessons"][(student["student_id"], trade_id)] = {"retry": True}
    st.rerun()
