"""여러 화면이 함께 쓰는 Streamlit 조각.

모양: 색·글꼴은 .streamlit/config.toml, 나머지는 style.css. 이 파일은 둘을 읽어 화면에 넣기만 한다.
"""

import tomllib
from html import escape
from pathlib import Path

import streamlit as st

from engine import quotes, store, unlock
from config import DEMO_MODE_DEFAULT, DEMO_TIMEOUT_SECONDS, PRICE_MODE_DEFAULT, REAL_VIRTUAL_CASH
from llm import client as llm

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / ".streamlit" / "config.toml"
STYLE_PATH = ROOT / "style.css"

# style.css의 var(--이름) ↔ config.toml [theme] 항목
THEME_VARS = {
    "primary": "primaryColor", "bg": "backgroundColor", "surface": "secondaryBackgroundColor",
    "text": "textColor", "border": "borderColor", "gray": "grayColor", "blue": "blueColor",
    "green": "greenColor", "violet": "violetColor", "yellow": "yellowColor",
    "orange": "orangeColor", "red": "redColor",
}

# 모든 화면 맨 위에 작게 보이는 안내. 공식 서비스로 오해되지 않게 한다.
DISCLAIMER = "대학 수업 프로젝트 · 우리은행 적용 가정 제안 시안 · 실제 우리은행 서비스 아님"

HOME = "app.py"
MARKET = "pages/1_가상_주식시장.py"
ENVELOPE = "pages/2_용돈봉투.py"
LESSON = "pages/3_실수에서_배우기.py"
MISSION = "pages/4_이번_주_미션.py"
REWARDS = "pages/5_포인트와_캐릭터.py"
PARENT = "pages/6_부모_리포트.py"
ASK = "pages/7_개념_물어보기.py"
UNLOCK = "pages/8_실전_준비_단계.py"
DASHBOARD = "pages/9_효과_측정.py"

# 아래 탭 바: 우리은행 앱의 상품 / 자산·소비 / 홈 / 주식 / 혜택 자리와 맞춘다
NAV_ITEMS = [
    ("envelope", ENVELOPE, "용돈", ":material/account_balance_wallet:"),
    ("mission", MISSION, "미션", ":material/flag:"),
    ("home", HOME, "홈", ":material/home:"),
    ("market", MARKET, "투자연습", ":material/show_chart:"),
    ("rewards", REWARDS, "혜택", ":material/redeem:"),
]


def style_html():
    theme = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))["theme"]
    variables = ";".join(f"--{name}:{theme[key]}" for name, key in THEME_VARS.items())
    return f"<style>:root{{{variables}}}\n{STYLE_PATH.read_text(encoding='utf-8')}</style>"


def setup(page_title, icon, active=None):
    """모든 화면 맨 위에서 부른다: 페이지 설정, 스타일, 학생 선택, 아래 탭 바. 고른 학생을 돌려준다."""
    st.set_page_config(page_title=page_title, page_icon=icon, initial_sidebar_state="collapsed")
    st.html(style_html())
    st.markdown(f"<div class='disclaimer'>{escape(DISCLAIMER)}</div>", unsafe_allow_html=True)
    student = pick_student()
    st.sidebar.toggle("시연 모드", key="demo_mode", value=DEMO_MODE_DEFAULT,
                      help=f"AI가 {DEMO_TIMEOUT_SECONDS}초 안에 답하지 않거나 실패하면 "
                           "미리 저장한 응답(민지 시나리오)을 바로 보여 줘요.")
    st.sidebar.page_link(DASHBOARD, label="효과 측정 대시보드 (교사·운영자용)", icon=":material/monitoring:")
    if "demo_notice" in st.session_state:
        st.toast(st.session_state.pop("demo_notice"), icon=":material/bolt:")
    bottom_nav(active)
    return student


def pick_student():
    """사이드바(데모 설정)에서 학생을 고른다. 화면을 옮겨도 선택이 유지된다."""
    students = {s["student_id"]: s for s in store.load_students()}
    labels = {f"{s['name']} ({s['grade']})": sid for sid, s in students.items()}
    ids = list(labels.values())
    current = st.session_state.get("student_id", ids[0])
    st.sidebar.caption("데모 설정")
    chosen = labels[st.sidebar.selectbox("학생 선택", list(labels), index=ids.index(current))]
    st.session_state["student_id"] = chosen
    return students[chosen]


