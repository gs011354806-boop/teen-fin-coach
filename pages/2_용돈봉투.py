"""용돈봉투 화면. 입출금 형식은 우리은행 청소년 마이데이터를 가정한다.

첫 화면: 요약 + 용돈 받기 + 봉투 카드 3장. 카드를 누르면 같은 페이지에서 봉투 상세로 바뀐다 (?env=SPEND 등).
기획: docs/ENVELOPE_REDESIGN.md (23번: 봉투 카드 + 상세 전환 + 첫 화면 정리)
"""

import base64
from html import escape
from pathlib import Path

import pandas as pd
from PIL import Image
import streamlit as st

import config
import ui_common as ui
from engine import cards, envelope, rewards, spend_quiz, store, unlock
from ui_common import won

ENVELOPE_LABELS = {"SPEND": "쓰기", "SAVE": "모으기", "INVEST": "투자연습"}
ENVELOPE_ICONS = {"SPEND": "🛍️", "SAVE": "🐷", "INVEST": "🌱"}
CATEGORY_LABELS = {"CONVENIENCE": "편의점", "CAFE_DESSERT": "카페·디저트",
                   "MEAL": "식사·분식", "MART": "마트",
                   "SHOPPING": "쇼핑", "TRANSPORT": "교통", "OTHER": "기타"}

student = ui.setup("용돈봉투", "✉️", active="envelope")
student_id = student["student_id"]
ratio = student["envelope_ratio"]
goal = student["saving_goal"]

allowance = store.load_allowance()
today = envelope.latest_date(allowance)
balance = envelope.balances(allowance, student_id)


def open_envelope(name):
    """봉투 카드·칩을 누르면 부른다 (on_click이라 따로 rerun하지 않아도 바로 바뀐다)."""
    if name:
        st.query_params["env"] = name
    else:
        st.query_params.pop("env", None)


def card_subtitle(name):
    """봉투 카드 아래 한 줄 (코드가 만든 사실만)."""
    if name == "SPEND":
        top = envelope.top_spending(allowance, student_id)
        return f"가장 많이 쓴 곳: {CATEGORY_LABELS[top[0]]}" if top else "아직 쓴 돈이 없어요"
    if name == "SAVE":
        return f"{goal['item']}까지 {envelope.goal_progress_pct(balance['SAVE'], goal['amount']):.0f}%"
    if config.INVEST_CONSENT_TRACK:
        return "실전 투자는 이 봉투에서 이체돼요"
    return f"실전 준비 {unlock.stage(store.load_unlocks(), student_id)}/3단계"


def history_table(name):
    rows = envelope.history(allowance, student_id, name)
    if not len(rows):
        st.info("아직 내역이 없어요.")
        return
    st.dataframe(
        pd.DataFrame({
            "날짜": [d[5:] for d in rows["date"]],
            "내용": rows["memo"],
            "금액": [f"{a:+,}원" for a in rows["amount"]],
        }),
        hide_index=True, width="stretch")


# ---------- 첫 화면 ----------

def render_overview():
    ui.app_bar("용돈봉투", badge="가상 용돈 기록")
    ui.muted(f"{today} 기준 · 데모용 가상 내역이에요.")

    with ui.card("summary"):
        st.markdown(f"<div class='env-total-label'>내 용돈 전체</div>"
                    f"<div class='env-total'>{won(sum(balance.values()))}</div>", unsafe_allow_html=True)
        weekly = student["weekly_allowance"]
        received = envelope.deposit_date_this_week(allowance, student_id, today)
        if received:
            st.markdown(f"<span class='chip chip-good'>이번 주 용돈 받음 · {received[5:]}</span>",
                        unsafe_allow_html=True)
        else:
            split = envelope.split_allowance(weekly, ratio)
            ui.muted("이번 용돈은 이렇게 나뉘어요: "
                     + " · ".join(f"{ENVELOPE_LABELS[n]} {won(split[n])}" for n in envelope.ENVELOPES))
            if st.button(f"용돈 {won(weekly)} 받기", type="primary", width="stretch"):
                # 빠르게 두 번 눌러도 중복되지 않게 저장 직전에 파일을 다시 읽어 확인한다.
                if not envelope.deposit_date_this_week(store.load_allowance(), student_id, today):
                    store.append_allowance(student_id, today, envelope.deposit_entries(weekly, ratio))
                    st.session_state["envelope_message"] = f"용돈 {won(weekly)}을 봉투에 나눠 담았어요."
                st.rerun()

    ui.section("내 봉투")
    for column, name in zip(ui.columns(3, key="envelopes", align="top"), envelope.ENVELOPES):
        with column, st.container(key=f"envcard-{name}"):
            st.markdown(
                f"<div class='env-card'>{ui.icon_html(ENVELOPE_ICONS[name])}"
                f"<div class='env-name'>{ENVELOPE_LABELS[name]}</div>"
                f"<div class='env-amount'>{won(balance[name])}</div>"
                f"<div class='env-sub'>{escape(card_subtitle(name))}</div>"
                f"<div class='env-more'>자세히 ›</div></div>", unsafe_allow_html=True)
            st.button(f"{ENVELOPE_LABELS[name]} 봉투 열기", key=f"open-{name}",
                      on_click=open_envelope, args=(name,))

    with ui.card("more"):
        with st.expander(f"용돈 나누는 비율 · 쓰기 {ratio['SPEND']} · 모으기 {ratio['SAVE']} · "
                         f"투자연습 {ratio['INVEST']}"):
            render_ratio_form()
        st.button("내 소비에 맞는 체크카드 보기", key="open-cards", width="stretch",
                  on_click=open_envelope, args=("SPEND",))
        with st.expander("전체 입출금 내역 보기"):
            mine = allowance[allowance["student_id"] == student_id].iloc[::-1]
            st.dataframe(
                pd.DataFrame({
                    "날짜": [d[5:] for d in mine["date"]],
                    "봉투": mine["envelope"].map(ENVELOPE_LABELS),
                    "내용": mine["memo"],
                    "금액": [f"{a:+,}원" for a in mine["amount"]],
                }),
                hide_index=True, width="stretch")


