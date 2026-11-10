"""쓰기 봉투 '내 소비 퀴즈': 학생 자신의 지출 내역으로 하루 5문제를 만든다. LLM 호출 금지.

- 문제·보기·정답은 모두 코드가 지출 기록에서 계산한다 (규칙 1).
- 같은 학생·같은 날이면 항상 같은 5문제 (seed = 학생 + 날짜). 날짜는 포인트와 같은 기준(용돈 기록의 마지막 날).
- 모두 맞히면 data/students/spend_quiz.csv에 한 줄 → 포인트는 engine/rewards.py가 기록에서 계산 (하루 1번).
- 정답 여부만 알려 주고 점수는 매기지 않는다 (규칙 5).
"""

import random

from engine import envelope

QUIZ_SIZE = 5
CATEGORY_LABELS = {"CONVENIENCE": "편의점", "CAFE_DESSERT": "카페·디저트", "MEAL": "식사·분식",
                   "MART": "마트", "SHOPPING": "쇼핑", "TRANSPORT": "교통", "OTHER": "기타"}
NEED_CATEGORIES = ("TRANSPORT",)                  # 보통 '필요'에 가까운 지출
WANT_CATEGORIES = envelope.IMPULSE_CATEGORIES      # 보통 '원함'에 가까운 지출 (편의점·카페·디저트)
SHARE_BUCKETS = [(0, 20, "20% 미만"), (20, 40, "20~40%"), (40, 60, "40~60%"), (60, 101, "60% 이상")]


def won(amount):
    return f"{amount:,}원"


def _amount_options(correct, rng, step=100):
    """정답 금액 + 그럴듯한 오답 3개 (step 단위로 반올림, 0원 이하·중복 없음)."""
    wrong = set()
    for factor in (0.5, 0.7, 1.3, 1.5, 2.0, 0.4):
        value = int(round(correct * factor / step) * step)
        if value > 0 and value != correct:
            wrong.add(value)
    for extra in (2000, 3000, 5000):  # 금액이 작아 비율로 오답이 안 생길 때
        wrong.add(correct + extra)
    picks = rng.sample(sorted(wrong), 3)
    return [won(v) for v in picks + [correct]], won(correct)


def _question(text, options, answer, rng, explain):
    options = list(dict.fromkeys(options))  # 중복 제거, 순서 유지
    rng.shuffle(options)
    return {"question": text, "options": options, "answer": answer, "explain": explain}


# ---------- 문제 만들기 (데이터가 모자라면 None) ----------

def q_top_category(spent, by_category, rng):
    if len(by_category) < 2:
        return None
    top = next(iter(by_category))
    others = [c for c in CATEGORY_LABELS if c != top]
    choices = [c for c in by_category if c != top][:3]
    choices += [c for c in others if c not in choices][:3 - len(choices)]
    return _question("이번 달 내가 돈을 가장 많이 쓴 곳은 어디일까요?",
                     [CATEGORY_LABELS[c] for c in choices + [top]], CATEGORY_LABELS[top], rng,
                     f"{CATEGORY_LABELS[top]}에 {won(by_category[top])}을 썼어요.")


def q_category_total(spent, by_category, rng):
    if not by_category:
        return None
    category = rng.choice(list(by_category))
    options, answer = _amount_options(by_category[category], rng)
    return _question(f"이번 달 {CATEGORY_LABELS[category]}에서 쓴 돈은 모두 얼마일까요?", options, answer, rng,
                     f"{CATEGORY_LABELS[category]} 지출을 모두 더하면 {answer}이에요.")


def q_count(spent, by_category, rng):
    n = len(spent)
    if n < 3:
        return None
    wrong = sorted({max(1, n + d) for d in (-3, -2, 2, 3, 5)} - {n})
    options = [f"{v}번" for v in rng.sample(wrong, 3)] + [f"{n}번"]
    return _question("이번 달 쓰기 봉투에서 돈을 쓴 횟수는 몇 번일까요?", options, f"{n}번", rng,
                     f"결제 기록이 모두 {n}번 있어요. 작은 결제도 모이면 횟수가 커져요.")


