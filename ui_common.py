"""여러 화면이 함께 쓰는 Streamlit 조각.

모양: 색·글꼴은 .streamlit/config.toml, 나머지는 style.css. 이 파일은 둘을 읽어 화면에 넣기만 한다.
"""

import tomllib
from html import escape
from pathlib import Path

import streamlit as st

from engine import store
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

HOME = "app.py"
MARKET = "pages/1_가상_주식시장.py"
ENVELOPE = "pages/2_용돈봉투.py"
LESSON = "pages/3_실수에서_배우기.py"
MISSION = "pages/4_이번_주_미션.py"
REWARDS = "pages/5_포인트와_캐릭터.py"
PARENT = "pages/6_부모_리포트.py"

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
    student = pick_student()
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


def chips(keywords, kind):
    """kind: good / practice"""
    st.markdown("".join(f"<span class='chip chip-{kind}'>{escape(k)}</span>" for k in keywords),
                unsafe_allow_html=True)


def muted(text):
    st.markdown(f"<div class='muted'>{escape(text)}</div>", unsafe_allow_html=True)


def won(amount):
    return f"{amount:,}원"


def run_llm(step):
    """LLM 단계를 실행한다. 키 없음·한도 초과·서버 과부하면 화면에 안내하고 멈춘다."""
    try:
        return step()
    except llm.MissingKeyError:
        st.error("AI 키가 없어요. `.env.example`을 `.env`로 복사하고 GEMINI_API_KEY에 키를 넣은 뒤 다시 실행해 주세요.")
        st.stop()
    except llm.QuotaExceededError:
        st.warning("AI 무료 한도 초과, 잠시 후 다시 시도")
        st.stop()
    except llm.ServiceUnavailableError:
        st.warning("AI가 지금 바빠요. 잠시 후 다시 시도해 주세요.")
        st.stop()