def bottom_nav(active):
    with st.container(key="bottom-nav", horizontal=True):
        for name, page, label, icon in NAV_ITEMS:
            with st.container(key="nav-active" if name == active else f"nav-{name}", width="content"):
                st.page_link(page, label=label, icon=icon)


def app_bar(title, badge=None, back=True):
    """화면 맨 위 큰 제목 (+ 작은 배지). 홈이 아닌 화면은 왼쪽 위에 뒤로가기(→ 홈)를 둔다."""
    with st.container(key="app-bar"):
        with st.container(key="title-row", horizontal=True, vertical_alignment="center", gap="small"):
            if back:
                with st.container(key="back", width="content"):
                    st.page_link(HOME, label="홈으로", icon=":material/arrow_back_ios:")
            st.title(title, anchor=False)
        if badge:
            st.markdown(f"<span class='badge'>{escape(badge)}</span>", unsafe_allow_html=True)


def columns(count, key, align="center"):
    """좁은 화면에서도 줄바꿈되거나 쌓이지 않는 나란한 칸 (st.columns는 좁으면 세로로 쌓인다)."""
    row = st.container(horizontal=True, vertical_alignment=align, key=f"cols-{key}")
    return [row.container() for _ in range(count)]


def section(title):
    st.markdown(f"<div class='section-title'>{escape(title)}</div>", unsafe_allow_html=True)


def card(key):
    """흰색 둥근 카드. with ui_common.card("이름"): 으로 쓴다."""
    return st.container(key=f"card-{key}")


def service_row(page, icon, title, subtitle, key):
    """아이콘 + 제목 + 설명 한 줄. 줄 전체를 누르면 page로 간다."""
    with st.container(key=f"row-{key}"):
        st.markdown(
            f"<div class='row'><div class='row-icon'>{icon}</div><div>"
            f"<div class='row-title'>{escape(title)}</div>"
            f"<div class='row-sub'>{escape(subtitle)}</div></div></div>",
            unsafe_allow_html=True)
        st.page_link(page, label=title)


def hero_card(page, tone, eyebrow, title, art, key):
    """가로로 넘기는 큰 소개 카드. hero_strip() 안에서 쓴다."""
    with st.container(key=f"hero-{key}"):
        st.markdown(
            f"<div class='hero tone-{tone}'><div><div class='hero-eyebrow'>{escape(eyebrow)}</div>"
            f"<div class='hero-title'>{escape(title)}</div></div>"
            f"<div class='hero-art'>{art}</div></div>", unsafe_allow_html=True)
        st.page_link(page, label=title)


def hero_strip():
    return st.container(key="hero-strip", horizontal=True)


ANSWER_MARKS = "①②③④⑤"


def quiz(concept, key):
    """개념 파일의 확인 문제. 정답 확인만 하고 점수는 매기지 않는다."""
    q = concept["quiz"]
    choice = st.radio(q["질문"], range(len(q["보기"])), index=None, key=f"quiz-{key}",
                      format_func=lambda i: f"{ANSWER_MARKS[i]} {q['보기'][i]}")
    if choice is not None:
        if ANSWER_MARKS[choice] == q["정답"]:
            st.success("맞았어요!")
        else:
            st.warning("다시 한 번 생각해 볼까요?")


def concept_card(concept, key, intro=None):
    """개념 파일(content/concepts)의 문장을 그대로 보여 준다. AI를 쓰지 않는다.
    '이런 행동이었어요'는 학생 행동처럼 쓰여 있어 빼고, 정의·확인 질문·확인 문제만 보여 준다."""
    sections = concept["sections"]
    if intro:
        muted(intro)
    st.markdown(f"**{concept['name_ko']}** · {sections['한 줄 정의']}")
    st.markdown(sections["다음엔 이렇게 확인해 보세요"])
    with st.expander("확인 문제 풀어 보기"):
        quiz(concept, key)


def chips(keywords, kind):
    """kind: good / practice"""
    st.markdown("".join(f"<span class='chip chip-{kind}'>{escape(k)}</span>" for k in keywords),
                unsafe_allow_html=True)


def muted(text):
    st.markdown(f"<div class='muted'>{escape(text)}</div>", unsafe_allow_html=True)


def won(amount):
    return f"{amount:,}원"


PRICE_MODES = {"scenario": "시나리오", "real": "실제 시세"}


