"""여러 화면이 함께 쓰는 Streamlit 조각.

모양: 색·글꼴은 .streamlit/config.toml, 나머지는 style.css. 이 파일은 둘을 읽어 화면에 넣기만 한다.
"""

import inspect
import tomllib
from html import escape
from pathlib import Path
from urllib.parse import quote

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
MYDATA = "pages/10_마이데이터_연결.py"
GAME = "pages/11_자산_키우기_게임.py"
NEWS = "pages/12_이번_주_금융_뉴스.py"

# 아래 탭 바: 우리은행 앱의 상품 / 자산·소비 / 홈 / 주식 / 혜택 자리와 맞춘다
# (이름, 화면, 글자, 선 아이콘(ICON_PATHS), 색). 색은 홈 타일과 맞춘다 (2026-11-13 리디자인)
NAV_ITEMS = [
    ("envelope", ENVELOPE, "용돈", "wallet", "orange"),
    ("mission", MISSION, "미션", "flag", "blue"),
    ("home", HOME, "홈", "home", "yellow"),
    ("market", MARKET, "투자연습", "chart", "green"),
    ("rewards", REWARDS, "혜택", "gift", "violet"),
]


def theme_colors():
    """config.toml의 색을 {이름: 값}으로 (게임처럼 style.css 밖에서 그리는 화면에 넘겨줄 때)."""
    theme = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))["theme"]
    return {name: theme[key] for name, key in THEME_VARS.items()}


def font_family(value):
    """config.toml 글꼴 값("이름:주소, 대체 글꼴")에서 CSS font-family로 쓸 이름만 남긴다."""
    names = []
    for part in value.split(","):
        name = part.strip().split(":http")[0].strip()
        if name:
            names.append(f'"{name}"' if " " in name else name)
    return ", ".join(names)


