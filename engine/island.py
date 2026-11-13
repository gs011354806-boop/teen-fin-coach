"""틴틴 자산섬 (자산 키우기 게임). LLM 호출 금지.

명세: game/tintin_island_handoff/ISLAND_GAME_SPEC.md (6장 로직, 7장 mock)
- 게임은 학생의 실제 기록을 '섬'으로 보여 주는 다른 방식이다. 숫자는 모두 기존 데이터에서 계산한다.
  용돈 기록(allowance.csv) → 저축 밭·물주기·소비 가방, 가상투자(trades.csv + 시세) → 투자 과수원·날씨,
  미션 탭(mission_runs.csv) → 퀘스트, 개념 카드 기록 → 금융 도감.
- 게임이 새로 저장하는 것은 게임 상태(씨앗 기록, 고친 태그, 찜, 고른 퀘스트, 토글)뿐이다 (store.ISLAND_TABLES).
- 2026-11-13 결정: 능력치는 숫자·막대 없이 '잘하는 것 / 다음에 키울 능력'만 (CLAUDE.md 규칙 5),
  씨앗은 게임 안 화폐로 포인트와 연결하지 않는다, 종목은 게임 안에서 가상 이름,
  주간 결산은 수익률 대신 날씨와 비중 (규칙 4).
"""

import json
import math
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

from engine import detect, envelope, portfolio, spend_mission as sm

MOCK_PATH = Path(__file__).resolve().parent.parent / "data" / "island_mock.json"
DAY_NAMES = "월화수목금토일"

# ---------- 6-2 작물 ----------
STAGE_NAMES = {1: "씨앗", 2: "새싹", 3: "꽃", 4: "열매"}
CROP_LABELS = {"pot": "화분", "potato": "감자", "appleTree": "사과나무"}

# ---------- 6-4 과수원 ----------
MANGO_STD_PCT = 2.5      # 최근 VOL_DAYS 거래일 일간 등락률 표준편차(%)가 이 값 이상이면 망고(변동성 큰 개별주)
VOL_DAYS = 60
TREE_UNIT_PCT = 20       # 나무 1그루 = 비중 20%
MAX_TREES = 5
WARN_WEIGHT_PCT = 50     # 최대 비중이 이보다 크면 '병충해 주의'
SPLIT_MAX_PCT = 40       # 나눠 심기 미리보기: 한 종목 최대 비중
STORM_PCT = -3.0         # 보유 종목 평균 등락이 이 값 이하면 태풍, 0 미만이면 흐림
FORECAST_DAYS = 3
TREE_LABELS = {"mango": "망고", "apple": "사과", "basket": "바구니"}
# 게임 안에서만 쓰는 가상 이름 (실존 기업명을 쓰지 않는다, 명세 0-3). 업종 + 알파벳
VIRTUAL_NAMES = {"005930": "반도체A", "000660": "반도체B", "035420": "인터넷A", "035720": "인터넷B",
                 "005380": "자동차A"}
ETF_TICKERS = set()      # ETF·지수형 종목코드 (지금 데이터에는 없다)

# ---------- 6-5 소비 가방 ----------
# (메모에 들어 있으면, 아이콘, 기본 태그). 위에서부터 먼저 맞는 것. 태그 규칙: 교통·식사·생수·학용품 → 필요,
# 간식·음료·굿즈·게임 → 원함 (명세 6-5). 학생이 고친 태그가 있으면 그 값을 쓴다.
ITEM_RULES = [
    (("교통", "충전", "버스"), "card", "need"),
    (("생수",), "bottle", "need"),
    (("문구", "학용품"), "pencil", "need"),
    (("간식", "과자", "디저트", "마트"), "snack", "want"),
    (("음료", "탄산", "카페", "커피", "주스"), "can", "want"),
    (("PC방", "노래방", "게임", "키링", "굿즈", "스티커", "쇼핑"), "keyring", "want"),
    (("분식", "식사", "김밥", "도시락", "패스트푸드", "편의점"), "onigiri", "need"),
]
CATEGORY_DEFAULT = {"TRANSPORT": ("card", "need"), "MEAL": ("onigiri", "need"), "CONVENIENCE": ("onigiri", "need"),
                    "CAFE_DESSERT": ("can", "want"), "MART": ("snack", "want"), "SHOPPING": ("keyring", "want"),
                    "OTHER": ("keyring", "want")}
BAG_SLOTS = 8
WISH_WAIT_HOURS = 24

# ---------- 6-6 씨앗 · 경험치 ----------
SEED_DAILY_CAP = 200
SEEDS = {"wish_cancel": 20, "harvest": 100, "weekly": 10}
EXP = {"water": 10, "quest": 30, "dex": 20, "wish_cancel": 5}
TITLES = [(1, "새싹 섬지기"), (3, "꾸준한 새싹 농부"), (6, "든든한 과수원지기"), (10, "자산섬 지킴이")]

# ---------- 6-7 능력 (숫자 없이 '잘하는 것 / 다음에 키울 능력') ----------
SKILLS = ["planSpend", "goalSaving", "knowledge", "risk", "decision"]
SKILL_LABELS = {"planSpend": "계획소비", "goalSaving": "목표저축", "knowledge": "금융지식", "risk": "위험관리",
                "decision": "의사결정"}