def render_ratio_form():
    with st.form("ratio", border=False):
        inputs = {}
        for column, name in zip(ui.columns(3, key="ratio"), envelope.ENVELOPES):
            inputs[name] = column.number_input(f"{ENVELOPE_LABELS[name]} (%)", min_value=0,
                                               max_value=100, value=ratio[name], step=5)
        submitted = st.form_submit_button("비율 저장", width="stretch")
    if submitted:
        new_ratio = {name: int(value) for name, value in inputs.items()}
        error = envelope.check_ratio(new_ratio)
        if error:
            st.error(error)
        else:
            store.save_envelope_ratio(student_id, new_ratio)
            st.session_state["envelope_message"] = "비율을 저장했어요. 다음 용돈부터 이렇게 나눠요."
            st.rerun()


# ---------- 봉투 상세 공통 ----------

def detail_header(name):
    ui.app_bar(f"{ENVELOPE_LABELS[name]} 봉투", badge="가상 용돈 기록", on_back=lambda: open_envelope(None))
    with st.container(key=f"envhead-{name}"):
        st.markdown(
            f"<div class='env-head'><div><div class='env-head-name'>{ui.icon_html(ENVELOPE_ICONS[name])} "
            f"{ENVELOPE_LABELS[name]} 봉투</div><div class='env-head-amount'>{won(balance[name])}</div></div>"
            f"<div class='env-head-sub'>{escape(card_subtitle(name))}</div></div>", unsafe_allow_html=True)
    with st.container(key="env-switch", horizontal=True):
        for other in envelope.ENVELOPES:
            if other != name:
                st.button(f"{ENVELOPE_LABELS[other]} 봉투로", key=f"switch-{other}",
                          on_click=open_envelope, args=(other,))


# ---------- 쓰기 봉투 (24번에서 내역 → 차트 → AI 피드백으로 다듬는다) ----------

def render_spend():
    detail_header("SPEND")
    ui.section("가장 많이 쓴 곳은?")
    with ui.card("spending"):
        spent = envelope.spending(allowance, student_id)
        if len(spent):
            by_category = envelope.spending_by_category(allowance, student_id)
            st.bar_chart(pd.Series({CATEGORY_LABELS[c]: total for c, total in by_category.items()},
                                   name="쓴 돈(원)"), height=220, horizontal=True)  # 분류 이름을 가로로 (좁은 화면)
            st.dataframe(
                pd.DataFrame({
                    "날짜": [d[5:] for d in spent["date"]],
                    "분류": spent["category"].map(CATEGORY_LABELS),
                    "내용": spent["memo"],
                    "금액": [won(-a) for a in spent["amount"]],
                }),
                hide_index=True, width="stretch")
        else:
            st.info("아직 지출 내역이 없어요.")

        share = envelope.impulse_share_pct(allowance, student_id)
        with ui.card("needs-wants"):
            ui.concept_card(
                store.load_concepts()["NEEDS_VS_WANTS"], key="envelope", with_quiz=False,
                intro=(f"알아 두면 좋은 개념 · 이번 달 지출 중 편의점·카페·디저트가 {share:.0f}%예요"
                       if share is not None else "알아 두면 좋은 개념"))
            with st.expander(f"확인 문제 풀어 보기 · 오늘의 내 소비 퀴즈 {spend_quiz.QUIZ_SIZE}문제"):
                render_spend_quiz()

    ui.section("내 소비에 맞는 체크카드")
    render_cards()


