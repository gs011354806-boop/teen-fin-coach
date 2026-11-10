"""28번 미션 탭 · 소비 미션 (Replay → Simulation → 미션 → 검증). LLM 호출 금지.

명세: teen-app/MISSION_TAB_SPEC.md 6-1(트리거) · 6-2(시뮬레이션) · 6-5(검증·포인트) · 6-7(코치 문구, 템플릿)
- 숫자는 모두 학생 자신의 용돈 기록(allowance.csv)에서 계산한다. 시안 mock 숫자는 쓰지 않는다.
- 주는 월요일에 시작한다. '이번 주' = 용돈 기록의 마지막 날이 속한 주 (데모 날짜 기준).
- 기준 주(baseline) = 이번 주 전의 주들 중 최근 4주 (용돈 입금이 있는 주).
- LATE_NIGHT 트리거는 결제 시각이 데이터에 없어 만들지 않는다.
"""

from datetime import date, timedelta

from engine import envelope

CATEGORY_LABELS = {"CONVENIENCE": "편의점", "CAFE_DESSERT": "카페·디저트", "MEAL": "식사·분식",
                   "MART": "마트", "SHOPPING": "쇼핑", "TRANSPORT": "교통", "OTHER": "기타"}
# 횟수를 줄여 볼 만한 업종 (교통처럼 꼭 필요한 지출·기타는 뺀다)
FREQ_CATEGORIES = ["CONVENIENCE", "CAFE_DESSERT", "MEAL", "MART", "SHOPPING"]
REDUCE_FIRST = ["CONVENIENCE", "CAFE_DESSERT"]  # A안에서 먼저 고를 업종 (원함 지출)
DAY_NAMES = "월화수목금토일"

BASELINE_WEEKS = 4
FREQ_MIN = 3             # SPEND_FREQ_HIGH: 한 업종 주 3회 이상
RATIO_MIN = 0.85         # SPEND_RATIO_HIGH: 최근 4주 쓴 돈 / 용돈 ≥ 85%
STREAK_MIN = 3           # SAVING_MISS_STREAK: 저축 계획 3주 연속 미달
TRIGGER_ORDER = ["SAVING_MISS_STREAK", "SPEND_RATIO_HIGH", "SPEND_FREQ_HIGH"]

WEEKS_PER_MONTH = 4.345
DAYS_PER_MONTH = 30.44
EXTRA_SAVE = 3000        # B안: 주당 저축 +3,000원
PARENT_MATCH = 0.2       # C안: 부모님 20% 매칭
REWARDS = {"A": 150, "B": 200, "C": 100}   # 보상 포인트 (× 수행률). 하루 상한 200P 안에서 준다
MIN_RESULT_WEEKDAY = 5   # 토요일(5)부터 '주말 결과 보기'


def won(amount):
    return f"{int(amount):,}원"


def monday(day):
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return (d - timedelta(days=d.weekday())).isoformat()


def week_label(week_start):
    d = date.fromisoformat(week_start)
    return f"{d.month}/{d.day}주"


# ---------- 주간 기록 ----------

def weekly(allowance, student_id):
    """{주 시작일: {"spend": {업종: (횟수, 금액)}, "save_net": 원, "deposit": 원, "spend_total": 원, "rows": DataFrame}}"""
    mine = allowance[allowance["student_id"] == student_id].copy()
    mine["week"] = mine["date"].map(monday)
    weeks = {}
    for week, rows in mine.groupby("week"):
        spent = rows[(rows["envelope"] == "SPEND") & (rows["amount"] < 0) & (rows["memo"] != envelope.TO_SAVE_MEMO)]
        by_cat = {c: (len(g), int(-g["amount"].sum())) for c, g in spent.groupby("category")}
        weeks[week] = {
            "spend": by_cat,
            "spend_total": int(-spent["amount"].sum()),
            "save_net": int(rows[rows["envelope"] == "SAVE"]["amount"].sum()),
            "deposit": int(rows[(rows["memo"] == envelope.DEPOSIT_MEMO) & (rows["amount"] > 0)]["amount"].sum()),
            "rows": spent,
        }
    return dict(sorted(weeks.items()))


def today_of(allowance):
    return envelope.latest_date(allowance)


def baseline_weeks(weeks, today):
    """이번 주 전의 주들 중 최근 4주 (오래된 것부터)."""
    current = monday(today)
    return [w for w in weeks if w < current and weeks[w]["deposit"] > 0][-BASELINE_WEEKS:]


