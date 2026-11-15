"""설정은 이 파일 한 곳에서만 정한다."""

# LLM 모델명 (CLAUDE.md 2번: 여기서만 바꾼다). 수업 지원 OpenAI 키(한도 $80).
# 2026-11-13: 문장 품질 때문에 gpt-6-luna(최저가) → gpt-6.1-terra → 최고급 gpt-6-astra (한 번 약 5센트, $80로 약 1,400번)
MODEL_NAME = "gpt-6-astra"
# 짧은 문장 한두 개만 쓰므로 깊게 생각할 필요가 없다. astra는 "none"이 없어 가장 낮은 "low"
REASONING_EFFORT = "low"

# LLM 응답을 기다리는 최대 시간(초). 넘으면 "AI가 바빠요" 안내 후 멈춘다 (자동 재시도 없음)
LLM_TIMEOUT_SECONDS = 45  # astra로 주간 카드뉴스가 약 20초

# 시연 모드: AI가 이 시간(초) 안에 답하지 않거나 실패하면 저장된 응답을 바로 보여 준다
DEMO_TIMEOUT_SECONDS = 12  # astra 보통 2.5~5초
DEMO_MODE_DEFAULT = False

# 투자 탭 동의 기반 2트랙 (2026-11-13, 시뮬레이션 · invest/tintin_invest_handoff/INVEST_TAB_SPEC.md, 명세의 consentTrack)
# True: 연습 모드(누구나, 가상 머니) + 실전 모드(부모 동의 + 계좌 연결, Mock 증권사). 레벨은 투자 진입·한도·범위와 무관.
# False: 예전 가상 주식 연습 화면과 레벨(실전 준비 단계) 기반 동작 (legacy/market_v1_page.py)
INVEST_CONSENT_TRACK = True

# 투자 탭 연습 모드 시세: "scenario"(가상 종목, 민지 시연용) 또는 "real"(공공데이터포털 실제 종가)
PRICE_MODE_DEFAULT = "scenario"
QUOTE_CACHE_SECONDS = 300        # 같은 시세를 다시 부르지 않고 재사용하는 시간
QUOTE_HISTORY_DAYS = 45          # 급등 추격 판단 등에 쓸 지난 일별 종가 기간(달력 기준)
QUOTE_HTTP_TIMEOUT_SECONDS = 10
# 실제 시세 모드의 가상 투자금. 실제 주가는 시나리오보다 비싸서(SK하이닉스 1주 약 126만 원) 따로 둔다.
# 시나리오 모드는 students.json의 virtual_cash(100만 원) 그대로 (민지 시연 기록이 그 기준이라서).
REAL_VIRTUAL_CASH = 2_000_000

# 미션 탭 (2026-11-10, 시뮬레이션 · teen-app/MISSION_TAB_SPEC.md)
# True: 소비/투자 미션 (Replay → Simulation → 검증) · False: 예전 AI 코칭 루프 (legacy/mission_loop_page.py)
MISSION_TAB_V2 = True
# 투자 미션은 화면만 만들어 두고 잠근다 (모의투자 주문 로그·과거 시세 데이터가 아직 없음)
INVEST_MISSION_ENABLED = False

# 자산섬 게임 (2026-11-13, 시뮬레이션 · game/tintin_island_handoff/ISLAND_GAME_SPEC.md)
# True: 틴틴 자산섬 (내 섬 · 저축 밭 · 투자 과수원 · 소비 가방 · 상태창 · 주간 결산)
# False: 예전 자산 키우기 게임 (좋은 습관 단어 받기, legacy/catch_game_page.py)
ISLAND_GAME = True
# 자산섬 버전: 2 = 가상 섬 경제 게임 (game2/tintin_island_handoff, 1일차부터 생산·판매·거래·투자로 집 키우기)
#              1 = 실제 용돈·가상투자 기록을 섬으로 보여 주는 v1 (legacy/island_v1_page.py)
ISLAND_VERSION = 2

# 혜택 탭 돼지 저금통 (2026-11-13, 시뮬레이션 · point/tintin_piggy/PIGGY_BANK_SPEC.md, 명세의 piggyBank)
# True: '내 캐릭터(알 키우기 · 먹이 주기)' 대신 '내 돼지 저금통' (포인트 잔액 = 단계, 쓰면 내려감). 먹이 주기 없음.
# False: 예전 알 키우기 화면 (먹이 50P로 틴이 키우기)
PIGGY_BANK = True

