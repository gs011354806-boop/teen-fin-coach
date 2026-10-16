"""가상투자 실수 패턴 감지와 Mistake-to-Lesson 재료 만들기. LLM 호출 금지.

패턴 기준은 docs/PLAN.md를 따른다.
- 급등 추격: 직전 거래일 대비 +10% 이상 오른 종목을 그날 매수
- 몰빵: 매수 직후 그 종목 비중이 총자산(주식 + 현금)의 60% 이상
- 근거 없음: 투자 일지가 비었거나 10자 미만 (공백 제외)
"""

import pandas as pd

from engine import portfolio

SURGE_PCT = 10
CONCENTRATION_PCT = 60
MIN_JOURNAL_CHARS = 10

SURGE, CONCENTRATION, NO_REASON = "급등 추격", "몰빵", "근거 없음"
PATTERNS = [SURGE, CONCENTRATION, NO_REASON]

ERROR_TYPES = ["FOMO", "과신", "근거 부족", "해당 없음"]
CONCEPT_FOR_ERROR = {"FOMO": "FOMO", "과신": "OVERCONFIDENCE", "근거 부족": "INVESTMENT_JOURNAL"}
CONCEPT_FOR_PATTERN = {SURGE: "FOMO", CONCENTRATION: "DIVERSIFICATION",
                       NO_REASON: "INVESTMENT_JOURNAL"}


def journal_chars(journal):
    """공백을 뺀 일지 글자 수."""
    return len("".join(journal.split()))


def detect(trades, prices, student):
    """학생의 매수마다 사실(그날 등락률, 매수 뒤 비중, 일지 글자 수)과 감지된 패턴을 시간순으로 돌려준다."""
    student_id = student["student_id"]
    mine = trades[trades["student_id"] == student_id].sort_values("date", kind="stable")
    results = []
    for i, t in enumerate(mine.itertuples()):
        if t.side != "BUY":
            continue
        so_far = mine.iloc[:i + 1]
        held = portfolio.holdings(so_far, student_id)
        cash = portfolio.cash_balance(student["virtual_cash"], so_far, student_id)
        rows = portfolio.position_rows(held, cash, portfolio.close_on(prices, t.date))
        weight = next(r["weight_pct"] for r in rows if r["ticker"] == t.ticker)
        change = portfolio.day_change_pct(prices[t.ticker], t.date)
        chars = journal_chars(t.journal)

        patterns = []
        if change is not None and change >= SURGE_PCT:
            patterns.append(SURGE)
        if weight >= CONCENTRATION_PCT:
            patterns.append(CONCENTRATION)
        if chars < MIN_JOURNAL_CHARS:
            patterns.append(NO_REASON)
        results.append({
            "trade_id": t.trade_id, "date": t.date, "ticker": t.ticker, "qty": int(t.qty),
            "journal": t.journal, "change_pct": None if change is None else round(change, 1),
            "weight_pct": round(weight), "journal_chars": chars, "patterns": patterns,
        })
    return results


def mistakes(detections):
    """패턴이 하나라도 있는 매수만, 최근 것이 위로."""
    return [d for d in reversed(detections) if d["patterns"]]


def past_same_pattern(detections, trade_id):
    """trade_id보다 앞선 매수 중 같은 패턴이 있었던 것들."""
    index = next(i for i, d in enumerate(detections) if d["trade_id"] == trade_id)
    current = set(detections[index]["patterns"])
    return [d for d in detections[:index] if current & set(d["patterns"])]


def pick_concept(error_type, patterns):
    """분류 결과에 맞는 개념. '해당 없음'이면 감지된 첫 패턴에 맞는 개념."""
    if error_type in CONCEPT_FOR_ERROR:
        return CONCEPT_FOR_ERROR[error_type]
    return CONCEPT_FOR_PATTERN[patterns[0]]


