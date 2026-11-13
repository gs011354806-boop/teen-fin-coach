"""틴틴 자산섬 v2: 게임 상태 → 화면 값 (components/island2/index.html이 그린다). LLM 호출 금지.

규칙 계산은 engine/island_game.py, 여기서는 그 값을 화면에 보여 줄 모양으로만 바꾼다.
능력치는 숫자 없이 '잘하는 중 / 연습 중 / 다음에 키울 능력'으로만 넘긴다 (2026-11-13 결정, CLAUDE.md 규칙 5).
"""

from engine import island_game as g
from engine.island_game import RULES, S, num

TREE_COLORS = {"red": "apple", "gold": "goldApple", "mango": "mango", "basket": "basket"}
NEXT_TEXT = {"trade": "거래 감각을 키워요: 시세가 평소보다 높은 날 팔아 봐요",
             "saving": "저축 습관을 키워요: 번 돈의 일부를 은행에 넣어 봐요",
             "knowledge": "금융지식을 키워요: 새로운 일을 해 보며 도감을 열어 봐요",
             "planning": "계획성을 키워요: 사고 싶을 땐 하루 기다려 봐요"}


def spark(values, w=64, h=22, pad=2):
    """7일 미니 차트 polyline 좌표."""
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    step = (w - 2 * pad) / max(1, len(values) - 1)
    return " ".join(f"{round(pad + i * step)},{round(h - pad - (v - lo) / span * (h - 2 * pad))}"
                    for i, v in enumerate(values))


def josa(word, pair):
    """받침에 따라 조사 고르기: pair = ("이", "가") 등."""
    code = ord(word[-1]) - 0xAC00
    return pair[0] if 0 <= code <= 11171 and code % 28 else pair[1]


def coach(state):
    """그날의 이벤트 하나를 골라 토리의 말과 선택지 2개로."""
    inv = state["inventory"]
    for e in state["events"]["today"]:
        if e["kind"] == "festival" and inv.get(e["target"]):
            n = g.item_name(e["target"])
            return {"text": f"축제 때문에 {n} 값이 어제보다 올랐대! 창고에 {n} {inv[e['target']]}개가 있는데, 지금 팔아볼까?",
                    "choices": [{"label": "시장에 가서 시세 보고 팔래", "to": "market"},
                                {"label": "과수원 나무 시세부터 볼래", "to": "orchard"}]}
    for e in state["events"]["tomorrow"]:
        if e["kind"] == "storm" and state["trees"].get(e["target"]):
            name = g.tree_name(e["target"])
            w = round(g.weights(state).get(e["target"], 0))
            return {"text": f"내일 {name[:-2]} 마을에 태풍 예보가 있대! 우리 과수원은 {name}{josa(name, ('이', '가'))} {w}%인데, 어떻게 할까?",
                    "choices": [{"label": "과수원에 가서 나눠 심을래", "to": "orchard"},
                                {"label": "시장부터 볼래", "to": "market"}]}
    ready = [g.plot_info(state, i) for i in range(len(state["plots"]))]
    ready = [p for p in ready if not p["empty"] and p["ready"]]
    if ready:
        n = ready[0]["name"]
        return {"text": f"{n}{josa(n, ('이', '가'))} 다 자랐어! 수확해서 시장에 팔아 볼까?",
                "choices": [{"label": "밭에 가서 수확할래", "to": "farm"}, {"label": "오늘 시세부터 볼래", "to": "market"}]}
    if state.get("offer"):
        return {"text": f"토끼 이웃 {state['offer']['from']}가 물건을 바꾸자고 왔어. 오늘 시세로 계산해 보고 정하자!",
                "choices": [{"label": "시장에서 거래 제안 볼래", "to": "market"}, {"label": "과수원 시세부터 볼래", "to": "orchard"}]}
    if any(l.get("overdue") and not l.get("repaid") for l in state["loans"]):
        return {"text": "갚을 날이 지난 대출이 있어. 현금이 모이면 상태창에서 먼저 갚자.",
                "choices": [{"label": "상태창에서 대출 보기", "to": "status"}, {"label": "시장에서 돈 벌기", "to": "market"}]}
    if state["day"] == 1:
        return {"text": f"어서 와! 텐트 하나와 {num(state['cash'])}냥으로 시작해. 밭에 씨앗을 심거나 바닷가에서 조개를 주워 팔아 보자.",
                "choices": [{"label": "밭에 씨앗 심으러 갈래", "to": "farm"}, {"label": "시장 시세부터 볼래", "to": "market"}]}
    return {"text": f"오늘은 무엇을 해 볼까? 행동력 {state['ap']}개가 남았어.",
            "choices": [{"label": "밭 둘러볼래", "to": "farm"}, {"label": "시장 시세 볼래", "to": "market"}]}


