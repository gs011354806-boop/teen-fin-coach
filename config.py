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

