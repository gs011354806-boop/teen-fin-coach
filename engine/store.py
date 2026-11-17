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
NEWS_QUIZ_PATH = DATA_DIR / "students" / "news_quiz.csv"
SPEND_QUIZ_PATH = DATA_DIR / "students" / "spend_quiz.csv"  # 23-1번 쓰기 봉투 내 소비 퀴즈
MISSION_RUNS_PATH = DATA_DIR / "students" / "mission_runs.csv"  # 28번 미션 탭 (소비/투자 미션)
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
NEWS_QUIZ_COLUMNS = ["student_id", "week", "date"]
SPEND_QUIZ_COLUMNS = ["student_id", "date"]
MISSION_RUN_COLUMNS = ["run_id", "student_id", "track", "option", "title", "metric", "category",
                       "baseline", "target", "direction", "start_date", "end_date", "reward_points",
                       "status", "parent_request", "current", "completion_rate", "points", "finished_date"]
MISSION_COLUMNS = ["mission_id", "student_id", "week_start", "skill", "text", "target_metric",
                   "target_value", "result_value", "done", "level"]
COACHING_COLUMNS = ["student_id", "week_start", "diag_week_start", "good", "practice", "summary",
                    "plan", "plan_weekly_save", "goal_date_before", "replay_comment",
                    "goal_date_after"]
SPEND_COLUMNS = ["spend_id", "student_id", "date", "kind", "item", "points"]
PRECHECK_COLUMNS = ["check_id", "student_id", "date", "mode", "ticker", "qty", "patterns", "question",
                    "decision", "added_reason", "trade_id"]


def load_students(path=None):
    path = path or STUDENTS_PATH  # 기본값을 부를 때 읽는다 (테스트에서 경로를 바꿀 수 있게)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_ticker_names(prices_dir=PRICES_DIR):
    """{종목코드: 종목명}"""
    tickers = json.loads((Path(prices_dir) / "tickers.json").read_text(encoding="utf-8"))
    return {t["ticker"]: t["name"] for t in tickers}


def load_prices(prices_dir=PRICES_DIR):
    """{종목코드: DataFrame(date, close)}"""
    return {p.stem: pd.read_csv(p, dtype={"date": str, "close": int})
            for p in sorted(Path(prices_dir).glob("*.csv"))}


def load_trades(path=None):
    path = path or TRADES_PATH  # 기본값을 부를 때 읽는다 (테스트에서 경로를 바꿀 수 있게)
    return pd.read_csv(path, keep_default_na=False,
                       dtype={"trade_id": str, "student_id": str, "date": str, "ticker": str,
                              "side": str, "qty": int, "price": int, "journal": str})


def append_trade(student_id, date, ticker, side, qty, price, journal, path=None, prefix="T"):
    """거래 한 줄을 추가하고 새 trade_id를 돌려준다. 일지는 비어 있어도 된다.
    prefix: 시나리오 T, 실제 시세 모드 R (5-1 기록의 trade_id가 겹치지 않게)."""
    path = path or TRADES_PATH  # 기본값을 부를 때 읽는다 (테스트에서 경로를 바꿀 수 있게)
    trades = load_trades(path)
    last = max((int(t[1:]) for t in trades["trade_id"]), default=0)
    trade_id = f"{prefix}{last + 1:04d}"
    journal = " ".join(journal.split())
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([trade_id, student_id, date, ticker, side, qty, price, journal])
    return trade_id


def load_allowance(path=None):
    path = path or ALLOWANCE_PATH  # 기본값을 부를 때 읽는다 (테스트에서 경로를 바꿀 수 있게)
    return pd.read_csv(path, keep_default_na=False,
                       dtype={"tx_id": str, "student_id": str, "date": str, "envelope": str,
                              "amount": int, "category": str, "memo": str})


