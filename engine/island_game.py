"""틴틴 자산섬 v2: 가상 섬 경제 게임의 규칙 엔진. LLM 호출 금지, 화면 없이 테스트한다.

명세: game2/tintin_island_handoff/ISLAND_GAME_SPEC.md (5장 모델, 6장 규칙, 7장 시안 상태)
- 게임은 앱의 실제 금융 데이터(용돈·거래·가상투자)를 읽거나 쓰지 않는다. 상태는 게임 전용 저장 파일에만.
- 규칙 값은 data/island/rules.json, 시안 재현 상태는 data/island/demo_day12.json.
- 게임 시간은 '하루 마치기'로만 흐른다. 난수는 시드 고정(seed + day + 용도)이라 같은 날을 다시 계산해도 같다.
- 상태는 JSON으로 저장할 수 있는 dict다. 행동 함수는 상태를 그 자리에서 바꾸고 (성공 여부, 안내 문장)을 돌려준다.
- 2026-11-13 결정(v1과 같음): 능력치는 학생 화면에 숫자로 보여 주지 않는다 (CLAUDE.md 규칙 5). 엔진은 0~100을 계산한다.
"""

import json
import math
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "island"
RULES = json.loads((DATA_DIR / "rules.json").read_text(encoding="utf-8"))
S = RULES["settings"]
VERSION = 1
NEIGHBORS = ["보리", "콩이", "단비"]
STAT_KEYS = ["trade", "saving", "knowledge", "risk", "planning"]
STAT_LABELS = {"trade": "거래 감각", "saving": "저축 습관", "knowledge": "금융지식", "risk": "위험관리",
               "planning": "계획성"}
STAT_LINKS = {"trade": "market", "saving": "status", "knowledge": "status", "risk": "orchard", "planning": "market"}
GOOD_STAT = 60


def load_demo():
    demo = json.loads((DATA_DIR / "demo_day12.json").read_text(encoding="utf-8"))
    demo.pop("_comment", None)
    return demo


def rng(state_or_seed, day, key):
    seed = state_or_seed["seed"] if isinstance(state_or_seed, dict) else state_or_seed
    return random.Random(f"{seed}:{day}:{key}")


def num(n):
    return f"{int(round(n)):,}"


# =====================================================================
# 기본 조회
# =====================================================================

def house(state, tier=None):
    return RULES["houses"][state["house"] if tier is None else tier]


def next_house(state):
    return RULES["houses"][state["house"] + 1] if state["house"] + 1 < len(RULES["houses"]) else None


def item_name(item):
    return RULES["items"][item]["name"]


def item_price(state, item):
    return state["market"][item]["price"]


def tree_price(state, tree):
    return state["treeHist"][tree][-1]


def tree_name(tree):
    return RULES["trees"][tree]["name"]


def level_from_exp(exp):
    """(레벨, 이번 레벨 경험치, 필요치). 레벨업 필요치 = 100 × 레벨."""
    level = 1
    while exp >= 100 * level:
        exp -= 100 * level
        level += 1
    return level, exp, 100 * level


def title_for(level):
    return [t for need, t in RULES["titles"] if level >= need][-1]


# =====================================================================
# 6-2 시장 시세 · 6-3 나무 시세 · 이벤트
# =====================================================================

def gen_events(seed, day):
    """day에 일어날 이벤트 (전날 게시판으로 예고된다)."""
    ev = RULES["events"]
    r = rng(seed, day, "events")
    out = []
    if r.random() < ev["stormChance"]:
        out.append({"kind": "storm", "target": r.choice(["red", "gold", "mango"])})
    if r.random() < ev["festivalChance"]:
        out.append({"kind": "festival", "target": r.choice(ev["festivalTargets"])})
    if r.random() < ev["trendChance"]:
        out.append({"kind": "trend", "target": "mango"})
    return out


def item_price_on(seed, day, item, events, prev=None):
    """price(d) = round(basePrice × (1 + noise_d) × (1 + eventEffect_d))."""
    d = RULES["items"][item]
    noise = rng(seed, day, f"item-{item}").uniform(-d["volatility"], d["volatility"])
    effect = S["festivalEffect"] if any(e["kind"] == "festival" and e["target"] == item for e in events) else 0
    return max(1, round(d["basePrice"] * (1 + noise) * (1 + effect)))


