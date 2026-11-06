"""data/ 아래 파일을 읽고 쓴다. 형식은 docs/DATA.md를 따른다."""

import csv
import json
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STUDENTS_PATH = DATA_DIR / "students" / "students.json"
TRADES_PATH = DATA_DIR / "students" / "trades.csv"
REAL_TRADES_PATH = DATA_DIR / "students" / "real_trades.csv"  # 실제 시세 모드의 가상 거래 (trade_id R0001…)
ALLOWANCE_PATH = DATA_DIR / "students" / "allowance.csv"
LESSONS_PATH = DATA_DIR / "students" / "lessons.csv"
MISSIONS_PATH = DATA_DIR / "students" / "missions.csv"
COACHING_PATH = DATA_DIR / "students" / "coaching_weeks.csv"
SPEND_PATH = DATA_DIR / "students" / "point_spend.csv"
DEMO_PATH = DATA_DIR / "students" / "demo_responses.json"
PRECHECK_PATH = DATA_DIR / "students" / "prechecks.csv"
RULES_PATH = DATA_DIR / "students" / "rules.csv"
QUESTIONS_PATH = DATA_DIR / "students" / "concept_questions.csv"
UNLOCKS_PATH = DATA_DIR / "students" / "unlocks.csv"
GAME_REVIEWS_PATH = DATA_DIR / "students" / "game_reviews.csv"
PRICES_DIR = DATA_DIR / "prices"
CONCEPTS_DIR = DATA_DIR.parent / "content" / "concepts"

TRADE_COLUMNS = ["trade_id", "student_id", "date", "ticker", "side", "qty", "price", "journal"]
LESSON_COLUMNS = ["lesson_id", "student_id", "trade_id", "date", "patterns", "question", "answer",
                  "followup_question", "followup_answer",
                  "error_type", "reason", "concept", "explanation", "next_try"]
RULE_COLUMNS = ["rule_id", "student_id", "date", "trade_id", "patterns", "rule"]
QUESTION_COLUMNS = ["question_id", "student_id", "date", "question", "concept"]
UNLOCK_COLUMNS = ["student_id", "stage", "date"]
GAME_REVIEW_COLUMNS = ["student_id", "date", "concept"]
MISSION_COLUMNS = ["mission_id", "student_id", "week_start", "skill", "text", "target_metric",
                   "target_value", "result_value", "done", "level"]
COACHING_COLUMNS = ["student_id", "week_start", "diag_week_start", "good", "practice", "summary",
                    "plan", "plan_weekly_save", "goal_date_before", "replay_comment",
                    "goal_date_after"]
SPEND_COLUMNS = ["spend_id", "student_id", "date", "kind", "item", "points"]
PRECHECK_COLUMNS = ["check_id", "student_id", "date", "mode", "ticker", "qty", "patterns", "question",
                    "decision", "added_reason", "trade_id"]