def q_biggest(spent, by_category, rng):
    if not len(spent):
        return None
    biggest = spent.loc[spent["amount"].idxmin()]  # 모든 결제 중에서 (지출은 음수라 가장 작은 값이 가장 큰 지출)
    largest_by_memo = (-spent.groupby("memo")["amount"].min())
    # 오답: 그 내용의 가장 큰 결제도 정답보다 작은 것만 (같은 금액이면 정답이 둘이 되므로 뺀다)
    candidates = sorted(m for m, v in largest_by_memo.items() if v < -biggest["amount"])
    if len(candidates) < 3:
        return None
    options = rng.sample(candidates, 3) + [biggest["memo"]]
    return _question("이번 달 한 번에 가장 많이 쓴 지출은 무엇일까요?", options, biggest["memo"], rng,
                     f"{biggest['date'][5:]} '{biggest['memo']}'에 {won(-int(biggest['amount']))}을 썼어요.")


def q_impulse_share(spent, by_category, rng):
    total = sum(by_category.values())
    if total == 0:
        return None
    share = sum(by_category.get(c, 0) for c in WANT_CATEGORIES) / total * 100
    answer = next(label for low, high, label in SHARE_BUCKETS if low <= share < high)
    return _question("이번 달 지출 중 편의점·카페·디저트는 어느 정도일까요?",
                     [label for _, _, label in SHARE_BUCKETS], answer, rng,
                     f"쓴 돈 {won(total)} 중 편의점·카페·디저트가 약 {share:.0f}%예요.")


def q_need(spent, by_category, rng):
    needs = spent[spent["category"].isin(NEED_CATEGORIES)].drop_duplicates("memo")
    wants = spent[spent["category"].isin(WANT_CATEGORIES)].drop_duplicates("memo")
    if len(needs) < 1 or len(wants) < 3:
        return None
    need = needs.sample(1, random_state=rng.randrange(10**6))["memo"].iloc[0]
    options = list(wants.sample(3, random_state=rng.randrange(10**6))["memo"]) + [need]
    return _question("내 지출 중 '꼭 필요한 지출'에 가장 가까운 것은 무엇일까요?", options, need, rng,
                     f"'{need}'처럼 학교 가는 데 드는 돈은 필요, 간식·음료는 원함에 가까워요.")


def q_spend_left(spent, by_category, rng, spend_balance=None):
    if spend_balance is None or spend_balance <= 0:
        return None
    options, answer = _amount_options(spend_balance, rng)
    return _question("지금 쓰기 봉투에 남은 돈은 얼마일까요?", options, answer, rng,
                     f"쓰기 봉투에는 {answer}이 남아 있어요. 남은 돈을 알고 쓰면 덜 흔들려요.")


MAKERS = [q_top_category, q_category_total, q_count, q_biggest, q_impulse_share, q_need]


def daily_questions(allowance, student_id, day, size=QUIZ_SIZE):
    """오늘의 문제 목록 (많아야 size개). 지출이 없으면 빈 목록."""
    spent = envelope.spending(allowance, student_id)
    if not len(spent):
        return []
    by_category = envelope.spending_by_category(allowance, student_id)
    rng = random.Random(f"{student_id}-{day}")
    balance = envelope.balances(allowance, student_id)["SPEND"]
    made = [q for q in (m(spent, by_category, rng) for m in MAKERS) if q]
    left = q_spend_left(spent, by_category, rng, balance)
    if left:
        made.append(left)
    return rng.sample(made, min(size, len(made)))


def all_correct(questions, answers):
    """answers: 학생이 고른 보기 목록 (안 고른 것은 None)."""
    return bool(questions) and all(a == q["answer"] for q, a in zip(questions, answers)) \
        and len(answers) == len(questions)


def already_done(records, student_id, day):
    return bool(((records["student_id"] == student_id) & (records["date"] == day)).any())