def append_allowance(student_id, date, entries, path=None):
    """entries: [(envelope, amount, category, memo)]. 새로 붙인 tx_id 목록을 돌려준다."""
    path = path or ALLOWANCE_PATH  # 기본값을 부를 때 읽는다 (테스트에서 경로를 바꿀 수 있게)
    allowance = load_allowance(path)
    last = max((int(t[1:]) for t in allowance["tx_id"]), default=0)
    tx_ids = []
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for offset, (envelope, amount, category, memo) in enumerate(entries, start=1):
            tx_ids.append(f"A{last + offset:04d}")
            writer.writerow([tx_ids[-1], student_id, date, envelope, amount, category, memo])
    return tx_ids


def save_envelope_ratio(student_id, ratio, path=None):
    path = path or STUDENTS_PATH  # 기본값을 부를 때 읽는다 (테스트에서 경로를 바꿀 수 있게)
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


def load_news_quiz(path=None):
    """22번 이번 주 금융 뉴스 퀴즈를 모두 맞힌 기록 (주차마다 1번, 포인트 계산에 쓴다)."""
    return _load_table(path or NEWS_QUIZ_PATH, NEWS_QUIZ_COLUMNS)


def append_news_quiz(student_id, week, date, path=None):
    path = path or NEWS_QUIZ_PATH
    done = load_news_quiz(path)
    row = {"student_id": student_id, "week": week, "date": date}
    _save_table(pd.concat([done, pd.DataFrame([row])], ignore_index=True), path, NEWS_QUIZ_COLUMNS)


def load_spend_quiz(path=None):
    """23-1번 쓰기 봉투 내 소비 퀴즈를 모두 맞힌 기록 (하루 1번, 포인트 계산에 쓴다)."""
    return _load_table(path or SPEND_QUIZ_PATH, SPEND_QUIZ_COLUMNS)


def append_spend_quiz(student_id, date, path=None):
    path = path or SPEND_QUIZ_PATH
    done = load_spend_quiz(path)
    row = {"student_id": student_id, "date": date}
    _save_table(pd.concat([done, pd.DataFrame([row])], ignore_index=True), path, SPEND_QUIZ_COLUMNS)


def load_mission_runs(path=None):
    """28번 미션 탭에서 시작한 미션 (track: spend | invest, status: active | completed).
    숫자 칸도 문자열로 읽는다 (engine/spend_mission.py가 바꿔 쓴다)."""
    return _load_table(path or MISSION_RUNS_PATH, MISSION_RUN_COLUMNS)


def append_mission_run(row, path=None):
    """새 미션 한 줄. run_id(R0001…)를 붙여 돌려준다."""
    path = path or MISSION_RUNS_PATH
    runs = load_mission_runs(path)
    run_id = f"MR{len(runs) + 1:04d}"
    full = {c: "" for c in MISSION_RUN_COLUMNS} | {k: str(v) for k, v in row.items()} | {"run_id": run_id}
    _save_table(pd.concat([runs, pd.DataFrame([full])], ignore_index=True), path, MISSION_RUN_COLUMNS)
    return run_id


def update_mission_run(run_id, values, path=None):
    """미션 한 줄의 칸을 바꾼다 (주말 결과를 적을 때)."""
    path = path or MISSION_RUNS_PATH
    runs = load_mission_runs(path)
    for key, value in values.items():
        runs.loc[runs["run_id"] == run_id, key] = str(value)
    _save_table(runs, path, MISSION_RUN_COLUMNS)


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


# ---------- 자산섬 게임 상태 (game/tintin_island_handoff/ISLAND_GAME_SPEC.md 5장) ----------
# 게임이 새로 저장하는 것은 게임 상태뿐이다. 거래·저축·투자 데이터는 위 표를 그대로 읽는다.
ISLAND_TABLES = {
    "seeds": ("island_seeds.csv", ["seed_id", "student_id", "date", "amount", "reason", "key"]),  # 씨앗 증감 기록
    "tags": ("island_tags.csv", ["student_id", "item", "tag"]),            # 학생이 고친 필요/원함 태그
    "wish": ("island_wish.csv", ["wish_id", "student_id", "name", "price", "added_at", "decision",
                                 "decided_at"]),                           # 찜 바구니 (24시간 기다리기)
    "quests": ("island_quests.csv", ["student_id", "week", "quest_id", "title", "skill", "seeds",
                                     "run_id", "date"]),                   # 주간 결산에서 고른 퀘스트
    "prefs": ("island_prefs.csv", ["student_id", "key", "value"]),        # 복리 토글, 결산 확인 주
}