def save_plan(student):
    """계획한 주간 저축액 = 주 용돈 × 모으기 비율."""
    return student["weekly_allowance"] * student["envelope_ratio"]["SAVE"] // 100


# ---------- 6-1 Replay 트리거 ----------

def _streak(weeks, base, plan):
    n = 0
    for w in reversed(base):
        if weeks[w]["save_net"] >= plan:
            break
        n += 1
    return n


def triggers(student, allowance):
    """걸린 트리거 목록 (우선순위 순). 각 항목: code, parts(문장 조각 [(글, 강조)]), chips[(이름, 원)], evidence."""
    weeks = weekly(allowance, student["student_id"])
    today = today_of(allowance)
    base = baseline_weeks(weeks, today)
    if not base:
        return []
    found = {}
    plan = save_plan(student)
    n = _streak(weeks, base, plan)
    if n >= STREAK_MIN:
        streak_weeks = base[-n:][-4:]
        found["SAVING_MISS_STREAK"] = {
            "code": "SAVING_MISS_STREAK",
            "parts": [(f"{student['saving_goal']['item']} 저축이 ", False), (f"{n}주째", True),
                      (f" 계획보다 늦어요. 계획은 주 {won(plan)}이에요.", False)],
            "chips": [(week_label(w), weeks[w]["save_net"]) for w in streak_weeks],
            "evidence": {"weeks": n, "plan": plan},
        }
    spend = sum(weeks[w]["spend_total"] for w in base)
    deposit = sum(weeks[w]["deposit"] for w in base)
    if deposit and spend / deposit >= RATIO_MIN:
        p = round(spend / deposit * 100)
        found["SPEND_RATIO_HIGH"] = {
            "code": "SPEND_RATIO_HIGH",
            "parts": [(f"최근 {len(base)}주 용돈의 ", False), (f"{p}%", True), ("를 이미 썼어요.", False)],
            "chips": [(week_label(w), weeks[w]["spend_total"]) for w in base],
            "evidence": {"ratio_pct": p},
        }
    last = base[-1]
    hits = [(c, *weeks[last]["spend"][c]) for c in FREQ_CATEGORIES
            if c in weeks[last]["spend"] and weeks[last]["spend"][c][0] >= FREQ_MIN]
    if hits:
        category, count, amount = max(hits, key=lambda h: (h[1], h[2]))
        p = round(amount / student["weekly_allowance"] * 100)
        rows = weeks[last]["rows"]
        rows = rows[rows["category"] == category]
        by_day = {}
        for r in rows.itertuples():
            day = DAY_NAMES[date.fromisoformat(r.date).weekday()]
            by_day[day] = by_day.get(day, 0) - int(r.amount)
        found["SPEND_FREQ_HIGH"] = {
            "code": "SPEND_FREQ_HIGH",
            "parts": [(f"지난주 {CATEGORY_LABELS[category]}에 ", False), (f"{count}번, {won(amount)}", True),
                      (f"을 썼어요. 용돈의 {p}%예요.", False)],
            "chips": sorted(by_day.items(), key=lambda kv: DAY_NAMES.index(kv[0]))[:4],
            "evidence": {"category": category, "count": count, "amount": amount, "ratio_pct": p},
        }
    return [found[c] for c in TRIGGER_ORDER if c in found]


def strengths(student, allowance):
    """트리거가 없을 때 보여 줄 '잘하고 있는 점' (코드가 고른 사실 문장, 많아야 2개)."""
    weeks = weekly(allowance, student["student_id"])
    base = baseline_weeks(weeks, today_of(allowance))
    if not base:
        return []
    facts = []
    plan = save_plan(student)
    kept = sum(weeks[w]["save_net"] >= plan for w in base)
    if kept == len(base):
        facts.append(f"{len(base)}주 내내 모으기 계획(주 {won(plan)})을 지켰어요.")
    max_visits = max((weeks[w]["spend"].get(c, (0, 0))[0] for w in base for c in FREQ_CATEGORIES), default=0)
    if max_visits < FREQ_MIN:
        facts.append(f"한 곳에 주 {FREQ_MIN}번 넘게 쓴 적이 없어요.")
    spend = sum(weeks[w]["spend_total"] for w in base)
    deposit = sum(weeks[w]["deposit"] for w in base)
    if deposit and spend / deposit < RATIO_MIN and len(facts) < 2:
        facts.append(f"최근 {len(base)}주 용돈의 {round(spend / deposit * 100)}%만 썼어요.")
    return facts[:2]


