# 28번 미션 탭 (소비/투자 미션) · 구현 정리

> 명세: `C:\dev\teen-app\MISSION_TAB_SPEC.md` · 시안: `teen-app/images/00~06`
> 상태: 시뮬레이션 브랜치 `simulation` (2026-11-10). 소비 미션 완료, 투자 미션은 화면만 만들고 잠금.

## 1. 결정 사항 (2026-11-10, 사용자)

| 항목 | 결정 |
|---|---|
| 기존 미션 탭 (AI 진단 → 미션 → 주말 Replay → 성장 회고) | **새 화면으로 교체.** 기존 화면은 `legacy/mission_loop_page.py`로 옮겨 두고 `config.MISSION_TAB_V2 = False`로 다시 켤 수 있다. 기존 테스트는 이 스위치를 끈 채로 그대로 돈다 (`legacy_mission_tab` fixture) |
| 저축 목표 기한 | **학생마다 다르게.** `students.json`의 `saving_goal.months`에 민지 6 · 준호 4 · 서연 8 (질문 예시 값을 일단 넣음, 바꿔도 됨) |
| 미션 포인트 | **명세대로.** 보상 × 수행률 (10P 단위 반올림). 하루 상한 200P 안에서 |
| 트리거 없는 학생 | **잘하고 있는 점 + 목표 시뮬레이션 버튼.** 데이터에 없는 트리거는 만들지 않음 |
| 투자 미션 | **화면만 만들고 실행하지 않음** (`config.INVEST_MISSION_ENABLED = False`, 데이터도 없음) |
| 시안 숫자 vs 계산 | **계산값을 쓴다.** 명세 7장 mock 숫자(민지 86,000원 등)는 쓰지 않고, 각 학생의 실제 기록에서 계산한다. 그래서 화면 숫자는 시안과 다르다 |

## 2. 코드베이스 대응 (명세 0-1)

| 명세 | 이 앱 |
|---|---|
| mission 모듈 | `engine/spend_mission.py`(소비) · `engine/invest_mission.py`(투자) · 화면 `pages/4_이번_주_미션.py` |
| 라우트 6개 | 같은 페이지 안 `?view=` (없음=홈, `spend_sim`, `spend_result&run=`, `invest_replay`, `invest_sim`) |
| 소비/투자 토글 | `st.segmented_control` (선택은 세션에 저장 → 탭을 다시 열어도 유지) |
| 하단 탭바 | 기존 탭바의 "미션" 그대로 (새로 만들지 않음) |
| 상세 화면 | 기존 패턴대로 왼쪽 위 뒤로가기 → 미션 홈. Streamlit 구조상 탭바는 숨기지 않음 |
| `MissionRepository` | `store.load_mission_runs / append_mission_run / update_mission_run` + `data/students/mission_runs.csv` |
| `CoachService.generate` | `spend_mission.coach_message(..., generate=None)`: 1차는 템플릿, `generate`를 넘기면 그걸 쓴다 |
| feature flag `missionTab` | `config.MISSION_TAB_V2` |

### 디자인 토큰 매핑 (명세 3장)

| 역할 | 시안 | 이 앱 토큰 (`.streamlit/config.toml` → `var(--…)`) |
|---|---|---|
| Primary | `#1D5FD8` | `primaryColor #2B7FF5` → `--primary` |
| Primary tint / chip | `#F2F7FF` / `#E8F0FD` | `--primary` 5~12% `color-mix` |
| Sky (다크 위 보조) | `#7CC4F5` | `--primary` 55% + 흰색 |
| Accent yellow | `#FFC531` | `yellowColor #F7B500` → `--yellow` |
| Point chip | `#FFF4D1` / `#8A5A00` | `--yellow` 18% / `--yellow` 45% + `--text` |
| Navy (다크 카드) | `#14213D` | `textColor #1B1D1F` → `--text` |
| Background / Surface | `#F4F7FB` / `#FFFFFF` | `--bg #F2F4F7` / `--surface` |
| Track / Border | `#E6EDF7` / `#E3E9F2` | `--primary` 10% + `--bg` / `--border` |
| Text secondary | `#4A5870` | `--gray` |
| Warning (지연·손실) | `#B4410C` | `--orange` 70% + `--red` |
| Success / Caution tint | `#EEF6EA` / `#FDEEE4` | `--green` 10% / `--orange` 10% |
| 폰트 | Noto Sans KR | 기존 Pretendard 그대로 |

새 색 토큰은 만들지 않았다. 모양은 `style.css`의 "미션 탭" 묶음에만 있다. 바, 마커, 원형, 라인 차트는 SVG이고 숫자는 SVG 속성으로만 넘긴다 (인라인 style 없음).

## 3. 수정한 기존 파일과 이유