def render_spend_quiz():
    """내 지출 내역으로 만든 오늘의 5문제. 모두 맞히면 하루 1번 포인트 (기록 → rewards가 계산)."""
    questions = spend_quiz.daily_questions(allowance, student_id, today)
    if not questions:
        st.info("지출 내역이 있어야 문제를 만들 수 있어요.")
        return
    done_before = spend_quiz.already_done(store.load_spend_quiz(), student_id, today)
    ui.muted(f"내 지출 기록으로 만든 문제예요. {len(questions)}문제를 모두 맞히면 {rewards.SPEND_QUIZ_POINTS}P "
             "(하루 1번)." if not done_before else "오늘 포인트는 이미 받았어요. 다시 풀어 보는 건 언제든 좋아요.")
    answers = []
    for i, q in enumerate(questions, start=1):
        choice = st.radio(f"{i}. {q['question']}", q["options"], index=None,
                          key=f"spend-quiz-{student_id}-{today}-{i}")
        answers.append(choice)
        if choice is not None:
            if choice == q["answer"]:
                st.success(f"맞았어요! {q['explain']}")
            else:
                st.warning("다시 한 번 생각해 볼까요? 위의 지출 내역을 살펴봐요.")
    if not spend_quiz.all_correct(questions, answers):
        return
    flag = f"spend-quiz-rewarded-{student_id}-{today}"
    if st.session_state.get(flag):
        st.success(st.session_state[flag])
        return
    if done_before:
        message = "🎉 오늘의 내 소비 퀴즈를 모두 맞혔어요! (오늘 포인트는 이미 받았어요)"
    else:
        store.append_spend_quiz(student_id, today)
        events = rewards.apply_daily_cap(rewards.earn_events(
            student, store.load_trades(), store.load_missions(), allowance, store.load_game_reviews(),
            store.load_news_quiz(), store.load_spend_quiz(), store.load_mission_runs()))
        granted = next((e["granted"] for e in events if e["kind"] == "소비 퀴즈" and e["date"] == today), 0)
        message = (f"🎉 모두 맞혔어요! {granted}P를 받았어요." if granted
                   else f"🎉 모두 맞혔어요! 오늘 받을 수 있는 포인트(하루 {rewards.DAILY_CAP}P)를 다 받아서 이번엔 0P예요.")
    st.session_state[flag] = message
    st.success(message)


# ---------- 모으기 봉투 (25번에서 내역 → 목표 → AI 계획 요약으로 다듬는다) ----------

def render_save():
    detail_header("SAVE")
    ui.section(f"모으기 목표: {goal['item']}")
    with ui.card("goal"):
        st.progress(envelope.goal_progress_pct(balance["SAVE"], goal["amount"]) / 100)
        st.write(f"{won(goal['amount'])} 중 **{won(balance['SAVE'])}** 모았어요. "
                 f"남은 돈은 {won(max(0, goal['amount'] - balance['SAVE']))}이에요.")
    ui.section("모으기 내역")
    with ui.card("save-history"):
        history_table("SAVE")


# ---------- 투자연습 봉투 (26번에서 실전 준비 자금 봉투로 바꾼다) ----------

def render_invest():
    detail_header("INVEST")
    with ui.card("invest-about"):
        if config.INVEST_CONSENT_TRACK:
            st.write("투자 탭의 연습 모드는 가상 투자금으로 연습해요. 부모님이 동의해서 실전 모드가 열리면, "
                     "실전 주문 금액은 이 봉투에서 이체돼요 (부모님이 정한 한 달 한도 안에서).")
            ui.service_row(ui.MARKET, "📈", "투자 탭으로 가기", "연습 모드는 누구나 · 실전은 부모님 동의로",
                           key="invest-market")
        else:
            st.write("투자연습 화면은 가상 투자금으로 연습해요. 이 봉투에 쌓인 돈은 따로 모아 두는 돈이에요.")
            ui.service_row(ui.UNLOCK, "🪜", "실전 준비 단계 보기", "연습 과정을 채우면 다음 단계가 열려요",
                           key="invest-unlock")
            ui.service_row(ui.MARKET, "📈", "투자연습하러 가기", "가상 투자금으로 사고팔며 일지 쓰기",
                           key="invest-market")
    ui.section("쌓인 내역")
    with ui.card("invest-history"):
        history_table("INVEST")


# ---------- 체크카드 추천 (14번, 쓰기 봉투 안) ----------

