"""가상 주식시장 + 투자 일지 화면.

시세 종류: 시나리오(가상 종목, 기본) / 실제 시세(공공데이터포털 종가). 거래는 어느 쪽이든 가상 투자금으로만 한다.
"""

import pandas as pd
import streamlit as st

import ui_common as ui
from engine import portfolio, quotes, store
from ui_common import won

SIDE_LABELS = {"BUY": "매수", "SELL": "매도"}

student = ui.setup("가상 주식 연습", "📈", active="market")
student_id = student["student_id"]

market = ui.market_context()
names, prices, trades = market["names"], market["prices"], market["trades"]
today = portfolio.latest_date(prices)
closes = portfolio.close_on(prices, today)
held = portfolio.holdings(trades, student_id)
cash = portfolio.cash_balance(student["virtual_cash"], trades, student_id)
positions = portfolio.position_rows(held, cash, closes)
stock_value = sum(p["value"] for p in positions)

ui.app_bar("가상 주식 연습", badge="실제 시세 · 가상 거래" if market["mode"] == "real" else "연습용 가상 시세")
ui.price_mode_switch()
quote = market["quote"]
if quote and quote["message"]:
    st.warning(quote["message"])
if market["mode"] == "real":
    fetched = quote["fetched_at"].strftime("%m/%d %H:%M")
    market_state = "장중" if quote["market_open"] else "장 마감"
    ui.muted(f"{today} 종가 기준 (마지막 가격) · 지금은 {market_state} · 시세 확인 {fetched} · "
             "하루 늦게 갱신돼요. 거래는 가상 투자금으로만 해요.")
    ui.muted(f"출처: {quotes.SOURCE}")
else:
    ui.muted(f"{today} 기준 · 실제 시세가 아니에요.")

if "order_message" in st.session_state:
    st.success(st.session_state.pop("order_message"))

with ui.card("assets"):
    st.metric("총자산", won(cash + stock_value))
    col_cash, col_stock = ui.columns(2, key="assets")
    col_cash.metric("가상 현금", won(cash))
    col_stock.metric("주식 평가금액", won(stock_value))

ui.section("종목 고르기")
with ui.card("stock"):
    ticker = st.selectbox("종목", list(names), format_func=lambda t: f"{names[t]} ({t})")
    price = closes[ticker]
    change = portfolio.day_change_pct(prices[ticker], today)
    st.metric(f"{names[ticker]} 현재가", won(price),
              delta=None if change is None else f"{change:+.1f}% (전 거래일 대비)")
    st.line_chart(prices[ticker].set_index("date")["close"], height=200)

ui.section("주문하기")
with ui.card("order"):
    st.write(f"지금 **{names[ticker]}** {held.get(ticker, 0)}주를 갖고 있어요.")
    with st.form("order", clear_on_submit=True, border=False):
        side = st.radio("무엇을 할까요?", list(SIDE_LABELS), format_func=SIDE_LABELS.get,
                        horizontal=True)
        qty = st.number_input("수량 (주)", min_value=1, value=1, step=1)
        journal = st.text_area("투자 일지: 왜 이렇게 하려고 하나요?",
                               placeholder="안 적어도 주문할 수 있어요.")
        submitted = st.form_submit_button("주문 넣기", type="primary", width="stretch")

if submitted:
    error = portfolio.check_order(side, int(qty), price, cash, held.get(ticker, 0))
    if error:
        st.error(error)
    else:
        store.append_trade(student_id, today, ticker, side, int(qty), price, journal,
                           path=market["trades_path"], prefix=market["prefix"])
        st.session_state["order_message"] = (
            f"{names[ticker]} {int(qty)}주 {SIDE_LABELS[side]} 완료 ({won(int(qty) * price)})")
        st.rerun()

ui.section("보유 현황")
with ui.card("holdings"):
    if positions:
        st.dataframe(
            pd.DataFrame({
                "종목": [names[p["ticker"]] for p in positions],
                "수량": [f"{p['qty']}주" for p in positions],
                "평가금액": [won(p["value"]) for p in positions],
                "비중": [f"{p['weight_pct']:.0f}%" for p in positions],
            }),
            hide_index=True, width="stretch")
        ui.muted("비중은 총자산(주식 + 현금) 대비예요.")
    else:
        st.info("아직 가진 종목이 없어요.")

ui.section("내 거래와 일지")
with ui.card("journal"):
    mine = trades[trades["student_id"] == student_id].iloc[::-1]
    if len(mine):
        st.dataframe(
            pd.DataFrame({
                "날짜": [d[5:] for d in mine["date"]],
                "종목": [names[t] for t in mine["ticker"]],
                "구분": mine["side"].map(SIDE_LABELS),
                "수량": [f"{q}주" for q in mine["qty"]],
                "일지": [j if j else "(안 적음)" for j in mine["journal"]],
            }),
            hide_index=True, width="stretch")
    else:
        st.info("아직 거래가 없어요.")

with ui.card("lesson-link"):
    ui.service_row(ui.LESSON, "🔍", "실수에서 배우기", "AI 코치와 그때의 판단 돌아보기", key="lesson")
