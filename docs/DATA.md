# 데이터 구조

모든 금액은 원 단위 정수. 날짜는 `YYYY-MM-DD` 문자열.

## data/students/students.json

```json
[{"student_id": "S01", "name": "민지", "grade": "중2", "type": "몰빵형",
  "weekly_allowance": 20000, "virtual_cash": 1000000,
  "envelope_ratio": {"SPEND": 50, "SAVE": 30, "INVEST": 20},
  "saving_goal": {"item": "에어팟", "amount": 250000}}]
```

- `type`: 몰빵형 / 저축 실패형 / 균형형
- `virtual_cash`: 가상투자 시작 금액(원). 용돈봉투의 INVEST와는 별개인 연습용 가상 돈이다.
- `envelope_ratio`: 용돈을 쓰기(SPEND)/모으기(SAVE)/투자연습(INVEST) 봉투에 나누는 비율(%). 정수, 합계 100. 용돈봉투 화면에서 바꾼다.
- 샘플 데이터는 `python data/make_sample_data.py`로 다시 만든다 (시드 고정, 기간 2026-09-07 ~ 2026-10-04).

## data/students/trades.csv (가상투자 거래)

| 컬럼 | 타입 | 예시 |
|---|---|---|
| trade_id | str | T0001 |
| student_id | str | S01 |
| date | str | 2026-10-05 |
| ticker | str | 005930 |
| side | str | BUY 또는 SELL |
| qty | int | 3 |
| price | int | 61000 |
| journal | str | 계속 오를 것 같아서 (빈 값 허용) |

## data/students/allowance.csv (용돈봉투 입출금, 우리은행 청소년 마이데이터 형식 가정)

| 컬럼 | 타입 | 예시 |
|---|---|---|
| tx_id | str | A0001 |
| student_id | str | S01 |
| date | str | 2026-10-06 |
| envelope | str | SPEND / SAVE / INVEST |
| amount | int | -4300 (출금은 음수) |
| category | str | CONVENIENCE / CAFE / FOOD / SHOPPING / TRANSPORT / OTHER |
| memo | str | 편의점 |

- 주간 용돈 입금은 봉투별로 한 줄씩, 양수 금액, category `OTHER`, memo `용돈 입금`.
- 입금액은 `envelope_ratio`대로 나눈다. 원 단위 나머지는 INVEST 봉투에 넣는다.
- 지출은 SPEND 봉투의 음수 금액만 센다. (SAVE에서 꺼낸 돈은 이동이지 지출이 아니다.)
- 용돈봉투 화면에서 넣는 입금의 날짜는 `allowance.csv`에 기록된 마지막 날짜다.
- 봉투 사이 이동은 두 줄로 적는다 (나가는 봉투 음수, 들어오는 봉투 양수, category `OTHER`).

## data/students/lessons.csv (Mistake-to-Lesson 기록)

5번 화면에서 학생이 답하면 한 줄씩 쌓인다. 8번 부모 리포트가 읽는다 (부모 화면에 `answer` 원문은 보여 주지 않는다).

| 컬럼 | 타입 | 예시 |
|---|---|---|
| lesson_id | str | L0001 |
| student_id | str | S01 |
| trade_id | str | T0014 (돌아본 매수) |
| date | str | 2026-10-02 (기록한 날: 데모의 "오늘" = 가격 데이터 마지막 거래일) |
| patterns | str | 몰빵\|근거 없음 (`\|`로 구분) |
| question | str | AI가 만든 질문 |
| answer | str | 학생 답 (줄바꿈은 공백으로) |
| error_type | str | FOMO / 과신 / 근거 부족 / 해당 없음 |
| reason | str | 분류 이유 1문장 (비어 있으면 AI 분류 실패로 기본값이 들어간 것) |
| concept | str | INVESTMENT_JOURNAL (`content/concepts`의 concept 값) |
| explanation | str | 개념 설명 |
| next_try | str | 다음에 해 볼 행동 |

- 같은 매수를 여러 번 돌아보면 여러 줄이 생긴다. 화면에는 그 매수의 가장 최근 기록을 보여 준다.

## data/students/real_trades.csv (실제 시세 모드의 가상 거래)

`trades.csv`와 같은 컬럼. 시나리오 거래와 섞이지 않게 따로 둔다. `trade_id`는 `R0001`부터 (5-1 기록의 trade_id가 겹치지 않게).
거래 날짜와 가격은 그 시점의 마지막 종가 기준일과 종가. 실제 주문은 없다.

## data/real/ (실제 시세)

- `watchlist.json`: 고정 종목 목록 `[{"ticker": "005930", "name": "삼성전자"}]`, 15개 이내. 설명은 `docs/STOCKS.md`.
- `quote_cache.json`: 마지막으로 받은 시세 (`{"fetched_at", "series": {코드: [{date, close}]}}`). 5분 안에는 다시 부르지 않고, API가 실패하면 이 값을 보여 준다. GitHub에 올리지 않는다.
- 시세 출처: 공공데이터포털 금융위원회_주식시세정보 `getStockPriceInfo` (하루 늦은 종가). 키는 `.env` / Streamlit Secrets의 `DATA_GO_KR_KEY`.

## data/students/missions.csv

| 컬럼 | 타입 | 예시 |
|---|---|---|
| mission_id | str | M0001 |
| student_id | str | S01 |
| week_start | str | 2026-10-05 |
| skill | str | 위험분산 |
| text | str | 한 종목 비중을 50% 아래로 낮추고 이유 적기 |
| target_metric | str | max_weight_pct |
| target_value | float | 50 |
| result_value | float | 45 (주말 Replay에서 채움) |
| done | bool | TRUE (주말 Replay 전에는 빈 값) |
| level | str | 쉬움 / 보통 / 어려움 (목표저축 미션은 빈 값) |

