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

# 투자연습 시세: "scenario"(가상 종목, 민지 시연용) 또는 "real"(공공데이터포털 실제 종가)
PRICE_MODE_DEFAULT = "scenario"
QUOTE_CACHE_SECONDS = 300        # 같은 시세를 다시 부르지 않고 재사용하는 시간
QUOTE_HISTORY_DAYS = 45          # 급등 추격 판단 등에 쓸 지난 일별 종가 기간(달력 기준)
QUOTE_HTTP_TIMEOUT_SECONDS = 10
# 실제 시세 모드의 가상 투자금. 실제 주가는 시나리오보다 비싸서(SK하이닉스 1주 약 126만 원) 따로 둔다.
# 시나리오 모드는 students.json의 virtual_cash(100만 원) 그대로 (민지 시연 기록이 그 기준이라서).
REAL_VIRTUAL_CASH = 2_000_000
