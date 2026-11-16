"""마스코트 '그로비(Growby)' — 모으면 자라는 새싹 저금통 (2026-11-16, 시뮬레이션 · mascot/teengrow_mascot/MASCOT_SPEC.md).

- 화면에서는 파일 이름을 쓰지 않고 상황 키로 부른다 (img_html("quiz_correct", ...)). 표정을 바꿀 땐 이 파일만 고친다.
- 그림: assets/growby/*.svg 11종 (표정 6 + 혜택 탭 저금통 단계 5). data URI로 넣는다.
- 말풍선 문구는 check_line을 통과해야 한다 (종목 추천·매매 권유·수익 칭찬·놀림·겁주기 금지, 해요체, 두 문장 · 45자 이내).
  걸리면 safe_line이 기본 문구로 바꾼다. AI가 만든 문구(카드뉴스 3번 한마디)도 같은 검사를 거친다.
- 크기 규칙: 말풍선 옆 40~72px, 결과·축하 96~120px, 빈 화면 160px. 모양은 style.css의 .growby-* 클래스.
- 한 화면에 그로비는 한 번만 (화면 코드에서 지킨다). 안전요원 표정은 실전 화면에서만.
- config.GROWBY_MASCOT = False면 예전 '틴이'(ui_common.mascot_html)가 나온다.
"""

import base64
import html
import re
from functools import lru_cache
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "growby"

# 표정 6가지: 키 → (파일, alt)
EXPRESSIONS = {
    "hello": ("growby_hello.svg", "인사하는 그로비"),
    "cheer": ("growby_cheer.svg", "신난 그로비"),
    "think": ("growby_think.svg", "생각하는 그로비"),
    "safety": ("growby_safety.svg", "실전 방패를 든 안전요원 그로비"),
    "sleep": ("growby_sleep.svg", "잠든 그로비"),
    "default": ("growby_default.svg", "그로비"),
}

# 혜택 탭 돼지 저금통 단계 (rewards.level_of(balance)["no"])
LEVELS = {
    1: ("growby_lv1_pink.svg", "분홍 그로비 · 씨앗"),
    2: ("growby_lv2_sky.svg", "하늘 그로비 · 떡잎"),
    3: ("growby_lv3_mint.svg", "민트 그로비 · 두 잎"),
    4: ("growby_lv4_purple.svg", "보라 그로비 · 꽃봉오리"),
    5: ("growby_lv5_gold.svg", "황금 그로비 · 황금 잎"),
}

# 상황 → 표정. 새 상황은 한 줄 추가. 없는 키는 default.
SITUATIONS = {
    "home_greeting": "hello",
    "news_progress": "default",
    "card_me": "default",  # 카드뉴스 3번 '나랑 무슨 상관?' 말풍선
    "invest_tip": "default",
    "weekly_feedback": "default",
    "quiz_correct": "cheer",
    "quiz_all_done": "cheer",
    "mission_done": "cheer",
    "savings_goal": "cheer",
    "level_up": "cheer",
    "quiz_wrong": "think",
    "retry": "think",
    "real_switch": "safety",
    "real_checklist": "safety",
    "real_blocked": "safety",
    "empty": "sleep",
    "update_failed": "sleep",
    "idle_return": "sleep",
}

SIZE = {"bubble": (40, 72), "result": (96, 120), "empty": (160, 160)}

MAX_SENTENCES = 2
MAX_CHARS = 45
FALLBACK = "같이 천천히 알아봐요."
BANNED = [
    (re.compile(r"(지금|당장|얼른|빨리)\s*(사|매수|팔|매도)"), "매매를 재촉함"),
    (re.compile(r"(사세요|파세요|사요!|살 때예요|팔 때예요|매수하세요|매도하세요)"), "매매를 권유함"),
    (re.compile(r"추천\s*(종목|주식)|(종목|주식)\s*추천"), "종목 추천"),
    (re.compile(r"(수익률|\d+\s*%\s*(벌|올랐|수익))"), "수익으로 칭찬"),
    (re.compile(r"(벌었네|돈 벌었|대박)"), "수익으로 칭찬"),
    (re.compile(r"(망했|바보|그것도 몰라|한심)"), "놀리거나 깎아내림"),
    (re.compile(r"(큰일 나|다 잃|파산)"), "겁주기"),
]


def expression_for(situation):
    return SITUATIONS.get(situation or "", "default")


def file_for(situation=None, level=None):
    """(파일 이름, alt). level을 주면 혜택 탭 저금통 그림."""
    if level is not None:
        return LEVELS[max(1, min(5, int(level)))]
    return EXPRESSIONS[expression_for(situation)]


def clamp_size(role, px):
    lo, hi = SIZE[role]
    return max(lo, min(hi, px))


def check_line(text):
    """말풍선 문구 검사. 문제 없으면 []."""
    text = (text or "").strip()
    problems = [why for pat, why in BANNED if pat.search(text)]
    if len(re.findall(r"[.!?](\s|$)", text)) > MAX_SENTENCES or len(text) > MAX_CHARS:
        problems.append("너무 김")
    if not re.search(r"(요|죠|까요)[.!?~]?\s*(\+?\d+P)?$", text):
        problems.append("해요체가 아님")
    return problems


def safe_line(text, fallback=FALLBACK):
    """검사에 걸리면 기본 문구로 (화면이 깨지지 않게)."""
    return text if not check_line(text) else fallback


def first_safe(*candidates, fallback=FALLBACK):
    """앞에서부터 검사를 통과하는 첫 문구 (긴 문구 → 짧은 문구 순으로 넘긴다)."""
    return next((c for c in candidates if c and not check_line(c)), fallback)


@lru_cache(maxsize=32)
def data_uri(filename):
    raw = (ASSET_DIR / filename).read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


def img_html(situation=None, role="bubble", px=56, level=None, decorative=False):
    """<img> 문자열. 옆에 같은 뜻의 글이 있으면 decorative=True (alt 비움). 크기는 width/height 속성 + style.css."""
    name, alt = file_for(situation, level)
    size = clamp_size(role, px)
    alt_attr = "" if decorative else html.escape(alt)
    expr = "level" if level is not None else expression_for(situation)
    return (f'<img class="growby growby-{role} growby-{expr}" src="{data_uri(name)}" alt="{alt_attr}" '
            f'width="{size}" height="{size}">')


def bubble_html(situation, text, px=56):
    """그로비 + 말풍선 (기존 '틴이' 말풍선과 같은 .say / .say-bubble 모양)."""
    line = html.escape(safe_line(text))
    return f"<div class='say'>{img_html(situation, 'bubble', px, decorative=True)}<div class='say-bubble'>{line}</div></div>"


def render(situation, text=None, role="bubble", px=56):
    """Streamlit 출력. 한 화면에 한 번만."""
    import streamlit as st
    st.markdown(bubble_html(situation, text, px) if text else img_html(situation, role, px), unsafe_allow_html=True)