# ---------- 6-2 Simulation ----------

def _months(start, today):
    return (date.fromisoformat(today) - date.fromisoformat(start)).days / DAYS_PER_MONTH


def eta_months(remaining, weekly_net, elapsed):
    """목표까지 걸리는 기간(개월, 시작부터). 모으는 돈이 없으면 None."""
    if remaining <= 0:
        return round(elapsed, 1)
    if weekly_net <= 0:
        return None
    return round(elapsed + remaining / weekly_net / WEEKS_PER_MONTH, 1)


def _reduce_category(weeks, base, trigger_list):
    freq = next((t for t in trigger_list if t["code"] == "SPEND_FREQ_HIGH"), None)
    if freq:
        return freq["evidence"]["category"]
    totals = {c: (sum(weeks[w]["spend"].get(c, (0, 0))[0] for w in base),
                  sum(weeks[w]["spend"].get(c, (0, 0))[1] for w in base)) for c in FREQ_CATEGORIES}
    ranked = sorted((c for c in totals if totals[c][0] > 0),
                    key=lambda c: (c not in REDUCE_FIRST, -totals[c][0], -totals[c][1]))
    return ranked[0] if ranked else None


def simulation(student, allowance):
    """목표·현재 예상·A/B/C 대안. 각 대안의 mission은 미션을 시작할 때 쓴다."""
    sid = student["student_id"]
    weeks = weekly(allowance, sid)
    today = today_of(allowance)
    base = baseline_weeks(weeks, today)
    goal = student["saving_goal"]
    saved = envelope.balances(allowance, sid)["SAVE"]
    remaining = max(0, goal["amount"] - saved)
    start = min(weeks) if weeks else today
    elapsed = _months(start, today)
    net = round(sum(weeks[w]["save_net"] for w in base) / len(base)) if base else 0
    current = eta_months(remaining, net, elapsed)
    trig = triggers(student, allowance)

    options = []
    category = _reduce_category(weeks, base, trig)
    if category:
        visits = sum(weeks[w]["spend"].get(category, (0, 0))[0] for w in base)
        amount = sum(weeks[w]["spend"].get(category, (0, 0))[1] for w in base)
        # 기준 횟수 = 지난주 실제 횟수 (지난주에 안 갔으면 기준 주 평균, 최소 1회)
        last_visits = weeks[base[-1]]["spend"].get(category, (0, 0))[0]
        per_week = last_visits or max(1, round(visits / len(base)))
        ticket = int(round(amount / visits / 100) * 100)
        name = CATEGORY_LABELS[category]
        options.append({
            "label": "A", "title": f"{name} 주 1회 줄이기", "subtitle": f"주 약 {won(ticket)} 절약",
            "weekly": net + ticket, "change": ticket, "parent": False,
            "mission": {"title": f"{name} 주 {per_week}회 → {per_week - 1}회로 줄이기", "metric": "visits",
                        "category": category, "baseline": per_week, "target": per_week - 1,
                        "direction": "decrease", "reward_points": REWARDS["A"],
                        "effect": f"성공하면 아낀 {won(ticket)} → {goal['item']} 저축통"}})
    options.append({
        "label": "B", "title": f"주당 저축 +{won(EXTRA_SAVE)}", "subtitle": "용돈 받는 날 바로 모으기 봉투에",
        "weekly": net + EXTRA_SAVE, "change": EXTRA_SAVE, "parent": False,
        "mission": {"title": f"주당 저축 +{won(EXTRA_SAVE)}", "metric": "save_net", "category": "",
                    "baseline": net, "target": net + EXTRA_SAVE, "direction": "increase",
                    "reward_points": REWARDS["B"],
                    "effect": f"성공하면 {goal['item']}이 더 가까워져요"}})
    keep = max(net, 1000)
    options.append({
        "label": "C", "title": f"부모님 {round(PARENT_MATCH * 100)}% 매칭저축",
        "subtitle": f"모은 돈의 {round(PARENT_MATCH * 100)}%를 부모님이 더해줘요",
        "weekly": round(net * (1 + PARENT_MATCH)), "change": round(net * PARENT_MATCH), "parent": True,
        "mission": {"title": f"주 {won(keep)} 이상 모으기 (부모님 {round(PARENT_MATCH * 100)}% 매칭)",
                    "metric": "save_net", "category": "", "baseline": 0, "target": keep,
                    "direction": "increase", "reward_points": REWARDS["C"],
                    "effect": "부모님 승인 후 매칭돼요 (시안)"}})
    for o in options:
        o["eta"] = eta_months(remaining, o["weekly"], elapsed)
    options = [o for o in options if o["eta"] is not None] or options
    recommended = _recommend(options, goal["months"])
    for o in options:
        o["recommended"] = o["label"] == recommended
    return {"goal": goal, "saved": saved, "remaining": remaining, "weekly_net": net, "elapsed": elapsed,
            "current_eta": current, "deadline": goal["months"], "options": options, "base_weeks": len(base)}


