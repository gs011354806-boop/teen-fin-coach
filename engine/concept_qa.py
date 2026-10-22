"""18번 금융 개념 물어보기: AI가 content/concepts 안에서만 답하게 하는 재료와 검사. LLM 호출 금지.

- AI에게는 개념 파일 문장만 준다. AI는 그중 하나를 고르고(concept), 그 문장으로 쉽게 풀어 답한다.
- 맞는 파일이 없으면 NONE → 화면은 "아직 준비된 내용이 없어요" (지어내지 않는다, CLAUDE.md 8번).
- 무엇을 사고팔지 묻는 질문은 ADVICE → 화면은 고정 문구 (종목 추천 금지, CLAUDE.md 3번).
- 답에 쓴 숫자는 고른 개념 파일에 있는 숫자만 허용한다.
"""

from engine.growth import NUMBER

NONE, ADVICE = "NONE", "ADVICE"
MAX_QUESTION_CHARS = 100
EXAMPLES = ["복리가 뭐예요?", "왜 여러 종목에 나눠서 사야 해요?", "갖고 싶은 것과 필요한 것은 어떻게 구분해요?"]
ADVICE_TEXT = ("어떤 종목을 사거나 팔지는 AI 코치가 정해 주지 않아요. "
               "대신 스스로 판단할 때 확인할 것을 함께 볼 수 있어요.")
ADVICE_CONCEPT = "INVESTMENT_JOURNAL"  # ADVICE일 때 보여 줄 개념 카드


def concept_text(concept):
    s = concept["sections"]
    return " ".join([concept["name_ko"], s["한 줄 정의"], s["이런 행동이었어요"], s["다음엔 이렇게 확인해 보세요"]])


def payload(question, concepts):
    return {"question": question,
            "concepts": [{"id": cid, "name_ko": c["name_ko"], "definition": c["sections"]["한 줄 정의"],
                          "example": c["sections"]["이런 행동이었어요"],
                          "checks": c["sections"]["다음엔 이렇게 확인해 보세요"]}
                         for cid, c in concepts.items()],
            "special_ids": [NONE, ADVICE]}


def answer_check(concepts):
    def numbers(text):
        return {"".join(n.split()) for n in NUMBER.findall(text)}

    def check(result):
        cid = result["concept"]
        if cid not in concepts and cid not in (NONE, ADVICE):
            raise ValueError(f"없는 개념: {cid}")
        if cid in concepts:
            extra = numbers(result["answer"]) - numbers(concept_text(concepts[cid]))
            if extra:
                raise ValueError(f"개념 파일에 없는 숫자: {sorted(extra)}")
    return check


def clean(question):
    return " ".join(question.split())[:MAX_QUESTION_CHARS]
