"""가상 학생 3명의 4주치 행동 데이터와 가상 주가를 만든다.

실행: python data/make_sample_data.py
시드를 고정했기 때문에 몇 번을 실행해도 같은 파일이 나온다.
형식은 docs/DATA.md를 따른다.
"""

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
START = date(2026, 9, 7)  # 월요일
WEEKS = 4
SURGE_PCT = 10  # 급등 추격 기준 (docs/PLAN.md)
CONCENTRATION_PCT = 60  # 몰빵 기준 (docs/PLAN.md)

DATA_DIR = Path(__file__).resolve().parent

STUDENTS = [
    {"student_id": "S01", "name": "민지", "grade": "중2", "type": "몰빵형",
     "weekly_allowance": 20000, "virtual_cash": 1000000,
     "envelope_ratio": {"SPEND": 50, "SAVE": 30, "INVEST": 20},
     "saving_goal": {"item": "에어팟", "amount": 250000}},
    {"student_id": "S02", "name": "준호", "grade": "중3", "type": "저축 실패형",
     "weekly_allowance": 15000, "virtual_cash": 1000000,
     "envelope_ratio": {"SPEND": 60, "SAVE": 30, "INVEST": 10},
     "saving_goal": {"item": "운동화", "amount": 150000}},
    {"student_id": "S03", "name": "서연", "grade": "고1", "type": "균형형",
     "weekly_allowance": 25000, "virtual_cash": 1000000,
     "envelope_ratio": {"SPEND": 48, "SAVE": 40, "INVEST": 12},
     "saving_goal": {"item": "자전거", "amount": 300000}},
]

# 가상 가격의 시작값. 실제 시세가 아니다.
BASE_PRICES = {
    "005930": 61000,
    "000660": 180000,
    "035420": 200000,
    "035720": 40000,
    "005380": 150000,
}
TICKER_NAMES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "005380": "현대차",
}
SURGE = ("035720", date(2026, 9, 16))  # 이 날 하루만 전일 대비 +10% 이상

# (날짜, 종목, 매수/매도, 수량, 일지)
TRADE_PLAN = {
    "S01": [
        ("2026-09-08", "005930", "BUY", 5, "계속 오를 것 같아서"),
        ("2026-09-10", "005930", "BUY", 4, ""),
        ("2026-09-16", "035720", "BUY", 3, "급등해서"),
        ("2026-09-18", "005930", "BUY", 3, "친구가 샀대"),
        ("2026-09-24", "035720", "SELL", 3, ""),
        ("2026-09-29", "005930", "BUY", 2, "더 오를듯"),
    ],
    "S02": [
        ("2026-09-09", "035420", "BUY", 1, "네이버를 자주 써서 한 주 사 봤음"),
        ("2026-09-10", "005930", "BUY", 3, ""),
        ("2026-09-22", "035720", "BUY", 4, "카카오톡을 매일 쓰니까 조금만 삼"),
    ],
    "S03": [
        ("2026-09-07", "005930", "BUY", 3, "반도체 수요가 늘 것 같아서 조금만 삼"),
        ("2026-09-08", "005380", "BUY", 1, "전기차 판매 기사를 읽고 한 주만 삼"),
        ("2026-09-10", "035720", "BUY", 4, "한 종목에 몰리지 않게 나눠서 삼"),
        ("2026-09-15", "000660", "BUY", 1, "같은 업종이지만 회사를 나눠 보려고"),
        ("2026-09-23", "005930", "SELL", 1, "비중이 커져서 한 주만 팔아 맞춤"),
        ("2026-09-30", "035720", "BUY", 1, "비중이 가장 작은 종목을 조금 채움"),
    ],
}

# 주간 용돈을 봉투에 나누는 금액 (원)
ENVELOPE_SPLIT = {
    "S01": {"SPEND": 10000, "SAVE": 6000, "INVEST": 4000},
    "S02": {"SPEND": 9000, "SAVE": 4500, "INVEST": 1500},
    "S03": {"SPEND": 12000, "SAVE": 10000, "INVEST": 3000},
}

# 주차별 지출 계획: (요일 범위, 그 구간에 쓸 수 있는 최대 금액)
# S02는 목요일마다 모으기 봉투에서 꺼내 쓴다.
SPEND_PLAN = {
    "S01": {"phases": [((0, 6), 9000)], "save_withdraw": [0, 0, 0, 0]},
    "S02": {"phases": [((0, 2), 9000)], "save_withdraw": [4000, 3500, 4500, 3000]},
    "S03": {"phases": [((0, 6), 8000)], "save_withdraw": [0, 0, 0, 0]},
}

