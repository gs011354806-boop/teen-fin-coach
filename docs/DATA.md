# 데이터 구조

모든 금액은 원 단위 정수. 날짜는 `YYYY-MM-DD` 문자열.

## data/students/students.json

```json
[{"student_id": "S01", "name": "민지", "grade": "중2", "type": "몰빵형",
  "gender": 2, "weekly_allowance": 40000, "virtual_cash": 1000000,
  "envelope_ratio": {"SPEND": 50, "SAVE": 30, "INVEST": 20},
  "saving_goal": {"item": "에어팟", "amount": 250000}}]
```

- `type`: 몰빵형 / 저축 실패형 / 균형형
- `gender`: BC 통계와 같은 성별 코드 1 = 남, 2 = 여 (민지 2, 준호 1, 서연 2). 용돈 지출을 성별 기준에 맞출 때 쓴다.
- `weekly_allowance`: 민지 40,000 / 준호 30,000 / 서연 50,000원. BC 통계의 건당 금액(요즘 물가)으로 한 주에 2~3건 쓸 수 있도록 2026-10-16에 2배로 올림.
- `virtual_cash`: 시나리오 모드의 가상투자 시작 금액(원). 용돈봉투의 INVEST와는 별개인 연습용 가상 돈이다. 실제 시세 모드는 실제 주가가 비싸서 `config.REAL_VIRTUAL_CASH`(200만 원)로 따로 시작한다 (2026-10-16 결정).
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
| category | str | CONVENIENCE / CAFE_DESSERT / MEAL / MART / SHOPPING / TRANSPORT / OTHER |
| memo | str | 편의점 |

- 주간 용돈 입금은 봉투별로 한 줄씩, 양수 금액, category `OTHER`, memo `용돈 입금`.
- 입금액은 `envelope_ratio`대로 나눈다. 원 단위 나머지는 INVEST 봉투에 넣는다.
- 지출은 SPEND 봉투의 음수 금액만 센다. (SAVE에서 꺼낸 돈은 이동이지 지출이 아니다.)
- 용돈봉투 화면에서 넣는 입금의 날짜는 `allowance.csv`에 기록된 마지막 날짜다.
- 봉투 사이 이동은 두 줄로 적는다 (나가는 봉투 음수, 들어오는 봉투 양수, category `OTHER`).
- 옛 카테고리 `CAFE`, `FOOD`는 2026-10-16에 아래 BC 기준 카테고리로 바뀌었다.

### 지출 기준: BC카드 소비 통계

- **출처:** BC카드 업종별 소비 데이터, 2026년 1~6월, 시도·시군구·성별·연령·업종별 결제 금액(`amt`, 원)과 건수(`cnt`). 원본: `data/reference/BC_AGE_CD_1.csv` (UTF-8)
- **코드 정의:** `AGE_CD` 1 = 20세 미만 (이 파일은 1만 있음). `GENDER_CD` 1 = 남, 2 = 여, 3 = 외국인 → **3은 제외**. 업종 `서양음식`에는 카페가 포함된다.
- **계산 (코드로, `engine/consumption.py`):** 전국·6개월을 합쳐 성별·카테고리별 건수 비율 = 그 카테고리 `cnt` 합 ÷ 4개 카테고리 `cnt` 합, 건당 금액 = `amt` 합 ÷ `cnt` 합.
- **화면 이름표:** `CAFE_DESSERT`는 그래프에서 글자가 잘리지 않게 "카페·디저트"로 줄여 보여 준다 (패스트푸드 포함).
- **BC에 없는 지출:** 쇼핑(`SHOPPING`)·교통(`TRANSPORT`)·기타(`OTHER`, 노래방·PC방)는 예전 데이터를 날짜·금액까지 그대로 유지한다.

| 앱 카테고리 | 코드 | BC 업종 | 남 건수 비율 | 남 건당 | 여 건수 비율 | 여 건당 |
|---|---|---|---|---|---|---|
| 편의점 | `CONVENIENCE` | 편의점 | 57.2% | 4,580원 | 46.7% | 5,296원 |
| 카페·패스트푸드·디저트 | `CAFE_DESSERT` | 서양음식(카페 포함), 제과점 | 19.9% | 8,727원 | 29.5% | 8,331원 |
| 식사·분식 | `MEAL` | 일반한식, 중국음식, 일식회집, 스넥 | 16.7% | 20,533원 | 18.2% | 18,924원 |
| 마트 | `MART` | 슈퍼마켓, 대형할인점 | 6.2% | 9,828원 | 5.6% | 11,299원 |