def island_path(name, data_dir=None):
    return Path(data_dir or DATA_DIR / "students") / ISLAND_TABLES[name][0]


def load_island(name, data_dir=None):
    """자산섬 게임 상태 표 (모든 값은 문자열). 파일이 없으면 빈 표."""
    return _load_table(island_path(name, data_dir), ISLAND_TABLES[name][1])


def save_island(name, table, data_dir=None):
    _save_table(table, island_path(name, data_dir), ISLAND_TABLES[name][1])


def append_island(name, row, data_dir=None):
    """한 줄 추가. seeds·wish는 번호(S0001·W0001)를 붙여 돌려준다."""
    columns = ISLAND_TABLES[name][1]
    table = load_island(name, data_dir)
    full = {c: "" for c in columns} | {k: str(v) for k, v in row.items()}
    prefix = {"seeds": ("seed_id", "S"), "wish": ("wish_id", "W")}.get(name)
    if prefix:
        full[prefix[0]] = f"{prefix[1]}{len(table) + 1:04d}"
    save_island(name, pd.concat([table, pd.DataFrame([full])], ignore_index=True), data_dir)
    return full.get(prefix[0]) if prefix else None


# ---------- 자산섬 v2 게임 저장 (game2/tintin_island_handoff/ISLAND_GAME_SPEC.md 5장) ----------
# 게임 상태만 학생별로 저장한다. 앱의 실제 금융 데이터(용돈·거래·가상투자)와 섞지 않는다.
ISLAND_GAME_FILE = "island_game.json"


def _island_game_path(data_dir=None):
    return Path(data_dir or DATA_DIR / "students") / ISLAND_GAME_FILE


