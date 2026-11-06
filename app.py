"""틴 금융코치 홈. 실행: streamlit run app.py

우리은행 앱 안에 붙는 추가 서비스처럼 보이게 만든 데모 첫 화면.
"""

import ui_common as ui
from engine import detect, envelope, mission, rewards, store, unlock

student = ui.setup("틴 금융코치", "🌱", active="home")
student_id = student["student_id"]

coaching = store.load_coaching()
mine = coaching[coaching["student_id"] == student_id]
practice = mine.iloc[-1]["practice"].split("|") if len(mine) else []
market = ui.market_context(student)
moments = detect.mistakes(detect.detect(market["trades"], market["prices"], market["student"]))
allowance = store.load_allowance()
spends = store.load_spends()
events = rewards.apply_daily_cap(rewards.earn_events(student, store.load_trades(),
                                                     store.load_missions(), allowance))
points = rewards.balance(events, spends, student_id)
stage_name = rewards.stage(rewards.feed_count(spends, student_id))[0]
save_balance = envelope.balances(allowance, student_id)["SAVE"]
stage = unlock.stage(store.load_unlocks(), student_id)

ui.app_bar("틴 금융코치", badge="우리틴틴 추가 서비스", back=False)
ui.muted(f"{student['name']} 님, 이번 주도 한 걸음씩 연습해 봐요.")

with ui.card("start"):  # 흐름의 시작: 마이데이터로 나에게 맞는 연습 정하기
    ui.service_row(ui.MYDATA, "🔗", "마이데이터 연결하고 시작하기", "용돈·카드 정보로 나에게 맞는 연습 정하기 (예시)",
                   key="mydata")

ui.section("이번 주 나의 코칭")
with ui.hero_strip():
    ui.hero_card(ui.MISSION, "green", "이번 주 연습할 것",
                 " · ".join(mission.practice_label(k) for k in practice) if practice else "첫 주 진단 받으러 가기", "🌱", key="mission")
    ui.hero_card(ui.LESSON, "violet", "실수에서 배우기",
                 f"다시 볼 매수 {len(moments)}건" if moments else "다시 볼 매수가 없어요",
                 "🔍", key="lesson")

ui.section("서비스 둘러보기")
with ui.card("services"):
    ui.service_row(ui.MARKET, "📈", "가상 주식 연습", "투자 일지를 쓰며 사고팔아 보기", key="market")
    ui.service_row(ui.GAME, "🧺", "자산 키우기 게임", "좋은 습관만 바구니에 담기 · AI 코치", key="game")
    ui.service_row(ui.ENVELOPE, "✉️", "용돈봉투",
                   f"모으기 봉투 {ui.won(save_balance)} · {student['saving_goal']['item']} 목표", key="envelope")
    ui.service_row(ui.LESSON, "🔍", "실수에서 배우기", "AI 코치와 그때의 판단 돌아보기", key="lesson")
    ui.service_row(ui.MISSION, "🎯", "이번 주 미션", "진단 → 미션 → 주말 Replay", key="mission")
    ui.service_row(ui.ASK, "💬", "개념 물어보기", "궁금한 금융 개념을 AI 코치에게", key="ask")
    ui.service_row(ui.UNLOCK, "🔓", "실전 준비 단계", f"지금 {stage}단계 · {unlock.STAGES[stage]}", key="unlock")

ui.section("혜택 둘러보기")
with ui.card("benefits"):
    ui.service_row(ui.REWARDS, "🐣", "포인트와 캐릭터", f"내 포인트 {points:,}P · 캐릭터 {stage_name} 단계",
                   key="rewards")
    ui.service_row(ui.REWARDS, "🎟️", "포인트 상점", "편의점·문화상품권 가상 쿠폰 교환", key="shop")

ui.section("보호자")
with ui.card("parent"):
    ui.service_row(ui.PARENT, "👪", "보호자 리포트", "저축률·미션 수행률 변화와 이번 달 부모 미션",
                   key="parent")

ui.muted("데모용 가상 데이터예요. 실제 돈과 실제 시세가 아니에요.")