def fact_sentences(detection, ticker_name, before=False):
    """화면과 LLM에 줄 사실 문장. 수익률은 넣지 않는다.
    before=True: 아직 사기 전(15번 사기 전 1분 점검)이라 "사면 ~돼요"로 쓴다."""
    sentences = []
    if SURGE in detection["patterns"]:
        sentences.append(f"오늘 가격이 전 거래일보다 {detection['change_pct']:.1f}% 올라 있어요." if before else
                         f"산 날 가격이 전 거래일보다 {detection['change_pct']:.1f}% 올라 있었어요.")
    if CONCENTRATION in detection["patterns"]:
        sentences.append(f"이번에 사면 {ticker_name} 비중이 총자산의 {detection['weight_pct']}%가 돼요." if before else
                         f"이번에 사고 나서 {ticker_name} 비중이 총자산의 {detection['weight_pct']}%가 됐어요.")
    if NO_REASON in detection["patterns"]:
        if detection["journal"].strip():
            sentences.append(f"투자 일지에는 \"{detection['journal']}\"라고만 적혀 있어요." if before else
                             f"투자 일지에는 \"{detection['journal']}\"라고만 적었어요.")
        else:
            sentences.append("투자 일지가 비어 있어요." if before else "투자 일지를 비워 두었어요.")
    return sentences


def question_payload(student, detection, past, names, before=False):
    return {
        "student": {"name": student["name"], "grade": student["grade"]},
        "trade": {"date": detection["date"], "stock": names[detection["ticker"]],
                  "qty": detection["qty"], "journal": detection["journal"]},
        "patterns": detection["patterns"],
        "facts": fact_sentences(detection, names[detection["ticker"]], before),
        "past_same_pattern": [{"date": p["date"], "stock": names[p["ticker"]],
                               "patterns": p["patterns"], "journal": p["journal"]} for p in past],
    }


def classify_payload(detection, question, answer):
    return {"patterns": detection["patterns"], "journal": detection["journal"],
            "question": question, "answer": answer, "error_types": ERROR_TYPES}


def explain_payload(student, detection, error_type, answer, concept):
    sections = concept["sections"]
    return {
        "student": {"name": student["name"], "grade": student["grade"]},
        "patterns": detection["patterns"], "error_type": error_type, "answer": answer,
        "concept": {"name_ko": concept["name_ko"], "definition": sections["한 줄 정의"],
                    "example": sections["이런 행동이었어요"],
                    "checks": sections["다음엔 이렇게 확인해 보세요"]},
    }


PRECHECK_ID = "PRECHECK"


def precheck(trades, prices, student, ticker, qty, price, journal, day):
    """주문을 저장하기 전에, 이 매수가 감지 기준에 걸리는지 미리 본다 (15번 사기 전 1분 점검).
    (이 매수의 detection, 같은 패턴이 있었던 지난 매수 목록)을 돌려준다. 거래는 저장하지 않는다."""
    row = {"trade_id": PRECHECK_ID, "student_id": student["student_id"], "date": day, "ticker": ticker,
           "side": "BUY", "qty": int(qty), "price": int(price), "journal": journal}
    trial = pd.concat([trades, pd.DataFrame([row])], ignore_index=True)
    detections = detect(trial, prices, student)
    current = next(d for d in detections if d["trade_id"] == PRECHECK_ID)
    return current, past_same_pattern(detections, PRECHECK_ID)


def precheck_demo_key(patterns):
    """시연 모드 저장 응답 키. 수량에 따라 숫자가 바뀌므로 패턴 조합만 쓴다 (저장 질문엔 숫자·종목명 없음)."""
    return "|".join(p for p in PATTERNS if p in patterns)


def precheck_default_question(detection, ticker_name):
    """AI가 실패했을 때 쓰는 질문 (사실 문장 + 판단을 묻는 질문, 권유 없음)."""
    facts = fact_sentences(detection, ticker_name, before=True)
    return f"잠깐 확인해요. {facts[0]} 이 매수를 하려는 이유를 한 줄로 더 적어 볼까요?"