# 다음에 키울 능력을 고를 때의 순서 (점수가 없으므로 고정 순서) + 연결 화면
NEXT_ORDER = ["risk", "planSpend", "goalSaving", "decision", "knowledge"]
SKILL_LINKS = {"risk": ("orchard", "과수원 나눠 심기"), "planSpend": ("bag", "가방에서 필요·원함 나누기"),
               "goalSaving": ("farm", "밭에 물 주기"), "decision": ("market", "근거 적고 가상투자 하기"),
               "knowledge": ("news", "이번 주 금융 뉴스 읽기")}
MIN_DEX_FOR_KNOWLEDGE = 2

# ---------- 6-8 퀘스트 ----------
QUEST_SEEDS = {"planSpend": 150, "risk": 200, "goalSaving": 100, "decision": 100, "knowledge": 100}
QUEST_COUNT = 3
DEFAULT_PICKED = 2

# ---------- 오늘의 상점 (교육용 카드 풀: 매일 묶음 할인 1장 + 자동결제 1장) ----------
SHOP_BUNDLES = [("1+1 음료", 2200, 2), ("과자 3개 묶음", 4500, 3), ("2+1 젤리", 3000, 3), ("컵라면 4개입", 5200, 4)]
SHOP_SUBSCRIPTIONS = [("스티커 구독", 3900), ("음악 앱", 7900), ("웹툰 쿠키 정기충전", 4900), ("게임 패스", 5900)]


def won(amount):
    return f"{int(round(amount)):,}원"


def num(amount):
    return f"{int(round(amount)):,}"


# =====================================================================
# 6-2 · 6-3 작물과 이자
# =====================================================================

def crop_stage(current, target):
    """성장 단계 1~4 (씨앗 < 25% ≤ 새싹 < 50% ≤ 꽃 < 90% ≤ 열매)."""
    ratio = current / target if target else 0
    return 1 if ratio < 0.25 else 2 if ratio < 0.5 else 3 if ratio < 0.9 else 4


def segments(pct):
    """10칸 분절 막대의 채운 칸 수 (0~100 → 0~10)."""
    return max(0, min(10, round(pct / 10)))


def installment_interest(monthly, annual_rate, months):
    """적금 만기 이자 (단리, 세전): 월 납입 × 연이율 × n(n+1)/2 / 12."""
    return monthly * annual_rate * months * (months + 1) / 2 / 12


def compound_amount(principal, rate, years):
    return principal * (1 + rate) ** years


def simple_amount(principal, rate, years):
    return principal * (1 + rate * years)


COMPOUND_EXAMPLE = (100_000, 0.03, 10)


def compound_text(on):
    p, r, t = COMPOUND_EXAMPLE
    value = compound_amount(p, r, t) if on else simple_amount(p, r, t)
    return f"예시) {p // 10000}만 원 · 연 {round(r * 100)}% · {t}년 → {won(value)}"


# =====================================================================
# 6-4 과수원
# =====================================================================

def volatility_pct(closes):
    """최근 VOL_DAYS 거래일 일간 등락률(%)의 표준편차."""
    closes = list(closes)[-(VOL_DAYS + 1):]
    returns = [(b / a - 1) * 100 for a, b in zip(closes, closes[1:]) if a]
    return statistics.pstdev(returns) if len(returns) >= 2 else 0.0


def tree_type(ticker, closes):
    if ticker in ETF_TICKERS:
        return "basket"
    return "mango" if volatility_pct(closes) >= MANGO_STD_PCT else "apple"


def tree_count(weight_pct):
    return max(1, round(weight_pct / TREE_UNIT_PCT))


def trees(holdings):
    """[{type, name}] 최대 MAX_TREES그루. 망고 → 사과 → 바구니 순, 같은 종류는 비중이 큰 종목부터."""
    order = list(TREE_LABELS)
    out = []
    for h in sorted(holdings, key=lambda h: (order.index(h["type"]), -h["weight"])):
        out += [{"type": h["type"], "name": h["name"]}] * tree_count(h["weight"])
    return out[:MAX_TREES]


def composition(holdings):
    """나무 종류별 비중 [{type, label, pct}] (망고 → 사과 → 바구니)."""
    by_type = {}
    for h in holdings:
        by_type[h["type"]] = by_type.get(h["type"], 0) + h["weight"]
    return [{"type": t, "label": TREE_LABELS[t], "pct": round(by_type[t])} for t in TREE_LABELS if t in by_type]


def split_preview(holdings):
    """나눠 심기 미리보기: 한 종목을 SPLIT_MAX_PCT 이하로 줄이고, 넘친 비중은 바구니(ETF)에 5% 단위로 심고
    남은 자투리는 줄이지 않은 종목에 비중대로 나눈다. (시안: 망고 78 / 사과 22 → 40 / 25 / 35)"""
    capped = [dict(h, weight=min(h["weight"], SPLIT_MAX_PCT)) for h in holdings]
    excess = sum(h["weight"] for h in holdings) - sum(h["weight"] for h in capped)
    if excess <= 0:
        return capped
    basket = excess // 5 * 5
    rest = excess - basket
    free = [h for h in capped if h["weight"] < SPLIT_MAX_PCT]
    room = sum(h["weight"] for h in free)
    if free and room:
        for h in free:
            h["weight"] += rest * h["weight"] / room
    else:
        basket += rest
    return capped + [{"type": "basket", "name": "ETF 바구니", "weight": basket}]


