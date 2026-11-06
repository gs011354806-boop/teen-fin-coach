"""행동 기반 포인트 → 캐릭터 먹이 주기 → 가상 쿠폰 교환."""

import pandas as pd
import streamlit as st

import ui_common as ui
from engine import envelope, rewards, store

STAGE_ICONS = {"알": "🥚", "아기": "🐣", "청소년": "🐥", "어른": "🐔"}

student = ui.setup("혜택", "🐣", active="rewards")
student_id = student["student_id"]
allowance = store.load_allowance()
today = envelope.latest_date(allowance)
events = rewards.apply_daily_cap(rewards.earn_events(
    student, store.load_trades(), store.load_missions(), allowance, store.load_game_reviews()))
spends = store.load_spends()
points = rewards.balance(events, spends, student_id)
feeds = rewards.feed_count(spends, student_id)
coupons = {c["item"]: c for c in rewards.COUPONS}


def spend(kind, item, cost):
    """버튼 콜백: 스크립트가 다시 그려지기 전에 한 번만 실행된다 (st.rerun 없이)."""
    error = rewards.check_spend(cost, points)
    if error:
        st.session_state["reward_error"] = error
        return
    store.append_spend(student_id, today, kind, item, cost)
    st.session_state["reward_message"] = "냠냠! 먹이를 줬어요."


def coupon_card(coupon, small=False):
    """쿠폰 그림: 특정 회사 로고 없이 카드로 그린다. 모양은 style.css의 .coupon"""
    size = " coupon-sm" if small else ""
    return (f"<div class='coupon tone-{coupon['tone']}{size}'>"
            f"<div class='coupon-icon'>{coupon['icon']}</div>"
            f"<div class='coupon-shop'>{coupon['shop']}"
            f"{'' if small else '<br>모바일 금액권 · 데모'}</div>"
            f"<div class='coupon-face'>{coupon['face']:,}원</div></div>")


def open_coupon(item):
    st.session_state["coupon_view"] = item
    st.session_state["coupon_qty"] = 1


def close_coupon():
    st.session_state.pop("coupon_view", None)


def exchange(item, qty):
    """버튼 콜백: 수량만큼 한 번에 교환한다. 포인트가 모자라면 아무것도 저장하지 않는다."""
    coupon = coupons[item]
    error = rewards.check_spend(rewards.coupon_total(coupon, qty), points)
    if error:
        st.session_state["reward_error"] = error
        return
    for _ in range(qty):
        store.append_spend(student_id, today, "COUPON", item, coupon["points"])
    st.session_state["reward_message"] = f"{item} {qty}장(가상)을 쿠폰함에 넣었어요."
    close_coupon()


ui.app_bar("혜택", badge="행동 포인트")
ui.muted("포인트는 행동으로만 모여요. 투자 결과나 쓴 돈의 크기와는 상관없고, 현금으로 바꿀 수 없어요.")

if "reward_message" in st.session_state:
    st.success(st.session_state.pop("reward_message"))
if "reward_error" in st.session_state:
    st.error(st.session_state.pop("reward_error"))

with ui.card("points"):
    col_points, col_today = ui.columns(2, key="points")
    col_points.metric("내 포인트", f"{points:,}P")
    today_capped = sum(e["granted"] for e in events if e["date"] == today and e["capped"])
    col_today.metric("오늘 받은 포인트", f"{today_capped}P / {rewards.DAILY_CAP}P")

ui.section("내 캐릭터")
with ui.card("character"):
    name, next_name, left = rewards.stage(feeds)
    icon_col, info_col = ui.columns(2, key="character")
    icon_col.markdown(f"<div class='character'>{STAGE_ICONS[name]}</div>", unsafe_allow_html=True)
    info_col.write(f"지금은 **{name}** 단계예요. 지금까지 먹이를 {feeds}개 먹었어요.")
    if next_name:
        need = dict(rewards.STAGES)[next_name] - dict(rewards.STAGES)[name]
        info_col.progress((need - left) / need)
        info_col.write(f"먹이를 {left}개 더 주면 **{next_name}**(으)로 자라요.")
    else:
        info_col.write("다 자랐어요! 앞으로도 함께해요.")
    ui.muted("미션을 못 한 주에도 캐릭터는 아프지 않아요. 기다려 줄 뿐이에요.")
    st.button(f"먹이 주기 ({rewards.FEED_COST}P)", on_click=spend, width="stretch",
              args=("FEED", "먹이", rewards.FEED_COST))