def price_mode():
    """투자연습 시세 종류. 화면을 옮겨도 유지되도록 위젯과 별도 키에 둔다."""
    return st.session_state.get("price_mode", PRICE_MODE_DEFAULT)


def real_mode_allowed(student_id):
    """9번: 실제 시세는 2단계를 연 학생만. 시연 모드에서는 잠금 없이 연다."""
    return demo_mode() or unlock.stage(store.load_unlocks(), student_id) >= 2


def price_mode_switch(student_id):
    labels = {label: mode for mode, label in PRICE_MODES.items()}
    if not real_mode_allowed(student_id):
        st.radio("시세 종류", list(labels), index=0, horizontal=True, disabled=True, key="price_mode_locked")
        with card("unlock-hint"):
            service_row(UNLOCK, "🔒", "실제 시세는 2단계에서 열려요", "실전 준비 단계에서 할 것 보기", key="unlock-hint")
        return

    def changed():
        st.session_state["price_mode"] = labels[st.session_state["price_mode_widget"]]

    st.radio("시세 종류", list(labels), index=list(PRICE_MODES).index(price_mode()),
             horizontal=True, key="price_mode_widget", on_change=changed)


def market_context(student):
    """투자연습·실수에서 배우기·홈이 함께 쓰는 시세와 거래.

    실제 시세 모드에서 시세를 못 받고 저장값도 없으면 시나리오 데이터로 바꾼다 (quote에 이유가 남는다).
    "student": 이 모드의 가상 투자금을 넣은 학생 정보 (실제 시세는 REAL_VIRTUAL_CASH)."""
    quote = None
    if price_mode() == "real" and real_mode_allowed(student["student_id"]):
        quote = quotes.load_quotes()
        if quote["prices"] is not None:
            return {"mode": "real", "names": quote["names"], "prices": quote["prices"],
                    "trades": store.load_trades(store.REAL_TRADES_PATH),
                    "trades_path": store.REAL_TRADES_PATH, "prefix": "R", "quote": quote,
                    "student": {**student, "virtual_cash": REAL_VIRTUAL_CASH}}
    return {"mode": "scenario", "names": store.load_ticker_names(), "prices": store.load_prices(),
            "trades": store.load_trades(store.TRADES_PATH), "trades_path": store.TRADES_PATH,
            "prefix": "T", "quote": quote, "student": student}


def demo_mode():
    return st.session_state.get("demo_mode", DEMO_MODE_DEFAULT)


def ask_ai(prompt_name, payload, student_id, demo_key=None, default=None, check=None):
    """화면에서 AI를 부르는 유일한 입구.

    시연 모드가 꺼져 있으면: 실패 시 안내를 띄우고 멈춘다 (run_llm).
    시연 모드가 켜져 있으면: 짧게 기다리고, 실패하면 저장 응답 → 기본 문구 순으로 바로 보여 준다.
    저장 응답도 AI 응답과 같은 규칙(존댓말·금지 표현·check)을 통과해야 쓴다."""
    if not demo_mode():
        return run_llm(lambda: llm.ask(prompt_name, payload, default=default, check=check))
    try:
        return llm.ask(prompt_name, payload, default=default, check=check,
                       timeout=DEMO_TIMEOUT_SECONDS, raise_on_fail=True)
    except llm.LLMError:
        saved = store.demo_response(student_id, prompt_name, demo_key)
        if saved is not None:
            try:
                result = llm.validate(prompt_name, saved, check)
                st.session_state["demo_notice"] = "시연 모드: 저장된 AI 응답을 보여 줘요"
                return result
            except ValueError:
                pass
        st.session_state["demo_notice"] = "시연 모드: AI 대신 기본 문구를 보여 줘요"
        return dict(default if default is not None else llm.SPECS[prompt_name]["default"])


def run_llm(step):
    """LLM 단계를 실행한다. 키 없음·한도 초과·서버 과부하면 화면에 안내하고 멈춘다."""
    try:
        return step()
    except llm.MissingKeyError:
        st.error("AI 키가 없어요. `.env.example`을 `.env`로 복사하고 OPENAI_API_KEY에 키를 넣은 뒤 다시 실행해 주세요.")
        st.stop()
    except llm.QuotaExceededError:
        st.warning("AI 사용 한도 초과, 잠시 후 다시 시도")
        st.stop()
    except llm.ServiceUnavailableError:
        st.warning("AI가 지금 바빠요. 잠시 후 다시 시도해 주세요.")
        st.stop()
