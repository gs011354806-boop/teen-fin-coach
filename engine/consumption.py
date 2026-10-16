"""BC카드 소비 통계에서 청소년 지출 기준(건수 비율, 건당 금액)을 계산한다. LLM 호출 금지.

원본: data/reference/BC_AGE_CD_1.csv (BC카드 업종별 소비 데이터, 2026년 1~6월, AGE_CD 1 = 20세 미만)
- GENDER_CD 1 = 남, 2 = 여, 3 = 외국인 → 3은 쓰지 않는다.
- 업종은 앱 지출 카테고리로 묶는다. 서양음식에는 카페가 포함된다.
"""

from pathlib import Path

import pandas as pd

REFERENCE_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "BC_AGE_CD_1.csv"
SOURCE = "BC카드 업종별 소비 데이터 (2026년 1~6월, 20세 미만)"
GENDERS = {1: "남", 2: "여"}  # 3(외국인)은 제외

# BC 업종명(공백 제거) → 앱 지출 카테고리
BC_TO_CATEGORY = {
    "편의점": "CONVENIENCE",
    "서양음식": "CAFE_DESSERT", "제과점": "CAFE_DESSERT",
    "일반한식": "MEAL", "중국음식": "MEAL", "일식회집": "MEAL", "스넥": "MEAL",
    "슈퍼마켓": "MART", "대형할인점": "MART",
}
BC_CATEGORIES = ["CONVENIENCE", "CAFE_DESSERT", "MEAL", "MART"]


def load_reference(path=None):
    return pd.read_csv(path or REFERENCE_PATH, encoding="utf-8")


def baseline(reference=None):
    """{성별코드: {카테고리: {"count_share": 0~1, "avg_amount": 원}}} — 외국인 제외."""
    df = reference if reference is not None else load_reference()
    df = df[df["GENDER_CD"].isin(GENDERS)].copy()
    df["category"] = df["TP_BUZ_NM"].str.replace(" ", "").map(BC_TO_CATEGORY)
    unknown = df[df["category"].isna()]["TP_BUZ_NM"].unique()
    if len(unknown):
        raise ValueError(f"카테고리가 정해지지 않은 업종: {list(unknown)}")
    totals = df.groupby(["GENDER_CD", "category"])[["amt", "cnt"]].sum()
    result = {}
    for gender in GENDERS:
        rows = totals.loc[gender]
        count_total = rows["cnt"].sum()
        result[gender] = {c: {"count_share": float(rows.loc[c, "cnt"] / count_total),
                              "avg_amount": float(rows.loc[c, "amt"] / rows.loc[c, "cnt"])}
                          for c in BC_CATEGORIES}
    return result


def tilt(shares, category, share):
    """한 카테고리 비중을 share로 바꾸고 나머지는 원래 비율대로 줄인다 (성향 반영용)."""
    rest = 1 - shares[category]
    return {c: share if c == category else s * (1 - share) / rest for c, s in shares.items()}


def allocate_counts(shares, total):
    """비율대로 total건을 나눈다 (최대 나머지 방식, 항상 같은 결과)."""
    raw = {c: s * total for c, s in shares.items()}
    counts = {c: int(v) for c, v in raw.items()}
    for c in sorted(raw, key=lambda c: raw[c] - counts[c], reverse=True)[:total - sum(counts.values())]:
        counts[c] += 1
    return counts