# 카테고리별 (메모 후보, 최소 금액, 최대 금액)
MENU = {
    "CONVENIENCE": (["편의점", "편의점 간식", "편의점 음료"], 1500, 4500),
    "CAFE": (["카페", "버블티", "카페 음료"], 2500, 5000),
    "FOOD": (["떡볶이", "분식집", "김밥"], 3000, 5500),
    "SHOPPING": (["문구점", "다이소", "스티커"], 2000, 5000),
    "TRANSPORT": (["버스카드 충전"], 2000, 3000),
    "OTHER": (["코인노래방", "PC방"], 2000, 4000),
}
CATEGORY_WEIGHTS = {
    "S01": {"CONVENIENCE": 3, "CAFE": 2, "FOOD": 2, "SHOPPING": 1, "TRANSPORT": 1, "OTHER": 1},
    "S02": {"CONVENIENCE": 5, "CAFE": 4, "FOOD": 2, "SHOPPING": 1, "TRANSPORT": 1, "OTHER": 1},
    "S03": {"CONVENIENCE": 2, "CAFE": 1, "FOOD": 2, "SHOPPING": 1, "TRANSPORT": 2, "OTHER": 1},
}


def trading_days():
    days = [START + timedelta(days=i) for i in range(WEEKS * 7)]
    return [d for d in days if d.weekday() < 5]


def make_prices(rng):
    prices = {}
    for ticker, base in BASE_PRICES.items():
        rows = []
        close = base
        for i, day in enumerate(trading_days()):
            if i > 0:
                change = rng.uniform(-0.025, 0.028)
                if (ticker, day) == SURGE:
                    change = 0.13
                close = round(close * (1 + change) / 100) * 100
            rows.append({"date": day.isoformat(), "close": close})
        prices[ticker] = rows
    return prices


def make_trades(prices):
    close_on = {t: {r["date"]: r["close"] for r in rows} for t, rows in prices.items()}
    rows = []
    for student_id, plan in TRADE_PLAN.items():
        for day, ticker, side, qty, journal in plan:
            rows.append({"student_id": student_id, "date": day, "ticker": ticker,
                         "side": side, "qty": qty, "price": close_on[ticker][day],
                         "journal": journal})
    rows.sort(key=lambda r: (r["date"], r["student_id"]))
    return [{"trade_id": f"T{i:04d}", **r} for i, r in enumerate(rows, start=1)]


def pick_spending(rng, student_id, week_start, day_range, budget):
    """day_range 안에서 budget을 넘지 않게 지출 내역을 고른다."""
    weights = CATEGORY_WEIGHTS[student_id]
    rows, total = [], 0
    for _ in range(30):
        category = rng.choices(list(weights), weights=list(weights.values()))[0]
        memos, low, high = MENU[category]
        amount = rng.randrange(low, high + 100, 100)
        if total + amount > budget:
            continue
        total += amount
        day = week_start + timedelta(days=rng.randint(*day_range))
        rows.append({"student_id": student_id, "date": day.isoformat(),
                     "envelope": "SPEND", "amount": -amount,
                     "category": category, "memo": rng.choice(memos)})
    return rows


def make_allowance(rng):
    rows = []
    for student in STUDENTS:
        student_id = student["student_id"]
        plan = SPEND_PLAN[student_id]
        for week in range(WEEKS):
            week_start = START + timedelta(days=7 * week)
            week_rows = []
            for envelope, amount in ENVELOPE_SPLIT[student_id].items():
                week_rows.append({"student_id": student_id, "date": week_start.isoformat(),
                                  "envelope": envelope, "amount": amount,
                                  "category": "OTHER", "memo": "용돈 입금"})
            for day_range, budget in plan["phases"]:
                week_rows += pick_spending(rng, student_id, week_start, day_range, budget)
            withdraw = plan["save_withdraw"][week]
            if withdraw:
                thursday = (week_start + timedelta(days=3)).isoformat()
                week_rows.append({"student_id": student_id, "date": thursday,
                                  "envelope": "SAVE", "amount": -withdraw,
                                  "category": "OTHER", "memo": "모으기에서 꺼냄"})
                week_rows.append({"student_id": student_id, "date": thursday,
                                  "envelope": "SPEND", "amount": withdraw,
                                  "category": "OTHER", "memo": "모으기에서 옮김"})
                week_rows += pick_spending(rng, student_id, week_start, (3, 6), withdraw)
            rows += week_rows
    # 안정 정렬이라 같은 날에는 위에서 넣은 순서(입금·이동 → 지출)가 유지된다.
    rows.sort(key=lambda r: (r["date"], r["student_id"]))
    return [{"tx_id": f"A{i:04d}", **r} for i, r in enumerate(rows, start=1)]