# ---------- 귀여운 버전 조각: 선 아이콘 · 마스코트 틴이 (2026-11-13 리디자인) ----------
# 아이콘은 같은 굵기의 선 그림(24×24). 색은 style.css의 tone-soft-<색> 클래스가 정한다.
ICON_PATHS = {
    "chart": "M3 17l6-6 4 4 8-8M15 7h6v6",
    "basket": "M4 10h16l-1.5 10h-13zM8 10l4-6 4 6",
    "news": "M5 4h11v16H5zM16 8h3v10a2 2 0 0 1-2 2M8 8h5M8 12h5M8 16h3",
    "env": "M3 6h18v13H3zM3 7l9 6 9-6",
    "search": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
    "flag": "M5 21V4M5 4h11l-2 4 2 4H5",
    "chat": "M4 5h16v11H9l-5 4z",
    "lock": "M6 11h12v9H6zM9 11V8a3 3 0 0 1 6 0v3",
    "unlock": "M6 11h12v9H6zM9 11V8a3 3 0 0 1 5.8-1",
    "gift": "M4 11h16v9H4zM3 7h18v4H3zM12 7v13M12 7c-2-4-6-3-4 0M12 7c2-4 6-3 4 0",
    "ticket": "M4 7h16v3a2 2 0 0 0 0 4v3H4v-3a2 2 0 0 0 0-4zM10 7v10",
    "family": "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16 11a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM3 20c0-3 2-5 5-5s5 2 5 5M14 20c0-2 1.5-4 4-4s3 2 3 4",
    "link": "M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1",
    "ladder": "M7 3v18M17 3v18M7 7h10M7 12h10M7 17h10",
    "bag": "M5 8h14l-1 12H6zM9 8V6a3 3 0 0 1 6 0v2",
    "piggy": "M5 11a7 6 0 0 1 13-1h2v4h-2a7 6 0 0 1-3 3v3h-3v-2h-2v2H7v-3a6 6 0 0 1-2-6zM15 10h.01",
    "sprout": "M12 20v-8M12 12c0-4-3-6-7-6 0 4 3 6 7 6zM12 12c0-3 2-5 6-5 0 3-2 5-6 5",
    "cart": "M3 4h2l2 11h11l2-8H6M9 20h.01M17 20h.01",
    "alert": "M12 3l9 16H3zM12 10v4M12 17h.01",
    "bank": "M3 10l9-6 9 6M5 10v8M9 10v8M15 10v8M19 10v8M3 20h18",
    "card": "M3 6h18v12H3zM3 10h18M7 15h4",
    "phone": "M7 3h10v18H7zM11 18h2",
    "home": "M4 11l8-7 8 7v9H4z",
    "briefcase": "M4 8h16v11H4zM9 8V5h6v3",
    "coin": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM10 8h3a2.5 2.5 0 0 1 0 5h-3zM10 8v9",
    "book": "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM8 7h7",
    "leaf": "M5 19c0-8 6-14 14-14 0 8-6 14-14 14zM5 19l7-7",
    "shield": "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
    "store": "M4 10h16v10H4zM3 6h18l-1 4H4zM10 20v-5h4v5",
    "film": "M4 6h16v12H4zM4 10h16M8 6v4M12 6v4M16 6v4",
    "wallet": "M4 7h16v12H4zM16 13h2M4 7l2-3h12",
}
# 화면 코드가 넘기는 이모지 → (선 아이콘, 기본 색). 표에 없는 이모지는 그대로 보여 준다.
EMOJI_ICONS = {
    "✉️": ("env", "orange"), "🎟️": ("ticket", "violet"), "🎯": ("flag", "blue"), "🐣": ("gift", "yellow"),
    "👪": ("family", "gray"), "💬": ("chat", "yellow"), "📈": ("chart", "blue"), "📰": ("news", "violet"),
    "🔍": ("search", "violet"), "🔒": ("lock", "gray"), "🔓": ("unlock", "gray"), "🔗": ("link", "blue"),
    "🧺": ("basket", "green"), "🪜": ("ladder", "green"), "🛍️": ("bag", "orange"), "🐷": ("piggy", "green"),
    "🌱": ("sprout", "blue"), "🛒": ("cart", "orange"), "🚨": ("alert", "red"), "🏦": ("bank", "blue"),
    "💳": ("card", "violet"), "📱": ("phone", "violet"), "🏠": ("home", "yellow"), "💼": ("briefcase", "blue"),
    "💰": ("coin", "green"), "📚": ("book", "blue"), "🥬": ("leaf", "green"), "🛡️": ("shield", "blue"),
    "🏪": ("store", "blue"), "🎬": ("film", "green"),
}


def icon_html(icon, tone=None, size="md"):
    """선 아이콘을 파스텔 네모 안에 넣은 HTML. icon은 ICON_PATHS 이름 또는 이모지."""
    name, default_tone = EMOJI_ICONS.get(icon, (icon, "gray"))
    tone = tone or default_tone
    path = ICON_PATHS.get(name)
    inner = (f"<svg viewBox='0 0 24 24' aria-hidden='true'><path d='{path}'/></svg>" if path
             else escape(icon))
    return f"<span class='ic ic-{size} tone-soft-{tone}'>{inner}</span>"


def mascot_html(stage="아기", size="md", label="틴이"):
    """마스코트 '틴이' (새싹을 키우는 병아리). stage: 알 / 아기 / 청소년 / 어른. 색은 style.css의 tini-* 클래스."""
    aria = f"role='img' aria-label='{escape(label)}'"
    if stage == "알":
        return (f"<svg class='tini tini-{size}' viewBox='0 0 52 64' {aria}>"
                "<ellipse class='tini-egg' cx='26' cy='36' rx='22' ry='26'/>"
                "<path class='tini-crack' d='M8 34l6-4 6 4 6-4 6 4 6-4 6 4'/></svg>")
    leaves = "<path class='tini-leaf' d='M32 16c0-7 5-12 12-12-1 7-5 11-12 12z'/>"
    if stage in ("청소년", "어른"):
        leaves += "<path class='tini-leaf2' d='M32 16c0-6-4-10-10-10 0 6 4 10 10 10z'/>"
    if stage == "어른":
        leaves += "<circle class='tini-flower' cx='44' cy='5' r='3.5'/>"
    return (f"<svg class='tini tini-{size}' viewBox='0 0 64 64' {aria}>{leaves}"
            "<ellipse class='tini-body' cx='32' cy='40' rx='25' ry='22'/>"
            "<circle class='tini-eye' cx='24' cy='38' r='3.2'/><circle class='tini-eye' cx='40' cy='38' r='3.2'/>"
            "<ellipse class='tini-cheek' cx='18' cy='46' rx='4.5' ry='2.8'/>"
            "<ellipse class='tini-cheek' cx='46' cy='46' rx='4.5' ry='2.8'/>"
            "<path class='tini-mouth' d='M28 46q4 4 8 0'/></svg>")


