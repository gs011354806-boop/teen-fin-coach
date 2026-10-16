"""용돈봉투 화면. 입출금 형식은 우리은행 청소년 마이데이터를 가정한다."""

import base64
from pathlib import Path

import pandas as pd
from PIL import Image
import streamlit as st

import ui_common as ui
from engine import cards, envelope, store
from ui_common import won

ENVELOPE_LABELS = {"SPEND": "쓰기", "SAVE": "모으기", "INVEST": "투자연습"}
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

ui.app_bar("용돈봉투", badge="가상 용돈 기록")
ui.muted(f"{today} 기준 · 데모용 가상 내역이에요.")

if "envelope_message" in st.session_state:
    st.success(st.session_state.pop("envelope_message"))

with ui.card("balances"):
    for column, name in zip(ui.columns(3, key="balances"), envelope.ENVELOPES):
        column.metric(f"{ENVELOPE_LABELS[name]} 봉투", won(balance[name]))

ui.section(f"모으기 목표: {goal['item']}")
with ui.card("goal"):
    st.progress(envelope.goal_progress_pct(balance["SAVE"], goal["amount"]) / 100)
    st.write(f"{won(goal['amount'])} 중 **{won(balance['SAVE'])}** 모았어요.")

ui.section("용돈 받기")
with ui.card("deposit"):
    weekly = student["weekly_allowance"]
    split = envelope.split_allowance(weekly, ratio)
    ui.muted("이번 용돈은 이렇게 나뉘어요: "
             + " · ".join(f"{ENVELOPE_LABELS[name]} {won(split[name])}" for name in envelope.ENVELOPES))
    if st.button(f"용돈 {won(weekly)} 받기", type="primary", width="stretch"):
        store.append_allowance(student_id, today, envelope.deposit_entries(weekly, ratio))
        st.session_state["envelope_message"] = f"용돈 {won(weekly)}을 봉투에 나눠 담았어요."
        st.rerun()

ui.section("용돈 나누는 비율")
with ui.card("ratio"):
    with st.form("ratio", border=False):
        inputs = {}
        for column, name in zip(ui.columns(3, key="ratio"), envelope.ENVELOPES):
            inputs[name] = column.number_input(f"{ENVELOPE_LABELS[name]} (%)", min_value=0,
                                               max_value=100, value=ratio[name], step=5)
        ratio_submitted = st.form_submit_button("비율 저장", width="stretch")

if ratio_submitted:
    new_ratio = {name: int(value) for name, value in inputs.items()}
    error = envelope.check_ratio(new_ratio)
    if error:
        st.error(error)
    else:
        store.save_envelope_ratio(student_id, new_ratio)
        st.session_state["envelope_message"] = "비율을 저장했어요. 다음 용돈부터 이렇게 나눠요."
        st.rerun()

ui.section("이번 달 가장 많이 쓴 곳은?")
with ui.card("spending"):
    spent = envelope.spending(allowance, student_id)
    if len(spent):
        by_category = envelope.spending_by_category(allowance, student_id)
        st.bar_chart(pd.Series({CATEGORY_LABELS[c]: total for c, total in by_category.items()},
                               name="쓴 돈(원)"), height=220)
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
            store.load_concepts()["NEEDS_VS_WANTS"], key="envelope",
            intro=(f"알아 두면 좋은 개념 · 이번 달 지출 중 편의점·카페·디저트가 {share:.0f}%예요"
                   if share is not None else "알아 두면 좋은 개념"))

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

ui.section("내 소비에 맞는 체크카드")


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