def max_weights(student, trades, prices, as_of):
    """as_of 날짜 기준 최대 종목 비중(%) 두 가지: (보유 종목 합 기준, 현금 포함 기준)."""
    cash = student["virtual_cash"]
    holdings = {}
    for t in trades:
        if t["student_id"] != student["student_id"] or t["date"] > as_of:
            continue
        sign = 1 if t["side"] == "BUY" else -1
        holdings[t["ticker"]] = holdings.get(t["ticker"], 0) + sign * t["qty"]
        cash -= sign * t["qty"] * t["price"]
    close_on = {t: {r["date"]: r["close"] for r in rows} for t, rows in prices.items()}
    values = [qty * close_on[ticker][as_of] for ticker, qty in holdings.items() if qty > 0]
    if not values:
        return 0.0, 0.0
    return max(values) / sum(values) * 100, max(values) / (sum(values) + cash) * 100


def check_design(trades, prices):
    """성향별 설계 의도가 데이터에 실제로 들어갔는지 확인한다."""
    for student in STUDENTS:
        split = ENVELOPE_SPLIT[student["student_id"]]
        for envelope, pct in student["envelope_ratio"].items():
            assert split[envelope] == student["weekly_allowance"] * pct // 100
    fridays = [(START + timedelta(days=7 * w + 4)).isoformat() for w in range(WEEKS)]
    for student in STUDENTS:
        if student["type"] == "몰빵형":
            assert min(max_weights(student, trades, prices, fridays[-1])) >= CONCENTRATION_PCT
        else:
            for friday in fridays:
                assert max(max_weights(student, trades, prices, friday)) < CONCENTRATION_PCT, \
                    (student["student_id"], friday)
    rows = prices[SURGE[0]]
    surge_day = SURGE[1].isoformat()
    for prev, cur in zip(rows, rows[1:]):
        if cur["date"] == surge_day:
            assert (cur["close"] / prev["close"] - 1) * 100 >= SURGE_PCT


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(out_dir=DATA_DIR):
    students_dir = Path(out_dir) / "students"
    prices_dir = Path(out_dir) / "prices"
    rng = random.Random(SEED)
    prices = make_prices(rng)
    trades = make_trades(prices)
    allowance = make_allowance(rng)
    check_design(trades, prices)

    students_dir.mkdir(parents=True, exist_ok=True)
    prices_dir.mkdir(parents=True, exist_ok=True)
    with open(students_dir / "students.json", "w", encoding="utf-8") as f:
        json.dump(STUDENTS, f, ensure_ascii=False, indent=2)
        f.write("\n")
    write_csv(students_dir / "trades.csv", trades,
              ["trade_id", "student_id", "date", "ticker", "side", "qty", "price", "journal"])
    write_csv(students_dir / "allowance.csv", allowance,
              ["tx_id", "student_id", "date", "envelope", "amount", "category", "memo"])
    # 미션은 6번 기능(AI 행동 미션 루프)에서 채운다. 지금은 헤더만 둔다.
    # Mistake-to-Lesson 기록은 5번 화면에서 학생이 답할 때 쌓인다. 지금은 헤더만 둔다.
    write_csv(students_dir / "lessons.csv", [],
              ["lesson_id", "student_id", "trade_id", "date", "patterns", "question", "answer",
               "error_type", "reason", "concept", "explanation", "next_try"])
    write_csv(students_dir / "missions.csv", [],
              ["mission_id", "student_id", "week_start", "skill", "text",
               "target_metric", "target_value", "result_value", "done", "level"])
    write_csv(students_dir / "point_spend.csv", [],
              ["spend_id", "student_id", "date", "kind", "item", "points"])
    write_csv(students_dir / "coaching_weeks.csv", [],
              ["student_id", "week_start", "diag_week_start", "good", "practice", "summary",
               "plan", "plan_weekly_save", "goal_date_before", "replay_comment",
               "goal_date_after"])
    for ticker, rows in prices.items():
        write_csv(prices_dir / f"{ticker}.csv", rows, ["date", "close"])
    tickers = [{"ticker": t, "name": TICKER_NAMES[t]} for t in prices]
    with open(prices_dir / "tickers.json", "w", encoding="utf-8") as f:
        json.dump(tickers, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"학생 {len(STUDENTS)}명, 거래 {len(trades)}건, 용돈 내역 {len(allowance)}건, "
          f"종목 {len(prices)}개 생성 완료")


if __name__ == "__main__":
    main()