def gen_market(seed, day, events, old=None):
    return {item: {"price": item_price_on(seed, day, item, events),
                   "prev": (old or {}).get(item, {}).get("price", RULES["items"][item]["basePrice"])}
            for item in RULES["items"]}


def tree_returns(seed, day, events):
    """다음 날 나무별 수익률: drift + volatility × z + 이벤트 충격. 바구니 = 나머지 나무 평균(같은 비중)."""
    out = {}
    for tid, t in RULES["trees"].items():
        if t.get("isBasket"):
            continue
        z = rng(seed, day, f"tree-{tid}").gauss(0, 1)
        shock = sum(t["eventSensitivity"].get(e["kind"], 0) for e in events if e["target"] == tid)
        out[tid] = t["drift"] + t["volatility"] * z + shock
    for tid, t in RULES["trees"].items():
        if t.get("isBasket"):
            out[tid] = sum(out.values()) / len(out)
    return out


def supply_drop(sold_before):
    """같은 날 한 품목을 supplyDropAfter개 넘게 판 뒤에는 넘은 개수마다 −2%, 최대 −20% (공급 증가).
    한 번에 파는 묶음 안에서는 같은 값이고, 다음 판매부터 내려간다 (시안: 사과 12개 = 12 × 45 = 540냥)."""
    return min(S["supplyDropMax"], max(0, sold_before - S["supplyDropAfter"]) * S["supplyDropPerUnit"])


def unit_prices(state, item, qty):
    price = round(item_price(state, item) * (1 - supply_drop(state["soldToday"].get(item, 0))))
    return [price] * qty


# =====================================================================
# 6-7 순자산 · 과수원
# =====================================================================

def orchard_value(state):
    return sum(n * tree_price(state, t) for t, n in state["trees"].items())


def storage_value(state):
    return sum(n * item_price(state, i) for i, n in state["inventory"].items())


def loan_balance(state):
    return sum(l["due"] for l in state["loans"] if not l.get("repaid"))


def house_value(state):
    """집 가격 = 지금까지 지은 단계 가격의 합 (오두막 3,000 → 통나무집 5,000을 더 들이면 8,000)."""
    return sum(h["price"] for h in RULES["houses"][:state["house"] + 1])


def net_worth(state):
    """현금 + 예금 + 나무(오늘 시세) + 창고(오늘 시세) + 집 가격 − 대출 잔액."""
    parts = {"cash": state["cash"], "deposit": state["deposit"]["amount"], "trees": orchard_value(state),
             "storage": storage_value(state), "house": house_value(state), "loans": loan_balance(state)}
    parts["total"] = parts["cash"] + parts["deposit"] + parts["trees"] + parts["storage"] + parts["house"] - parts["loans"]
    return parts


def weights(state):
    """나무별 비중(%) {tree: pct} (보유한 나무만)."""
    total = orchard_value(state)
    if not total:
        return {}
    return {t: n * tree_price(state, t) / total * 100 for t, n in state["trees"].items() if n}


def max_weight(state):
    """최대 비중 = max(가치_i) / 과수원 총가치. 바구니(ETF)도 한 종목으로 센다 (명세 6-3)."""
    w = weights(state)
    return max(w.values()) if w else 0


def change_7d(state, tree):
    hist = state["treeHist"][tree][-7:]
    return (hist[-1] / hist[0] - 1) * 100 if len(hist) > 1 and hist[0] else 0.0


# =====================================================================
# 밭 · 도구 · 집
# =====================================================================

def crop_yield(state, crop):
    level = state["tools"].get("wateringCan", 1)
    return round(RULES["crops"][crop]["yield"] * (1 + S["toolYieldBonusPerLevel"] * (level - 1)))


def plot_info(state, i):
    p = state["plots"][i]
    if not p.get("crop"):
        return {"index": i, "empty": True}
    c = RULES["crops"][p["crop"]]
    grown = state["day"] - p["planted"]
    ready = grown >= c["days"]
    qty = crop_yield(state, p["crop"])
    price = item_price(state, c["item"])
    sale = qty * price
    profit = sale - c["seedCost"]
    return {"index": i, "empty": False, "crop": p["crop"], "name": c["name"], "planted": p["planted"],
            "harvest_day": p["planted"] + c["days"], "days_left": max(0, c["days"] - grown), "ready": ready,
            "progress": min(1.0, grown / c["days"]), "seg": min(10, math.floor(grown / c["days"] * 10)),
            "stage": 4 if ready else 1 + min(2, int(grown / c["days"] * 3)), "cost": c["seedCost"], "qty": qty,
            "price": price, "sale": sale, "profit": profit, "profit_pct": round(profit / c["seedCost"] * 100),
            "note": c.get("note", "")}


