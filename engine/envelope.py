"""용돈봉투 계산. LLM 호출 금지."""

from datetime import date, timedelta

ENVELOPES = ["SPEND", "SAVE", "INVEST"]
DEPOSIT_MEMO = "용돈 입금"
TO_SAVE_MEMO = "모으기로 옮김"     # 쓰기 → 모으기 옮기기 (지출이 아니다)
FROM_SPEND_MEMO = "쓰기에서 옮김"


def check_ratio(ratio):
    """비율을 쓸 수 없으면 이유(문장)를, 쓸 수 있으면 None을 돌려준다."""
    if any(ratio[e] < 0 for e in ENVELOPES):
        return "비율은 0%보다 작을 수 없어요."
    total = sum(ratio[e] for e in ENVELOPES)
    if total != 100:
        return f"세 봉투의 합이 100%가 되어야 해요. 지금은 {total}%예요."
    return None


def split_allowance(amount, ratio):
    """용돈을 비율대로 나눈다. 원 단위 나머지는 INVEST 봉투에 넣어 합계가 정확히 맞게 한다."""
    spend = amount * ratio["SPEND"] // 100
    save = amount * ratio["SAVE"] // 100
    return {"SPEND": spend, "SAVE": save, "INVEST": amount - spend - save}


def deposit_entries(amount, ratio):
    """store.append_allowance에 넘길 입금 줄. 금액이 0인 봉투는 뺀다."""
    return [(envelope, part, "OTHER", DEPOSIT_MEMO)
            for envelope, part in split_allowance(amount, ratio).items() if part > 0]


def deposit_date_this_week(allowance, student_id, today):
    """today가 속한 주(월요일 시작)에 이미 받은 용돈 입금 날짜. 없으면 None.
    용돈은 한 주에 한 번만 받는다 (버튼을 여러 번 눌러도 중복 입금되지 않게)."""
    day = date.fromisoformat(today)
    monday = (day - timedelta(days=day.weekday())).isoformat()
    sunday = (day + timedelta(days=6 - day.weekday())).isoformat()
    mine = allowance[(allowance["student_id"] == student_id)
                     & (allowance["memo"] == DEPOSIT_MEMO)
                     & (allowance["amount"] > 0)
                     & (allowance["date"] >= monday) & (allowance["date"] <= sunday)]
    return mine["date"].min() if len(mine) else None


def transfer_entries(amount):
    """쓰기 봉투 → 모으기 봉투로 옮기는 두 줄 (store.append_allowance에 넘긴다)."""
    return [("SPEND", -amount, "OTHER", TO_SAVE_MEMO), ("SAVE", amount, "OTHER", FROM_SPEND_MEMO)]


def balances(allowance, student_id):
    """{봉투: 잔액}"""
    mine = allowance[allowance["student_id"] == student_id]
    sums = mine.groupby("envelope")["amount"].sum()
    return {e: int(sums.get(e, 0)) for e in ENVELOPES}


def spending(allowance, student_id):
    """지출 내역만: SPEND 봉투의 음수 금액 (모으기로 옮긴 돈은 지출이 아니라 뺀다). 최근 것이 위로 온다."""
    mine = allowance[(allowance["student_id"] == student_id)
                     & (allowance["envelope"] == "SPEND") & (allowance["amount"] < 0)
                     & (allowance["memo"] != TO_SAVE_MEMO)]
    return mine.sort_values("date", ascending=False, kind="stable")


def spending_by_category(allowance, student_id):
    """{카테고리: 지출 합계(양수)} 많이 쓴 순서."""
    spent = -spending(allowance, student_id).groupby("category")["amount"].sum()
    return {category: int(total) for category, total in spent.sort_values(ascending=False).items()}


IMPULSE_CATEGORIES = ("CONVENIENCE", "CAFE_DESSERT")  # "필요 vs 원함"을 함께 보여 줄 때 비중을 계산하는 분류


def impulse_share_pct(allowance, student_id):
    """지출 중 편의점·카페·패스트푸드·디저트 비중(%). 지출이 없으면 None."""
    by_category = spending_by_category(allowance, student_id)
    total = sum(by_category.values())
    if total == 0:
        return None
    return sum(by_category.get(c, 0) for c in IMPULSE_CATEGORIES) / total * 100


def top_spending(allowance, student_id):
    """가장 많이 쓴 분류와 금액 (category, amount). 지출이 없으면 None. 봉투 카드 한 줄 요약용."""
    by_category = spending_by_category(allowance, student_id)
    return next(iter(by_category.items()), None)


def history(allowance, student_id, name):
    """한 봉투의 입출금 줄 전체. 최근 것이 위로 온다 (같은 날은 나중에 적은 줄이 위)."""
    mine = allowance[(allowance["student_id"] == student_id) & (allowance["envelope"] == name)]
    return mine.iloc[::-1].sort_values("date", ascending=False, kind="stable")


def goal_progress_pct(save_balance, goal_amount):
    """모으기 봉투 잔액이 목표의 몇 %인지 (0~100)."""
    return max(0.0, min(100.0, save_balance / goal_amount * 100))


def latest_date(allowance):
    return allowance["date"].max()