- **학생 데이터 만드는 법 (`data/make_sample_data.py`):** 4주 동안 쓰기 봉투(+꺼내 쓴 돈)에서 쇼핑·교통·기타를 뺀 금액의 90% 안에서 가능한 가장 많은 건수를 성별 비율대로 나눈다(최대 나머지 방식). 건당 금액은 BC 평균에 1.0, 0.9, 1.1, 0.95, 1.05를 차례로 곱하고 100원 단위로 반올림한다. 쓰기 봉투 잔액이 어느 날에도 음수가 되지 않게 날짜를 정한다.
- **성향:** 민지(몰빵형)·서연(균형형)은 여성 기준 그대로. 준호(저축 실패형)는 편의점 건수 비율을 70%(남성 기준 57.2%)로 올리고 나머지는 원래 비율대로 줄인다. 매주 목요일 모으기 봉투에서 꺼내 쓰는 패턴은 그대로.
- **주의:** 학생 1명이 4주에 6~11건이라 건수 비율은 반올림 때문에 기준과 몇 %p 차이가 난다 (테스트 허용 오차 ±10%p).

## data/reference/virtual_accounts.csv (20번 마이데이터 연결 예시, 팀 제작)

팀원이 카드 소비 통계를 바탕으로 만든 가상 마이데이터 프로필 1,000명 (실제 개인 정보 아님). 거래 내역은 없고 프로필만 있다. 원본 그대로 두고, `engine/mydata.load_profiles()`가 불러올 때 19세(`legal_adult` True)를 빼서 783명만 쓴다.

| 컬럼 | 예시 | 쓰는 곳 |
|---|---|---|
| user_id | U00001 | 예시 구분 |
| age, school_level, grade | 15, 중학교, 2 | 학년 표시, 만 14세 미만 보호자 동의 안내 |
| guardian_consent | True | 보호자 동의를 **받았다**는 뜻 (팀 확인, 2026-11-13). 데이터에서는 만 14세 미만만 True. 14세 미만 + True면 '보호자 동의 완료', + False면 '동의 받고 불러오기' |
| weak_skill | 목표저축 / 계획소비 / 투자 위험관리 / 금융지식 | 이번 주 연습할 것·개념 카드 (`mydata.START`) |
| monthly_allowance, avg_monthly_spend | 125000, 107300 | 목표까지 계산 (남는 돈 = 용돈 - 지출) |
| allowance_cycle | 월1회 / 주1회 / 미션형 | 표시만 |
| goal_item, goal_amount, goal_months | 게임기, 400000, 3 | 매달 필요 금액(100원 올림), 지금 페이스 기간 |
| 그 밖 (sido, ccg, gender, weight, persona 등) | | 화면에 쓰지 않음. persona(성향 이름)는 학생에게 보여 주지 않는다 |

## data/students/game_reviews.csv (21번 게임 1분 복습 기록)

게임 코인이 기준보다 적을 때 하는 1분 복습을 모두 맞히면 한 줄 쌓인다. 포인트(`engine/rewards.py`)가 이 기록에서 복습 1번당 30P를 계산한다 (같은 날 같은 개념은 1번만, 하루 상한 200P 안에서). 게임 코인 자체는 저장하지 않고 포인트와도 연결하지 않는다.

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| student_id, date | S01, 2026-10-04 | date는 용돈 기록의 마지막 날 (포인트 화면과 같은 기준) |
| concept | DIVERSIFICATION | 복습한 개념 |

## data/real/news_<주차>.json (22번 이번 주 금융 뉴스, 예: news_2026-W45.json)

한 주에 한 번 만든 카드뉴스 묶음. `week`, `range`(11/2~11/8), `made_at`, `source`, `cards`(3개: tag, headline, highlight(제목 속 형광펜 낱말), number(큰 숫자, 없으면 빈 값), fact(무슨 일? 한 줄), learn, learn_highlight, why, summary(캡션), concept, art(표지 그림 키), news{title, link, press, date}), `quiz`(3문제: question, options 3개, answer 1~3). 뉴스 원문은 저장하지 않고 제목·링크만 둔다.