def seed_options(state):
    """씨앗 상점 비교표: 원가, 기간, 예상 수확량, 오늘 시세, 예상 이익, 하루당 이익."""
    out = []
    for cid, c in RULES["crops"].items():
        qty = crop_yield(state, cid)
        price = item_price(state, c["item"])
        profit = qty * price - c["seedCost"]
        out.append({"crop": cid, "name": c["name"], "cost": c["seedCost"], "days": c["days"], "qty": qty,
                    "price": price, "profit": profit, "per_day": round(profit / c["days"]),
                    "affordable": state["cash"] >= c["seedCost"]})
    return out


def tool_offer(state):
    """물뿌리개 다음 단계: 가격, 효과, 본전 회수일 = 가격 / (최근 7일 작물 판매 평균 × 0.25)."""
    level = state["tools"].get("wateringCan", 1)
    prices = RULES["tools"]["wateringCan"]["prices"]
    if level >= len(prices):
        return None
    price = prices[level]
    recent = state.get("cropSales", [])[-7:]
    extra = (sum(recent) / len(recent) if recent else 0) * S["toolYieldBonusPerLevel"]
    payback = math.ceil(price / extra) if extra else None
    return {"name": RULES["tools"]["wateringCan"]["name"], "level": level + 1, "price": price,
            "bonus_pct": round(S["toolYieldBonusPerLevel"] * 100), "extra_per_day": round(extra), "payback": payback}


def avg_daily_net(state, days=7):
    recent = [h.get("net", 0) for h in state["history"][-days:]]
    return round(sum(recent) / len(recent)) if recent else 0


def house_plan(state):
    """다음 집: 가격, 부족액, 모아서 짓기 예상일(부족액 / 최근 7일 평균 순수입), 대출 상환액(×1.05, 7일 뒤)."""
    nxt = next_house(state)
    if not nxt:
        return None
    shortfall = max(0, nxt["price"] - state["cash"])
    avg = avg_daily_net(state)
    repay = round(shortfall * (1 + S["loanRatePer7Days"]))
    return {"tier": nxt["tier"], "name": nxt["name"], "price": nxt["price"], "shortfall": shortfall,
            "avg_net": avg, "save_days": math.ceil(shortfall / avg) if avg > 0 and shortfall else (0 if not shortfall else None),
            "repay": repay, "interest": repay - shortfall, "loan_day": state["day"] + S["loanDays"],
            "storage_plus": nxt["storage"] - house(state)["storage"],
            "ap_plus": nxt["actionPoints"] - house(state)["actionPoints"],
            "progress": min(1.0, state["cash"] / nxt["price"]) if nxt["price"] else 1.0}


# =====================================================================
# 6-8 능력치 · 6-9 도감 · 6-10 경험치
# =====================================================================

def stats(state):
    """0~100 (최근 7일). 학생 화면에는 숫자로 보여 주지 않는다."""
    if state.get("statsOverride"):
        return dict(state["statsOverride"])
    days = state.get("daily", [])[-(S["statDays"] - 1):] + [state.get("counters", {})]
    c = {}
    for d in days:
        for k, v in d.items():
            c[k] = c.get(k, 0) + v
    deals = c.get("trades", 0) + c.get("sells", 0)
    trade = round((c.get("good_trades", 0) + c.get("sells_above", 0)) / deals * 100) if deals else 50
    positive = sum(max(0, h.get("net", 0)) for h in state["history"][-S["statDays"]:])
    saving = min(100, round(c.get("saved", 0) / positive * 100)) if positive else 50
    knowledge = round(len(state["dex"]) / len(RULES["dex"]) * 100)
    risk = 50 if not orchard_value(state) else max(0, min(100, round(100 - max(0, max_weight(state) - 30))))
    risk = min(100, risk + 10 * c.get("storm_response", 0))
    planning = max(0, min(100, 70 + 10 * c.get("wish_wait", 0) - 20 * c.get("buy_now", 0)
                          - 30 * c.get("missed_living", 0) - 30 * c.get("overdue", 0)))
    return {"trade": trade, "saving": saving, "knowledge": knowledge, "risk": risk, "planning": planning}


