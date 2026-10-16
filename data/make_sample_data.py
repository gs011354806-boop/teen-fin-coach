"""가상 학생 3명의 4주치 행동 데이터와 가상 주가를 만든다.

실행: python data/make_sample_data.py              (전부 새로 만든다: 화면에서 쌓인 기록도 지워진다)
      python data/make_sample_data.py --only allowance   (students.json과 allowance.csv만)
시드를 고정했기 때문에 몇 번을 실행해도 같은 파일이 나온다.
형식은 docs/DATA.md를 따른다.

용돈 지출은 BC카드 소비 통계(engine/consumption.py)의 성별 건수 비율과 건당 금액을 기준으로 만든다.
"""

import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import consumption  # noqa: E402

SEED = 42
START = date(2026, 9, 7)  # 월요일
WEEKS = 4
SURGE_PCT = 10  # 급등 추격 기준 (docs/PLAN.md)
CONCENTRATION_PCT = 60  # 몰빵 기준 (docs/PLAN.md)

DATA_DIR = Path(__file__).resolve().parent

STUDENTS = [
    {"student_id": "S01", "name": "민지", "grade": "중2", "type": "몰빵형",
     "gender": 2, "weekly_allowance": 40000, "virtual_cash": 1000000,
     "envelope_ratio": {"SPEND": 50, "SAVE": 30, "INVEST": 20},
     "saving_goal": {"item": "에어팟", "amount": 250000}},
    {"student_id": "S02", "name": "준호", "grade": "중3", "type": "저축 실패형",
     "gender": 1, "weekly_allowance": 30000, "virtual_cash": 1000000,
     "envelope_ratio": {"SPEND": 60, "SAVE": 30, "INVEST": 10},
     "saving_goal": {"item": "운동화", "amount": 150000}},
    {"student_id": "S03", "name": "서연", "grade": "고1", "type": "균형형",
     "gender": 2, "weekly_allowance": 50000, "virtual_cash": 1000000,
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

# 준호(저축 실패형)는 목요일마다 모으기 봉투에서 꺼내 쓴다 (원)
SAVE_WITHDRAW = {"S02": [8000, 7000, 9000, 6000]}

# BC 통계에 없는 지출(쇼핑·교통·기타)은 예전 데이터를 날짜·금액까지 그대로 유지한다
KEPT_SPENDING = [
    ("S02", "2026-09-07", "OTHER", 2400, "코인노래방"),
    ("S02", "2026-09-09", "TRANSPORT", 2300, "버스카드 충전"),
    ("S03", "2026-09-11", "OTHER", 3600, "PC방"),
    ("S01", "2026-09-12", "OTHER", 2000, "코인노래방"),
    ("S01", "2026-09-14", "TRANSPORT", 2700, "버스카드 충전"),
    ("S02", "2026-09-14", "OTHER", 3900, "PC방"),
    ("S03", "2026-09-14", "SHOPPING", 4400, "문구점"),
    ("S01", "2026-09-16", "OTHER", 4000, "PC방"),
    ("S02", "2026-09-21", "SHOPPING", 3500, "스티커"),
    ("S01", "2026-09-22", "TRANSPORT", 2000, "버스카드 충전"),
    ("S03", "2026-09-25", "OTHER", 2700, "PC방"),
    ("S03", "2026-09-28", "TRANSPORT", 2000, "버스카드 충전"),
    ("S01", "2026-09-30", "TRANSPORT", 2500, "버스카드 충전"),
    ("S03", "2026-09-30", "TRANSPORT", 2400, "버스카드 충전"),
    ("S03", "2026-10-01", "TRANSPORT", 2100, "버스카드 충전"),
    ("S01", "2026-10-03", "TRANSPORT", 2400, "버스카드 충전"),
]

# 성향: 기준(BC 성별 비율)에서 의도한 만큼만 벗어난다. 준호는 편의점 비중을 남성 기준보다 높게.
CONVENIENCE_TILT = {"S02": 0.70}
SPEND_USE = 0.9  # 쓰기 봉투(+꺼내 쓴 돈)에서 BC 카테고리 지출에 쓰는 비율. 조금 남겨 둔다
AMOUNT_STEPS = [1.0, 0.9, 1.1, 0.95, 1.05]  # 건당 금액에 차례로 곱한다. 첫 건은 평균 그대로, 이후 짝지어 평균 유지
DAY_ORDER = [1, 2, 4, 5, 6, 0, 3]  # 한 주 안에서 지출을 놓아 볼 요일 순서 (화·수·금·토·일·월·목)
BC_MEMOS = {
    "CONVENIENCE": ["편의점", "편의점 간식", "편의점 음료"],
    "CAFE_DESSERT": ["카페", "패스트푸드", "베이커리"],
    "MEAL": ["분식집", "한식당", "김밥집", "중국집"],
    "MART": ["동네 마트", "대형마트"],
}


def envelope_split(student):
    """주간 용돈을 봉투 비율대로 나눈 금액 (원)."""
    weekly = student["weekly_allowance"]
    return {e: weekly * pct // 100 for e, pct in student["envelope_ratio"].items()}


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


def student_shares(student, base):
    shares = {c: v["count_share"] for c, v in base[student["gender"]].items()}
    if student["student_id"] in CONVENIENCE_TILT:
        shares = consumption.tilt(shares, "CONVENIENCE", CONVENIENCE_TILT[student["student_id"]])
    return shares


def bc_transactions(student, base, budget):
    """예산 안에서 가능한 가장 많은 건수로, 성별 비율대로 나눈 지출 [(카테고리, 금액)]."""
    shares = student_shares(student, base)
    averages = {c: v["avg_amount"] for c, v in base[student["gender"]].items()}
    total = 0
    while True:
        counts = consumption.allocate_counts(shares, total + 1)
        if sum(n * averages[c] for c, n in counts.items()) > budget * SPEND_USE:
            break
        total += 1
    counts = consumption.allocate_counts(shares, total)
    txs = []
    for category in consumption.BC_CATEGORIES:
        for i in range(counts[category]):
            amount = round(averages[category] * AMOUNT_STEPS[i % len(AMOUNT_STEPS)] / 100) * 100
            txs.append((category, amount))
    return txs


def make_allowance():
    """입금·이동은 봉투 비율대로, 지출은 BC 기준으로. 쓰기 봉투 잔액이 어느 날에도 음수가 되지 않게 놓는다."""
    base = consumption.baseline()
    rows = []
    days = [START + timedelta(days=i) for i in range(WEEKS * 7)]
    for student in STUDENTS:
        student_id = student["student_id"]
        split = envelope_split(student)
        withdraws = SAVE_WITHDRAW.get(student_id, [0] * WEEKS)
        inflow, spend_rows = [], []
        flow = [0] * len(days)  # 날짜별 쓰기 봉투 증감
        for week in range(WEEKS):
            monday = START + timedelta(days=7 * week)
            for envelope, amount in split.items():
                inflow.append({"student_id": student_id, "date": monday.isoformat(),
                               "envelope": envelope, "amount": amount,
                               "category": "OTHER", "memo": "용돈 입금"})
            flow[7 * week] += split["SPEND"]
            if withdraws[week]:
                thursday = (monday + timedelta(days=3)).isoformat()
                inflow.append({"student_id": student_id, "date": thursday, "envelope": "SAVE",
                               "amount": -withdraws[week], "category": "OTHER", "memo": "모으기에서 꺼냄"})
                inflow.append({"student_id": student_id, "date": thursday, "envelope": "SPEND",
                               "amount": withdraws[week], "category": "OTHER", "memo": "모으기에서 옮김"})
                flow[7 * week + 3] += withdraws[week]
        for sid, day, category, amount, memo in KEPT_SPENDING:
            if sid == student_id:
                spend_rows.append({"student_id": sid, "date": day, "envelope": "SPEND",
                                   "amount": -amount, "category": category, "memo": memo})
                flow[(date.fromisoformat(day) - START).days] -= amount

        budget = sum(flow)
        txs = sorted(bc_transactions(student, base, budget), key=lambda t: -t[1])
        balance = [sum(flow[:i + 1]) for i in range(len(days))]
        memo_turn = {c: 0 for c in BC_MEMOS}
        for n, (category, amount) in enumerate(txs):
            week = n % WEEKS  # 큰 금액부터 주마다 돌아가며 놓아 주별 지출을 고르게
            candidates = [7 * w + d for w in list(range(week, WEEKS)) + list(range(week)) for d in DAY_ORDER]
            day_index = next((i for i in candidates if min(balance[i:]) >= amount), None)
            if day_index is None:
                raise ValueError(f"{student_id}: 예산 안에 놓을 수 없는 지출 {category} {amount}")
            for i in range(day_index, len(days)):
                balance[i] -= amount
            memos = BC_MEMOS[category]
            spend_rows.append({"student_id": student_id, "date": days[day_index].isoformat(),
                               "envelope": "SPEND", "amount": -amount, "category": category,
                               "memo": memos[memo_turn[category] % len(memos)]})
            memo_turn[category] += 1
        rows += inflow + spend_rows
    # 안정 정렬이라 같은 날에는 입금·이동이 지출보다 먼저 온다.
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
        assert sum(envelope_split(student).values()) == student["weekly_allowance"]
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


def main(out_dir=DATA_DIR, only_allowance=False):
    students_dir = Path(out_dir) / "students"
    prices_dir = Path(out_dir) / "prices"
    rng = random.Random(SEED)
    prices = make_prices(rng)
    trades = make_trades(prices)
    allowance = make_allowance()
    check_design(trades, prices)

    students_dir.mkdir(parents=True, exist_ok=True)
    prices_dir.mkdir(parents=True, exist_ok=True)
    with open(students_dir / "students.json", "w", encoding="utf-8") as f:
        json.dump(STUDENTS, f, ensure_ascii=False, indent=2)
        f.write("\n")
    write_csv(students_dir / "allowance.csv", allowance,
              ["tx_id", "student_id", "date", "envelope", "amount", "category", "memo"])
    if only_allowance:
        print(f"students.json, allowance.csv만 새로 만듦 (용돈 내역 {len(allowance)}건)")
        return
    write_csv(students_dir / "trades.csv", trades,
              ["trade_id", "student_id", "date", "ticker", "side", "qty", "price", "journal"])
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
    main(only_allowance=sys.argv[1:] == ["--only", "allowance"])