## data/students/news_quiz.csv (22번 뉴스 퀴즈 기록)

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| student_id | S01 | |
| week | 2026-W45 | 카드뉴스 주차 (주마다 1번만 포인트) |
| date | 2026-10-04 | 포인트 하루 상한 계산용 날짜 (용돈 기록의 마지막 날, 포인트 화면과 같은 기준) |

## data/students/spend_quiz.csv (23-1번 쓰기 봉투 내 소비 퀴즈 기록, 시뮬레이션)

쓰기 봉투의 "오늘의 내 소비 퀴즈" 5문제를 모두 맞히면 한 줄 쌓인다. 문제는 `engine/spend_quiz.py`가 학생 자신의 지출 기록에서 코드로 만든다 (가장 많이 쓴 곳, 분류별 합계, 결제 횟수, 가장 큰 지출, 편의점·카페·디저트 비중, 꼭 필요한 지출, 쓰기 봉투 잔액 중 5개 · 같은 날은 같은 문제). 포인트(`engine/rewards.py`)는 이 기록에서 하루 1번 30P를 계산한다 (하루 상한 200P 안에서).

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| student_id, date | S01, 2026-10-03 | date는 용돈 기록의 마지막 날 (포인트 화면과 같은 기준) |

## data/students/mission_runs.csv (28번 미션 탭 기록, 시뮬레이션)

미션 탭에서 시작한 미션 한 줄. "주말 결과 보기"를 누르면 같은 줄에 결과를 적는다. 포인트(`engine/rewards.py`)는 completed 줄의 points를 결과 본 날 준다 (하루 상한 안에서). 계산 규칙은 `engine/spend_mission.py`, 정리는 `docs/MISSION_TAB.md`.

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| run_id, student_id, track | MR0001, S02, spend | track: spend / invest |
| option, title | A, 편의점 주 4회 → 3회로 줄이기 | 고른 시뮬레이션 안 |
| metric, category | visits, CONVENIENCE | visits = 그 업종 이용 횟수, save_net = 모으기 봉투 순증가 |
| baseline, target, direction | 4, 3, decrease | 수행률 = (기준 − 결과) / (기준 − 목표), 0~1 |
| start_date, end_date | 2026-09-28, 2026-10-04 | 그 주 월~일 |
| reward_points, status | 150, completed | 포인트 = 보상 × 수행률 (10P 단위) |
| parent_request | REQUESTED | C안(부모님 매칭) 승인 요청 (시안) |
| current, completion_rate, points, finished_date | 2, 1.0, 150, 2026-10-03 | 주말 결과 |

`students.json`의 `saving_goal.months`는 저축 목표 기한(개월)이다. 미션 탭 시뮬레이션에서 목표 마커와 추천안 계산에 쓴다.

"쓰기 봉투에서 모으기로 옮기기"는 `allowance.csv`에 두 줄(SPEND −, memo "모으기로 옮김" / SAVE +, memo "쓰기에서 옮김")로 남는다. 옮긴 돈은 지출에서 빠진다.

## data/students/unlocks.csv (9번 Skill Unlock 기록)

학생이 '실전 준비 단계' 화면에서 단계를 연 날 한 줄씩 쌓인다. 지금 단계 = 이 학생 기록의 가장 큰 stage (없으면 1). 조건 판정은 `engine/unlock.py`가 매번 데이터로 계산하고, 이 파일은 연 기록만 남긴다 (한 번 열면 다시 잠기지 않게).

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| student_id | S03 | |
| stage | 2 | 2 = 실제 시세 연습 열기, 3 = 보호자에게 실전 신청 보냄 (시안, 실제 주문 연결 없음) |
| date | 2026-10-02 | 연 날 (시나리오 마지막 시세일) |

## data/students/concept_questions.csv (18번 개념 물어보기 기록)

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| question_id | Q0001 | |
| student_id, date | S01, 2026-10-02 | |
| question | 복리가 뭐예요? | 학생 질문 (100자까지) |
| concept | COMPOUND_INTEREST | 답에 쓴 개념 / NONE(카드 없음, 카드 추가 후보) / ADVICE(종목·매매 요청) |

## data/students/rules.csv (16번 나만의 규칙)