def unlock(state, key):
    """도감 개념을 연다 (경험으로만). 처음이면 경험치 +20, 토리 설명을 돌려준다."""
    if key in state["dex"]:
        return None
    state["dex"].append(key)
    state.setdefault("todayDex", []).append(key)
    state["exp"] += RULES["exp"]["dex"]
    d = RULES["dex"][key]
    return f"새 도감: {d['label']}! {d['text']}"


def _count(state, key, n=1):
    state.setdefault("counters", {})
    state["counters"][key] = state["counters"].get(key, 0) + n


def _spend_ap(state):
    if state["ap"] <= 0:
        return False
    state["ap"] -= 1
    state["exp"] += RULES["exp"]["action"]
    return True


def _line(state, kind, label, amount):
    state["today"][kind].append([label, amount])


# =====================================================================
# 행동 (상태를 바꾸고 (ok, 안내 문장) 반환)
# =====================================================================

NO_AP = "행동력이 다 떨어졌어요. '하루 마치기'로 쉬고 내일 다시 해요."


def harvest(state, i):
    info = plot_info(state, i)
    if info["empty"] or not info["ready"]:
        return False, "아직 수확할 수 없어요."
    item = RULES["crops"][info["crop"]]["item"]
    if item not in state["inventory"] and len(state["inventory"]) >= house(state)["storage"]:
        return False, "창고가 가득 찼어요. 물건을 팔거나 집을 키워 창고를 늘려요."
    if not _spend_ap(state):
        return False, NO_AP
    state["inventory"][item] = state["inventory"].get(item, 0) + info["qty"]
    state["plots"][i] = {"crop": None, "planted": None}
    msg = f"{info['name']} {info['qty']}개를 수확해 창고에 넣었어요. 원가 {num(info['cost'])}냥 → 오늘 시세로 {num(info['sale'])}냥어치예요."
    tip = unlock(state, "cost_profit")
    return True, msg + (f" {tip}" if tip else "")


def plant(state, i, crop):
    if state["plots"][i].get("crop"):
        return False, "이미 작물이 자라고 있어요."
    c = RULES["crops"][crop]
    if state["cash"] < c["seedCost"]:
        return False, f"씨앗값 {num(c['seedCost'])}냥이 모자라요."
    if not _spend_ap(state):
        return False, NO_AP
    state["cash"] -= c["seedCost"]
    state["plots"][i] = {"crop": crop, "planted": state["day"]}
    _line(state, "expense", f"{c['name']} 씨앗 구입", -c["seedCost"])
    return True, f"{c['name']} 씨앗을 심었어요. {state['day'] + c['days']}일차에 수확할 수 있어요."


def gather(state, kind):
    g = RULES["gather"][kind]
    if kind not in state["inventory"] and len(state["inventory"]) >= house(state)["storage"]:
        return False, "창고가 가득 찼어요."
    if not _spend_ap(state):
        return False, NO_AP
    n = state["counters"].get(f"gather-{kind}", 0) if state.get("counters") else 0
    qty = rng(state, state["day"], f"gather-{kind}-{n}").randint(g["min"], g["max"])
    _count(state, f"gather-{kind}")
    state["inventory"][kind] = state["inventory"].get(kind, 0) + qty
    return True, f"{g['label']}: {item_name(kind)} {qty}개를 얻었어요."


def sell(state, item, qty=None):
    have = state["inventory"].get(item, 0)
    qty = have if qty is None else min(qty, have)
    if qty <= 0:
        return False, "팔 물건이 없어요."
    if not _spend_ap(state):
        return False, NO_AP
    units = unit_prices(state, item, qty)
    total = sum(units)
    state["cash"] += total
    state["inventory"][item] = have - qty
    if not state["inventory"][item]:
        del state["inventory"][item]
    state["soldToday"][item] = state["soldToday"].get(item, 0) + qty
    sales = state["today"].setdefault("sales", {})
    s = sales.setdefault(item, [0, 0])
    s[0] += qty
    s[1] += total
    _count(state, "sells")
    if item_price(state, item) > RULES["items"][item]["basePrice"]:
        _count(state, "sells_above")
    if "crop" in RULES["items"][item]["tags"]:
        _count(state, "crop_sales", total)
    msg = f"{item_name(item)} {qty}개를 {num(total)}냥에 팔았어요."
    if units[0] < item_price(state, item):
        msg += f" 오늘 이미 많이 팔아서 개당 {num(units[0])}냥으로 내려갔어요(공급 증가)."
    elif supply_drop(state["soldToday"][item]) > 0:
        msg += " 오늘 너무 많이 팔아서, 다음에 팔 때는 값이 조금 내려가요(공급 증가)."
    if any(e["kind"] == "festival" and e["target"] == item for e in state["events"]["today"]):
        tip = unlock(state, "supply_demand")
        if tip:
            msg += f" {tip}"
    return True, msg


