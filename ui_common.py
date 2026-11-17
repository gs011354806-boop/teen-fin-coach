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
from splash import render_splash

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
PARENT_INVEST = "pages/13_보호자_투자_동의.py"  # 투자 탭 ④ 보호자 동의·안전장치 (앱 안 보호자 모드)

# 아래 탭 바: 우리은행 앱의 상품 / 자산·소비 / 홈 / 주식 / 혜택 자리와 맞춘다
# (이름, 화면, 글자, 선 아이콘(ICON_PATHS), 색). 색은 홈 타일과 맞춘다 (2026-11-13 리디자인)
NAV_ITEMS = [
    ("envelope", ENVELOPE, "용돈", "wallet", "orange"),
    ("mission", MISSION, "미션", "flag", "blue"),
    ("home", HOME, "홈", "home", "yellow"),
    ("market", MARKET, "투자", "chart", "green"),
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


GROWBY_PX = {"sm": 44, "md": 56, "lg": 72, "xl": 120}


def mascot_html(stage="아기", size="md", label="틴이", situation="default", decorative=True):
    """마스코트. config.GROWBY_MASCOT이면 그로비(상황 키로 표정), 아니면 예전 '틴이' (새싹을 키우는 병아리).
    틴이 stage: 알 / 아기 / 청소년 / 어른. 색은 style.css의 tini-* · growby-* 클래스."""
    import config
    if config.GROWBY_MASCOT:
        import growby
        role = "result" if size == "xl" else "bubble"
        return growby.img_html(situation, role, GROWBY_PX.get(size, 56), decorative=decorative)
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


def mascot_say(text, key, page=None, cta=None, situation="home_greeting"):
    """마스코트 + 말풍선 카드. page·cta를 주면 아래에 큰 알약 버튼(화면 이동)을 단다.
    그로비일 때 문구는 growby.check_line을 통과해야 한다 (걸리면 기본 문구)."""
    import config
    if config.GROWBY_MASCOT:
        import growby
        text = growby.safe_line(text)
    with st.container(key=f"say-{key}"):
        st.markdown(f"<div class='say'>{mascot_html(size='lg', situation=situation)}"
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
    render_splash()  # 앱 시작 로고 화면 (세션당 1회, splash.py)
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


def app_bar(title, badge=None, back=True, on_back=None, pill=None):
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
        if pill:  # 투자 탭 모드 배지 (mode_pill이 만든 HTML)
            st.markdown(pill, unsafe_allow_html=True)


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
    """투자 탭 연습 모드 시세 종류. 화면을 옮겨도 유지되도록 위젯과 별도 키에 둔다."""
    return st.session_state.get("price_mode", PRICE_MODE_DEFAULT)


def real_mode_allowed(student_id):
    """9번: 실제 시세는 2단계를 연 학생만. 시연 모드에서는 잠금 없이 연다.
    투자 탭 동의 2트랙(config.INVEST_CONSENT_TRACK)에서는 레벨과 무관하게 누구나 실제 시세로 연습한다."""
    import config
    if config.INVEST_CONSENT_TRACK:
        return True
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
    """투자 탭 연습 모드·실수에서 배우기·홈이 함께 쓰는 시세와 거래.

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


# ---------- 투자 탭 동의 기반 2트랙 조각 (invest/tintin_invest_handoff, 2026-11-13) ----------
# 색은 config.toml 값만 쓴다: 네이비 = 글자색(--text), 상승 = 빨강, 하락 = 파랑(국내 관례), 실전 점 = 노랑.
# 막대 길이처럼 값에서 오는 크기만 style='--w:..%'로 넘기고, 모양은 style.css가 정한다.

MODE_PILLS = {"PRACTICE": ("mode-practice", "연습 모드 · 가상 머니"), "REAL": ("mode-real", "실전 모드 · 부모님 동의")}


def mode_pill(track, text=None):
    """연습: 밝은 파랑 배지 + 파란 점, 실전: 네이비 배지 + 노란 점 (두 모드를 헷갈리지 않게)."""
    cls, label = MODE_PILLS[track]
    return f"<span class='mode-pill {cls}'><i></i>{escape(text or label)}</span>"


def change_html(pct, prefix=""):
    """등락률: 오르면 빨강 +, 내리면 파랑 −, 그대로면 회색 (색과 기호를 함께)."""
    if pct is None:
        return ""
    kind = "up" if pct > 0 else "down" if pct < 0 else "flat"
    text = f"{prefix}{pct:+.1f}%".replace("-", "−")
    return f"<span class='chg chg-{kind}'>{escape(text)}</span>"


def navy_card(eyebrow, title_html, sub=None):
    """네이비 안내 카드. title_html은 부르는 쪽에서 escape한 HTML (<b class='hl'>로 노란 강조)."""
    sub_html = f"<div class='navy-sub'>{escape(sub)}</div>" if sub else ""
    st.markdown(f"<div class='navy'><div class='navy-eyebrow'>{escape(eyebrow)}</div>"
                f"<div class='navy-title'>{title_html}</div>{sub_html}</div>", unsafe_allow_html=True)


def account_html(label, right, value, pct, bar=None, foot=None, real=False):
    """계좌 카드 HTML. bar: 구성 막대 비율 목록(%) · foot: (왼쪽, 오른쪽) 한 줄. real이면 '실제 돈' 표시."""
    right_html = (f"<span class='acc-tag'>{escape(right)}</span>" if real
                  else f"<span class='acc-right'>{escape(right)}</span>")
    bar_html = ""
    if bar is not None:
        parts = "".join(f"<i class='seg seg-{k % 4}' style='--w:{max(0, w)}%'></i>" for k, w in enumerate(bar))
        bar_html = f"<div class='acc-bar'>{parts}</div>"
    foot_html = ""
    if foot:
        foot_html = f"<div class='acc-foot'><span>{escape(foot[0])}</span><span>{escape(foot[1])}</span></div>"
    return (f"<div class='acc'><div class='acc-head'><span class='acc-label'>{escape(label)}</span>{right_html}</div>"
            f"<div class='acc-value'><span>{value:,}원</span>{change_html(pct)}</div>{bar_html}{foot_html}</div>")


def limit_html(used, limit, foot):
    pct = 0 if not limit else min(100, round(used / limit * 100))
    return (f"<div class='lim'><div class='lim-head'><span>이번 달 투자 한도</span><b>{used:,} / {limit:,}원</b></div>"
            f"<div class='lim-bar'><i style='--w:{pct}%'></i></div><div class='lim-foot'>{escape(foot)}</div></div>")


def stock_row(row, key, action=None):
    """보유·관심 종목 한 줄 (이름 · 수량·평가액 · 등락률 또는 동작 글자). 줄 전체가 버튼이다. 눌렀으면 True."""
    chip = f" <span class='surge-chip'>오늘 {row['changePct']:+.0f}%</span>" if row.get("surge") else ""
    right = (f"<span class='srow-action'>{escape(action)}</span>" if action
             else change_html(row["changePct"]))
    with st.container(key=f"srow-{key}"):
        st.markdown(f"<div class='srow'><div><div class='srow-name'>{escape(row['name'])}{chip}</div>"
                    f"<div class='srow-sub'>{escape(row['sub'])}</div></div>{right}</div>", unsafe_allow_html=True)
        return st.button(f"{row['name']} {action or '보기'}", key=f"srow-btn-{key}")


def spark_svg(history, surge=False):
    """최근 한 달 종가 선 그림 (inline SVG, 색은 style.css). 급등이면 마지막 점에 '오늘 급등'."""
    closes = [c for _, c in history]
    if len(closes) < 2:
        return ""
    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1
    w, h = 310, 110
    pts = [(round(i * (w - 12) / (len(closes) - 1), 1), round(100 - (c - lo) / span * 80, 1))
           for i, c in enumerate(closes)]
    line = " ".join(f"{x},{y}" for x, y in pts)
    kind = "up" if closes[-1] >= closes[0] else "down"
    end = pts[-1]
    mark = (f"<circle class='spark-dot' cx='{end[0]}' cy='{end[1]}' r='5'/>"
            f"<text class='spark-note' x='{end[0]}' y='{max(12, end[1] - 10)}' text-anchor='end'>오늘 급등</text>"
            if surge else "")
    label = "최근 한 달 주가 흐름" + (": 오늘 급등" if surge else "")
    return (f"<svg class='spark spark-{kind}' viewBox='0 0 {w} {h}' role='img' aria-label='{label}'>"
            f"<line class='spark-base' x1='0' y1='100' x2='{w}' y2='100'/>"
            f"<polyline points='{line}'/>{mark}</svg>")


def price_html(price, pct, label, chart=""):
    return (f"<div class='price'><div class='price-row'><span class='price-value'>{price:,}원</span>{change_html(pct)}"
            f"<span class='price-label'>{escape(label)}</span></div>{chart}</div>")


def headlines_html(items, note=None):
    rows = []
    for h in items:
        title = escape(h["title"])
        if h.get("url"):
            title = f"<a href='{escape(h['url'], quote=True)}' target='_blank'>{title}</a>"
        src = f"<span class='hl-src'>{escape(h['source'])}</span>" if h.get("source") else ""
        rows.append(f"<div class='hl-row'><span class='hl-kind'>[{escape(h['type'])}]</span> {title}{src}</div>")
    if not rows:
        rows.append(f"<div class='muted'>{escape(note or '')}</div>")
    return f"<div class='hl-list'>{''.join(rows)}</div>"


def steps_html(steps):
    """번호가 붙은 단계 안내. steps: [(제목, 설명)] — 첫 단계가 지금 할 일."""
    rows = "".join(f"<div class='step{' step-on' if i == 0 else ''}'><span class='step-no'>{i + 1}</span>"
                   f"<div><div class='step-title'>{escape(t)}</div><div class='step-sub'>{escape(d)}</div></div></div>"
                   for i, (t, d) in enumerate(steps))
    return f"<div class='steps'>{rows}</div>"


SKILL_LABELS = {"knowledge": "금융지식", "risk": "위험관리", "decision": "의사결정"}


def report_html(report, title="부모님께 보낼 연습 리포트"):
    """연습 리포트 (네이비). 역량은 점수 없이 '잘하는 중 / 연습 중'만 (CLAUDE.md 규칙 5)."""
    rate = report["checklistRate"]
    stats = [("연습 기간", f"{report['weeks']}주"), ("투자일지", f"{report['journalCount']}회"),
             ("체크리스트", "기록 전" if rate is None else f"{round(rate * 100)}%")]
    tiles = "".join(f"<div class='rep-tile'><span>{escape(k)}</span><b>{escape(v)}</b></div>" for k, v in stats)
    skills = "".join(f"<div class='rep-skill'><span>{SKILL_LABELS[k]}</span>"
                     f"<b class='{'good' if ok else 'practice'}'>{'잘하는 중' if ok else '연습 중'}</b></div>"
                     for k, ok in report["skills"].items())
    hl = " · ".join(report["highlights"])
    hl_html = f"<div class='navy-sub'>{escape(hl)}</div>" if hl else ""
    return (f"<div class='navy rep'><div class='navy-eyebrow'>{escape(title)}</div>"
            f"<div class='rep-tiles'>{tiles}</div><div class='rep-skills'>{skills}</div>{hl_html}</div>")


def record_html(items, title="이번 달 내 투자 기록", note=None):
    """돌아보는 기록 (등급·평가 아님). items: [(이름, 값)]."""
    cells = "".join(f"<div class='rec-cell'>{escape(k)} <b>{escape(v)}</b></div>" for k, v in items)
    note_html = f"<div class='navy-sub'>{escape(note)}</div>" if note else ""
    return (f"<div class='navy rec'><div class='navy-eyebrow'>{escape(title)}</div>"
            f"<div class='rec-grid'>{cells}</div>{note_html}</div>")


def summary_html(items):
    rows = "".join(f"<div class='sum-row'><span>{escape(k)}</span><b>{escape(v)}</b></div>" for k, v in items)
    return f"<div class='sum'>{rows}</div>"


# ---------- 혜택 탭 돼지 저금통 (point/tintin_piggy, 2026-11-13) ----------
# 단계 색은 style.css의 .piggy-<key>가 config.toml 색을 흰색·글자색과 섞어 만든다 (body · shade · ink · tint).

def piggy_svg(level, label=None):
    """돼지 저금통 그림 (reference 좌표 그대로, 168×140). 황금이면 흰 반짝임 3개."""
    sparkle = ("<path class='pig-spark' d='M14 14 l3 7 7 3 -7 3 -3 7 -3 -7 -7 -3 7 -3z'/>"
               "<path class='pig-spark' d='M104 8 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z'/>"
               "<path class='pig-spark' d='M110 82 l2 4 4 2 -4 2 -2 4 -2 -4 -4 -2 4 -2z'/>"
               if level["key"] == "gold" else "")
    return (f"<svg class='pig' viewBox='0 0 120 100' role='img' aria-label='{escape(label or level['name'] + ' 저금통')}'>"
            f"{sparkle}"
            "<rect class='pig-shade' x='32' y='70' width='13' height='18' rx='5'/>"
            "<rect class='pig-shade' x='72' y='70' width='13' height='18' rx='5'/>"
            "<path class='pig-tail' d='M20 50 q-10 -2 -7 -11'/>"
            "<ellipse class='pig-body' cx='58' cy='52' rx='40' ry='31'/>"
            "<path class='pig-shade' d='M40 28 L46 11 L57 25 Z'/>"
            "<rect class='pig-ink' x='49' y='22' width='20' height='5' rx='2.5'/>"
            "<ellipse class='pig-shade' cx='96' cy='55' rx='10' ry='9'/>"
            "<circle class='pig-ink' cx='93' cy='54' r='1.8'/><circle class='pig-ink' cx='99' cy='54' r='1.8'/>"
            "<circle class='pig-ink' cx='78' cy='44' r='3.4'/>"
            "<ellipse class='pig-cheek' cx='80' cy='60' rx='5' ry='3'/></svg>")


def piggy_art(level):
    """혜택 탭 저금통 그림: 그로비 5단계 (씨앗 → 떡잎 → 두 잎 → 꽃봉오리 → 황금 잎), 아니면 예전 돼지 그림."""
    import config
    if config.GROWBY_MASCOT:
        import growby
        return growby.img_html(level=level["no"], role="result", px=120)
    return piggy_svg(level)


def piggy_card(level, line, progress, range_text, right_text, levels, badge=None):
    """내 돼지 저금통: 돼지 카드 + 진행 바 + 5단계 표시 + 안내 문구 (HTML 한 덩어리)."""
    badge_html = (f"<div class='pig-badge'>🏅 {escape(badge[0])} · 칭호 '{escape(badge[1])}'</div>" if badge else "")
    dots = "".join(
        f"<div class='pig-dot-wrap'><span class='pig-dot piggy-{l['key']}{' on' if l['no'] == level['no'] else ''}'></span>"
        f"<b>{escape(l['short'])}</b><small>{l['min']:,}P</small></div>" for l in levels)
    return (f"<div class='piggy piggy-{level['key']}'>"
            f"<div class='pig-box'>{piggy_art(level)}<div class='pig-lv'>Lv.{level['no']}</div>"
            f"<div class='pig-name'>{escape(level['name'])}</div><div class='pig-line'>{escape(line)}</div>{badge_html}</div>"
            f"<div class='pig-bar'><i style='--w:{round(progress * 100)}%'></i></div>"
            f"<div class='pig-bar-foot'><span>{escape(range_text)}</span><span>{escape(right_text)}</span></div>"
            f"<div class='pig-dots'>{dots}</div>"
            "<div class='muted'>포인트를 쓰면 저금통이 가벼워져서 단계가 내려가요. 다 쓰면 분홍 돼지부터 다시 시작해요.</div>"
            "</div>")


# ---------- 오늘의 뉴스 · 시세 자동 업데이트 조각 (NEWS_MARKET_SPEC.md, 2026-11-16) ----------
# 카테고리 → 카드 바탕 색 (config.toml 색 이름). 그림은 assets/news_illustrations의 키워드 일러스트만.
NEWS_TONES = {"semiconductor": "blue", "interest": "yellow", "exchange": "green", "trade": "blue",
              "prices": "orange", "security": "red", "payments": "blue", "stockmarket": "red",
              "housing": "orange", "energy": "yellow", "jobs": "violet", "policy": "violet", "general": "gray"}


def update_status(kind, text, extra=None):
    """자동 업데이트 상태 줄: ok(초록) / busy(노랑) / fail(주황). role=status."""
    tail = f" <span class='upd-extra'>· {escape(extra)}</span>" if extra else ""
    st.markdown(f"<div role='status' class='upd upd-{kind}'><i></i><span><b>{escape(text)}</b>{tail}</span></div>",
                unsafe_allow_html=True)


def news_thumb(uri, cat, label, alt):
    tone = NEWS_TONES.get(cat, "gray")
    return (f"<div class='nthumb'><img class='nthumb-img tone-bg-{tone}' src='{uri}' alt='{escape(alt)}'>"
            f"<span class='nchip tone-chip-{tone}'>{escape(label)}</span></div>")


def change_arrow_html(pct, change=None):
    """▲ 1,000원 (+1.8%) — 상승 빨강 ▲, 하락 파랑 ▼ (기호와 색을 함께)."""
    if pct is None:
        return ""
    kind = "up" if pct > 0 else "down" if pct < 0 else "flat"
    mark = {"up": "▲", "down": "▼", "flat": ""}[kind]
    amount = f"{abs(change):,}원 " if change is not None else ""
    text = f"{mark} {amount}({pct:+.1f}%)".replace("-", "−")
    return f"<span class='chg chg-{kind}'>{text}</span>"


def news_card_html(item, index, total, uri, label, cat, alt, time_text):
    tone = NEWS_TONES.get(cat, "gray")
    thumb = news_thumb(uri, cat, label, alt) if uri else f"<span class='nchip tone-chip-{tone}'>{escape(label)}</span>"
    return (f"<div class='ncard'>{thumb}<div class='ncard-text'>"
            f"<div class='ncard-meta'>{index}/{total} · {escape(item['publisher'])} · {escape(time_text)}</div>"
            f"<div class='ncard-title'>{escape(item['cards'][0]['title'])}</div>"
            f"<div class='ncard-sum'>{escape(item['summary'])}</div></div></div>")


def slide_html(item, slide, uri, cat, alt, label, index, total, tini=True):
    """카드뉴스 한 장 (진행 막대 · 키워드 그림 + 캡션 · 태그 칩 · 해시태그 · 제목 · 설명 · 틴이 한마디/단어)."""
    tone = NEWS_TONES.get(cat, "gray")
    card = item["cards"][slide]
    bars = "".join(f"<i class='{'on' if k <= slide else ''}'></i>" for k in range(4))
    image = (f"<div class='slide-img'><img src='{uri}' alt='{escape(alt)}'>"
             f"<span class='slide-cap'>키워드 이미지 · 실제 뉴스 사진 아님</span></div>" if uri else "")
    tags = "".join(f"<span>#{escape(t)}</span>" for t in item["tags"][:2])
    if slide == 3:
        meaning = (escape(card["meaning"]) if card.get("meaning")
                   else f"콘텐츠 없음: {escape(card['word'])} (개념 카드가 아직 없어요)")
        body = (f"<div class='slide-word'><div class='slide-word-k'>오늘의 단어</div><b>{escape(card['word'])}</b>"
                f"<div>{meaning}</div><small>단어장에 담았어요</small></div>")
    else:
        body = (f"<div class='slide-title'>{escape(card['title'])}</div>"
                f"<div class='slide-body'>{escape(card['body'])}</div>")
        if slide == 2 and card.get("tip") and tini:
            import config
            tip = card["tip"]
            if config.GROWBY_MASCOT:  # AI가 만든 한마디도 그로비 말 규칙 검사
                import growby
                tip = growby.safe_line(tip)
            body += (f"<div class='say'>{mascot_html(size='md', situation='card_me')}"
                     f"<div class='say-bubble'>{escape(tip)}</div></div>")
    return (f"<div class='slide slide-{tone}'><div class='slide-bars'>{bars}</div>"
            f"<div class='slide-head'>뉴스 {index}/{total} · {escape(label)}</div>{image}"
            f"<div class='slide-tags'><span class='slide-tag'>{escape(card['tag'])}</span>{tags}</div>{body}</div>")


def source_line(item, when):
    link = escape(item["url"], quote=True)
    return (f"<div class='nsource'>AI 요약 · {escape(item['publisher'])} {escape(when)}"
            + (f" · <a href='{link}' target='_blank'>원문 보기</a>" if item.get("url") else "") + "</div>")


def day_circles_html(days, by_day):
    names = "월화수목금토일"
    cells = []
    for k, d in enumerate(days):
        n = by_day.get(d)
        dot = "" if n is None else f"<span class='dc dc-{'full' if n >= 3 else 'part'}'>{n}</span>"
        cells.append(f"<div class='dcol'><small>{names[k]}</small>{dot}</div>")
    return f"<div class='dcircles'>{''.join(cells)}</div>"


def stat_tiles_html(items):
    return "<div class='stiles'>" + "".join(
        f"<div class='stile'><b>{escape(v)}</b><small>{escape(k)}</small></div>" for k, v in items) + "</div>"


# ---------- 좁은 화면용 차트 (2026-11-16 화면 점검: 축 글자가 세로로 눕거나 범례가 잘리던 것) ----------

def line_chart(frame, height=220):
    """주차별 선 차트. x축 글자는 가로로, 범례는 아래 2줄로 (휴대폰 폭에서 잘리지 않게). 색은 테마(config.toml)."""
    import altair as alt
    xname = frame.index.name or "x"
    data = frame.reset_index().melt(xname, var_name="항목", value_name="값")
    chart = alt.Chart(data).mark_line(point=True).encode(
        x=alt.X(f"{xname}:N", sort=list(frame.index), axis=alt.Axis(labelAngle=0, title=None)),
        y=alt.Y("값:Q", title=None),
        color=alt.Color("항목:N", sort=list(frame.columns),
                        legend=alt.Legend(orient="bottom", columns=2, title=None, labelLimit=160)),
        tooltip=[xname, "항목", "값"]).properties(height=height)
    st.altair_chart(chart, width="stretch")


# ---------- 주식 차트 (2026-11-17, CHART_SPEC.md): 기간 · 봉 · 선/캔들 · 거래량 · 내 평균 단가 ----------
# Plotly 대신 Streamlit에 들어 있는 Altair로 그린다 (CLAUDE.md 기술 스택 변경 금지). 색은 config.toml (상승 빨강 · 하락 파랑).
CHART_KIND_LABEL = {"line": "선", "candle": "캔들"}
WEEKDAYS = "월화수목금토일"


def chart_bar_label(b, interval):
    if interval == "D":
        return f"{b.d.year}.{b.d.month}.{b.d.day} ({WEEKDAYS[b.d.weekday()]})"
    if interval == "W":
        e = b.e or b.d
        return f"{b.d.month}.{b.d.day} ~ {e.month}.{e.day} 주" + (" (진행 중)" if b.partial else "")
    return f"{b.d.year}년 {b.d.month}월" + (" (진행 중)" if b.partial else "")


def chart_tick_label(b, interval, period):
    if interval == "M":
        return f"{b.d.year % 100}.{b.d.month}"
    if period in ("1Y", "3Y", "ALL"):
        return f"{b.d.year % 100}.{b.d.month}.{b.d.day}"
    return f"{b.d.month}.{b.d.day}"


def _signed_won(n):
    return f"{'+' if n >= 0 else '−'}{abs(n):,.0f}원"


def build_price_chart(view, kind="candle", avg_price=None, split_events=None, show_volume=True, height=230):
    """Altair 차트: 가격(캔들 또는 선+옅은 면) + 아래 거래량. x축은 순서(휴장일 빈칸 없음), 날짜 눈금 3개,
    가격 눈금은 오른쪽 3개. 누르거나 올리면 그 막대의 날짜·시고저종·거래량. 확대·끌기는 없다."""
    import json as _json

    import altair as alt
    import pandas as pd

    colors = theme_colors()
    up, down, gray = colors["red"], colors["blue"], colors["gray"]
    bars = view.bars
    n = len(bars)
    picks = sorted({0, n // 2, n - 1})
    ticks = ["" for _ in bars]
    for i in picks:
        ticks[i] = chart_tick_label(bars[i], view.interval, view.period)
    prev = [None] + [b.c for b in bars[:-1]]
    df = pd.DataFrame({
        "i": range(n), "날짜": [chart_bar_label(b, view.interval) for b in bars],
        "o": [b.o for b in bars], "h": [b.h for b in bars], "l": [b.l for b in bars], "c": [b.c for b in bars],
        "v": [b.v for b in bars], "dir": ["up" if b.c >= b.o else "down" for b in bars],
        "등락": ["" if p is None else f"{(b.c / p - 1) * 100:+.1f}%" for b, p in zip(bars, prev)],
    })
    x_axis = alt.Axis(values=picks, labelExpr=f"{_json.dumps(ticks, ensure_ascii=False)}[datum.value]",
                      labelAngle=0, title=None, grid=False, ticks=False, domain=False, labelColor=gray,
                      labelFlush=True)  # 첫·마지막 날짜가 그래프 밖으로 잘리지 않게
    color = alt.Color("dir:N", scale=alt.Scale(domain=["up", "down"], range=[up, down]), legend=None)
    lo, hi = min(b.l for b in bars), max(b.h for b in bars)
    pad = (hi - lo) * 0.06 or hi * 0.02
    # 한 장의 겹친 그래프: 가격은 위쪽, 거래량은 아래 1/4 (각자 다른 세로 눈금). 두 장으로 나누면(vconcat)
    # Streamlit이 폭을 카드에 맞추지 못해 오른쪽 가격 눈금과 마지막 날짜가 잘렸다.
    vol_room = (hi - lo + 2 * pad) * (0.36 if show_volume else 0)
    y_scale = alt.Scale(domain=[lo - pad - vol_room, hi + pad], zero=False, nice=False)
    y_axis = alt.Axis(orient="right", values=_price_ticks(lo, hi), format=",.0f", title=None, labelColor=gray,
                      domain=False, ticks=False, gridColor=colors["border"])
    hover = alt.selection_point(fields=["i"], on="pointerover", nearest=False, empty=False, clear="pointerout")
    tooltip = [alt.Tooltip("날짜:N"), alt.Tooltip("c:Q", title="종가", format=",.0f"), alt.Tooltip("등락:N"),
               alt.Tooltip("o:Q", title="시가", format=",.0f"), alt.Tooltip("h:Q", title="고가", format=",.0f"),
               alt.Tooltip("l:Q", title="저가", format=",.0f"), alt.Tooltip("v:Q", title="거래량", format=",.0f")]
    base = alt.Chart(df).encode(x=alt.X("i:O", axis=x_axis, scale=alt.Scale(paddingInner=0.25, paddingOuter=0.2)))
    layers = []
    if show_volume:
        vmax = max(1, max(b.v for b in bars))
        layers.append(base.mark_bar(opacity=0.35).encode(
            y=alt.Y("v:Q", scale=alt.Scale(domain=[0, vmax / 0.24]), axis=None), color=color))
    if kind == "candle":
        price = (base.mark_rule().encode(y=alt.Y("l:Q", scale=y_scale, axis=y_axis), y2="h:Q", color=color)
                 + base.mark_bar().encode(y=alt.Y("o:Q", scale=y_scale, axis=y_axis), y2="c:Q", color=color))
    else:
        trend = up if view.pct >= 0 else down
        price = (base.mark_area(opacity=0.08, color=trend).encode(y=alt.Y("c:Q", scale=y_scale, axis=y_axis),
                                                                  y2=alt.datum(lo - pad))
                 + base.mark_line(color=trend, strokeWidth=2.4).encode(y=alt.Y("c:Q", scale=y_scale, axis=y_axis)))
    layers.append(price)
    if avg_price:
        avg = pd.DataFrame({"y": [avg_price], "t": [f"내 평균 단가 {avg_price:,.0f}"]})
        layers.append(alt.Chart(avg).mark_rule(color=colors["blue"], strokeDash=[6, 4], strokeWidth=1.4).encode(
            y=alt.Y("y:Q", scale=y_scale, axis=None)))
        layers.append(alt.Chart(avg).mark_text(align="left", dx=4, dy=-7, color=colors["blue"], fontSize=11,
                                               fontWeight="bold").encode(x=alt.value(0), y=alt.Y("y:Q", scale=y_scale, axis=None),
                                                                         text="t:N"))
    flags = []
    for ev in split_events or []:
        hit = next((i for i, b in enumerate(bars) if b.d <= ev.d <= (b.e or b.d)), None)
        if hit is not None:
            flags.append({"i": hit, "t": f"1:{ev.ratio:g} 분할" if ev.ratio >= 1 else f"{1 / ev.ratio:g}:1 병합"})
    if flags:
        layers.append(alt.Chart(pd.DataFrame(flags)).mark_text(dy=8, fontSize=10, fontWeight="bold",
                                                                color=colors["orange"]).encode(
            x="i:O", y=alt.value(0), text="t:N"))
    total = height + (70 if show_volume else 0)
    layers += [base.mark_rule(color=colors["text"], strokeDash=[3, 3]).encode(
                   opacity=alt.condition(hover, alt.value(0.7), alt.value(0))),
               base.mark_bar(opacity=0).encode(tooltip=tooltip).add_params(hover)]  # x만 있으면 위아래 전체를 덮는다
    # autosize fit + padding 포함: 축 글자까지 카드 폭 안에 맞춘다 (기본값은 축만큼 넓어져 오른쪽이 잘렸다)
    return (alt.layer(*layers).resolve_scale(y="independent")
            .properties(height=total, width="container", autosize=alt.AutoSizeParams(type="fit", contains="padding"),
                        padding={"left": 14, "right": 2, "top": 4, "bottom": 2})
            .configure_view(strokeWidth=0))


def _price_ticks(lo, hi):
    """오른쪽 가격 눈금 3개 (가장 낮은 값 근처 · 가운데 · 가장 높은 값 근처, 보기 좋게 반올림)."""
    step = 10 ** max(0, len(str(int(max(1, hi - lo)))) - 2)
    r = lambda x: round(x / step) * step
    return [r(lo + (hi - lo) * k) for k in (0.08, 0.5, 0.92)]


def render_stock_chart(code, daily, today, events=None, avg_price=None, backfill_pct=1.0, key_prefix="chart",
                       close_only=False, note=None, avg_qty=None):
    """종목 상세의 그래프 블록 하나 (연습·실전이 같은 함수를 쓴다). daily: 분할 보정까지 마친 일봉 (chart_series.Bar)."""
    from engine import chart_series as cs
    if not daily:
        st.info("시세를 아직 받지 못했어요. 영업일 오후 1시 30분에 자동으로 받아요.")
        return
    k = lambda name: f"{key_prefix}-{code}-{name}"
    first_day, end = daily[0].d, daily[-1].d
    periods = cs.period_buttons(first_day, end)
    if backfill_pct < 1.0 and "3Y" in periods:  # 3년치를 받는 중이면 3년만 잠근다
        periods = [p for p in periods if p != "3Y"]
    default = "1Y" if "1Y" in periods else periods[-1]
    with st.container(key=f"chart-ctl-{key_prefix}"):
        period = st.segmented_control("기간", periods, default=st.session_state.get(k("p"), default) if
                                      st.session_state.get(k("p")) in periods else default,
                                      format_func=lambda p: cs.PERIOD_LABEL[p], key=k("p-ctl"),
                                      label_visibility="collapsed") or default
        if st.session_state.get(k("p")) != period:  # 기간을 바꾸면 봉은 그 기간의 기본으로
            st.session_state[k("p")] = period
            st.session_state.pop(k("i"), None)
        allowed = cs.ALLOWED[period]
        with st.container(key=f"chart-row-{key_prefix}", horizontal=True):
            iv = st.segmented_control("봉", allowed, default=cs.normalize(period, st.session_state.get(k("i"))),
                                      format_func=lambda i: cs.INTERVAL_LABEL[i][0], key=k(f"i-ctl-{period}"),
                                      label_visibility="collapsed")
            iv = cs.normalize(period, iv)
            st.session_state[k("i")] = iv
            if close_only:
                kind = "line"
            else:
                kind = st.segmented_control("모양", ["line", "candle"], default=st.session_state.get(k("kind"), "candle"),
                                            format_func=CHART_KIND_LABEL.get, key=k("kind-ctl"),
                                            label_visibility="collapsed") or "candle"
                st.session_state[k("kind")] = kind
    notes = [cs.blocked_note(period)] if cs.blocked_note(period) else []
    if backfill_pct < 1.0:
        notes.append(f"3년치 시세를 받는 중이에요 · 36개월 중 {round(backfill_pct * 36)}개월 받았어요 (3년은 준비 중)")
    if close_only:
        notes.append("연습용 가상 시세는 종가만 있어 선 그래프로 봐요")
    if note:
        notes.append(note)
    for line in notes:
        muted(line)

    view = cs.window(daily, period, iv, today)
    kind_word = "up" if view.pct > 0 else "down" if view.pct < 0 else "flat"
    mark = {"up": "▲", "down": "▼", "flat": ""}[kind_word]
    st.markdown(f"<div class='chart-period chg-{kind_word}'>{cs.PERIOD_LABEL[period]} 동안 {mark} {abs(view.pct):.1f}% "
                f"<span>({_signed_won(view.change)})</span></div>", unsafe_allow_html=True)
    last, before = view.bars[-1], (view.bars[-2] if len(view.bars) > 1 else None)
    diff = None if before is None else (last.c / before.c - 1) * 100
    diff_html = "" if diff is None else change_arrow_html(diff)
    ohlv = "" if close_only else (f"<div class='chart-info-sub'>시 {last.o:,.0f} · 고 {last.h:,.0f} · 저 {last.l:,.0f}"
                                  f" · 거래량 {_volume_text(last.v)}</div>")
    st.markdown(f"<div class='chart-info'><div class='chart-info-top'><b>{escape(chart_bar_label(last, iv))}</b>"
                f"<span>종가 <b>{last.c:,.0f}원</b> {diff_html}</span></div>{ohlv}</div>", unsafe_allow_html=True)
    st.altair_chart(build_price_chart(view, kind, avg_price, events, show_volume=not close_only), width="stretch",
                    key=k("fig"))
    with st.container(key=f"chart-foot-{key_prefix}", horizontal=True):
        muted(f"{cs.INTERVAL_LABEL[iv]} {len(view.bars)}개 · 그래프에 올리면(누르면) 그날 가격이 보여요")
        if not close_only:
            with st.popover("캔들 읽는 법"):
                candle_guide()
    sm = cs.summary(daily, view)
    items = [("기간 수익률", f"<b class='chg-{kind_word}'>{view.pct:+.1f}%</b>"),
             ("기간 시작 가격", f"<b>{sm['base']:,.0f}원</b>"),
             ("가장 높았던 날", f"<b>{sm['high']:,.0f}원</b> · {sm['high_date']:%y.%m.%d}"),
             ("가장 낮았던 날", f"<b>{sm['low']:,.0f}원</b> · {sm['low_date']:%y.%m.%d}")]
    if not close_only:
        items.append(("하루 평균 거래량", f"<b>{_volume_text(sm['avg_volume'])}</b>"))
    if avg_price:
        items.append(("내 평균 단가", f"<b class='chg-down'>{avg_price:,.0f}원</b>"
                      + (f" ({avg_qty})" if avg_qty else "")))
    cells = "".join(f"<div class='sum-cell'><small>{escape(t)}</small><div>{v}</div></div>" for t, v in items)
    st.markdown(f"<div class='chart-summary'><div class='chart-summary-title'>{cs.PERIOD_LABEL[period]} 한눈에 보기</div>"
                f"<div class='chart-summary-grid'>{cells}</div></div>", unsafe_allow_html=True)


def _volume_text(v):
    v = int(v or 0)
    return f"{v / 10_000:,.0f}만 주" if v >= 100_000 else f"{v:,}주"


def candle_guide():
    """캔들 읽는 법 (시트). 지나간 가격을 읽는 법까지만 — 내일 가격을 맞히는 법이 아니다."""
    import config
    face = ""
    if config.GROWBY_MASCOT:
        import growby
        face = growby.img_html("default", "bubble", 56, decorative=True)
    st.markdown(
        f"<div class='candle-guide'><div class='candle-guide-head'>{face}<b>캔들 읽는 법</b></div>"
        "<div class='candle-row'><span class='candle candle-up'><i></i></span><div><b class='chg-up'>빨간 캔들 · 올랐어요</b>"
        "<small>아래가 시가(시작 가격), 위가 종가(끝 가격). 몸통이 길수록 많이 올랐어요.</small></div></div>"
        "<div class='candle-row'><span class='candle candle-down'><i></i></span><div><b class='chg-down'>파란 캔들 · 내렸어요</b>"
        "<small>위가 시가, 아래가 종가. 위아래 꼬리 끝은 그동안의 가장 높은 값(고가)과 낮은 값(저가)이에요.</small></div></div>"
        "<div class='candle-units'><div><b>일봉</b> 하루 = 막대 하나</div><div><b>주봉</b> 한 주(월~금) = 막대 하나</div>"
        "<div><b>월봉</b> 한 달 = 막대 하나</div></div>"
        "<div class='candle-note'>캔들은 지나간 가격을 보여줄 뿐이에요. 모양만 보고 내일 가격을 맞힐 수는 없어요.</div></div>",
        unsafe_allow_html=True)
