"""18번 금융 개념 물어보기: 학생 질문에 content/concepts 개념 카드 안에서만 답한다."""

import streamlit as st

import ui_common as ui
from engine import concept_qa, store

student = ui.setup("개념 물어보기", "💬", coach=False)  # 이 화면 자체가 개념 물어보기라 떠 있는 버튼은 끈다
student_id = student["student_id"]
concepts = store.load_concepts()

ui.app_bar("개념 물어보기", badge="AI 코치")
ui.muted("검토한 금융 개념 카드 안에서만 답해요. 카드에 없는 내용은 지어내지 않아요.")


def ask(question):
    ui.ask_concept(student_id, question)


with ui.card("ask"):
    with st.form("ask", clear_on_submit=True, border=False):
        question = st.text_input("궁금한 금융 개념을 물어보세요", max_chars=concept_qa.MAX_QUESTION_CHARS,
                                 placeholder="예: 복리가 뭐예요?")
        submitted = st.form_submit_button("물어보기", type="primary", width="stretch")
    ui.muted("이런 걸 물어볼 수 있어요")
    picked = None
    for i, example in enumerate(concept_qa.EXAMPLES):
        if st.button(example, key=f"example-{i}", width="stretch"):
            picked = example

if submitted or picked:
    with st.spinner("개념 카드에서 찾고 있어요..."):
        ask(picked or question)
    st.rerun()

chat = st.session_state.get("concept_chat", {}).get(student_id, [])
for i, item in enumerate(reversed(chat)):
    ui.section(f"Q. {item['question']}")
    with ui.card(f"answer-{len(chat) - i}"):
        if item["concept"] in concepts:
            concept = concepts[item["concept"]]
            st.info(item["answer"])
            ui.muted(f"출처: 개념 카드 · {concept['name_ko']}")
            ui.concept_card(concept, key=f"ask-{len(chat) - i}")
        elif item["concept"] == concept_qa.ADVICE:
            st.info(concept_qa.ADVICE_TEXT)
            ui.concept_card(concepts[concept_qa.ADVICE_CONCEPT], key=f"ask-{len(chat) - i}")
        else:
            st.warning("아직 준비된 내용이 없어요. 선생님이나 보호자께 물어보거나, 다른 질문을 해 보세요.")
            ui.muted("이 질문은 개념 카드를 늘릴 때 참고하도록 기록해 둘게요.")