def offer_values(state, offer=None):
    o = offer or state.get("offer")
    if not o:
        return None
    give = sum(item_price(state, i) * n for i, n in o["give"].items())
    want = sum(item_price(state, i) * n for i, n in o["want"].items())
    return {"give": give, "want": want, "good": give > want}


def trade(state):
    o = state.get("offer")
    if not o:
        return False, "오늘은 거래 제안이 없어요."
    if any(state["inventory"].get(i, 0) < n for i, n in o["want"].items()):
        return False, "바꿔 줄 물건이 모자라요."
    if not _spend_ap(state):
        return False, NO_AP
    v = offer_values(state)
    for i, n in o["want"].items():
        state["inventory"][i] -= n
        if not state["inventory"][i]:
            del state["inventory"][i]
    for i, n in o["give"].items():
        state["inventory"][i] = state["inventory"].get(i, 0) + n
    state["offer"] = None
    _count(state, "trades")
    if v["good"]:
        _count(state, "good_trades")
        state["exp"] += RULES["exp"]["profitTrade"]
    msg = (f"거래 완료! 받은 것 {num(v['give'])}냥어치, 준 것 {num(v['want'])}냥어치 — "
           + ("이득인 거래였어요." if v["good"] else "손해인 거래였어요. 다음엔 시세로 먼저 계산해 봐요."))
    tip = unlock(state, "value_compare")
    return True, msg + (f" {tip}" if tip else "")


def _tree_ap(state, tree):
    """과수원 매매는 그날 그 나무를 처음 거래할 때만 행동력 1."""
    if tree in state["treeTradedToday"]:
        return True
    if not _spend_ap(state):
        return False
    state["treeTradedToday"].append(tree)
    return True


def buy_tree(state, tree):
    price = round(tree_price(state, tree) * (1 + S["tradeFeeRate"]))
    if state["cash"] < price:
        return False, f"현금이 모자라요. {tree_name(tree)}는 {num(price)}냥이에요."
    if not _tree_ap(state, tree):
        return False, NO_AP
    state["cash"] -= price
    state["trees"][tree] += 1
    msg = f"{tree_name(tree)} 1그루를 {num(price)}냥에 샀어요."
    if any(e["kind"] == "storm" for e in state["events"]["tomorrow"]):
        _count(state, "storm_response")
    tips = [unlock(state, "etf") if RULES["trees"][tree].get("isBasket") else None, _check_diversified(state)]
    return True, " ".join([msg] + [t for t in tips if t])


def sell_tree(state, tree):
    if state["trees"][tree] <= 0:
        return False, "팔 나무가 없어요."
    if not _tree_ap(state, tree):
        return False, NO_AP
    price = round(tree_price(state, tree) * (1 - S["tradeFeeRate"]))
    state["cash"] += price
    state["trees"][tree] -= 1
    if any(e["kind"] == "storm" and e["target"] == tree for e in state["events"]["tomorrow"]):
        _count(state, "storm_response")
    tip = _check_diversified(state)
    return True, f"{tree_name(tree)} 1그루를 {num(price)}냥에 팔았어요." + (f" {tip}" if tip else "")


def _check_diversified(state):
    kinds = sum(1 for n in state["trees"].values() if n)
    if kinds >= 3 and max_weight(state) <= S["warnWeightPct"]:
        return unlock(state, "diversification")
    return None


def wish_temptation(state):
    t = state.get("temptation")
    if not t:
        return False, "오늘의 유혹 상품이 없어요."
    state["wish"] = {"name": t["name"], "price": t["price"], "day": state["day"]}
    state["temptation"] = None
    _count(state, "wish_wait")
    return True, f"찜했어요! 내일({state['day'] + 1}일차) 다시 물어볼게요."


def opportunity_text(state, price):
    apple = item_price(state, "apple")
    return f"{num(price)}냥이면 사과 {math.ceil(price / apple)}개를 팔아야 하는 돈이에요. 정말 지금 필요할까요?"