def load_students(path=STUDENTS_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_ticker_names(prices_dir=PRICES_DIR):
    """{종목코드: 종목명}"""
    tickers = json.loads((Path(prices_dir) / "tickers.json").read_text(encoding="utf-8"))
    return {t["ticker"]: t["name"] for t in tickers}


def load_prices(prices_dir=PRICES_DIR):
    """{종목코드: DataFrame(date, close)}"""
    return {p.stem: pd.read_csv(p, dtype={"date": str, "close": int})
            for p in sorted(Path(prices_dir).glob("*.csv"))}


def load_trades(path=TRADES_PATH):
    return pd.read_csv(path, keep_default_na=False,
                       dtype={"trade_id": str, "student_id": str, "date": str, "ticker": str,
                              "side": str, "qty": int, "price": int, "journal": str})


def append_trade(student_id, date, ticker, side, qty, price, journal, path=TRADES_PATH, prefix="T"):
    """거래 한 줄을 추가하고 새 trade_id를 돌려준다. 일지는 비어 있어도 된다.
    prefix: 시나리오 T, 실제 시세 모드 R (5-1 기록의 trade_id가 겹치지 않게)."""
    trades = load_trades(path)
    last = max((int(t[1:]) for t in trades["trade_id"]), default=0)
    trade_id = f"{prefix}{last + 1:04d}"
    journal = " ".join(journal.split())
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([trade_id, student_id, date, ticker, side, qty, price, journal])
    return trade_id


def load_allowance(path=ALLOWANCE_PATH):
    return pd.read_csv(path, keep_default_na=False,
                       dtype={"tx_id": str, "student_id": str, "date": str, "envelope": str,
                              "amount": int, "category": str, "memo": str})


def append_allowance(student_id, date, entries, path=ALLOWANCE_PATH):
    """entries: [(envelope, amount, category, memo)]. 새로 붙인 tx_id 목록을 돌려준다."""
    allowance = load_allowance(path)
    last = max((int(t[1:]) for t in allowance["tx_id"]), default=0)
    tx_ids = []
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for offset, (envelope, amount, category, memo) in enumerate(entries, start=1):
            tx_ids.append(f"A{last + offset:04d}")
            writer.writerow([tx_ids[-1], student_id, date, envelope, amount, category, memo])
    return tx_ids


def save_envelope_ratio(student_id, ratio, path=STUDENTS_PATH):
    students = load_students(path)
    for student in students:
        if student["student_id"] == student_id:
            student["envelope_ratio"] = ratio
    with open(path, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_concept(text):
    """content/concepts/*.md 한 개를 읽어 dict로 만든다. 형식은 _TEMPLATE.md를 따른다."""
    _, front, body = text.split("---", 2)
    meta = {}
    for line in front.strip().splitlines():
        key, value = (part.strip() for part in line.split(":", 1))
        if value.startswith("[") and value.endswith("]"):
            value = [item.strip() for item in value[1:-1].split(",") if item.strip()]
        meta[key] = value
    sections = {}
    for chunk in re.split(r"^## ", body, flags=re.M)[1:]:
        title, _, content = chunk.partition("\n")
        sections[title.strip()] = content.strip()
    quiz = {}
    for line in sections.get("확인 문제", "").splitlines():
        key, _, value = line.lstrip("- ").partition(":")
        quiz[key.strip()] = value.strip()
    if "보기" in quiz:
        quiz["보기"] = [opt.strip() for opt in re.split(r"[①②③④⑤]", quiz["보기"]) if opt.strip()]
    return {**meta, "sections": sections, "quiz": quiz}


def load_concepts(concepts_dir=CONCEPTS_DIR):
    """{concept: 내용}. 밑줄로 시작하는 파일(_TEMPLATE.md)은 뺀다."""
    concepts = {}
    for path in sorted(Path(concepts_dir).glob("*.md")):
        if not path.name.startswith("_"):
            concept = parse_concept(path.read_text(encoding="utf-8"))
            concepts[concept["concept"]] = concept
    return concepts


def load_lessons(path=None):
    """Mistake-to-Lesson 기록. patterns는 리스트로 돌려준다. 파일이 없으면 빈 표."""
    lessons = _load_table(path or LESSONS_PATH, LESSON_COLUMNS)  # 16번 전 파일은 후속 질문 칸이 빈 값
    lessons["patterns"] = [p.split("|") if p else [] for p in lessons["patterns"]]
    return lessons


def append_lesson(record, path=None):
    """기록 한 줄을 추가하고 새 lesson_id를 돌려준다. record에는 lesson_id를 뺀 모든 컬럼이 있어야 한다."""
    path = Path(path or LESSONS_PATH)
    lessons = load_lessons(path)
    last = max((int(t[1:]) for t in lessons["lesson_id"]), default=0)
    lesson_id = f"L{last + 1:04d}"
    row = {**record, "lesson_id": lesson_id, "patterns": "|".join(record["patterns"])}
    lessons["patterns"] = ["|".join(p) for p in lessons["patterns"]]
    _save_table(pd.concat([lessons, pd.DataFrame([row])], ignore_index=True), path, LESSON_COLUMNS)
    return lesson_id


def _load_table(path, columns):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=columns)
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in columns:  # 예전 헤더에 없던 컬럼은 빈 값으로 채운다
        if column not in table:
            table[column] = ""
    return table[columns]


def _save_table(table, path, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in table[columns].itertuples(index=False):
            writer.writerow([" ".join(str(v).split()) for v in row])


def load_missions(path=None):
    """미션 표 (모든 값은 문자열). 형식은 docs/DATA.md의 missions.csv."""
    return _load_table(path or MISSIONS_PATH, MISSION_COLUMNS)


def save_missions(missions, path=None):
    _save_table(missions, path or MISSIONS_PATH, MISSION_COLUMNS)


def load_coaching(path=None):
    """주차별 진단·대안 선택·Replay 해석. good/practice는 '|'로 구분된 문자열."""
    return _load_table(path or COACHING_PATH, COACHING_COLUMNS)


def save_coaching(coaching, path=None):
    _save_table(coaching, path or COACHING_PATH, COACHING_COLUMNS)


def next_mission_ids(missions, count):
    last = max((int(m[1:]) for m in missions["mission_id"]), default=0)
    return [f"M{last + i:04d}" for i in range(1, count + 1)]


def load_spends(path=None):
    """포인트 사용 기록 (먹이 주기, 가상 쿠폰 교환). 받은 포인트는 저장하지 않고 매번 계산한다."""
    return _load_table(path or SPEND_PATH, SPEND_COLUMNS)


def append_spend(student_id, date, kind, item, points, path=None):
    spends = load_spends(path)
    last = max((int(s[1:]) for s in spends["spend_id"]), default=0)
    row = {"spend_id": f"P{last + 1:04d}", "student_id": student_id, "date": date,
           "kind": kind, "item": item, "points": str(points)}
    _save_table(pd.concat([spends, pd.DataFrame([row])], ignore_index=True),
                path or SPEND_PATH, SPEND_COLUMNS)
    return row["spend_id"]


def load_demo(path=None):
    """시연 모드용 저장 응답. 파일이 없으면 빈 구조. 만드는 법: python data/make_demo_responses.py"""
    path = Path(path or DEMO_PATH)
    if not path.exists():
        return {"students": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def demo_response(student_id, prompt_name, key, path=None):
    """저장된 응답 dict 하나. 없으면 None."""
    if key is None:
        return None
    saved = load_demo(path)["students"].get(student_id, {}).get("responses", {})
    return saved.get(prompt_name, {}).get(key)


def demo_answer(student_id, trade_id, path=None):
    """5번 시연용 예시 학생 답. 없으면 None."""
    return load_demo(path)["students"].get(student_id, {}).get("answers", {}).get(trade_id)


def demo_followup_answer(student_id, trade_id, path=None):
    """16번 시연용 예시 꼬리 질문 답. 없으면 None."""
    return load_demo(path)["students"].get(student_id, {}).get("followup_answers", {}).get(trade_id)


def load_prechecks(path=None):
    """사기 전 1분 점검 기록. decision: BUY(그대로 주문) / CANCEL(다시 생각)."""
    return _load_table(path or PRECHECK_PATH, PRECHECK_COLUMNS)


def append_precheck(record, path=None):
    path = path or PRECHECK_PATH
    checks = load_prechecks(path)
    last = max((int(c[1:]) for c in checks["check_id"]), default=0)
    row = {**record, "check_id": f"C{last + 1:04d}", "patterns": "|".join(record["patterns"])}
    _save_table(pd.concat([checks, pd.DataFrame([row])], ignore_index=True), path, PRECHECK_COLUMNS)
    return row["check_id"]


def load_rules(path=None):
    """16번 나만의 규칙 (실수에서 배우기에서 학생이 직접 쓴 한 줄). patterns는 '|'로 구분된 문자열."""
    return _load_table(path or RULES_PATH, RULE_COLUMNS)


def append_rule(record, path=None):
    path = path or RULES_PATH
    rules = load_rules(path)
    last = max((int(r[1:]) for r in rules["rule_id"]), default=0)
    row = {**record, "rule_id": f"U{last + 1:04d}", "patterns": "|".join(record["patterns"])}
    _save_table(pd.concat([rules, pd.DataFrame([row])], ignore_index=True), path, RULE_COLUMNS)
    return row["rule_id"]


def load_unlocks(path=None):
    """9번 Skill Unlock 기록. 학생이 단계를 연 날 한 줄씩 (stage 2 = 실제 시세 연습, 3 = 실전 신청 시안)."""
    return _load_table(path or UNLOCKS_PATH, UNLOCK_COLUMNS)


def append_unlock(student_id, stage, date, path=None):
    path = path or UNLOCKS_PATH
    unlocks = load_unlocks(path)
    row = {"student_id": student_id, "stage": str(stage), "date": date}
    _save_table(pd.concat([unlocks, pd.DataFrame([row])], ignore_index=True), path, UNLOCK_COLUMNS)


def load_game_reviews(path=None):
    """21번 게임 1분 복습을 모두 맞힌 기록 (포인트 계산에 쓴다)."""
    return _load_table(path or GAME_REVIEWS_PATH, GAME_REVIEW_COLUMNS)


def append_game_review(student_id, date, concept, path=None):
    path = path or GAME_REVIEWS_PATH
    reviews = load_game_reviews(path)
    row = {"student_id": student_id, "date": date, "concept": concept}
    _save_table(pd.concat([reviews, pd.DataFrame([row])], ignore_index=True), path, GAME_REVIEW_COLUMNS)


def load_questions(path=None):
    """18번 개념 물어보기 기록. concept: 답에 쓴 개념 / NONE(콘텐츠 없음) / ADVICE(종목 추천 요청)."""
    return _load_table(path or QUESTIONS_PATH, QUESTION_COLUMNS)


def append_question(record, path=None):
    path = path or QUESTIONS_PATH
    questions = load_questions(path)
    last = max((int(q[1:]) for q in questions["question_id"]), default=0)
    row = {**record, "question_id": f"Q{last + 1:04d}"}
    _save_table(pd.concat([questions, pd.DataFrame([row])], ignore_index=True), path, QUESTION_COLUMNS)
    return row["question_id"]