def _orchard(state):
    ws = g.weights(state)
    storm = next((e for e in state["events"]["tomorrow"] if e["kind"] == "storm"), None)
    warn = bool(ws) and max(ws.values()) > S["warnWeightPct"]
    top = max(ws, key=ws.get) if ws else None
    rows = []
    for tid, t in RULES["trees"].items():
        hist = state["treeHist"][tid][-7:]
        rows.append({"id": tid, "name": t["name"], "trait": t["trait"], "price": num(hist[-1]),
                     "chg": round(g.change_7d(state, tid)), "spark": spark(hist) if len(hist) > 1 else "",
                     "held": state["trees"][tid], "can_buy": state["cash"] >= hist[-1], "can_sell": state["trees"][tid] > 0})
    if warn:
        name = g.tree_name(top)
        title = f"{name}{josa(name, ('이', '가'))} {round(ws[top])}%예요! 병충해 주의"
        body = ("내일 태풍이 오면 과수원 전체가 크게 흔들려요. " if storm else "태풍 한 번에 과수원 전체가 흔들릴 수 있어요. ") + \
            "한 종목에 몰린 상태를 집중 위험이라고 해요. 다른 나무를 사서 나눠 볼까요?"
    elif ws:
        title = "튼튼한 과수원! 여러 나무에 나눠 심었어요" if len(ws) > 1 else "튼튼한 과수원이에요"
        body = " · ".join(f"{g.tree_name(t)} {round(p)}%" for t, p in ws.items()) + \
            (" — 한 나무가 태풍을 맞아도 다른 나무가 버텨줘요(분산투자)." if len(ws) > 1 else "")
    else:
        title, body = "아직 빈 과수원이에요", "나무 = 종목이에요. 묘목을 사면 열매(배당)와 시세 변화가 생겨요."
    return {"board": (f"게시판: {g.tree_name(storm['target'])[:-2]} 마을에 내일 태풍 예보" if storm
                      else "게시판: 내일은 큰 소식이 없어요"),
            "forecast": f"{state['day'] + 1}일차 {'태풍' if storm else '맑음'}", "storm": bool(storm),
            "cash": num(state["cash"]), "rows": rows,
            "composition": [{"id": t, "pct": round(p), "color": TREE_COLORS[t]} for t, p in ws.items()],
            "warn": warn, "title": title, "body": body}


def _market(state):
    items = []
    for item, qty in sorted(state["inventory"].items(), key=lambda kv: list(RULES["items"]).index(kv[0])):
        m = state["market"][item]
        unit = g.unit_prices(state, item, 1)[0]
        festival = any(e["kind"] == "festival" and e["target"] == item for e in state["events"]["today"])
        items.append({"id": item, "name": g.item_name(item), "qty": qty, "price": num(unit), "diff": m["price"] - m["prev"],
                      "note": "축제 수요" if festival else "", "unit": unit, "total": num(unit * qty)})
    offer = None
    if state.get("offer"):
        o = state["offer"]
        v = g.offer_values(state)
        give = " · ".join(f"{g.item_name(i)} {n}개" for i, n in o["give"].items())
        want = " · ".join(f"{g.item_name(i)} {n}개" for i, n in o["want"].items())
        calc = lambda side: " + ".join(f"{g.item_name(i)} {n}×{g.item_price(state, i)}" for i, n in side.items())
        offer = {"from": o["from"], "text": f"\"{give} 줄게, {want}{josa(want[:-1] + '개', ('랑', '랑'))} 바꿀래?\"",
                 "hint": f"계산해 보기: {calc(o['give'])}={num(v['give'])}냥 vs {calc(o['want'])}={num(v['want'])}냥",
                 "can": all(state["inventory"].get(i, 0) >= n for i, n in o["want"].items())}
    t, w = state.get("temptation"), state.get("wish")
    return {"cash": num(state["cash"]), "items": items, "offer": offer,
            "temptation": ({"name": t["name"], "price": num(t["price"]), "opportunity": g.opportunity_text(state, t["price"]),
                            "can": state["cash"] >= t["price"]} if t else None),
            "wish": ({"name": w["name"], "price": num(w["price"]), "day": w["day"], "waited": state["day"] > w["day"],
                      "can": state["cash"] >= w["price"]} if w else None)}