def buy_decor(state, source):
    """source: temptation(바로 사기) | wish(하루 기다린 뒤 사기)."""
    t = state.get(source)
    if not t:
        return False, "살 물건이 없어요."
    if state["cash"] < t["price"]:
        return False, "현금이 모자라요."
    state["cash"] -= t["price"]
    state["decor"].append(t["name"])
    state[source] = None
    _line(state, "expense", f"{t['name']} 구입", -t["price"])
    if source == "temptation":
        _count(state, "buy_now")
        return True, f"{t['name']}을(를) 샀어요. 예쁘지만 돈을 벌어다 주지는 않아요."
    return True, f"하루 기다리고도 갖고 싶었던 {t['name']}을(를) 샀어요. 계획한 소비예요."


def drop_wish(state):
    w = state.get("wish")
    if not w:
        return False, "찜한 물건이 없어요."
    state["wish"] = None
    tip = unlock(state, "opportunity_cost")
    return True, f"{w['name']}을(를) 사지 않기로 했어요. {num(w['price'])}냥이 그대로 남았어요." + (f" {tip}" if tip else "")


def upgrade_tool(state):
    t = tool_offer(state)
    if not t:
        return False, "이미 가장 좋은 물뿌리개예요."
    if state["cash"] < t["price"]:
        return False, f"{num(t['price'])}냥이 모자라요."
    state["cash"] -= t["price"]
    state["tools"]["wateringCan"] = t["level"]
    _line(state, "expense", f"물뿌리개 Lv.{t['level']}", -t["price"])
    tip = unlock(state, "payback")
    return True, f"물뿌리개 Lv.{t['level']}! 수확량이 {t['bonus_pct']}% 늘어요." + (f" {tip}" if tip else "")


def deposit(state, amount):
    amount = int(amount)
    if amount <= 0 or amount > state["cash"]:
        return False, "넣을 수 있는 금액이 아니에요."
    if state["deposit"]["amount"] == 0:
        state["deposit"]["last"] = state["day"]
    state["cash"] -= amount
    state["deposit"]["amount"] += amount
    _count(state, "saved", amount)
    return True, f"은행에 {num(amount)}냥을 넣었어요. 7일마다 이자 1%가 붙어요(복리)."


def withdraw(state, amount):
    amount = int(amount)
    if amount <= 0 or amount > state["deposit"]["amount"]:
        return False, "꺼낼 수 있는 금액이 아니에요."
    state["deposit"]["amount"] -= amount
    state["cash"] += amount
    _count(state, "saved", -amount)
    return True, f"예금에서 {num(amount)}냥을 꺼냈어요."


def build_house(state, mode):
    """mode: cash(모은 돈으로) | loan(부족액을 빌려서)."""
    plan = house_plan(state)
    if not plan:
        return False, "이미 가장 큰 집이에요."
    if mode == "cash":
        if plan["shortfall"]:
            return False, f"{num(plan['shortfall'])}냥이 모자라요."
        state["cash"] -= plan["price"]
        tip = None
    else:
        if not plan["shortfall"]:
            return build_house(state, "cash")
        state["loans"].append({"principal": plan["shortfall"], "due": plan["repay"], "takenDay": state["day"],
                               "dueDay": plan["loan_day"], "repaid": False, "overdue": False})
        state["cash"] = state["cash"] + plan["shortfall"] - plan["price"]
        tip = unlock(state, "interest")
    state["house"] = plan["tier"]
    state["houseDays"][str(plan["tier"])] = state["day"]
    state["exp"] += RULES["exp"]["house"]
    while len(state["plots"]) < house(state)["plots"]:
        state["plots"].append({"crop": None, "planted": None})
    msg = f"{plan['name']}을(를) 지었어요! 창고 {house(state)['storage']}칸, 하루 행동력 {house(state)['actionPoints']}."
    if mode == "loan" and plan["shortfall"]:
        msg += f" {plan['loan_day']}일차에 {num(plan['repay'])}냥을 갚아야 해요."
    return True, msg + (f" {tip}" if tip else "")


def repay_loan(state, index):
    loan = state["loans"][index]
    if loan.get("repaid"):
        return False, "이미 갚은 대출이에요."
    if state["cash"] < loan["due"]:
        return False, f"{num(loan['due'])}냥이 있어야 갚을 수 있어요."
    state["cash"] -= loan["due"]
    loan["repaid"] = True
    _line(state, "expense", "대출 상환 (이자 포함)", -loan["due"])
    return True, f"대출 {num(loan['due'])}냥을 갚았어요."