@st.cache_data
def card_photo_src(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


@st.cache_data
def is_portrait(path):
    with Image.open(path) as image:
        return image.height > image.width


def card_art(card, small=False):
    """실제 카드 사진. 사진이 없으면 카드 모양 그래픽 (색은 style.css의 tone 클래스).
    작은 사진은 모두 같은 가로 카드 크기로: 세로 카드는 눕혀서 보여 준다."""
    photo = cards.image_path(card)
    if photo:
        src = card_photo_src(str(photo))
        if not small:
            return f"<img class='card-photo' src='{src}' alt='{card['name']}'>"
        turn = " card-thumb-turn" if is_portrait(str(photo)) else ""
        return f"<div class='card-thumb'><img class='card-photo{turn}' src='{src}' alt='{card['name']}'></div>"
    size = " card-art-sm" if small else ""
    short = card["name"].replace("카드의정석 ", "")
    return (f"<div class='card-art tone-{card['tone']}{size}'><div class='card-art-issuer'>{card['issuer']}</div>"
            f"<div class='card-art-chip'></div><div class='card-art-name'>{short}</div></div>")


def man_won(amount):
    """243400 → '24.3만 원' (좁은 칸에 한 줄로 들어가게)."""
    return f"{amount / 10000:.1f}".rstrip("0").rstrip(".") + "만 원"


def value(result):
    return f"{result['benefit']:,}{result['card']['unit']}"


def render_cards():
    results = cards.compare(cards.load_cards(), allowance, student_id)
    best = results[0]
    with ui.card("card-best"):
        if best["benefit"] > 0:
            ui.muted("이번 달 내 지출로 계산하면 혜택이 가장 큰 카드예요")
            st.markdown(card_art(best["card"]), unsafe_allow_html=True)
            st.markdown(f"**{best['card']['name']}**  \n{best['card']['tagline']}")
            st.metric("이번 달 예상 혜택", value(best))
        else:
            st.write("지금 소비로는 어느 카드도 혜택이 거의 없어요.")
        st.info("혜택을 받으려고 더 쓰면 손해예요. 필요한 지출에서만 챙겨요.")

        for result in results[1:]:
            card = result["card"]
            art, text = ui.columns(2, key=f"card-row-{card['card_id']}")
            art.markdown(card_art(card, small=True), unsafe_allow_html=True)
            reason = (card["tagline"] if result["tier_met"]
                      else f"실적 {man_won(result['min_spend'])}부터 · {man_won(result['gap'])} 부족")
            text.markdown(f"**{card['name']}**  \n{value(result)}")
            text.markdown(f"<div class='fineprint'>{reason}</div>", unsafe_allow_html=True)

        with st.expander("자세히 보기"):
            st.write(f"이번 달 실적 인정 금액은 **{won(best['performance'])}**이에요 (버스카드 충전은 실적·혜택에서 빠져요).")
            for result in results:
                card = result["card"]
                if result["tier_met"]:
                    detail = (f"특별 {result['special']:,}{card['unit']} + 기본 {result['base']:,}{card['unit']}"
                              if card["rules"] and card["base_rate"] else f"{value(result)}")
                else:
                    detail = f"실적 조건 미달 → 기본 적립 {result['base']:,}{card['unit']}만"
                st.markdown(f"- **{card['name']}** · {card['tagline']} → {detail}"
                            + (" · 한도 확인 필요" if card["caps_unknown"] else ""))
            stretch = [r for r in results if not r["tier_met"] and cards.max_special_if_met(r["card"])]
            if stretch:
                r = max(stretch, key=lambda r: cards.max_special_if_met(r["card"]))
                st.warning(f"{r['card']['name']} 실적 {won(r['min_spend'])}을 채우려면 {won(r['gap'])}을 더 써야 하지만, "
                           f"늘어나는 혜택은 최대 {cards.max_special_if_met(r['card']):,}{r['card']['unit']}이에요. "
                           "혜택보다 더 쓰는 돈이 훨씬 커요.")
            peer = cards.peer_comparison(allowance, student_id, student["gender"])
            if peer:
                more = "더 자주" if peer["diff"] > 0 else "덜"
                st.write(f"또래(같은 성별, 20세 미만)보다 편의점을 {more} 이용해요: 내 결제의 {peer['mine']:.0f}% · "
                         f"또래 {peer['peer']:.0f}%")

        sources = " · ".join(sorted({c["source"].split(" (")[0] for c in (r["card"] for r in results)}))
        st.markdown(f"<div class='fineprint'>가입 권유 아님 · 1P=1원으로 비교 · 데이터에 없는 혜택(배달·쇼핑앱 등) 제외 · "
                    f"출처: {sources} · 확인 {best['card']['checked']} · 발급 가능 여부·최신 조건은 우리카드에서 확인</div>",
                    unsafe_allow_html=True)


# ---------- 화면 고르기 ----------

if "envelope_message" in st.session_state:
    st.toast(st.session_state.pop("envelope_message"), icon=":material/check_circle:")

view = st.query_params.get("env")
{"SPEND": render_spend, "SAVE": render_save, "INVEST": render_invest}.get(view, render_overview)()