| 파일 | 이유 |
|---|---|
| `pages/4_이번_주_미션.py` | 새 미션 탭 (기존 내용은 `legacy/mission_loop_page.py`로 이동, 스위치로 다시 켬) |
| `config.py` | `MISSION_TAB_V2`, `INVEST_MISSION_ENABLED` 스위치 |
| `engine/store.py` | 미션 기록 읽기·쓰기 추가. 기본 경로를 함수가 불릴 때 읽도록 고침 (테스트가 실제 data/에 쓰던 문제) |
| `engine/rewards.py` | `earn_events(..., mission_runs=)`: 미션 결과 포인트 |
| `engine/envelope.py` | 쓰기 → 모으기 옮기기 (`transfer_entries`). 옮긴 돈은 지출에서 뺀다 |
| `app.py`, `pages/2·5·11·12` | 포인트 계산에 미션 기록을 넘긴다 (화면마다 포인트가 같게) |
| `data/students/students.json` | `saving_goal.months` (목표 기한) |
| `style.css` | 미션 탭 모양 |
| `tests/` | 예전 미션 탭 테스트에 `legacy_mission_tab` 표시, 새 테스트 `test_mission_tab.py` |

## 4. 학생별로 보이는 것 (데모 날짜 2026-10-03 기준)

| | 민지 | 준호 | 서연 |
|---|---|---|---|
| AI Replay | 없음 → "잘하고 있어요" (3주 내내 모으기 계획 지킴 등) | **운동화 저축이 3주째 계획보다 늦어요** (계획 주 9,000원) | 없음 → "잘하고 있어요" |
| 지금처럼 모으면 | 4.7개월 (기한 6개월보다 1.3개월 빠름) | 34개월 (기한 4개월) | 3.4개월 (기한 8개월) |
| 추천안 | B 주당 저축 +3,000원 | A 편의점 주 1회 줄이기 (주 4회 → 3회) | B 주당 저축 +3,000원 |

## 5. 명세와 다르게 한 점

- **LATE_NIGHT 트리거 없음.** 결제 시각이 데이터에 없다.
- **SPEND_RATIO_HIGH는 "이번 달" 대신 "최근 4주"로 본다.** 데모 데이터가 9월 7일~10월 3일이라 "이번 달"이 1주뿐이다.
- **SPEND_FREQ_HIGH에서 교통·기타는 뺀다.** 버스카드 충전을 줄이라는 미션은 맞지 않는다.
- **미션 기간은 1주(이번 주 월~일)다.** 데모 날짜가 토요일로 고정돼 있어 "주말 결과 보기"를 바로 누를 수 있다.
  - 저축 미션은 "쓰기 봉투에서 모으기로 옮기기"로 실제로 달성할 수 있다.
  - 횟수 미션은 이번 주에 이미 있는 기록으로 판정한다.
- **"달라진 행동"의 두 번째 칸은 "소비계획 달성률" 대신 "미션 지표 이전 → 이후"다.** 예: 편의점 4회 → 2회. 소비계획을 정의할 데이터가 없다.
- **보상 포인트:** A 150P · B 200P · C 100P. 하루 상한(200P) 때문에 명세 mock의 300P는 쓰지 않는다.
- **추천 규칙:** 기한 안에 드는 안 중 행동 변화가 가장 작은 안. 부모님 매칭(C)은 다른 안이 없을 때만 고른다.
- **부모 승인과 공유는 시안이다.** 실제 부모 앱과 연결하지 않고, 기록과 안내만 남긴다.
- **새 미션은 아직 부모 리포트와 효과 측정에 들어가지 않는다.** 둘 다 예전 `missions.csv`를 읽는다. 반영하려면 다음 작업으로 해야 한다.

## 6. 투자 미션: 켜기 전에 할 일

1. 모의투자 주문 로그를 만든다: `order_id, user_id, datetime, symbol, side, qty, price, viewed_info, memo`. 지금 `trades.csv`에는 `viewed_info`가 없다.
2. 시세를 준비한다: `{symbol: [(date, close)]}`.
3. `pages/4_이번_주_미션.py`의 `load_invest_data()`가 위 데이터를 돌려주게 하고 `INVEST_MISSION_ENABLED = True`로 바꾼다.
4. **규칙 충돌을 정해야 한다.** ⑥ 시뮬레이션은 대안을 수익률(-11%, -3% …)로 비교한다. CLAUDE.md 규칙 4는 "수익률로 평가하지 않는다"이다. 켜기 전에 표시 방식을 정해야 한다 (예: 수익률 대신 "흔들림 폭"이나 "손실이 절반 이하로"처럼 비교만).
5. 명세 mock 시세(바이오A 9일)로 계산하면 실제 매수는 -11%로 시안과 같다. 대안은 명세 공식대로 계산해서 시안 값과 다르다: 관찰 후 매수 0%, 분할 -7%. 시안 숫자에 맞추려면 공식이나 mock을 조정해야 한다.
6. 개념 카드 "정보와 가격 반영"과 "분할매수"가 `content/concepts`에 없다. 지금은 각각 투자 일지 카드와 분산투자 카드로 대신한다 (규칙 8: 콘텐츠 없음).