# =====================================================================
# 6-1 하루 진행
# =====================================================================

def gen_offer(state, day):
    if not state["inventory"]:
        return None
    r = rng(state, day, "offer")
    if r.random() > RULES["events"]["offerChance"]:
        return None
    want_item = r.choice(sorted(state["inventory"]))
    want_qty = max(1, min(state["inventory"][want_item], r.randint(1, 4)))
    give_item = r.choice([i for i in RULES["items"] if i != want_item])
    ratio = r.uniform(*RULES["events"]["offerValueRange"])
    give_qty = max(1, round(want_qty * item_price(state, want_item) * ratio / item_price(state, give_item)))
    return {"from": r.choice(NEIGHBORS), "give": {give_item: give_qty}, "want": {want_item: want_qty}}


def gen_temptation(state, day):
    return rng(state, day, "temptation").choice(RULES["temptations"]) if day > 1 else None


def can_end_day(state, real_date):
    return state["realLog"].get(real_date, 0) < S["maxGameDaysPerRealDay"]


def end_day(state, real_date):
    """6-1 순서대로 하루를 마치고 다음 날로. 결산 기록(dict)을 돌려준다 (실제 하루 상한이면 None)."""
    if not can_end_day(state, real_date):
        return None
    day = state["day"]
    sales = state["today"].pop("sales", {})
    income = ([[f"판매 ({' · '.join(f'{item_name(i)} {q}' for i, (q, _) in sales.items())})",
                sum(a for _, a in sales.values())]] if sales else []) + state["today"]["income"]
    expense = list(state["today"]["expense"])

    # 1 생활비 (못 내도 게임 오버 없이 기록만)
    cost = house(state)["livingCost"]
    paid = min(state["cash"], cost)
    state["cash"] -= paid
    expense.append(["생활비", -cost])
    if paid < cost:
        _count(state, "missed_living")
    # 2 작물 성장: day가 지나면 plot_info가 계산한다
    # 3 배당 열매
    div = {t: RULES["trees"][t]["dividendPerDay"] * n for t, n in state["trees"].items()
           if n and RULES["trees"][t]["dividendPerDay"]}
    if div:
        amount = sum(div.values())
        state["cash"] += amount
        income.append([f"배당 열매 ({' · '.join(tree_name(t) for t in div)})", amount])
        unlock(state, "dividend")
    # 4 예금 이자 (7일마다 1%, 복리)
    dep = state["deposit"]
    if dep["amount"] > 0 and day + 1 - dep["last"] >= 7:  # 넣은 날부터 7일째가 되는 날로 넘어갈 때
        interest = round(dep["amount"] * S["depositRatePer7Days"])
        dep["amount"] += interest
        dep["last"] = day + 1
        income.append(["예금 이자 (복리)", interest])
        unlock(state, "compound")
    # 5 대출 만기 (현금이 모자라면 연체 표시만)
    for loan in state["loans"]:
        if not loan.get("repaid") and day + 1 >= loan["dueDay"]:  # 만기일로 넘어갈 때
            if state["cash"] >= loan["due"]:
                state["cash"] -= loan["due"]
                loan["repaid"] = True
                expense.append(["대출 상환 (이자 포함)", -loan["due"]])
            elif not loan.get("overdue"):
                loan["overdue"] = True
                _count(state, "overdue")
    # 6 다음 날 시세 (7 이벤트 반영)
    new_day = day + 1
    events_new = state["events"]["tomorrow"]
    before = orchard_value(state)
    rets = tree_returns(state["seed"], new_day, events_new)
    for t, r in rets.items():
        hist = state["treeHist"][t]
        hist.append(max(10, round(hist[-1] * (1 + r))))
        if len(hist) > S["treeHistoryDays"]:
            hist.pop(0)
            state["treeHistStart"] = state.get("treeHistStart", 1) + 1
    change = orchard_value(state) - before
    if change:
        (income if change > 0 else expense).append(["과수원 시세 변화", change])
    if change < 0 and any(e["kind"] == "storm" and state["trees"].get(e["target"]) for e in events_new):
        unlock(state, "concentration")
    state["market"] = gen_market(state["seed"], new_day, events_new, state["market"])
    state["events"] = {"today": events_new, "tomorrow": gen_events(state["seed"], new_day + 1)}
    # 8 행동력 회복
    state["ap"] = house(state)["actionPoints"]
    # 9 결산 기록
    total = net_worth(state)["total"]
    cash_net = sum(a for _, a in income if _ != "과수원 시세 변화") + sum(
        a for _, a in expense if _ != "과수원 시세 변화")
    record = {"day": day, "netWorth": total, "net": cash_net, "netChange": total - state.get("dayStartNetWorth", total),
              "income": income, "expense": expense,
              "newDex": [RULES["dex"][k]["label"] for k in state.pop("todayDex", [])]}
    state["history"].append({"day": day, "netWorth": total, "net": cash_net})
    state["lastResult"] = record
    state.setdefault("daily", []).append(state.get("counters", {}))
    state["daily"] = state["daily"][-S["statDays"]:]
    state.setdefault("cropSales", []).append(state.get("counters", {}).get("crop_sales", 0))
    state["cropSales"] = state["cropSales"][-7:]
    state["statsOverride"] = None
    # 다음 날 준비
    state["day"] = new_day
    state["counters"] = {}
    state["soldToday"] = {}
    state["treeTradedToday"] = []
    state["today"] = {"income": [], "expense": []}
    state["offer"] = gen_offer(state, new_day)
    state["temptation"] = gen_temptation(state, new_day)
    state["dayStartNetWorth"] = total
    state["realLog"][real_date] = state["realLog"].get(real_date, 0) + 1
    return record