def load_island_game(student_id, data_dir=None):
    """학생의 게임 상태 dict (없으면 None)."""
    path = _island_game_path(data_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get(student_id)


def save_island_game(student_id, state, data_dir=None):
    path = _island_game_path(data_dir)
    games = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    games[student_id] = state
    path.write_text(json.dumps(games, ensure_ascii=False), encoding="utf-8")


# ---------- 투자 탭 동의 기반 2트랙 (invest/tintin_invest_handoff/INVEST_TAB_SPEC.md 4장) ----------
# 동의 상태·부모 안전장치·실전(Mock) 계좌·관심 종목·변경 요청·알림을 학생별로 저장한다.
# 기존 가상 계좌(trades.csv·real_trades.csv)는 그대로 두고 건드리지 않는다.
INVEST_PATH = DATA_DIR / "students" / "invest.json"


def load_invest(student_id, path=None):
    """학생의 투자 탭 상태 dict (없으면 None)."""
    path = Path(path or INVEST_PATH)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get(student_id)


def load_all_invest(path=None):
    path = Path(path or INVEST_PATH)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_invest(student_id, state, path=None):
    path = Path(path or INVEST_PATH)
    states = load_all_invest(path)
    states[student_id] = state
    path.write_text(json.dumps(states, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- 혜택 탭 배지 (돼지 저금통 황금 돼지 첫 도달, point/tintin_piggy/PIGGY_BANK_SPEC.md 3장) ----------
BADGES_PATH = DATA_DIR / "students" / "badges.csv"
BADGE_COLUMNS = ["student_id", "badge", "title", "date"]


def load_badges(path=None):
    return _load_table(path or BADGES_PATH, BADGE_COLUMNS)


def append_badge(student_id, badge, title, date, path=None):
    """같은 배지는 한 번만 남긴다. 새로 남겼으면 True."""
    path = Path(path or BADGES_PATH)
    table = load_badges(path)
    if ((table["student_id"] == student_id) & (table["badge"] == badge)).any():
        return False
    row = {"student_id": student_id, "badge": badge, "title": title, "date": date}
    _save_table(pd.concat([table, pd.DataFrame([row])], ignore_index=True), path, BADGE_COLUMNS)
    return True



# ---------- 오늘의 뉴스 기록 (NEWS_MARKET_SPEC.md 9장): 읽기 · 퀴즈 답 · 주말 복습 ----------
NEWS_READS_PATH = DATA_DIR / "students" / "news_reads.csv"
NEWS_ANSWERS_PATH = DATA_DIR / "students" / "news_answers.csv"
NEWS_REVIEWS_PATH = DATA_DIR / "students" / "news_reviews.csv"
NEWS_READ_COLUMNS = ["student_id", "day", "news_id", "date"]
NEWS_ANSWER_COLUMNS = ["student_id", "day", "news_id", "quiz_type", "choice", "correct", "retry", "date"]
NEWS_REVIEW_COLUMNS = ["student_id", "week", "qid", "choice", "correct", "date"]


def load_news_reads(path=None):
    return _load_table(path or NEWS_READS_PATH, NEWS_READ_COLUMNS)


def append_news_read(student_id, day, news_id, date, path=None):
    path = path or NEWS_READS_PATH
    table = load_news_reads(path)
    if ((table["student_id"] == student_id) & (table["day"] == day) & (table["news_id"] == news_id)).any():
        return
    row = {"student_id": student_id, "day": day, "news_id": news_id, "date": date}
    _save_table(pd.concat([table, pd.DataFrame([row])], ignore_index=True), path, NEWS_READ_COLUMNS)


def load_news_answers(path=None):
    return _load_table(path or NEWS_ANSWERS_PATH, NEWS_ANSWER_COLUMNS)


def append_news_answer(row, path=None):
    """퀴즈 답 한 줄. 같은 문제를 이미 풀었으면 retry=TRUE (포인트·정답률에 넣지 않는다)."""
    path = path or NEWS_ANSWERS_PATH
    table = load_news_answers(path)
    done = ((table["student_id"] == row["student_id"]) & (table["day"] == row["day"])
            & (table["news_id"] == row["news_id"])).any()
    full = {c: "" for c in NEWS_ANSWER_COLUMNS} | {k: str(v) for k, v in row.items()} | {"retry": "TRUE" if done else "FALSE"}
    _save_table(pd.concat([table, pd.DataFrame([full])], ignore_index=True), path, NEWS_ANSWER_COLUMNS)
    return not done


def load_news_reviews(path=None):
    return _load_table(path or NEWS_REVIEWS_PATH, NEWS_REVIEW_COLUMNS)


def append_news_review(row, path=None):
    path = path or NEWS_REVIEWS_PATH
    table = load_news_reviews(path)
    full = {c: "" for c in NEWS_REVIEW_COLUMNS} | {k: str(v) for k, v in row.items()}
    _save_table(pd.concat([table, pd.DataFrame([full])], ignore_index=True), path, NEWS_REVIEW_COLUMNS)


# ---------- 실전 준비 기준 (criteria/teengrow_ready/READY_SPEC.md 5장) ----------
# 학생별 {"state": {qualified_at, last_active_at, recheck_since}, "reflections": [...], "quiz": [...]}
# 진행 숫자는 저장하지 않고 기록에서 매번 계산한다 (engine/ready.evaluate).
READY_PATH = DATA_DIR / "students" / "ready.json"


def load_ready(student_id, path=None):
    path = Path(path or READY_PATH)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get(student_id) or {}


def save_ready(student_id, doc, path=None):
    path = Path(path or READY_PATH)
    docs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    docs[student_id] = doc
    path.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