실수에서 배우기 끝에 학생이 직접 쓴 한 줄 규칙. 투자연습 매수가 같은 패턴에 걸리면 1분 점검 카드에 가장 최근 규칙을 다시 보여 주고 AI 질문 재료(`my_rule`)로도 쓴다. 부모 화면에는 보여 주지 않는다.

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| rule_id | U0001 | |
| student_id, date | S01, 2026-10-02 | |
| trade_id | T0014 | 규칙을 정할 때 돌아본 매수 |
| patterns | 몰빵\|근거 없음 | 그 매수의 감지 패턴 (1분 점검과 겹치면 보여 줌) |
| rule | 한 종목은 절반까지만 담기 | 학생 글 (공백 빼고 5자 이상) |

## data/students/lessons.csv (Mistake-to-Lesson 기록)

5번 화면에서 학생이 꼬리 질문까지 답하면 한 줄씩 쌓인다. 8번 부모 리포트가 읽는다 (부모 화면에 `answer`·`followup_answer` 원문은 보여 주지 않는다).

| 컬럼 | 타입 | 예시 |
|---|---|---|
| lesson_id | str | L0001 |
| student_id | str | S01 |
| trade_id | str | T0014 (돌아본 매수) |
| date | str | 2026-10-02 (기록한 날: 데모의 "오늘" = 가격 데이터 마지막 거래일) |
| patterns | str | 몰빵\|근거 없음 (`\|`로 구분) |
| question | str | AI가 만든 질문 |
| answer | str | 학생 답 (줄바꿈은 공백으로) |
| followup_question | str | 16번 AI 꼬리 질문 (16번 전 기록은 빈 값) |
| followup_answer | str | 꼬리 질문에 한 학생 답 |
| error_type | str | FOMO / 과신 / 근거 부족 / 해당 없음 |
| reason | str | 분류 이유 1문장 (비어 있으면 AI 분류 실패로 기본값이 들어간 것) |
| concept | str | INVESTMENT_JOURNAL (`content/concepts`의 concept 값) |
| explanation | str | 개념 설명 |
| next_try | str | 다음에 해 볼 행동 |

- 같은 매수를 여러 번 돌아보면 여러 줄이 생긴다. 화면에는 그 매수의 가장 최근 기록을 보여 준다.

## data/students/real_trades.csv (실제 시세 모드의 가상 거래)

`trades.csv`와 같은 컬럼. 시나리오 거래와 섞이지 않게 따로 둔다. `trade_id`는 `R0001`부터 (5-1 기록의 trade_id가 겹치지 않게).
거래 날짜와 가격은 그 시점의 마지막 종가 기준일과 종가. 실제 주문은 없다.

## data/reference/cards.json (체크카드 혜택 비교)

우리카드 체크카드의 혜택 조건 (청소년 전용이 아니어도 된다). 화면은 이 파일만 보고 계산한다 (`engine/cards.py`).
지금 4장: 카드의정석 DON CHECK, 네이버페이 우리카드 체크, 카드의정석 EVERYDAY CHECK, 카드의정석 SSO3 CHECK.
혜택 업종이 우리 데이터에 없는 카드(위비트래블·오늘하루 체크 등)는 넣지 않았다.

| 키 | 예 | 뜻 |
|---|---|---|
| base_rate | 0.01 | 특별 혜택을 받지 않은 모든 결제의 기본 적립률 (실적 조건 없음) |
| rules | [{label, categories, rate, per_payment_cap, min_payment}] | 카테고리별 특별 혜택. 1건마다 금액×비율(1원 미만 버림), 1회 한도, 최소 결제금액 |
| tiers | [{min_spend, rule_monthly_cap, total_monthly_cap}] | 실적 구간. 구간이 있는데 못 채우면 특별 혜택 0. null 한도 = 제한 없음 |
| performance_excludes / benefit_excludes | ["TRANSPORT"] | 실적·혜택에서 빼는 카테고리 (데이터의 교통 = 버스카드 충전이라 제외) |
| caps_unknown | true | 한도를 확인하지 못한 카드 (화면에 "한도 확인 필요") |
| unit | P / 원 | 적립 포인트 또는 할인 금액. 비교할 때 1P = 1원 |
| tone, tagline | | 카드 그림 색(style.css), 한 줄 설명 |
| source / source_urls / checked | 뱅크샐러드 / 2026-10-16 | 출처와 확인일. 화면에 작은 글씨로 표시 |