def _recommend(options, deadline):
    """목표 기한 안에 드는 안 중 행동 변화가 가장 작은 안 (부모님 도움 C안은 다른 안이 없을 때만).
    기한 안에 드는 안이 없으면 가장 빨리 끝나는 안."""
    timed = [o for o in options if o["eta"] is not None]
    inside = [o for o in timed if o["eta"] <= deadline]
    own = [o for o in inside if not o["parent"]]
    pool = own or inside
    if pool:
        return min(pool, key=lambda o: o["change"])["label"]
    return min(timed, key=lambda o: o["eta"])["label"] if timed else options[0]["label"]


def eta_sentence(sim):
    """'지금처럼 쓰면 N개월 걸려요. 목표보다 M개월 늦어요/빨라요.' (조각 [(글, 강조)])"""
    eta, deadline = sim["current_eta"], sim["deadline"]
    if sim["remaining"] == 0:
        return [("벌써 목표를 다 모았어요!", True)]
    if eta is None:
        return [("지금처럼이면 모으기 봉투가 늘지 않아서 ", False), ("목표에 닿기 어려워요", True), (".", False)]
    gap = round(eta - deadline, 1)
    tail = (f" 목표보다 {gap}개월 늦어요." if gap > 0 else
            f" 목표보다 {abs(gap)}개월 빨라요." if gap < 0 else " 목표 기한에 딱 맞아요.")
    return [("지금처럼 쓰면 ", False), (f"{eta}개월", True), (f" 걸려요.{tail}", False)]


# ---------- 미션 시작 · 진행 · 6-5 검증 ----------

def start_row(student, option, today):
    """미션 한 줄 (store.append_mission_run에 넘긴다). 이번 주 월~일."""
    start = monday(today)
    end = (date.fromisoformat(start) + timedelta(days=6)).isoformat()
    m = option["mission"]
    return {"student_id": student["student_id"], "track": "spend", "option": option["label"],
            "title": m["title"], "metric": m["metric"], "category": m["category"],
            "baseline": m["baseline"], "target": m["target"], "direction": m["direction"],
            "start_date": start, "end_date": end, "reward_points": m["reward_points"], "status": "active",
            "parent_request": "REQUESTED" if option["parent"] else ""}


def active_run(runs, student_id, track="spend"):
    mine = runs[(runs["student_id"] == student_id) & (runs["track"] == track) & (runs["status"] == "active")]
    return mine.iloc[-1].to_dict() if len(mine) else None


def completed_runs(runs, student_id, track="spend"):
    mine = runs[(runs["student_id"] == student_id) & (runs["track"] == track) & (runs["status"] == "completed")]
    return [r for _, r in mine.iloc[::-1].iterrows()]


def metric_value(run, allowance, student_id):
    """미션 기간(월~오늘) 동안의 지표 값: visits = 그 업종 이용 횟수, save_net = 모으기 봉투 순증가."""
    mine = allowance[(allowance["student_id"] == student_id)
                     & (allowance["date"] >= run["start_date"]) & (allowance["date"] <= run["end_date"])]
    if run["metric"] == "visits":
        return int(((mine["envelope"] == "SPEND") & (mine["amount"] < 0) & (mine["memo"] != envelope.TO_SAVE_MEMO)
                    & (mine["category"] == run["category"])).sum())
    return int(mine[mine["envelope"] == "SAVE"]["amount"].sum())


def completion_rate(direction, baseline, target, current):
    """6-5 수행률 = clamp(달성량 / 목표 변화량, 0, 1). 목표 변화가 0이면 목표를 채웠는지로 본다."""
    baseline, target, current = float(baseline), float(target), float(current)
    if direction == "decrease":
        need, done = baseline - target, baseline - current
    else:
        need, done = target - baseline, current - baseline
    if need <= 0:
        met = current <= target if direction == "decrease" else current >= target
        return 1.0 if met else 0.0
    return max(0.0, min(1.0, done / need))


def met(direction, target, current):
    return float(current) <= float(target) if direction == "decrease" else float(current) >= float(target)


