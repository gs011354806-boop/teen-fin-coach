# CLAUDE.md — 청소년 금융행동 AI 코칭 엔진

## 0. 최우선 규칙 (모든 작업에서 MUST)

1. MUST: 금액·비율·기간·횟수 계산은 Python 코드로 한다. NEVER: LLM에게 숫자를 계산시키지 않는다.
2. MUST: LLM은 해석·질문·설명·미션 문장만 만든다. 출력은 항상 JSON으로 받는다.
3. NEVER: 특정 종목을 사라/팔라고 권유하는 문장을 만들지 않는다. 판단 과정만 질문한다.
4. NEVER: 수익률로 행동을 평가하거나 보상하지 않는다. 평가는 과정(근거 기록, 비중, 보유 기간)으로만 한다.
5. NEVER: 학생 화면에 역량 점수 숫자를 보여주지 않는다. "이번 주 연습할 것"만 보여준다.
6. MUST: 한 번에 기능 1개만 만든다. 순서는 `docs/FEATURES.md` 표를 따른다.
7. NEVER: API 키를 코드에 쓰지 않는다. 키는 `.env`/Streamlit Secrets에서만 읽는다 (`OPENAI_API_KEY`, 시세·뉴스 `DATA_GO_KR_KEY`).
8. MUST: 개념 설명은 `content/concepts/`에 있는 파일에서 골라 쓴다. 해당 파일이 없으면 지어내지 말고 사용자에게 "콘텐츠 없음: <개념명>"으로 보고한다.
9. NEVER: 파일을 삭제하거나 폴더 구조를 바꾸기 전에 사용자 확인 없이 진행하지 않는다.

## 1. 프로젝트

우리은행 청소년 서비스(우리틴틴, 청소년 마이데이터)에 붙이는 AI 코칭 엔진의 데모.
대표 기능 2개: ① Mistake-to-Lesson ② AI 행동 미션 루프. 상세: `docs/PLAN.md`

## 2. 기술 스택 (변경 금지)

- Python 3.11 이상, Streamlit, pandas, openai, python-dotenv, pytest
- LLM 모델명은 `config.py`의 `MODEL_NAME` 한 곳에서만 정한다. 기본값 `gpt-6-luna` (2026-11-03 변경: Gemini 무료 키 → 수업 지원 OpenAI 유료 키(한도 $80). 교수님 안내대로 경량 모델 사용)
- 데이터는 `data/` 아래 CSV·JSON 파일. DB 사용 금지.
- 주간 뉴스는 공식 API(공공데이터포털 정책브리핑 정책뉴스)만 쓴다. 종목 이름·투자 권유 표현이 든 뉴스는 거르고, 카드에 출처·원문 링크를 단다.
- 실제 시세는 공식 API(공공데이터포털 금융위원회_주식시세정보)만 쓴다. NEVER: 웹사이트 크롤링, 실제 매수·매도 주문 연결. 키는 `.env`/Streamlit Secrets의 `DATA_GO_KR_KEY`에만.
- 화면 모양: 색·글꼴은 `.streamlit/config.toml`에서만, 나머지(크기·간격·모서리·배치)는 `style.css`에서만 정한다. 화면 코드에 인라인 style을 쓰지 않고 `ui_common.py`의 조각(app_bar, section, card, service_row 등)을 쓴다.
- 우리은행 앱 안의 추가 서비스처럼 보이게 한다 (모바일 폭, 회색 바탕 + 흰 둥근 카드, 아래 탭 바). 특정 회사 로고·상표 이미지는 쓰지 않는다. 대학 수업 발표용(비공개)이라 화면 문구에 우리은행·우리카드 등 공식 명칭을 써도 된다 (2026-10-16 결정). 모든 화면 맨 위의 `ui_common.DISCLAIMER` 안내 문구는 유지한다. 실제 상품 정보를 보여 줄 때는 출처·확인일을 함께 표시한다.

## 3. 폴더 구조