def mascot_say(text, key, page=None, cta=None):
    """틴이 + 말풍선 카드. page·cta를 주면 아래에 큰 알약 버튼(화면 이동)을 단다."""
    with st.container(key=f"say-{key}"):
        st.markdown(f"<div class='say'>{mascot_html(size='lg')}"
                    f"<div class='say-bubble'>{escape(text)}</div></div>", unsafe_allow_html=True)
        if page and cta:
            st.page_link(page, label=cta)


def tile_grid():
    """홈의 큰 파스텔 타일 2×2. with ui_common.tile_grid(): 안에서 tile()을 부른다."""
    return st.container(key="tiles", horizontal=True)


def tile(page, icon, title, subtitle, tone, key):
    """큰 파스텔 타일 (아이콘 + 제목 + 한 줄). 타일 전체를 누르면 page로 간다."""
    with st.container(key=f"tile-{key}"):
        st.markdown(
            f"<div class='tile tile-{tone}'>{icon_html(icon, tone, 'lg')}"
            f"<div><div class='tile-title'>{escape(title)}</div>"
            f"<div class='tile-sub'>{escape(subtitle)}</div></div></div>", unsafe_allow_html=True)
        st.page_link(page, label=title)


_catch_game = None


def catch_game(words, round_id, duration, start_coins, good_coins, bad_coins):
    """21번 자산 키우기 게임 (components/catch_game). 끝나면 {"round", "caught", "missed"}, 그 전에는 None."""
    global _catch_game
    import streamlit.components.v1 as components

    if _catch_game is None:
        _catch_game = components.declare_component("catch_game", path=str(ROOT / "components" / "catch_game"))
    theme = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))["theme"]
    return _catch_game(words=words, round=round_id, duration=duration, start_coins=start_coins,
                       good_coins=good_coins, bad_coins=bad_coins, colors=theme_colors(),
                       font=font_family(theme["headingFont"]), key=f"catch-game-{round_id}", default=None)


_island_game = None


def island_game(view, key):
    """자산섬 게임 화면 (components/island). 게임 안 동작(태그·찜·퀘스트·토글·화면 이동)을 dict로 돌려준다."""
    global _island_game
    import streamlit.components.v1 as components

    if _island_game is None:
        _island_game = components.declare_component("island_game", path=str(ROOT / "components" / "island"))
    return _island_game(view=view, key=key, default=None)


_island_game2 = None


def island_game2(view, key):
    """자산섬 v2 게임 화면 (components/island2). 게임 안 행동을 dict로 돌려준다."""
    global _island_game2
    import streamlit.components.v1 as components

    if _island_game2 is None:
        _island_game2 = components.declare_component("island_game2", path=str(ROOT / "components" / "island2"))
    return _island_game2(view=view, key=key, default=None)


def style_html():
    theme = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))["theme"]
    variables = ";".join(f"--{name}:{theme[key]}" for name, key in THEME_VARS.items())
    weight = theme["headingFontWeights"][0]
    variables += (f";--heading-font:{font_family(theme['headingFont'])};--heading-weight:{weight}"
                  f";--heading-spacing:{'-0.02em' if weight >= 600 else 'normal'}")
    return f"<style>:root{{{variables}}}\n{STYLE_PATH.read_text(encoding='utf-8')}\n{nav_icon_css()}</style>"


