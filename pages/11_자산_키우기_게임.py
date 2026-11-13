"""틴틴 자산섬 (자산 키우기 게임, 2026-11-13 시뮬레이션). 명세: game/tintin_island_handoff/ISLAND_GAME_SPEC.md

내 실제 저축·소비·투자 기록이 섬으로 보인다: ① 내 섬 ② 저축 밭 ③ 투자 과수원 ④ 소비 가방 ⑤ 상태창 ⑥ 주간 결산.
화면(픽셀 아트, 게임 메뉴)은 components/island/index.html 한 장에서 바뀌고, 계산은 engine/island.py가 한다.
이 페이지는 화면 값을 넘기고, 게임 안 동작(태그·찜·퀘스트·토글)을 store의 게임 상태 표에 저장한다.
?mock=1 이면 명세 7장 예시 데이터로 보여 준다 (시안과 비교용, 저장하지 않음).
config.ISLAND_GAME = False면 예전 단어 받기 게임(legacy/catch_game_page.py)을 그대로 보여 준다.
"""

import runpy
from datetime import datetime
from pathlib import Path

import streamlit as st

import config

if not config.ISLAND_GAME:
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "legacy" / "catch_game_page.py"))
    st.stop()

import pandas as pd  # noqa: E402

import ui_common as ui  # noqa: E402
from engine import island, spend_mission as sm, store  # noqa: E402

student = ui.setup("틴틴 자산섬", "🏝️")
sid = student["student_id"]
mock = st.query_params.get("mock") == "1"
PAGES = {"market": ui.MARKET, "envelope": ui.ENVELOPE, "news": ui.NEWS}


def context():
    return dict(allowance=store.load_allowance(), trades=store.load_trades(), prices=store.load_prices(),
                runs=store.load_mission_runs(), concepts=store.load_concepts(), lessons=store.load_lessons(),
                reviews=store.load_game_reviews(), questions=store.load_questions(),
                **{name: store.load_island(name) for name in store.ISLAND_TABLES})


def set_pref(key, value):
    prefs = store.load_island("prefs")
    prefs = prefs[~((prefs["student_id"] == sid) & (prefs["key"] == key))]
    row = pd.DataFrame([{"student_id": sid, "key": key, "value": str(value)}])
    store.save_island("prefs", pd.concat([prefs, row], ignore_index=True))


def handle(event, view, today):
    """게임에서 온 동작 하나를 저장하고, 보여 줄 한 줄을 돌려준다."""
    kind = event.get("type")
    if kind == "page":
        st.switch_page(PAGES[event["page"]])
    if mock:
        return "시안 예시 데이터에서는 저장하지 않아요."
    if kind == "compound":
        set_pref("compound", "on" if event["on"] else "off")
        return "이자 열매를 다시 심으면(복리) 이자에도 이자가 붙어요." if event["on"] else "이자 열매를 따기만 하면(단리) 원금에만 이자가 붙어요."
    if kind == "weekly_seen":
        set_pref("weekly_seen", event["week"])
        got = island.grant(store, sid, today, island.SEEDS["weekly"], "주간 결산 확인", f"weekly-{event['week']}")
        return f"이번 주 결산을 확인했어요. 씨앗 +{got}" if got else None
    if kind == "tag":
        tags = store.load_island("tags")
        tags = tags[~((tags["student_id"] == sid) & (tags["item"] == event["item"]))]
        row = pd.DataFrame([{"student_id": sid, "item": event["item"], "tag": event["tag"]}])
        store.save_island("tags", pd.concat([tags, row], ignore_index=True))
        return f"'{event['item']}'을(를) {'필요' if event['tag'] == 'need' else '원함'}(으)로 바꿨어요. 다음에도 이렇게 나눌게요."
    if kind == "wish_add":
        name, price = event.get("name", "")[:20], int(event.get("price") or 0)
        if not name or price <= 0:
            return "물건 이름과 가격을 적어 주세요."
        store.append_island("wish", {"student_id": sid, "name": name, "price": price,
                                     "added_at": datetime.now().isoformat(timespec="minutes")})
        return f"{name}을(를) 찜했어요. 24시간 뒤에도 갖고 싶은지 다시 물어볼게요."
    if kind == "wish":
        wishes = store.load_island("wish")
        hit = wishes["wish_id"] == event["id"]
        if not hit.any():
            return None
        name, price = wishes.loc[hit, "name"].iloc[0], int(wishes.loc[hit, "price"].iloc[0])
        wishes.loc[hit, ["decision", "decided_at"]] = [event["decision"], datetime.now().isoformat(timespec="minutes")]
        store.save_island("wish", wishes)
        if event["decision"] == "wait":
            return "좋아요! 내일 이 화면에서 다시 물어볼게요."
        if event["decision"] == "cancel":
            got = island.grant(store, sid, today, island.SEEDS["wish_cancel"], f"찜 취소: {name}", f"wish-{event['id']}")
            goal = student["saving_goal"]["item"]
            return (f"참은 {island.won(price)}을 {goal} 화분 물로 줘 볼까요? 용돈봉투에서 모으기로 옮길 수 있어요."
                    + (f" 씨앗 +{got}" if got else " (오늘 씨앗은 다 받았어요)"))
        return "알겠어요. 하루 기다리고도 갖고 싶었다면 계획한 소비예요."
    if kind == "quests":
        chosen = [q for q in view["weekly"]["quests"] if q["id"] in event.get("ids", [])]
        runs = store.load_mission_runs()
        has_mission = sm.active_run(runs, sid) is not None
        options = {o["label"]: o for o in sm.simulation(student, store.load_allowance())["options"]}
        linked = None
        for q in chosen:
            run_id = ""
            if not has_mission and q["mission_option"] in options and linked is None:
                run_id = store.append_mission_run(sm.start_row(student, options[q["mission_option"]], today))
                linked = q["title"]
            store.append_island("quests", {"student_id": sid, "week": view["weekly"]["week"], "quest_id": q["id"],
                                           "title": q["title"], "skill": q["skill"], "seeds": q["seeds"],
                                           "run_id": run_id, "date": today})
        return (f"퀘스트 {len(chosen)}개로 시작해요!" +
                (f" '{linked}'은(는) 미션 탭에서도 확인할 수 있어요." if linked else ""))
    return None


ui.app_bar("틴틴 자산섬", badge="자산 키우기 게임")
with st.container(key="island-page"):  # style.css: 이 화면에서는 앱 아래 탭 바를 숨기고 게임 메뉴를 쓴다
    if mock:
        view = island.build_mock_view()
        today = island.load_mock()["island"]["today"]
    else:
        ctx = context()
        today = sm.today_of(ctx["allowance"])
        island.ensure_rewards(student, ctx, store, today)
        view = island.build_view(student, context())
    view["toast"] = st.session_state.pop("island_toast", None)
    event = ui.island_game(view, key=f"island-{sid}-{'mock' if mock else 'real'}")

if event and event.get("nonce") != st.session_state.get("island_nonce"):
    st.session_state["island_nonce"] = event.get("nonce")
    message = handle(event, view, today)
    if message:
        st.session_state["island_toast"] = message
    st.rerun()