def new_state(name, seed, avatar="blue"):
    """1일차: 1,000냥과 텐트."""
    tent = RULES["houses"][0]
    events_today = gen_events(seed, 1)
    state = {"version": VERSION, "seed": seed, "name": name, "avatar": avatar, "day": 1,
             "ap": tent["actionPoints"], "cash": S["startCash"], "house": 0, "exp": 0, "inventory": {},
             "plots": [{"crop": None, "planted": None} for _ in range(tent["plots"])],
             "trees": {t: 0 for t in RULES["trees"]},
             "treeHist": {t: [d["basePrice"]] for t, d in RULES["trees"].items()}, "treeHistStart": 1,
             "market": gen_market(seed, 1, events_today),
             "events": {"today": events_today, "tomorrow": gen_events(seed, 2)},
             "offer": None, "temptation": None, "wish": None, "decor": [],
             "deposit": {"amount": 0, "last": 1}, "loans": [], "tools": {"wateringCan": 1}, "dex": [],
             "soldToday": {}, "treeTradedToday": [], "today": {"income": [], "expense": []},
             "dayStartNetWorth": S["startCash"], "history": [], "houseDays": {"0": 1}, "cropSales": [],
             "counters": {}, "daily": [], "statsOverride": None, "realLog": {}, "lastResult": None}
    return state


def migrate(state):
    """저장 데이터 버전 맞추기 (지금은 1뿐). 빠진 칸은 기본값으로 채운다."""
    base = new_state(state.get("name", ""), state.get("seed", 1))
    for k, v in base.items():
        state.setdefault(k, v)
    state["version"] = VERSION
    return state


ACTIONS = {
    "harvest": lambda s, a: harvest(s, int(a["plot"])),
    "plant": lambda s, a: plant(s, int(a["plot"]), a["crop"]),
    "gather": lambda s, a: gather(s, a["kind"]),
    "sell": lambda s, a: sell(s, a["item"], a.get("qty")),
    "trade": lambda s, a: trade(s),
    "buy_tree": lambda s, a: buy_tree(s, a["tree"]),
    "sell_tree": lambda s, a: sell_tree(s, a["tree"]),
    "wish": lambda s, a: wish_temptation(s),
    "buy_now": lambda s, a: buy_decor(s, "temptation"),
    "wish_buy": lambda s, a: buy_decor(s, "wish"),
    "wish_drop": lambda s, a: drop_wish(s),
    "upgrade": lambda s, a: upgrade_tool(s),
    "deposit": lambda s, a: deposit(s, a["amount"]),
    "withdraw": lambda s, a: withdraw(s, a["amount"]),
    "build": lambda s, a: build_house(s, a["mode"]),
    "repay": lambda s, a: repay_loan(s, int(a["loan"])),
}


def act(state, action):
    """화면에서 온 행동 하나. (ok, 안내 문장)."""
    fn = ACTIONS.get(action.get("action"))
    return fn(state, action) if fn else (False, "알 수 없는 행동이에요.")
