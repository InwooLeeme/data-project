"""
[실습 3] Pandas EDA / Polars Lazy / DuckDB SQL 비교
작성자: 이인우
파일 이름 : 광주_1반_이인우.py

설명:
    data/sales_100k.csv로 Pandas 기초 EDA와 IQR 이상치 제거를 수행하고,
    region/category별 매출 집계를 Pandas named aggregation, Polars Lazy API,
    DuckDB SQL 세 가지 방식으로 구현한 뒤 timeit으로 실행 속도를 비교한다.

변경내역:
    - 2026-07-21 최초 작성
    - 2026-07-21 DuckDB: CSV 일부 행의 컬럼 누락(ragged row)으로 인한 파싱 오류 수정
      (read_csv_auto에 null_padding=true 옵션 추가)
    - 2026-07-21 Pandas named aggregation: groupby에 dropna=False 적용
      (category 결측 그룹이 Polars/DuckDB 결과에서는 유지되는데 Pandas만 누락되던 것을 일치시킴)
    - 2026-07-21 헤더에 파일 이름 항목 추가
    - 2026-07-21 섹션 구분 주석을 "# 제목" 형태로 간소화
    - 2026-07-21 timeit 반복 횟수(NUMBER)를 3 -> 20으로 변경
    - 2026-07-21 print 출력 문구 불필요한 부분 수정
    - 2026-07-21 CSV 로딩 예외 처리 보강 (컬럼 누락 검증, amount 비수치 데이터 처리,
      ParserError/EmptyDataError 처리 추가)
    - 2026-07-21 timeit 성능 비교: Pandas도 CSV 읽기+필터를 포함하도록 pandas_pipeline
      함수를 추가해 Polars/DuckDB와 동일한 조건으로 비교
    - 2026-07-21 polars_agg, pandas_pipeline에 예외 처리 추가
      (DuckDB 경로와 동일하게 파일 없음/파싱 오류 시 SystemExit로 종료하도록 통일)
"""

import timeit
from pathlib import Path

import duckdb
import pandas as pd
import polars as pl

CSV_PATH = Path("data/sales_100k.csv")

REQUIRED_COLUMNS = {"region", "category", "amount"}

try:
    df = pd.read_csv(CSV_PATH)
except FileNotFoundError:
    raise SystemExit(f"CSV 파일을 찾을 수 없습니다: {CSV_PATH}")
except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
    raise SystemExit(f"CSV 파싱 중 오류가 발생했습니다: {exc}")

missing_columns = REQUIRED_COLUMNS - set(df.columns)
if missing_columns:
    raise SystemExit(f"필수 컬럼이 없습니다: {missing_columns}")

# amount에 숫자로 변환할 수 없는 값이 있으면 NaN 처리
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

print("상위 5행")
print(df.head())

print("\ndf.info()")
df.info()

print("\n결측치 개수 (isnull().sum())")
print(df.isnull().sum())

# IQR 방법으로 amount 컬럼 이상치 제거
q1 = df["amount"].quantile(0.25)
q3 = df["amount"].quantile(0.75)
iqr = q3 - q1
lower = q1 - 1.5 * iqr
upper = q3 + 1.5 * iqr

print(f"\nIQR 정상 범위: {lower:.2f} ~ {upper:.2f}")
print(f"이상치 제거 전 행 수: {len(df)}")

df_clean = df[df["amount"].between(lower, upper)]
print(f"이상치 제거 후 행 수: {len(df_clean)}")


# Pandas named aggregation
# region, category별 총매출/평균/건수를 계산해 총매출 내림차순으로 반환한다.
def pandas_agg(data: pd.DataFrame) -> pd.DataFrame:
    return (
        data.groupby(["region", "category"], dropna=False)
        .agg(
            total=("amount", "sum"),
            mean=("amount", "mean"),
            count=("amount", "count"),
        )
        .sort_values("total", ascending=False)
        .reset_index()
    )


pandas_result = pandas_agg(df_clean)
print("\nPandas named aggregation 결과")
print(pandas_result)


# Polars Lazy API
# scan_csv->filter->group_by->agg->sort->collect 체인으로 동일 집계를 수행한다.
def polars_agg(csv_path: Path, lower: float, upper: float) -> pl.DataFrame:
    try:
        return (
            pl.scan_csv(csv_path)
            .filter(pl.col("amount").is_between(lower, upper))
            .group_by(["region", "category"])
            .agg(
                pl.col("amount").sum().alias("total"),
                pl.col("amount").mean().alias("mean"),
                pl.col("amount").count().alias("count"),
            )
            .sort("total", descending=True)
            .collect()
        )
    except (FileNotFoundError, pl.exceptions.ComputeError) as exc:
        raise SystemExit(f"Polars 집계 중 오류가 발생했습니다: {exc}")


polars_result = polars_agg(CSV_PATH, lower, upper)
print("\nPolars Lazy API 결과")
print(polars_result)


# DuckDB SQL
# DuckDB SQL GROUP BY로 동일 집계를 수행한다.
def duckdb_agg(csv_path: Path, lower: float, upper: float) -> pd.DataFrame:
    query = f"""
        SELECT region, category,
               SUM(amount) AS total,
               AVG(amount) AS mean,
               COUNT(amount) AS count
        FROM read_csv_auto('{csv_path}', null_padding=true)
        WHERE amount BETWEEN {lower} AND {upper}
        GROUP BY region, category
        ORDER BY total DESC
    """
    try:
        return duckdb.sql(query).df()
    except duckdb.Error as exc:
        raise SystemExit(f"DuckDB 쿼리 실행 중 오류가 발생했습니다: {exc}")


duckdb_result = duckdb_agg(CSV_PATH, lower, upper)
print("\nDuckDB SQL 결과")
print(duckdb_result)


# timeit 성능 비교
# Polars/DuckDB는 CSV 읽기+필터+집계를 모두 포함해 측정하므로,
# Pandas도 같은 조건으로 비교하도록 CSV 읽기부터 다시 수행한다.
# CSV 읽기 -> IQR 필터 -> named aggregation까지 포함한 전체 파이프라인.
def pandas_pipeline() -> pd.DataFrame:
    try:
        data = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        raise SystemExit(f"CSV 파일을 찾을 수 없습니다: {CSV_PATH}")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise SystemExit(f"CSV 파싱 중 오류가 발생했습니다: {exc}")

    data = data[data["amount"].between(lower, upper)]
    return pandas_agg(data)


NUMBER = 20

pandas_time = timeit.timeit(pandas_pipeline, number=NUMBER)
polars_time = timeit.timeit(lambda: polars_agg(CSV_PATH, lower, upper), number=NUMBER)
duckdb_time = timeit.timeit(lambda: duckdb_agg(CSV_PATH, lower, upper), number=NUMBER)

print(f"\ntimeit 성능 비교 (반복횟수={NUMBER})")
print(f"Pandas : {pandas_time:.4f}초")
print(f"Polars : {polars_time:.4f}초")
print(f"DuckDB : {duckdb_time:.4f}초")