- 데모 데이터는 4주뿐이라 "전월 실적"은 이번 달(4주) 지출로 판단한다.
- 실적을 채우려면 더 써야 하는 금액과, 채웠을 때 늘어나는 혜택 최대치를 함께 보여 준다 (교육용).

## data/real/ (실제 시세)

- `watchlist.json`: 고정 종목 목록 `[{"ticker": "005930", "name": "삼성전자"}]`, 15개 이내. 설명은 `docs/STOCKS.md`.
- `quote_cache.json`: 마지막으로 받은 시세 (`{"fetched_at", "series": {코드: [{date, close}]}}`). 5분 안에는 다시 부르지 않고, API가 실패하면 이 값을 보여 준다. GitHub에 올리지 않는다.
- 시세 출처: 공공데이터포털 금융위원회_주식시세정보 V2 `GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2` (하루 늦은 종가, 2026-09-09부터 V2만 신규 호출 가능). 키는 `.env` / Streamlit Secrets의 `DATA_GO_KR_KEY`.

## data/students/prechecks.csv (15번 사기 전 1분 점검 기록)

| 컬럼 | 예시 | 뜻 |
|---|---|---|
| check_id | C0001 | |
| student_id, date, mode | S01, 2026-10-02, scenario | mode: scenario / real (시세 종류) |
| ticker, qty | 005930, 2 | 점검한 매수 |
| patterns | 몰빵\|근거 없음 | 걸린 감지 기준 |
| question | | AI(또는 기본) 질문 |
| decision | BUY / CANCEL | 이대로 주문 / 다시 생각 |
| added_reason | | 점검 화면에서 더 적은 이유 (BUY면 투자 일지에도 붙는다) |
| trade_id | T0016 | BUY일 때 저장된 거래 |

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

## data/students/island_game.json (30번 자산섬 v2 게임 저장)

학생별 게임 상태 `{student_id: GameState}` 하나뿐이다. 앱의 실제 금융 데이터(용돈·거래·가상투자)와 섞지 않는다. 형식은 `engine/island_game.py`의 `new_state()` (version 필드로 마이그레이션, `migrate()`).
주요 칸: day, ap, cash, house, exp, inventory, plots, trees, treeHist(나무 시세 기록), market(오늘·어제 시세), events(오늘·내일), offer, temptation, wish, deposit, loans, tools, dex, today(오늘 수입·지출 줄), history(일별 순자산·순수입), houseDays, realLog(실제 날짜별 진행 일수), lastResult(직전 결산).

- 규칙 값: `data/island/rules.json` (가격·변동성·이벤트 확률·집 단계·도감 문장). 시안 재현 상태: `data/island/demo_day12.json`.
- 게임 화폐는 냥이다. 실제 돈·포인트와 연결하지 않는다.

## data/students/island_*.csv (29번 자산섬 게임 상태)

게임은 실제 기록(용돈·가상투자·미션·개념 카드)을 읽기만 한다. 게임이 새로 저장하는 것은 아래 게임 상태뿐이다. 형식은 `engine/store.py`의 `ISLAND_TABLES`.

| 파일 | 컬럼 | 내용 |
|---|---|---|
| island_seeds.csv | seed_id, student_id, date, amount, reason, key | 씨앗 증감 기록. 같은 key는 한 번만 (예: `wish-W0001`, `weekly-40`, `quest-MR0003`). 하루 200 상한 |
| island_tags.csv | student_id, item, tag | 학생이 고친 필요(need)/원함(want) 태그. item = 지출 메모 |
| island_wish.csv | wish_id, student_id, name, price, added_at, decision, decided_at | 찜 바구니. decision: (빈칸) / wait / cancel / buy |
| island_quests.csv | student_id, week, quest_id, title, skill, seeds, run_id, date | 주간 결산에서 고른 퀘스트. run_id가 있으면 미션 탭 미션과 연결 |
| island_prefs.csv | student_id, key, value | compound(on/off), weekly_seen(이번 주 결산 확인한 ISO 주차) |