# 앱 시작 스플래시 (2026-11-13, 시뮬레이션 · initiation/teengrow_splash/SPLASH_SPEC.md)
# True: 세션당 한 번 teengrow 로고 화면 → 약 2.5초 뒤 화면으로 (splash.py). False: 지금 앱과 똑같다.
SPLASH_ENABLED = True
SPLASH_TOTAL_MS = 2500    # 전체 노출 시간 (1500~4000 권장)
SPLASH_FADE_MS = 500      # 마지막 페이드아웃
SPLASH_REDUCED_MS = 1000  # '동작 줄이기' 사용자의 노출 시간

# ---------- 뉴스 카드·퀴즈 + 시세 자동 업데이트 + 실전 거래 UI (2026-11-16, 시뮬레이션 ·
#            invest & card_new/teengrow_news_market/NEWS_MARKET_SPEC.md) ----------
# 모두 False면 예전처럼: 이번 주 금융 뉴스(주 1회 카드뉴스) · 시세 5분 캐시 · 실전은 31번 화면.
NEWS_MARKET_FLAGS = {
    "autoUpdate": True,      # 정해진 시각이 지나면 앱을 열 때 시세·뉴스를 자동으로 다시 받는다
    "newsImages": True,      # 카드뉴스 키워드 일러스트 (assets/news_illustrations, 실제 뉴스 사진 아님)
    "newsStockLink": True,   # 기사에 이름이 나온 회사만 '뉴스 속 종목' 칩으로 잇는다
    "realTrading": True,     # 종목 상세의 [연습 | 실전] 전환과 실전 주문 확인·완료·차단 화면
}
# 오늘의 뉴스 (하루 3개). False면 예전 '이번 주 금융 뉴스' 화면 (legacy/weekly_news_page.py)
NEWS_DAILY = True

# 자동 업데이트 일정 (KST "HH:MM"). 첫 칸 = 정시, 나머지 = 재시도. 마지막 칸 뒤에는 RETRY_AFTER_LAST_MIN분마다 (앱을 열 때)
UPDATE_JOBS = {
    "news": {"slots": ["07:00", "07:30", "08:00", "09:00"], "business_days_only": False},
    "stock_eod": {"slots": ["13:30", "15:00", "17:00", "19:00"], "business_days_only": True},
}
RETRY_AFTER_LAST_MIN = 60

# 실전 시세 출처: "eod" = 지금 (공공데이터 전 영업일 종가, 연습과 같은 값으로 체결)
#                 "broker" = 나중 (증권사 실시간 30초 갱신, 장중에만 주문). 어댑터 없이 바꾸면 오류로 막힌다
REAL_QUOTE_SOURCE = "eod"
REALTIME_QUOTE_INTERVAL_SEC = 30
REALTIME_QUOTE_STALE_SEC = 60
BROKER_FEE_RATE = 0.0015   # Mock 체결 수수료 (실제 증권사 요율로 맞추는 설정값)

# 오늘의 뉴스 고르기
DAILY_NEWS_COUNT = 3
NEWS_LOOKBACK_DAYS = 7        # 정책브리핑은 주말에 기사가 거의 없고 금융 기사가 하루 몇 건뿐이라 최근 7일 (명세는 24시간)
NEWS_REUSE_BLOCK_DAYS = 3     # 최근 3일 안에 쓴 기사는 다시 고르지 않는다 (명세 7일이면 정책뉴스 후보가 주중에 바닥난다)
NEWS_TITLE_SIMILAR = 0.6      # 제목 낱말 겹침이 이 이상이면 같은 기사

# 뉴스 퀴즈 포인트 (기존 하루 200P 상한 안에서 적립)
NEWS_QUIZ_CORRECT_POINTS = 10      # 문제당 (처음 풀어 맞힌 것만)
NEWS_QUIZ_ALL_DONE_BONUS = 20      # 오늘 3문제 모두 풀면
NEWS_REVIEW_CORRECT_POINTS = 10    # 주말 복습 퀴즈 문제당
NEWS_REVIEW_COUNT = 5              # 주말 복습: 오답노트 + 단어 문제