def _status(state):
    h = g.house(state)
    level, exp_in, exp_need = g.level_from_exp(state["exp"])
    nw = g.net_worth(state)
    ws = g.weights(state)
    st = g.stats(state)
    low = min(g.STAT_KEYS, key=lambda k: st[k])
    top = max(ws, key=ws.get) if ws else None
    days = state["history"][-11:] + [{"day": state["day"], "netWorth": nw["total"]}]
    hi = max(d["netWorth"] for d in days) or 1
    built = {int(day): int(tier) for tier, day in state["houseDays"].items() if int(tier) > 0}
    bars = [{"day": d["day"], "h": max(2, round(d["netWorth"] / hi * 70)),
             "kind": "today" if d["day"] == state["day"] else "house" if d["day"] in built else ""} for d in days]
    shown = [(d, RULES["houses"][t]["name"]) for d, t in built.items() if days[0]["day"] <= d <= state["day"]]
    if low == "risk":
        name = g.tree_name(top) if top else ""
        nxt = (f"위험관리가 낮아요: {name}{josa(name, ('이', '가'))} {round(ws[top])}%예요" if top
               else "위험관리를 키워요: 여러 나무에 나눠 심어 봐요")
    else:
        nxt = NEXT_TEXT[low]
    return {"level": level, "title": g.title_for(level), "house": h["name"], "exp_seg": round(exp_in / exp_need * 10),
            "net_worth": num(nw["total"]), "bars": bars,
            "chart_labels": [f"{days[0]['day']}일차" + (" 텐트 · 1,000냥" if days[0]["day"] == 1 else ""),
                             (f"{shown[-1][0]}일차 {shown[-1][1]}" if shown else ""), f"{state['day']}일차"],
            "assets": [["현금", num(nw["cash"]), ""], ["은행 예금", num(nw["deposit"]), "(7일마다 이자 1%, 복리)"],
                       ["과수원 나무", num(nw["trees"]), "(오늘 시세)"], ["창고 물건", num(nw["storage"]), "(오늘 시세)"],
                       [f"집 ({h['name']})", num(nw["house"]), ""], ["대출", num(nw["loans"]), ""]],
            "bank": {"deposit": state["deposit"]["amount"], "cash": state["cash"]},
            "loans": [{"index": i, "due": num(l["due"]), "day": l["dueDay"], "overdue": l.get("overdue", False),
                       "can": state["cash"] >= l["due"]} for i, l in enumerate(state["loans"]) if not l.get("repaid")],
            "stats": [{"key": k, "label": g.STAT_LABELS[k], "good": st[k] >= g.GOOD_STAT, "next": k == low} for k in g.STAT_KEYS],
            "next": {"text": nxt, "to": g.STAT_LINKS[low]},
            "dex": {"count": len(state["dex"]), "total": len(RULES["dex"]),
                    "items": [RULES["dex"][k]["label"] for k in state["dex"]][-8:]}}


def build_view(state, real_date, mock=False):
    h = g.house(state)
    plots = [g.plot_info(state, i) for i in range(len(state["plots"]))]
    res = state.get("lastResult")
    return {
        "mock": mock, "day": state["day"], "name": state["name"], "avatar": state.get("avatar", "blue"),
        "hud": {"day": f"{state['day']}일차",
                "weather": "storm" if any(e["kind"] == "storm" for e in state["events"]["today"]) else "sunny",
                "title": f"{state['name']}의 섬 · {h['name']}", "cash": num(state["cash"])},
        "map": {"house_label": f"{h['name']} Lv.{state['house'] + 1}", "house_tier": state["house"],
                "plots": [0 if p["empty"] else p["stage"] for p in plots],
                "trees": [t for t, n in state["trees"].items() for _ in range(n)][:4]},
        "coach": dict(coach(state), ap=state["ap"], ap_max=h["actionPoints"],
                      gather=[{"kind": k, "label": v["label"]} for k, v in RULES["gather"].items()],
                      can_end=g.can_end_day(state, real_date),
                      days_left_today=S["maxGameDaysPerRealDay"] - state["realLog"].get(real_date, 0)),
        "farm": {"plots": plots, "seeds": g.seed_options(state), "tool": g.tool_offer(state),
                 "storage": f"창고 {len(state['inventory'])}/{h['storage']}칸"},
        "orchard": _orchard(state),
        "market": _market(state),
        "status": _status(state),
        "result": ({"day": res["day"], "netChange": res["netChange"], "rows": res["income"] + res["expense"],
                    "newDex": " · ".join(res.get("newDex") or [])} if res else None),
        "plan": g.house_plan(state),
    }