def max_weight(holdings):
    """한 종목 최대 비중. 바구니(ETF)는 그 안에서 이미 나눠 담겨 있어 쏠림으로 보지 않는다."""
    return max((h["weight"] for h in holdings if h["type"] != "basket"), default=0)


def orchard_status(holdings):
    """(경고 여부, 제목, 설명)."""
    if not holdings:
        return False, "아직 빈 과수원이에요", "가상 주식 연습에서 첫 나무를 심어 보세요. 나무 = 종목이에요."
    singles = [h for h in holdings if h["type"] != "basket"]
    top = max(singles, key=lambda h: h["weight"]) if singles else None
    if top and top["weight"] > WARN_WEIGHT_PCT:
        tree = TREE_LABELS[top["type"]]
        return (True, f"병충해 주의! {tree}나무({top['name']})가 {round(top['weight'])}%예요",
                "태풍(급락) 소식 하나에 과수원 전체가 흔들려요. 한 종목에 몰린 상태를 집중 위험이라고 해요.")
    kinds = len({h["type"] for h in holdings})
    body = "한 나무가 흔들려도 다른 나무가 버텨줘요. 이게 분산투자예요."
    if any(h["type"] == "basket" for h in holdings):
        body += " 바구니 묘목은 여러 열매를 한 번에 담은 ETF예요."
    return False, ("튼튼한 과수원! 종류를 나눠 심었어요" if kinds > 1 else "튼튼한 과수원이에요"), body


def weather_kind(change_pct):
    if change_pct is None:
        return "cloudy"
    return "storm" if change_pct <= STORM_PCT else "cloudy" if change_pct < 0 else "sunny"


WEATHER_LABELS = {"sunny": "맑음", "cloudy": "흐림", "storm": "태풍"}


# =====================================================================
# 6-5 가방
# =====================================================================

def item_rule(category, memo):
    """(아이콘, 기본 태그)."""
    for words, icon, tag in ITEM_RULES:
        if any(w in memo for w in words):
            return icon, tag
    return CATEGORY_DEFAULT.get(category, ("keyring", "want"))


def bag_items(rows, user_tags):
    """이번 주 지출 줄 [{category, memo, amount(양수)}] → 같은 메모끼리 묶은 아이템. user_tags: {이름: need|want}."""
    items = {}
    for r in rows:
        item = items.setdefault(r["memo"], {"name": r["memo"], "category": r["category"], "qty": 0, "amount": 0})
        item["qty"] += 1
        item["amount"] += r["amount"]
    out = []
    for item in items.values():
        icon, tag = item_rule(item["category"], item["name"])
        user = user_tags.get(item["name"])
        out.append(dict(item, icon=icon, tag=user or tag, tag_source="user" if user else "auto"))
    return sorted(out, key=lambda i: (i["tag"] != "need", -i["amount"]))


def need_want(items):
    need = sum(i["amount"] for i in items if i["tag"] == "need")
    want = sum(i["amount"] for i in items if i["tag"] == "want")
    total = need + want
    return need, want, round(want / total * 100) if total else 0