- `skill`: 위험분산 / 근거 적기 / 목표저축
- `target_metric`: `max_weight_pct`(주말 기준 가장 큰 종목 비중, 이하면 수행), `no_reason_buy_pct`(그 주 매수 중 일지 10자 미만 비율, 이하면 수행, 매수가 없으면 0), `save_net`(그 주 모으기 봉투 넣은 돈 − 꺼낸 돈, 이상이면 수행)
- 목표 숫자는 `engine/mission.py`가 정한다. LLM은 미션 문장만 쓴다.

## data/students/point_spend.csv (포인트 사용 기록)

받은 포인트는 저장하지 않는다. `engine/rewards.py`가 거래(일지)·미션·용돈 기록에서 매번 다시 계산한다. 이 파일에는 쓴 포인트만 쌓인다.

| 컬럼 | 타입 | 예시 |
|---|---|---|
| spend_id | str | P0001 |
| student_id | str | S01 |
| date | str | 2026-10-04 (데모의 "오늘" = 용돈 기록 마지막 날) |
| kind | str | FEED (캐릭터 먹이) / COUPON (가상 쿠폰 교환) |
| item | str | 먹이 / 편의점 1,000원권 |
| points | int | 50 |

- 포인트 값·하루 상한·캐릭터 단계·쿠폰 가격은 `engine/rewards.py` 맨 위 상수에서만 정한다.

## data/students/demo_responses.json (시연 모드 저장 응답)

시연 모드를 켜면 AI가 `config.DEMO_TIMEOUT_SECONDS`(8초) 안에 답하지 않거나 실패할 때 이 파일의 응답을 보여 준다. 없으면 기본 문구.
만드는 법: `python data/make_demo_responses.py` (실제 Gemini로 민지 시나리오를 돌려, 규칙 검사를 통과한 응답만 저장)

```json
{"model": "gemini-3.5-flash-lite",
 "students": {"S01": {
   "answers": {"T0014": "시연 때 학생 답 칸에 미리 채울 예시 답"},
   "responses": {
     "mistake_question": {"T0014": {"question": "..."}},
     "classify_mistake": {"T0014": {"error_type": "근거 부족", "reason": "..."}},
     "explain_concept":  {"T0014|근거 부족": {"explanation": "...", "next_try": "..."}},
     "diagnose_week":    {"2026-09-07": {"good": [...], "practice": [...], "summary": "..."}},
     "weekly_mission":   {"<목표 문구(goal phrase)>": {"text": "..."}},
     "replay_comment":   {"2026-09-14|FT": {"comment": "..."}}}}}}
```

- 분류·설명은 학생 답이 `answers`의 예시 답과 같을 때만 쓴다 (답이 다르면 기본 문구).
- `replay_comment` 키의 `FT`는 그 주 미션 순서대로 수행 여부(T/F). 결과가 다르면 쓰지 않는다.
- 저장 응답도 AI 응답과 같은 검사(존댓말·금지 표현·목표 숫자·후보 키워드)를 통과해야 화면에 나온다.

## data/students/coaching_weeks.csv (주차별 진단·대안 선택·Replay)

6번 화면이 한 주 사이클마다 한 줄씩 쓴다. 데모는 기존 4주 기록을 재생한다: `diag_week_start` 주 기록으로 진단 → `week_start` 주 미션 → 그 주 기록으로 Replay.

| 컬럼 | 타입 | 예시 |
|---|---|---|
| student_id | str | S01 |
| week_start | str | 2026-09-14 (미션 주) |
| diag_week_start | str | 2026-09-07 (진단에 쓴 주) |
| good | str | 꾸준히 모으기 (`\|`로 구분, 1~2개) |
| practice | str | 근거 없는 매수\|한 종목 쏠림 (1~2개) |
| summary | str | 진단 한 문장 |
| plan | str | A / B / C (고른 저축 대안) |
| plan_weekly_save | int | 6000 |
| goal_date_before | str | 2027-06-27 (계획할 때 저축 목표 달성 예상일, 닿지 않으면 빈 값) |
| replay_comment | str | Replay 해석 (Replay 전에는 빈 값) |
| goal_date_after | str | Replay 뒤 다시 계산한 예상일 |

## data/prices/<ticker>.csv

| 컬럼 | 타입 | 예시 |
|---|---|---|
| date | str | 2026-10-05 |
| close | int | 61000 |

## data/prices/tickers.json (종목명)

```json
[{"ticker": "005930", "name": "삼성전자"}]
```

- 화면에는 종목명을 먼저, 코드를 뒤에 보여 준다. 예: `삼성전자 (005930)`
- 가상투자 화면의 "오늘"은 가격 데이터의 마지막 거래일이다. 화면에서 넣은 주문은 그날 종가로 `trades.csv`에 추가된다.
- 처음에는 가상 가격 데이터로 시작한다. 실제 데이터는 공공데이터포털 "금융위원회_주식시세정보"(일별)로 교체 예정.

## content/concepts/<이름>.md (금융 개념 콘텐츠)

- 1개념 1파일, 형식은 `content/concepts/_TEMPLATE.md`. 읽기는 `engine/store.load_concepts()`.
- `concept` 값: FOMO / DIVERSIFICATION / OVERCONFIDENCE / GOAL_SAVING / NEEDS_VS_WANTS / COMPOUND_INTEREST / INVESTMENT_JOURNAL
- `related_mistakes` 값: 급등 추격 / 몰빵 / 근거 없음 (가상투자), 저축 인출 / 충동 지출 (용돈봉투)
- 콘텐츠 속 예시 숫자는 Python으로 계산해 확인한 값만 쓴다.
