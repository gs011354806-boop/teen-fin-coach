"""틴 금융코치 홈. 실행: streamlit run app.py

우리은행 앱 안에 붙는 추가 서비스처럼 보이게 만든 데모 첫 화면.
"""

import config
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
                                                     store.load_missions(), allowance,
                                                     store.load_game_reviews(), store.load_news_quiz(), store.load_spend_quiz(), store.load_mission_runs()))
points = rewards.balance(events, spends, student_id)
stage_name = rewards.stage(rewards.feed_count(spends, student_id))[0]
save_balance = envelope.balances(allowance, student_id)["SAVE"]
stage = unlock.stage(store.load_unlocks(), student_id)
unlock_title = "연습 습관 단계" if config.INVEST_CONSENT_TRACK else "실전 준비 단계"

ui.app_bar(f"안녕, {student['name']}!", badge="우리틴틴 추가 서비스", back=False)

# 틴이 말풍선: 이번 주 연습할 것 (없으면 첫 주 진단으로 안내)
if practice:
    ui.mascot_say(f"이번 주엔 '{' · '.join(mission.practice_label(k) for k in practice)}'를 연습해 봐요!",
                  key="coach", page=ui.MISSION, cta="이번 주 미션 보기")
else:
    ui.mascot_say("이번 주엔 첫 진단부터 해 볼까요? 나에게 맞는 미션을 정해 줄게요!",
                  key="coach", page=ui.MISSION, cta="진단 시작하기")

with ui.tile_grid():
    ui.tile(ui.ENVELOPE, "✉️", "용돈봉투", f"모으기 {ui.won(save_balance)}", "orange", key="envelope")
    ui.tile(ui.MISSION, "🎯", "이번 주 미션", "진단 → 미션 → 돌아보기", "blue", key="mission")
    ui.tile(ui.NEWS, "📰", "금융 뉴스", "오늘의 뉴스 3개 · 퀴즈" if config.NEWS_DAILY else "카드 3장 · 퀴즈", "violet", key="news")
    ui.tile(ui.GAME, "🧺", "자산섬", "내 습관이 자라는 섬 게임", "green", key="game")

ui.section("더 해 보기")
with ui.card("services"):
    ui.service_row(ui.MARKET, "📈", "투자", "연습 모드는 누구나 · 실전은 부모님 동의로", key="market")
    ui.service_row(ui.LESSON, "🔍", "실수에서 배우기",
                   f"다시 볼 매수 {len(moments)}건 · AI 코치와 돌아보기" if moments else "AI 코치와 그때의 판단 돌아보기",
                   key="lesson")
    ui.service_row(ui.ASK, "💬", "개념 물어보기", "궁금한 금융 단어를 AI 코치에게", key="ask")
    ui.service_row(ui.UNLOCK, "🔓", unlock_title, f"지금 {stage}단계 · {unlock.names()[stage]}", key="unlock")
    ui.service_row(ui.MYDATA, "🔗", "마이데이터 연결", "용돈·카드 정보로 나에게 맞는 연습 정하기 (예시)", key="mydata")

ui.section("혜택과 보호자")
with ui.card("benefits"):
    if config.PIGGY_BANK:
        ui.service_row(ui.REWARDS, "🐷", "포인트와 돼지 저금통",
                       f"내 포인트 {points:,}P · {rewards.level_of(points)['name']}", key="rewards")
    else:
        ui.service_row(ui.REWARDS, "🐣", "포인트와 캐릭터", f"내 포인트 {points:,}P · 틴이 {stage_name} 단계",
                       key="rewards")
    ui.service_row(ui.REWARDS, "🎟️", "포인트 상점", "편의점·문화상품권 가상 쿠폰 교환", key="shop")
    ui.service_row(ui.PARENT, "👪", "보호자 리포트", "저축률·미션 수행률 변화와 이번 달 부모 미션",
                   key="parent")

ui.muted("데모용 가상 데이터예요. 실제 돈과 실제 시세가 아니에요.")