def wish_remaining(added_at, now):
    """찜한 뒤 남은 시간 'HH:MM' (다 지났으면 None)."""
    left = datetime.fromisoformat(added_at) + timedelta(hours=WISH_WAIT_HOURS) - now
    if left.total_seconds() <= 0:
        return None
    minutes = int(left.total_seconds() // 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def shop_cards(day):
    """오늘의 상점: 날짜마다 묶음 할인 1장 + 자동결제 1장을 돌려 보여 준다. 숫자는 계산한다."""
    n = date.fromisoformat(day).toordinal()
    name, price, count = SHOP_BUNDLES[n % len(SHOP_BUNDLES)]
    sub, monthly = SHOP_SUBSCRIPTIONS[n % len(SHOP_SUBSCRIPTIONS)]
    return [{"title": f"{name} {won(price)}", "body": f"개당 {won(price / count)} · {count}개가 필요할 때만 이득",
             "badge": ""},
            {"title": f"{sub} 월 {won(monthly)}", "body": f"1년이면 {won(monthly * 12)}", "badge": "자동결제 주의"}]


# =====================================================================
# 6-6 씨앗 · 레벨
# =====================================================================

def capped_grant(amount, granted_today, cap=SEED_DAILY_CAP):
    """하루 지급 상한을 적용한 실제 지급량."""
    return max(0, min(amount, cap - granted_today))


def seed_balance(ledger, student_id):
    mine = ledger[ledger["student_id"] == student_id]
    return int(sum(int(a) for a in mine["amount"]))


def granted_on(ledger, student_id, day):
    mine = ledger[(ledger["student_id"] == student_id) & (ledger["date"] == day)]
    return int(sum(max(0, int(a)) for a in mine["amount"]))


def level_from_exp(exp):
    """(레벨, 이번 레벨에서 모은 경험치, 다음 레벨까지 필요한 양). 레벨업 필요치 = 100 × 레벨."""
    level = 1
    while exp >= 100 * level:
        exp -= 100 * level
        level += 1
    return level, exp, 100 * level


def title_for(level):
    return [t for need, t in TITLES if level >= need][-1]


# =====================================================================
# 6-7 능력 · 6-8 결산과 퀘스트
# =====================================================================

def next_skills(good):
    """good: {skill: bool}. 아직 연습 중인 능력 (NEXT_ORDER 순)."""
    return [s for s in NEXT_ORDER if not good.get(s)]


def stars(water_done, water_planned, max_weight_pct, want_pct):
    """별 = (물주기 달성률 ≥ 75%) + (최대 비중 ≤ 50%) + (원함 비율 ≤ 50%)."""
    water = water_planned and water_done / water_planned >= 0.75
    return int(bool(water)) + int(max_weight_pct <= WARN_WEIGHT_PCT) + int(want_pct <= 50)


def quest_for(skill, freq=None):
    """능력 하나에 대한 퀘스트. freq: SPEND_FREQ_HIGH 근거(업종 라벨·횟수)가 있으면 계획소비 퀘스트에 쓴다."""
    if skill == "planSpend":
        if freq:
            title = f"{freq['label']}은 {max(1, freq['count'] - 1)}번만 가기"
        else:
            title = "원함 결제 1번 줄이기"
        mission = "A" if freq else None
    else:
        title = {"risk": "바구니 묘목 1그루 심기", "goalSaving": f"주당 저축 +{won(sm.EXTRA_SAVE)}",
                 "decision": "근거를 10자 넘게 적고 사기", "knowledge": "이번 주 뉴스 퀴즈 풀기"}[skill]
        mission = "B" if skill == "goalSaving" else None
    return {"id": skill, "title": title, "skill": skill, "skill_label": SKILL_LABELS[skill],
            "seeds": QUEST_SEEDS[skill], "mission_option": mission}


TRIGGER_SKILL = {"SPEND_FREQ_HIGH": "planSpend", "SPEND_RATIO_HIGH": "planSpend",
                 "SAVING_MISS_STREAK": "goalSaving", "CONCENTRATION": "risk"}


def recommend_quests(good, trigger=None, freq=None):
    """연습 중인 능력 2개 + 이번 주 트리거 1개 → 퀘스트 3개 (모자라면 나머지 능력으로 채움). 앞의 2개를 기본 선택."""
    picks = next_skills(good)[:2]
    trigger_skill = TRIGGER_SKILL.get(trigger)
    if trigger_skill and trigger_skill not in picks:
        picks.append(trigger_skill)
    for s in NEXT_ORDER:
        if len(picks) >= QUEST_COUNT:
            break
        if s not in picks:
            picks.append(s)
    return [dict(quest_for(s, freq), selected=i < DEFAULT_PICKED) for i, s in enumerate(picks[:QUEST_COUNT])]


def iso_week(day):
    return date.fromisoformat(day).isocalendar()[1]


def week_range(day):
    start = date.fromisoformat(sm.monday(day))
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat(), f"{start:%m/%d} ~ {end:%m/%d}"


def hud_date(day):
    d = date.fromisoformat(day)
    return f"{d.month}/{d.day} ({DAY_NAMES[d.weekday()]})"


# =====================================================================
# 6-1 섬 대화
# =====================================================================

def insight(trigger_list, holdings, goal_item):
    """우선순위가 가장 높은 트리거 하나를 섬 비유로 (문장, 선택지 2개, 코드)."""
    codes = {t["code"]: t for t in trigger_list}
    if "SPEND_FREQ_HIGH" in codes:
        e = codes["SPEND_FREQ_HIGH"]["evidence"]
        label = sm.CATEGORY_LABELS[e["category"]]
        return {"code": "SPEND_FREQ_HIGH",
                "text": f"지난주엔 {label}에 {e['count']}번 갔구나! 그래서 밭에 줄 물(저축)이 조금 모자라. 어떻게 할까?",
                "choices": [{"label": f"다음 주엔 {max(1, e['count'] - 1)}번만 갈게! (밭 보러 가기)", "to": "farm"},
                            {"label": "뭘 샀는지 가방부터 볼래", "to": "bag"}]}
    if "SAVING_MISS_STREAK" in codes:
        n = codes["SAVING_MISS_STREAK"]["evidence"]["weeks"]
        return {"code": "SAVING_MISS_STREAK",
                "text": f"{goal_item} 화분에 {n}주째 물을 덜 줬어. 조금씩이라도 줘 볼까?",
                "choices": [{"label": "밭에 물 주러 갈래! (밭 보러 가기)", "to": "farm"},
                            {"label": "어디에 썼는지 가방부터 볼래", "to": "bag"}]}
    if "SPEND_RATIO_HIGH" in codes:
        p = codes["SPEND_RATIO_HIGH"]["evidence"]["ratio_pct"]
        return {"code": "SPEND_RATIO_HIGH",
                "text": f"최근 용돈의 {p}%를 벌써 썼어. 밭에 줄 물이 점점 줄고 있어. 어떻게 할까?",
                "choices": [{"label": "뭘 샀는지 가방부터 볼래", "to": "bag"},
                            {"label": "밭 상태 보러 갈래", "to": "farm"}]}
    if holdings and max_weight(holdings) > WARN_WEIGHT_PCT:
        top = max(holdings, key=lambda h: h["weight"])
        return {"code": "CONCENTRATION",
                "text": f"과수원에 {top['name']} 나무가 {round(top['weight'])}%야. 태풍 한 번에 다 흔들릴 수 있어. 어떻게 할까?",
                "choices": [{"label": "나눠 심기 미리 볼래! (과수원 가기)", "to": "orchard"},
                            {"label": "내 능력부터 볼래", "to": "status"}]}
    return {"code": None, "text": "이번 주 섬은 평화로워! 밭이랑 과수원을 한 바퀴 둘러볼까?",
            "choices": [{"label": "밭 보러 가기", "to": "farm"}, {"label": "과수원 보러 가기", "to": "orchard"}]}


# =====================================================================
# 화면에 넘길 값 (실제 데이터 → view)
# =====================================================================

def _holdings(student, trades, prices):
    sid = student["student_id"]
    held = portfolio.holdings(trades, sid)
    if not held:
        return [], 0
    closes = portfolio.close_on(prices, portfolio.latest_date(prices))
    values = {t: q * closes[t] for t, q in held.items() if t in closes}
    total = sum(values.values())
    names = iter("ABCDEFGH")
    out = [{"ticker": t, "name": VIRTUAL_NAMES.get(t) or f"종목{next(names)}",
            "type": tree_type(t, prices[t]["close"].astype(int)), "weight": v / total * 100, "value": v}
           for t, v in values.items()]
    return out, total


def _forecast(holdings, prices):
    """보유 종목(없으면 전체 종목) 평균 등락률로 최근 거래일 3일의 날씨. 태풍이면 가장 많이 떨어진 종목의 업종 소식."""
    pool = [h["ticker"] for h in holdings] or list(prices)
    days = sorted(set(prices[pool[0]]["date"]))[-FORECAST_DAYS:]
    out = []
    for day in days:
        changes = {t: portfolio.day_change_pct(prices[t], day) for t in pool}
        valid = [c for c in changes.values() if c is not None]
        avg = sum(valid) / len(valid) if valid else None
        kind = weather_kind(avg)
        note = ""
        if kind == "storm":
            worst = min((t for t in changes if changes[t] is not None), key=lambda t: changes[t])
            sector = VIRTUAL_NAMES.get(worst, "종목")[:-1] or "종목"
            note = f"{sector} 마을에 태풍 소식이 들려요"
        out.append({"day": DAY_NAMES[date.fromisoformat(day).weekday()], "kind": kind,
                    "label": WEATHER_LABELS[kind], "note": note})
    return out


def _board(forecast, holdings):
    storm = next((f["note"] for f in forecast if f["kind"] == "storm"), "")
    if storm:
        return storm
    if all(f["kind"] == "sunny" for f in forecast):
        return "과수원에 햇살이 가득한 한 주예요" if holdings else "시장에 햇살이 가득한 한 주예요"
    return "구름이 조금 지나가요. 큰 소식은 없어요"


def _watering(student, allowance):
    weeks = sm.weekly(allowance, student["student_id"])
    base = sm.baseline_weeks(weeks, sm.today_of(allowance))
    plan = sm.save_plan(student)
    done = sum(1 for w in base if weeks[w]["save_net"] >= plan)
    ratio = student["envelope_ratio"]["SAVE"]
    total_done = sum(1 for w in weeks if weeks[w]["deposit"] > 0 and weeks[w]["save_net"] >= plan)
    return {"done": done, "planned": len(base), "auto": ratio > 0,
            "auto_text": (f"용돈 받는 날 자동 물주기 켜짐 (모으기 {ratio}%)" if ratio > 0
                          else "용돈 받는 날 자동 물주기 꺼짐"), "total_done": total_done, "plan": plan}


def _farm(student, allowance):
    goal = student["saving_goal"]
    saved = envelope.balances(allowance, student["student_id"])["SAVE"]
    sim = sm.simulation(student, allowance)
    stage = crop_stage(saved, goal["amount"])
    remaining = max(0, goal["amount"] - saved)
    if stage == 4 or remaining == 0:
        note = "수확할 수 있어요!" if remaining == 0 else "열매 단계 · 거의 다 왔어요"
    elif sim["weekly_net"] > 0:
        months = remaining / sim["weekly_net"] / sm.WEEKS_PER_MONTH
        note = f"{STAGE_NAMES[stage]} 단계 · 수확까지 약 {months:.1f}개월"
    else:
        note = f"{STAGE_NAMES[stage]} 단계 · 물(저축)이 늘면 수확 시기가 보여요"
    return [{"id": "goal", "name": f"{goal['item']} 화분", "crop": "pot", "stage": stage, "current": saved,
             "target": goal["amount"], "amount_text": f"{num(saved)} / {num(goal['amount'])}원",
             "seg": segments(saved / goal["amount"] * 100), "note": note}]


def _bag(student, allowance, tags):
    start, end, _ = week_range(sm.today_of(allowance))
    spent = envelope.spending(allowance, student["student_id"])
    spent = spent[(spent["date"] >= start) & (spent["date"] <= end)]
    rows = [{"category": r.category, "memo": r.memo, "amount": -int(r.amount)} for r in spent.itertuples()]
    mine = tags[tags["student_id"] == student["student_id"]]
    return bag_items(rows, dict(zip(mine["item"], mine["tag"])))


def _dex(student_id, concepts, lessons, reviews, questions):
    found = {}
    for table, kind in ((lessons, "mistake"), (reviews, "lesson"), (questions, "lesson")):
        mine = table[table["student_id"] == student_id]
        for r in mine.itertuples():
            if r.concept in concepts and (r.concept not in found or r.date < found[r.concept][0]):
                found[r.concept] = (r.date, kind)
    recent = sorted(found, key=lambda c: found[c][0], reverse=True)
    return {"count": len(found), "total": len(concepts),
            "recent": [concepts[c]["name_ko"] for c in recent[:4]],
            "dates": {concepts[c]["name_ko"]: found[c][0] for c in recent}}


def _good_skills(holdings, watering, want_pct, bag_count, dex_count, detections):
    buys = len(detections)
    reasoned = sum(1 for d in detections if d["journal_chars"] >= detect.MIN_JOURNAL_CHARS)
    return {"planSpend": bag_count == 0 or want_pct <= 50,
            "goalSaving": bool(watering["planned"]) and watering["done"] / watering["planned"] >= 0.75,
            "knowledge": dex_count >= MIN_DEX_FOR_KNOWLEDGE,
            "risk": bool(holdings) and max_weight(holdings) <= WARN_WEIGHT_PCT,
            "decision": buys > 0 and reasoned / buys >= 0.5}


def ensure_rewards(student, ctx, store_mod, today):
    """기록에서 다시 계산할 수 있는 씨앗 보상을 한 번씩만 준다 (목표 수확, 미션과 연결된 퀘스트 완료)."""
    sid = student["student_id"]
    ledger = store_mod.load_island("seeds")
    keys = set(ledger[ledger["student_id"] == sid]["key"])
    goal = student["saving_goal"]
    if envelope.balances(ctx["allowance"], sid)["SAVE"] >= goal["amount"]:
        grant(store_mod, sid, today, SEEDS["harvest"], f"{goal['item']} 화분 수확", f"harvest-{goal['item']}", keys)
    quests = store_mod.load_island("quests")
    runs = ctx["runs"]
    for q in quests[(quests["student_id"] == sid) & (quests["run_id"] != "")].itertuples():
        run = runs[runs["run_id"] == q.run_id]
        if len(run) and run.iloc[0]["status"] == "completed" and float(run.iloc[0]["completion_rate"] or 0) >= 1:
            grant(store_mod, sid, today, int(q.seeds), f"퀘스트 완료: {q.title}", f"quest-{q.run_id}", keys)


def grant(store_mod, student_id, day, amount, reason, key, keys=None):
    """씨앗 지급 (같은 key는 한 번만, 하루 상한 적용). 실제 지급량을 돌려준다."""
    ledger = store_mod.load_island("seeds")
    if keys is None:
        keys = set(ledger[ledger["student_id"] == student_id]["key"])
    if key in keys:
        return 0
    amount = capped_grant(amount, granted_on(ledger, student_id, day))
    store_mod.append_island("seeds", {"student_id": student_id, "date": day, "amount": amount,
                                      "reason": reason if amount else f"{reason} (오늘 씨앗 상한)", "key": key})
    keys.add(key)
    return amount


def _today_weather(forecast, today):
    """오늘 요일의 날씨 (시세가 없는 날이면 가장 최근 거래일의 날씨)."""
    day = DAY_NAMES[date.fromisoformat(today).weekday()]
    hit = next((f for f in forecast if f["day"] == day), None) or (forecast[-1] if forecast else None)
    return hit["kind"] if hit else "sunny"


def build_view(student, ctx, now=None):
    """실제 기록 → 화면 값. ctx: allowance, trades, prices, runs, concepts, lessons, reviews, questions,
    seeds, tags, wish, quests, prefs (store에서 읽은 표)."""
    sid = student["student_id"]
    allowance = ctx["allowance"]
    today = sm.today_of(allowance)
    now = now or datetime.now()
    holdings, orchard_value = _holdings(student, ctx["trades"], ctx["prices"])
    forecast = _forecast(holdings, ctx["prices"])
    watering = _watering(student, allowance)
    plots = _farm(student, allowance)
    items = _bag(student, allowance, ctx["tags"])
    need, want, want_pct = need_want(items)
    dex = _dex(sid, ctx["concepts"], ctx["lessons"], ctx["reviews"], ctx["questions"])
    detections = detect.detect(ctx["trades"], ctx["prices"], student)
    good = _good_skills(holdings, watering, want_pct, len(items), dex["count"], detections)
    trig = sm.triggers(student, allowance)
    ins = insight(trig, holdings, student["saving_goal"]["item"])
    freq = next(({"label": sm.CATEGORY_LABELS[t["evidence"]["category"]], "count": t["evidence"]["count"]}
                 for t in trig if t["code"] == "SPEND_FREQ_HIGH"), None)

    runs = ctx["runs"]
    completed = len(runs[(runs["student_id"] == sid) & (runs["status"] == "completed")])
    wishes = ctx["wish"][ctx["wish"]["student_id"] == sid]
    cancels = int((wishes["decision"] == "cancel").sum())
    exp = (EXP["water"] * watering["total_done"] + EXP["quest"] * completed + EXP["dex"] * dex["count"]
           + EXP["wish_cancel"] * cancels)
    level, exp_in, exp_need = level_from_exp(exp)

    prefs = ctx["prefs"][ctx["prefs"]["student_id"] == sid]
    pref = dict(zip(prefs["key"], prefs["value"]))
    start, end, label = week_range(today)
    week = iso_week(today)
    ledger = ctx["seeds"][ctx["seeds"]["student_id"] == sid]
    week_seeds = int(sum(int(a) for d, a in zip(ledger["date"], ledger["amount"]) if start <= d <= end))
    new_dex = next((n for n, d in dex["dates"].items() if start <= d <= end), "")

    saved_start = int(allowance[(allowance["student_id"] == sid) & (allowance["envelope"] == "SAVE")
                                & (allowance["date"] < start)]["amount"].sum())
    plot = plots[0]
    grown = plot["stage"] - crop_stage(saved_start, plot["target"])
    growth = (f"{plot['name']} +{grown}단계" if grown > 0 else f"{plot['name']} {STAGE_NAMES[plot['stage']]} 그대로")
    top = max(holdings, key=lambda h: h["weight"]) if holdings else None
    worst = next((f for f in forecast if f["kind"] == "storm"), None) or \
        next((f for f in forecast if f["kind"] == "cloudy"), None) or forecast[-1]

    quests_table = ctx["quests"]
    chosen = quests_table[(quests_table["student_id"] == sid) & (quests_table["week"] == str(week))]
    wish = None
    open_wish = wishes[wishes["decision"].isin(["", "wait"])]
    if len(open_wish):
        w = open_wish.iloc[-1]
        wish = {"id": w["wish_id"], "name": w["name"], "price": won(int(w["price"])),
                "remaining": wish_remaining(w["added_at"], now), "waiting": w["decision"] == "wait"}

    return _assemble(
        name=student["name"], today=today, seeds=seed_balance(ctx["seeds"], sid), level=level,
        exp_pct=round(exp_in / exp_need * 100), title=title_for(level), insight=ins, watering=watering,
        plots=plots, compound_on=pref.get("compound", "on") == "on", holdings=holdings,
        orchard_value=orchard_value, forecast=forecast, board=_board(forecast, holdings), items=items,
        wish=wish, shop=shop_cards(today), farm_total=plot["current"], good=good, dex=dex,
        weekly={"week": week, "range": label, "stars": stars(watering["done"], watering["planned"],
                                                             max_weight(holdings), want_pct),
                "rows": [
                    {"label": f"저축 밭 · 물주기 {watering['done']}/{watering['planned']}", "value": growth,
                     "tone": "good" if grown > 0 else ""},
                    {"label": f"투자 과수원 · {worst['label']}",
                     "value": (f"{TREE_LABELS[top['type']]} 비중 {round(top['weight'])}%" if top else "빈 과수원"),
                     "tone": "warn" if top and top["weight"] > WARN_WEIGHT_PCT else "good" if top else ""},
                    {"label": "소비 가방 · 원함", "value": f"{won(want)} ({want_pct}%)" if items else "결제 없음",
                     "tone": ""},
                    {"label": "새 도감", "value": new_dex or "없음", "tone": ""}],
                "seeds": week_seeds},
        quests=recommend_quests(good, ins["code"], freq), chosen=list(chosen["title"]),
        weekly_seen=pref.get("weekly_seen") == str(week), mock=False)


# =====================================================================
# 명세 7장 mock → 같은 화면 값 (시안과 비교·테스트용, ?mock=1)
# =====================================================================

def load_mock(path=MOCK_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mock_plots(mock):
    plots = []
    for f in mock["farm"]:
        if "installment" in f:
            ins = f["installment"]
            current = ins["monthly"] * ins["paidCount"]
            stage = crop_stage(ins["paidCount"], ins["totalCount"])
            interest = installment_interest(ins["monthly"], ins["annualRate"], ins["totalCount"])
            plots.append({"id": f["goalId"], "name": f["name"], "crop": f["cropType"], "stage": stage,
                          "current": current, "target": ins["monthly"] * ins["totalCount"],
                          "amount_text": f"월 {ins['monthly'] // 10000}만 원 · {ins['paidCount']}/{ins['totalCount']}회 납입",
                          "seg": segments(ins["paidCount"] / ins["totalCount"] * 100),
                          "note": f"만기 이자 열매 약 +{won(interest)}"})
            continue
        stage = crop_stage(f["currentAmount"], f["targetAmount"])
        note = (f"{STAGE_NAMES[stage]} 단계 · 수확까지 약 {f['etaMonths']}개월" if f.get("etaMonths")
                else "급할 때만 캐는 작물" if f["cropType"] == "potato" else f"{STAGE_NAMES[stage]} 단계")
        plots.append({"id": f["goalId"], "name": f["name"], "crop": f["cropType"], "stage": stage,
                      "current": f["currentAmount"], "target": f["targetAmount"],
                      "amount_text": f"{num(f['currentAmount'])} / {num(f['targetAmount'])}원",
                      "seg": segments(f["currentAmount"] / f["targetAmount"] * 100), "note": note})
    return plots


def build_mock_view(mock=None):
    mock = mock or load_mock()
    isl = mock["island"]
    holdings = [{"ticker": o["symbol"], "name": o["displayName"], "type": o["treeType"], "weight": o["weightPct"]}
                for o in mock["orchard"]]
    items = [dict(i, icon=item_rule("", i["category"] + i["name"])[0], tag_source="auto") for i in mock["bag"]]
    need, want, want_pct = need_want(items)
    good = {k: v >= 50 for k, v in mock["stats"].items()}
    w = mock["watering"]
    ins_src = mock["insight"]
    ins = {"code": ins_src["trigger"],
           "text": f"이번 주엔 {ins_src['category']}에 {ins_src['count']}번 갔구나! 그래서 밭에 줄 물(저축)이 조금 모자라. 어떻게 할까?",
           "choices": [{"label": f"다음 주엔 {ins_src['count'] - 2}번만 갈게! (밭 보러 가기)", "to": "farm"},
                       {"label": "뭘 샀는지 가방부터 볼래", "to": "bag"}]}
    plots = mock_plots(mock)
    wk = mock["weekly"]
    forecast = [dict(f, label=WEATHER_LABELS[f["kind"]], note=f.get("note", "")) for f in mock["forecast"]]
    return _assemble(
        name=isl["name"], today=isl["today"], seeds=isl["seeds"], level=isl["islandLevel"], exp_pct=isl["exp"],
        title=isl["title"], insight=ins,
        watering={"done": w["done"], "planned": w["planned"], "auto": w["autoWatering"],
                  "auto_text": "용돈 받는 날 자동 물주기 " + ("켜짐" if w["autoWatering"] else "꺼짐")},
        plots=plots, compound_on=True, holdings=holdings, orchard_value=mock["orchardValue"], forecast=forecast,
        board=next(f["note"] for f in forecast if f["note"]) + "이 들려요", items=items,
        wish={"id": "mock", "name": mock["wish"]["name"], "price": won(mock["wish"]["price"]),
              "remaining": mock["wish"]["remaining"], "waiting": False},
        shop=[dict(c, badge=c.get("badge", "")) for c in mock["shopCards"]],
        farm_total=sum(p["current"] for p in plots), good=good,
        dex={"count": mock["dex"]["count"], "total": mock["dex"]["total"], "recent": mock["dex"]["recent"]},
        weekly={"week": isl["weekIndex"], "range": wk["range"], "stars": wk["stars"], "seeds": wk["seeds"],
                "rows": [{"label": f"저축 밭 · 물주기 {w['done']}/{w['planned']}", "value": wk["farmGrowth"],
                          "tone": "good"},
                         {"label": "투자 과수원 · 태풍", "value": f"망고 비중 {holdings[0]['weight']}%", "tone": "warn"},
                         {"label": "소비 가방 · 원함", "value": f"{won(wk['wantAmount'])} ({wk['wantPct']}%)",
                          "tone": ""},
                         {"label": "새 도감", "value": wk["newDex"], "tone": ""}]},
        quests=[{"id": q["id"], "title": q["title"], "skill": q["skill"], "skill_label": SKILL_LABELS[q["skill"]],
                 "seeds": q["seedReward"], "selected": q["selected"], "mission_option": None}
                for q in mock["quests"]],
        chosen=[], weekly_seen=True, mock=True)


# =====================================================================
# 공통 조립
# =====================================================================

def _assemble(*, name, today, seeds, level, exp_pct, title, insight, watering, plots, compound_on, holdings,
              orchard_value, forecast, board, items, wish, shop, farm_total, good, dex, weekly, quests, chosen,
              weekly_seen, mock):
    preview = split_preview(holdings) if holdings and max_weight(holdings) > SPLIT_MAX_PCT else None

    def orchard_part(hs):
        warn, head, body = orchard_status(hs)
        return {"trees": trees(hs), "composition": composition(hs), "warn": warn, "title": head, "body": body}

    nxt = next_skills(good)
    next_skill = nxt[0] if nxt else None
    _, want, want_pct = need_want(items)
    need = sum(i["amount"] for i in items if i["tag"] == "need")
    fruit = [t["type"] for t in trees(holdings)][:4] if holdings else []
    return {
        "mock": mock,
        "hud": {"date": hud_date(today), "weather": _today_weather(forecast, today),
                "title": f"Lv.{level} {name}의 섬", "seeds": num(seeds)},
        "player": {"name": name, "level": level, "exp_pct": exp_pct, "exp_seg": segments(exp_pct), "title": title},
        "map": {"house_level": level, "crop_stage": plots[0]["stage"] if plots else 1, "fruit": fruit},
        "insight": insight,
        "farm": {"watering": watering, "plots": plots,
                 "compound": {"on": compound_on, "text": compound_text(compound_on)}},
        "orchard": {"empty": not holdings, "board": board, "forecast": forecast, "now": orchard_part(holdings),
                    "preview": orchard_part(preview) if preview else None},
        "bag": {"items": [dict(i, amount_text=won(i["amount"])) for i in items][:BAG_SLOTS],
                "slots": BAG_SLOTS, "need": won(need), "want": won(want), "want_pct": want_pct,
                "need_pct": 100 - want_pct if items else 0, "wish": wish, "shop": shop},
        "status": {"assets": {"farm": num(farm_total), "orchard": num(orchard_value),
                              "total": num(farm_total + orchard_value)},
                   "skills": [{"key": s, "label": SKILL_LABELS[s], "good": bool(good.get(s)), "next": s == next_skill}
                              for s in SKILLS],
                   "next": ({"skill": SKILL_LABELS[next_skill], "to": SKILL_LINKS[next_skill][0],
                             "text": SKILL_LINKS[next_skill][1]} if next_skill else None),
                   "dex": {"count": dex["count"], "total": dex["total"], "recent": dex["recent"]}},
        "weekly": dict(weekly, seeds=f"+{weekly['seeds']}", quests=quests, chosen=chosen),
        "start": "island" if weekly_seen or mock else "weekly",
    }