- 씨앗은 게임 안 화폐다. 포인트(`point_spend.csv`, `engine/rewards.py`)와 연결하지 않고 현금성 혜택으로 바꾸지 않는다.
- `data/island_mock.json`: 명세 7장 예시 데이터. `?mock=1`로 시안과 비교할 때와 테스트에서만 쓴다.

## data/students/demo_responses.json (시연 모드 저장 응답)

시연 모드를 켜면 AI가 `config.DEMO_TIMEOUT_SECONDS`(12초) 안에 답하지 않거나 실패할 때 이 파일의 응답을 보여 준다. 없으면 기본 문구.
만드는 법: `python data/make_demo_responses.py` (실제 AI(`config.MODEL_NAME`)로 민지 시나리오를 돌려, 규칙 검사를 통과한 응답만 저장. 전부 새로 만들어 손으로 고친 응답도 덮어씀)

19번만 추가: `python data/make_demo_responses.py --only spending` → 민지 `responses.weekly_mission["이번 주 편의점·카페·디저트 지출을 …원 이하로 줄이기"]` 3개.

18번만 추가·교체: `python data/make_demo_responses.py --only concept` → 학생 3명 `responses.concept_answer[예시 질문]` (같은 답).

17번만 추가·교체: `python data/make_demo_responses.py --only growth` → 민지 `responses.growth_review[최근 주 시작일]` (1주차와 비교, 행동 사실만으로 만든 회고).

16번만 추가·교체: `python data/make_demo_responses.py --only followup` → 민지 매수 5개의 `responses.followup_question[trade_id]`와 꼬리 질문 예시 답 `followup_answers[trade_id]` (T0014는 손으로 다듬음).

15번만 추가·교체: `python data/make_demo_responses.py --only precheck` → 학생마다 `responses.precheck_question["몰빵|근거 없음"]`처럼 패턴 조합(급등 추격·몰빵·근거 없음 순서) 키 7개. 수량마다 숫자가 바뀌므로 질문에 숫자·종목명을 넣지 않는다.

```json
{"model": "gpt-6-astra",   // 만든 모델 (예전 응답은 gemini-3.5-flash-lite로 만듦)
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

## data/students/invest.json (31번 투자 탭 동의 기반 2트랙)

학생별 투자 탭 상태 `{student_id: state}`. 기존 가상 계좌(`trades.csv`, `real_trades.csv`)는 그대로 쓰고 여기에 복사하지 않는다.
테스트는 임시 파일을 쓴다 (`tests/conftest.py`). `?mock` 시안 상태는 저장하지 않는다.

| 키 | 내용 |
|---|---|
| consent | status(NONE·PENDING·ACTIVE·REJECTED·REVOKED), parent_id, requested_at, decided_at, revoked_at, student_message, report_snapshot(연습 리포트: weeks, journalCount, checklistRate, skills는 True/False만, highlights), broker_account_id |
| guardrails | monthlyLimit(5만·10만·20만), perOrderLimit(한도의 50%), scope(ETF_ONLY·ETF_LARGECAP·ALL), notifyParentOnTrade, fomoCheck, fomoThresholdPct(10), marginAllowed(항상 false), updatedBy, updatedAt |
| history | 동의 상태 전이 기록 [{at, from, to, by}] |
| real | Mock 실전 계좌: account_id, cash(판 돈), funded(용돈 투자 봉투에서 이체한 누적), holdings {종목: {qty(소수), avgPrice}}, orders [{id, date, symbol, side, amount, qty, price, reason(투자일지), fomo, changePct}] |
| watch | 관심 종목 [{symbol, addedAt, priceAtAdd, reason(FOMO_WAIT·USER), account(PRACTICE·REAL)}] |
| change_requests | 학생의 한도·범위 변경 요청 [{id, at, requestedMonthlyLimit, requestedScope, message, attachRecord, status(SENT·APPROVED·DECLINED·ADJUSTED), parentNote}] |
| notifications | 알림 기록 [{at, to(STUDENT·PARENT), text}] |
| checklists | 연습 주문의 사기 전 체크리스트 [{date, symbol, side, trade_id, surge, news, chart, journal}] |

- 종목 구분(ETF/대형주): `data/invest/instruments.json` (표에 없으면 STOCK · 대형주 아님).
- 시안 재현 데이터: `data/invest/demo.json` (명세 7장, 가상 종목).