def setup(page_title, icon, active=None):
    """모든 화면 맨 위에서 부른다: 페이지 설정, 스타일, 학생 선택, 아래 탭 바. 고른 학생을 돌려준다."""
    st.set_page_config(page_title=page_title, page_icon=icon, initial_sidebar_state="collapsed")
    st.html(style_html())
    student = pick_student()
    st.sidebar.toggle("시연 모드", key="demo_mode", value=DEMO_MODE_DEFAULT,
                      help=f"AI가 {DEMO_TIMEOUT_SECONDS}초 안에 답하지 않거나 실패하면 "
                           "미리 저장한 응답(민지 시나리오)을 바로 보여 줘요.")
    st.sidebar.page_link(DASHBOARD, label="효과 측정 대시보드 (교사·운영자용)", icon=":material/monitoring:")
    if "demo_notice" in st.session_state:
        st.toast(st.session_state.pop("demo_notice"), icon=":material/bolt:")
    track_page(_caller_page())
    bottom_nav(active)
    return student


def _caller_page():
    """setup()을 부른 화면 파일 경로 (app.py 또는 pages/…). 못 찾으면 None."""
    for frame in inspect.stack()[2:]:
        path = Path(frame.filename).resolve()
        if path == ROOT / HOME or path.parent == ROOT / "pages":
            return path.relative_to(ROOT).as_posix()
    return None


def track_page(current):
    """지나온 화면을 기억해서 뒤로가기가 바로 전 화면으로 가게 한다 (기록이 없으면 홈).
    - 같은 화면에서 다시 그려지면 그대로
    - 바로 전 화면으로 돌아오면(뒤로가기) 맨 위를 뺀다
    - 홈에 오면 처음부터 다시 쌓는다"""
    if current is None:
        return
    stack = st.session_state.setdefault("page_stack", [])
    if current == HOME:
        stack[:] = [HOME]
    elif stack and stack[-1] == current:
        pass
    elif len(stack) >= 2 and stack[-2] == current:
        stack.pop()
    else:
        stack.append(current)
        del stack[:-10]
    st.session_state["back_page"] = stack[-2] if len(stack) >= 2 else HOME


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


def nav_icon_css():
    """아래 탭 바의 선 아이콘(마스크 그림)과 탭별 색. 모양은 style.css의 .st-key-bottom-nav 규칙."""
    rules = []
    for name, _, _, icon, tone in NAV_ITEMS:
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
               f"stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='{ICON_PATHS[icon]}'/></svg>")
        uri = "data:image/svg+xml," + quote(svg)
        ink = 45 if tone == "yellow" else 72  # 흰 바탕에서 글자 대비 4.5:1 이상이 되게 진한 남색과 섞는 비율
        rules.append(f'.st-key-nav-{name}, .st-key-nav-on-{name} {{ --nav-icon: url("{uri}"); --tone: var(--{tone}); '
                     f'--tone-ink: color-mix(in srgb, var(--{tone}) {ink}%, var(--text)); }}')
    return "\n".join(rules)


def bottom_nav(active):
    """아래 탭 바. 선택된 탭은 st-key-nav-on-<이름> (파스텔 알약 + 진한 색)."""
    with st.container(key="bottom-nav", horizontal=True):
        for name, page, label, _, _ in NAV_ITEMS:
            with st.container(key=f"nav-on-{name}" if name == active else f"nav-{name}", width="content"):
                st.page_link(page, label=label)


def app_bar(title, badge=None, back=True, on_back=None):
    """화면 맨 위 큰 제목 (+ 작은 배지). 홈이 아닌 화면은 왼쪽 위에 뒤로가기를 둔다.
    뒤로가기는 바로 전 화면으로 간다 (track_page). on_back을 주면 화면 이동 대신 그 함수를 부른다
    (같은 페이지 안의 상세 화면 → 목록처럼)."""
    with st.container(key="app-bar"):
        with st.container(key="title-row", horizontal=True, vertical_alignment="center", gap="small"):
            if back:
                with st.container(key="back", width="content"):
                    if on_back:
                        st.button("뒤로", key="back-button", icon=":material/arrow_back_ios:", on_click=on_back)
                    else:
                        st.page_link(st.session_state.get("back_page", HOME), label="뒤로",
                                     icon=":material/arrow_back_ios:")
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
            f"<div class='row'>{icon_html(icon)}<div>"
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