```
app.py                 # Streamlit 시작 화면
pages/                 # Streamlit 페이지 (화면별 1파일)
engine/                # 계산·규칙 (LLM 호출 금지)
  detect.py            # 실수 패턴 감지
  simulate.py          # 목표 달성 시뮬레이션
  replay.py            # 주간 수행 결과 계산
components/catch_game/ # 21번 게임 화면 (HTML·JS 하나, 색은 config.toml 값을 넘겨받음)
llm/                   # LLM 호출 전용
  client.py            # OpenAI 호출 + JSON 파싱 + 재시도
  prompts/             # 프롬프트 템플릿 (.md)
data/students/         # 가상 학생 행동 데이터
data/prices/           # 주가 데이터 CSV
content/concepts/      # 금융 개념 콘텐츠 (.md, 1개념 1파일)
tests/                 # pytest
docs/                  # 기획·기능·데이터 문서
```

## 4. 명령어 (그대로 사용)

- 설치: `pip install -r requirements.txt`
- 실행: `streamlit run app.py`
- 테스트: `pytest -q`

## 5. 분기 규칙

- 요청 기능의 선행 기능이 `docs/FEATURES.md`에서 "완료"가 아니면 → 작업 전에 사용자에게 알리고 선행 기능부터 제안한다.
- 요구사항이 두 가지 이상으로 해석되면 → 코드를 쓰기 전에 질문 1개만 한다.
- LLM 응답 JSON 파싱 실패 → 1회 재시도. 또 실패하면 기본 문구를 반환하고 `logs/llm_errors.log`에 기록한다.
- OpenAI 429(요청 한도 초과) → 화면에 "AI 사용 한도 초과, 잠시 후 다시 시도" 표시. 자동 반복 재시도 금지.
- 시연 모드(사이드바 스위치)가 켜져 있으면 → AI 실패·지연 시 멈추지 않고 `data/students/demo_responses.json`의 저장 응답, 없으면 기본 문구를 보여 준다. 화면에서 AI는 항상 `ui_common.ask_ai`로 부른다.
- `.env`가 없거나 키가 비어 있으면 → 실행을 멈추고 사용자에게 `.env.example`을 복사해 키를 넣으라고 안내한다.
- 테스트가 실패하면 → 고치고 다시 실행한다. 3회 연속 실패하면 멈추고 원인을 사용자에게 보고한다.

## 6. 예시

**Good — 계산은 코드, 해석은 LLM**
```python
weight = position_value / total_value          # engine/detect.py에서 계산
payload = {"weight_pct": round(weight*100), "journal": "계속 오를 것 같아서"}
result = llm.ask("classify_mistake", payload)  # → {"error_type": "FOMO", "question": "..."}
```

**Bad — LLM에게 계산과 판단을 통째로 맡김**
```python
llm.ask(f"이 거래내역 보고 수익률이랑 비중 계산해서 평가해줘: {all_trades}")
```

**Good 미션 문장:** "이번 주에는 한 종목 비중을 50% 아래로 낮추고, 이유를 한 줄 적어 보세요."
**Bad 미션 문장:** "삼성전자를 팔고 배당주를 사세요." (규칙 3 위반)

**Good 피드백:** "급등 직후에 근거를 적지 않고 샀어요. 다음엔 무엇을 확인할 수 있을까요?"
**Bad 피드백:** "-11% 손실이 났으니 잘못된 투자예요." (규칙 4 위반)

## 7. 작업 후 검증 체크리스트 (매 작업 끝에 반드시)

1. `pytest -q` 실행 → 전부 통과 확인
2. 사용자에게 `streamlit run app.py` 실행을 요청하고, 화면에서 오류가 없는지 결과를 받는다
3. 변경 파일 diff를 다시 읽고 0번 규칙 1~5 위반이 없는지 확인한다
4. `docs/FEATURES.md`의 상태 칸을 갱신한다
5. 사용자에게 3줄 이내로 보고: 만든 것 / 확인한 것 / 다음 할 일

1~3 중 하나라도 실패 → 수정 후 1번부터 다시.

## 8. 상세 문서

- 기획 요약: `docs/PLAN.md`
- 기능 목록·순서·상태: `docs/FEATURES.md`
- 데이터 구조: `docs/DATA.md`