def points_for(reward_points, rate):
    """포인트 = 보상 × 수행률 (10P 단위 반올림)."""
    return int(round(int(reward_points) * rate / 10) * 10)


def d_day(run, today):
    return (date.fromisoformat(run["end_date"]) - date.fromisoformat(today)).days


def can_finish(run, today):
    """주말(토요일)부터 결과를 볼 수 있다."""
    return date.fromisoformat(today) >= date.fromisoformat(run["start_date"]) + timedelta(days=MIN_RESULT_WEEKDAY)


def progress(run, allowance, student_id, today):
    current = metric_value(run, allowance, student_id)
    return {"current": current, "d_day": d_day(run, today),
            "rate": completion_rate(run["direction"], run["baseline"], run["target"], current)}


def finish_values(run, allowance, student_id, today):
    """주말 결과를 store.update_mission_run에 넘길 값."""
    current = metric_value(run, allowance, student_id)
    rate = completion_rate(run["direction"], run["baseline"], run["target"], current)
    return {"status": "completed", "current": current, "completion_rate": round(rate, 2),
            "points": points_for(run["reward_points"], rate), "finished_date": today}


def metric_text(run, value):
    if run["metric"] == "visits":
        return f"{CATEGORY_LABELS[run['category']]} {int(float(value))}회"
    return won(float(value))


def result(student, run, allowance):
    """③ 결과 화면 숫자 (모두 코드 계산)."""
    sid = student["student_id"]
    weeks = weekly(allowance, sid)
    base = [w for w in weeks if w < run["start_date"] and weeks[w]["deposit"] > 0][-BASELINE_WEEKS:]
    mission_week = weeks.get(run["start_date"])

    def saving_rate(ws):
        dep = sum(weeks[w]["deposit"] for w in ws)
        return sum(weeks[w]["save_net"] for w in ws) / dep if dep else 0.0

    before_rate = saving_rate(base)
    after_rate = saving_rate([run["start_date"]]) if mission_week else before_rate
    goal = student["saving_goal"]
    saved = envelope.balances(allowance, sid)["SAVE"]
    remaining = max(0, goal["amount"] - saved)
    start = min(weeks)
    elapsed = _months(start, run["finished_date"] or today_of(allowance))
    before_net = round(sum(weeks[w]["save_net"] for w in base) / len(base)) if base else 0
    after_ws = base[1:] + [run["start_date"]] if mission_week else base
    after_net = round(sum(weeks[w]["save_net"] for w in after_ws) / len(after_ws)) if after_ws else 0
    eta_before = eta_months(remaining, before_net, elapsed)
    eta_after = eta_months(remaining, after_net, elapsed)
    delta_days = (round((eta_before - eta_after) * DAYS_PER_MONTH)
                  if eta_before is not None and eta_after is not None else None)
    rate = float(run["completion_rate"])
    succeeded = met(run["direction"], run["target"], run["current"])
    return {"rate": rate, "weeks_succeeded": int(succeeded), "weeks_total": 1,
            "actual": metric_text(run, run["current"]), "target": metric_text(run, run["target"]),
            "baseline": metric_text(run, run["baseline"]),
            "saving_rate": (before_rate, after_rate), "eta": eta_after, "eta_delta_days": delta_days,
            "points": int(float(run["points"] or 0)), "succeeded": succeeded,
            "coach": coach_message(run, rate, succeeded, goal["item"])}


def coach_message(run, rate, succeeded, goal_item, generate=None):
    """6-7 AI 코치 문구. 1차는 템플릿. generate(facts) → 문장을 주면 그걸 쓴다 (LLM 연결 자리, CoachService)."""
    facts = {"title": run["title"], "rate_pct": round(rate * 100), "succeeded": succeeded, "goal_item": goal_item}
    if generate:
        return generate(facts)
    if succeeded:
        return (f"'{run['title']}'를 해냈어요. {goal_item}까지 한 걸음 더 왔어요. "
                "다음 주에는 같은 미션을 한 번 더 이어 가 볼까요?")
    if rate >= 0.5:
        return (f"목표의 {facts['rate_pct']}%까지 왔어요. 거의 다 왔으니, 다음 주에는 목표를 조금 낮춰서 "
                "확실히 해내 보는 것도 좋아요.")
    return ("이번 주는 쉽지 않았어요. 벌점은 없어요. 다시 시뮬레이션해서 더 쉬운 안으로 "
            "다음 주를 시작해 봐요.")