ui.section("포인트 상점")
viewing = st.session_state.get("coupon_view")
if viewing not in coupons:
    with ui.card("shop"):
        ui.muted("데모용 가상 쿠폰이에요. 실제로 발급되거나 사용할 수 없어요.")
        for coupon in coupons.values():
            card_col, info_col = ui.columns(2, key=f"shop-{coupon['face']}")
            card_col.markdown(coupon_card(coupon, small=True), unsafe_allow_html=True)
            info_col.write(f"**{coupon['item']}**  \n{coupon['points']:,}P")
            info_col.button("자세히 보기", key=f"view-{coupon['item']}", on_click=open_coupon,
                            args=(coupon["item"],))
else:
    coupon = coupons[viewing]
    st.button("← 상점으로", on_click=close_coupon)
    with ui.card("coupon-detail"):
        st.markdown(coupon_card(coupon), unsafe_allow_html=True)
        st.markdown(f"{coupon['icon']} **{coupon['shop']}**")
        st.markdown(f"### {coupon['item']}")
        st.markdown(f"## {coupon['points']:,}P")
        st.divider()
        st.markdown(f"**교환권** &nbsp; 금액권 (데모용 가상 쿠폰)  \n"
                    f"**유효기간** &nbsp; 교환일부터 {rewards.COUPON_VALID_DAYS}일 (가상)  \n"
                    "**사용처** &nbsp; 실제 매장에서 사용할 수 없어요", unsafe_allow_html=True)

    with ui.card("coupon-order"):
        qty = int(st.number_input("수량", min_value=1, max_value=rewards.MAX_COUPON_QTY, step=1,
                                  key="coupon_qty"))
        ui.muted("🚨 포인트는 현금으로 바꿀 수 없어요. 누군가 포인트나 쿠폰을 대신 써 달라고 하면 "
                 "꼭 보호자와 먼저 이야기해 주세요.")
        total = rewards.coupon_total(coupon, qty)
        count_col, total_col = ui.columns(2, key="total")
        count_col.markdown(f"**총 {qty}개**")
        total_col.markdown(f"<div class='price-total'>필요 포인트 <b>{total:,}P</b></div>",
                           unsafe_allow_html=True)
        lacking = rewards.check_spend(total, points)
        if lacking:
            st.warning(lacking)
        st.button("나에게 교환하기", type="primary", width="stretch",
                  disabled=lacking is not None, on_click=exchange, args=(coupon["item"], qty))

my_coupons = spends[(spends["student_id"] == student_id) & (spends["kind"] == "COUPON")]
if len(my_coupons):
    with st.expander(f"내 쿠폰함 ({len(my_coupons)}장)"):
        for column, c in zip(ui.columns(2, key="box") * len(my_coupons), my_coupons.itertuples()):
            if c.item in coupons:
                column.markdown(coupon_card(coupons[c.item], small=True), unsafe_allow_html=True)
            column.caption(f"{c.item} · {c.date} 교환 · 사용 불가")

ui.section("포인트 받는 방법")
with ui.card("how"):
    st.markdown(
        f"- 이번 주 미션을 해내면 미션 1개에 **{rewards.MISSION_POINTS}P** (모으기 미션 포함)\n"
        f"- 근거를 10자 이상 적은 투자 일지 1건에 **{rewards.JOURNAL_POINTS}P** "
        "(대충 쓴 일지는 포인트가 없어요)\n"
        f"- 저축 목표 금액을 다 모은 날 **{rewards.GOAL_BONUS_POINTS}P**\n"
        f"- 미션과 일지 포인트는 하루 **{rewards.DAILY_CAP}P**까지 모여요")

ui.section("받은 포인트 기록")
with ui.card("history"):
    if events:
        st.dataframe(pd.DataFrame({
            "날짜": [e["date"][5:] for e in reversed(events)],
            "내용": [e["label"] for e in reversed(events)],
            "포인트": [f"+{e['granted']}P" + ("" if e["granted"] == e["points"] else " (상한)")
                    for e in reversed(events)],
        }), hide_index=True, width="stretch")
    else:
        st.info("아직 받은 포인트가 없어요. 이번 주 미션부터 시작해 볼까요?")