def _marked(text, word):
    """text 안 첫 word를 형광펜(<mark>)으로. word가 없으면 그대로. 둘 다 escape한다."""
    safe = escape(text or "")
    w = escape(word or "")
    return safe.replace(w, f"<mark>{w}</mark>", 1) if w and w in safe else safe


def news_post(card, index, total, art, tone):
    """22번 카드뉴스를 인스타그램 게시물처럼: 프로필 머리 → 옆으로 넘기는 정사각형 4장 → 캡션.
    tone: style.css의 ig-<색> (orange, red, green, blue, violet, yellow)."""
    news = card["news"]
    dots = lambda on: "<div class='ig-dots'>" + "".join(
        f"<span class='ig-dot{' on' if k == on else ''}'></span>" for k in range(4)) + "</div>"
    number = f"<div class='ig-number'>{escape(card['number'])}</div>" if card.get("number") else ""
    fact = card.get("fact") or card.get("summary", "")
    cover = (f"<div class='ig-slide ig-cover'><div class='ig-deco ig-deco-a'></div><div class='ig-deco ig-deco-b'></div>"
             f"<div class='ig-tag'>#{escape(card.get('tag') or '금융')}</div><div class='ig-art'>{art}</div>"
             f"<div class='ig-title'>{_marked(card['headline'], card.get('highlight'))}</div>"
             f"<div class='ig-foot'><span>teen_fin_coach</span><span>넘겨 보기 →</span></div>{dots(0)}</div>")
    what = (f"<div class='ig-slide ig-plain'><div class='ig-kicker'>무슨 일?</div>{number}"
            f"<div class='ig-line'>{escape(fact)}</div>{dots(1)}</div>")
    learn = (f"<div class='ig-slide ig-tint'><div class='ig-kicker'>📘 이 뉴스로 배우는 금융</div>"
             f"<div class='ig-big'>{_marked(card['learn'], card.get('learn_highlight'))}</div>{dots(2)}</div>")
    me = (f"<div class='ig-slide ig-plain'><div class='ig-kicker'>나에게는?</div>"
          f"<div class='ig-check'><span class='ig-tick'>✓</span><span>{escape(card['why'])}</span></div>"
          f"<div class='ig-source'>출처: {escape(news['press'])} · 정책브리핑</div>{dots(3)}</div>")
    link = escape(news["link"], quote=True)
    st.markdown(
        f"<div class='ig-post ig-{tone}'>"
        f"<div class='ig-head'><div class='ig-avatar'>📰</div><div><div class='ig-name'>teen_fin_coach</div>"
        f"<div class='ig-sub'>{escape(news['press'])} · {escape(news['date'])} · {index}/{total}</div></div></div>"
        f"<div class='ig-carousel'>{cover}{what}{learn}{me}</div>"
        f"<div class='ig-caption'><b>teen_fin_coach</b> {escape(card['summary'])} "
        f"<span class='ig-hash'>#{escape(card.get('tag') or '금융')} #청소년금융</span><br>"
        f"<a href='{link}' target='_blank'>원문 보기: {escape(news['title'])}</a></div></div>",
        unsafe_allow_html=True)


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


def concept_card(concept, key, intro=None, with_quiz=True):
    """개념 파일(content/concepts)의 문장을 그대로 보여 준다. AI를 쓰지 않는다.
    '이런 행동이었어요'는 학생 행동처럼 쓰여 있어 빼고, 정의·확인 질문·확인 문제만 보여 준다."""
    sections = concept["sections"]
    if intro:
        muted(intro)
    st.markdown(f"**{concept['name_ko']}** · {sections['한 줄 정의']}")
    st.markdown(sections["다음엔 이렇게 확인해 보세요"])
    if with_quiz:
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
