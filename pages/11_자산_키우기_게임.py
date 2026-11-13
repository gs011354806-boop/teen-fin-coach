"""틴틴 자산섬 (자산 키우기 게임, 2026-11-13 시뮬레이션).

v2(기본): 가상 섬 경제 게임. 명세: game2/tintin_island_handoff/ISLAND_GAME_SPEC.md
- 1일차 텐트와 1,000냥으로 시작해 생산(밭)·판매(시장)·거래(이웃)·투자(과수원)·저축(은행)으로 집과 순자산을 키운다.
- 앱의 실제 금융 데이터(용돈·거래·가상투자)를 읽거나 쓰지 않는다. 게임 상태는 data/students/island_game.json에만.
- 규칙: engine/island_game.py + data/island/rules.json, 화면 값: engine/island_view.py, 화면: components/island2/index.html.
- 게임 시간은 '하루 마치기'로만 흐르고, 실제 하루에 3일까지만 진행한다 (rules.json maxGameDaysPerRealDay).
- ?mock=1 → 명세 7장 시안 상태(12일차 아침), ?mock=result → 12일차 결산 화면. 둘 다 저장하지 않는다.
config.ISLAND_GAME = False → 예전 단어 받기 게임, config.ISLAND_VERSION = 1 → v1 (실제 기록을 섬으로 보기).
"""

import copy
import hashlib
import runpy
from datetime import date
from pathlib import Path

import streamlit as st

import config

LEGACY = Path(__file__).resolve().parent.parent / "legacy"
if not config.ISLAND_GAME:
    runpy.run_path(str(LEGACY / "catch_game_page.py"))
    st.stop()
if config.ISLAND_VERSION == 1:
    runpy.run_path(str(LEGACY / "island_v1_page.py"))
    st.stop()

import ui_common as ui  # noqa: E402
from engine import island_game as g, island_view as iv, store  # noqa: E402

student = ui.setup("틴틴 자산섬", "🏝️")
sid = student["student_id"]
mock = st.query_params.get("mock")
real_date = date.today().isoformat()
MOCK_KEY = "island2-mock-state"


def load():
    if mock:
        if MOCK_KEY not in st.session_state:
            st.session_state[MOCK_KEY] = copy.deepcopy(g.load_demo())
        return st.session_state[MOCK_KEY]
    saved = store.load_island_game(sid)
    return g.migrate(saved) if saved else None


def save(game):
    if not mock:  # 시안 상태는 저장하지 않는다
        store.save_island_game(sid, game)


def goto(screen):
    st.session_state["island2-goto"] = {"screen": screen, "id": f"{screen}-{st.session_state.get('island2-goto-n', 0) + 1}"}
    st.session_state["island2-goto-n"] = st.session_state.get("island2-goto-n", 0) + 1


def handle(event, game):
    """게임에서 온 행동 하나. 보여 줄 한 줄을 돌려준다."""
    kind = event.get("type")
    if kind == "start":
        seed = int(hashlib.sha256(f"{sid}-{real_date}".encode()).hexdigest()[:8], 16)
        game = g.new_state(event.get("name") or student["name"], seed, event.get("avatar", "blue"))
        save(game)
        if mock:
            st.session_state[MOCK_KEY] = game
        goto("island")
        return "섬에 온 걸 환영해! 행동력을 써서 일하고, '하루 마치기'로 다음 날로 넘어가요."
    if game is None:
        return None
    if kind == "act":
        _, message = g.act(game, event)
        save(game)
        return message
    if kind == "end_day":
        record = g.end_day(game, real_date)
        if record is None:
            return f"오늘은 게임 속 {g.S['maxGameDaysPerRealDay']}일을 다 보냈어요. 내일 다시 와요! (쉬어도 불이익은 없어요)"
        save(game)
        goto("result")
        return None
    if kind == "next_day":
        message = None
        if event.get("choice") in ("loan", "cash"):
            _, message = g.act(game, {"action": "build", "mode": event["choice"]})
            save(game)
        goto("island")
        return message
    return None


ui.app_bar("틴틴 자산섬", badge="자산 키우기 게임")
with st.container(key="island-page"):  # style.css: 이 화면에서는 앱 아래 탭 바를 숨기고 게임 메뉴를 쓴다
    game = load()
    if mock == "result" and "island2-goto-n" not in st.session_state:
        goto("result")
    if game is None:
        view = {"screen": "start", "name": student["name"], "avatar": "blue", "mock": False}
    else:
        view = iv.build_view(game, real_date, mock=bool(mock))
    view["toast"] = st.session_state.pop("island2-toast", None)
    view["goto"] = st.session_state.get("island2-goto")
    event = ui.island_game2(view, key=f"island2-{sid}-{'mock' if mock else 'real'}")

if event and event.get("nonce") != st.session_state.get("island2-nonce"):
    st.session_state["island2-nonce"] = event.get("nonce")
    message = handle(event, game)
    if message:
        st.session_state["island2-toast"] = message
    st.rerun()
