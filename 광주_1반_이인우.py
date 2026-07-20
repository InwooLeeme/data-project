# [실습 1] 자료구조 집계 · 컴프리헨션 · 제너레이터
# 작성자: 이인우
# 작성 목적 : 자료구조 집계 · 컴프리헨션 · 제너레이터 실습
#
# 파일 설명
# - 이 파일은 Python_Practice1_Data.json의 Sales 데이터를 기반으로
#   자료구조 집계, 컴프리헨션, Counter, defaultdict, 제너레이터 사용법을
#   한 번에 실습하기 위한 제출용 Python 실행 파일이다.
# - 실행 시 JSON 데이터를 읽고 각 요구사항별 결과를 출력한 뒤,
#   assert 기반 Checkpoint로 계산 결과와 메모리 비교 조건을 검증한다.
#
# 주요 기능
# - JSON Sales 데이터 로딩 및 필수 필드와 amount 타입 검증
# - amount 기준 거래 필터링과 지역별 총매출 계산
# - Counter를 이용한 지역별 거래 건수 집계
# - defaultdict(list)를 이용한 카테고리별 amount 목록 그룹핑
# - amount > 1000 거래 제너레이터와 리스트 버전의 메모리 크기 비교
# - month·category 기준 월별 카테고리 총매출 집계
# - top3 거래 금액 내림차순 정렬 및 Checkpoint 검증
#
# 프로그램 전체 설명
# - Python_Practice1_Data.json 파일에 저장된 Sales 데이터를 읽어온다.
# - amount 조건에 따라 거래를 필터링하고, 지역별 총매출을 계산한다.
# - Counter로 지역별 거래 건수를 집계하고, defaultdict로 카테고리별
#   amount 리스트를 만든다.
# - amount > 1000 조건을 만족하는 거래를 제너레이터로 yield 하고,
#   같은 조건의 리스트 버전과 sys.getsizeof() 결과를 비교한다.
# - month와 category를 기준으로 월별 카테고리 총매출 dict를 완성한다.
# - 마지막에 assert로 Checkpoint 조건을 검증한다.
#
# 변경내역
# - 2026-07-20 : 실습에 필요한 Python_Practice1_Data.json 데이터 준비
# - 2026-07-20 : 실습 요구사항에 맞춰 JSON 데이터 연동
# - 2026-07-20 : 리스트/딕셔너리 컴프리헨션, Counter, defaultdict, 제너레이터, 월별 카테고리 집계 기능 추가
# - 2026-07-20 : 제출 실행 시 데이터 로딩/Checkpoint 오류 메시지 출력 추가
# - 2026-07-20 : JSON 데이터가 sales 또는 Sales 키로 감싸진 경우도 읽도록 보완
# - 2026-07-20 : 각 함수의 역할과 처리 이유를 이해하기 쉽도록 주석 보강
# - 2026-07-20 : 카테고리별 합계·월별 총매출 Checkpoint 검증 추가, most_common() 동점 순서 종속성 제거, 메모리 비교 출력문 추가

from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path
import json
import sys

DATA_FILE = Path(__file__).with_name("Python_Practice1_Data.json")
REQUIRED_FIELDS = {"month", "region", "category", "amount"}
SALES_KEYS = ("sales", "Sales")


def load_sales(path=DATA_FILE):
    """
    Sales JSON 파일을 읽어서 집계에 사용할 거래 리스트를 반환한다.
    현재 데이터 파일처럼 JSON 최상위가 바로 리스트인 경우도 처리하고,
    {"sales": [...]} 또는 {"Sales": [...]}처럼 한 번 감싸진 형태도 함께 처리한다.
    파일 로딩, JSON 문법, 필수 필드, amount 타입을 여기서 먼저 확인해 두면
    이후 집계 함수에서 데이터 형식 검사를 반복하지 않아도 된다.
    """
    data_path = Path(path)

    # 파일이 없거나 JSON 문법이 잘못된 경우에는 원인을 알 수 있는 예외 메시지를 만든다.
    try:
        with data_path.open(encoding="utf-8") as file:
            raw_data = json.load(file)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Data file not found: {data_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON data: {data_path}") from exc

    sales = raw_data
    if isinstance(raw_data, dict):
        # 제공 데이터가 sales 또는 Sales 키로 감싸진 경우에도 같은 방식으로 처리한다.
        sales = next((raw_data[key] for key in SALES_KEYS if key in raw_data), None)

    # 집계 대상은 거래 목록이어야 하므로 최종 결과가 리스트인지 확인한다.
    if not isinstance(sales, list):
        raise ValueError("Sales data must be a list or a sales/Sales list.")

    # 각 거래 행이 집계에 필요한 기본 구조를 갖추었는지 확인한다.
    for index, sale in enumerate(sales, start=1):
        if not isinstance(sale, dict):
            raise ValueError(f"Row {index} must be a dictionary.")

        # month, region, category, amount 중 하나라도 없으면 정확한 집계가 어렵다.
        missing_fields = REQUIRED_FIELDS - sale.keys()
        if missing_fields:
            fields = ", ".join(sorted(missing_fields))
            raise ValueError(f"Row {index} is missing fields: {fields}")

        # amount는 합계와 정렬에 사용되므로 숫자형인지 미리 확인한다.
        if not isinstance(sale["amount"], (int, float)):
            raise ValueError(f"Row {index} amount must be a number.")

    return sales


def filter_sales_min_amount(sales, minimum):
    """
    amount가 minimum 이상인 거래만 골라 새 리스트로 만든다.
    요구사항 1에서 리스트 컴프리헨션 사용을 요구하므로,
    for 루프로 append하지 않고 조건식이 들어간 리스트 컴프리헨션으로 작성했다.
    """
    # region_total은 amount >= 1000 거래만 대상으로 계산해야 해서 먼저 필터링한다.
    return [sale for sale in sales if sale["amount"] >= minimum]


def build_region_total(sales):
    """
    필터링된 거래 목록을 받아 지역별 총매출 dict를 만든다.
    딕셔너리 컴프리헨션을 보여주기 위해 groupby 결과를 바로 dict 형태로 변환한다.
    groupby는 같은 지역끼리 붙어 있어야 제대로 묶이므로 region 기준으로 먼저 정렬한다.
    """
    # groupby는 연속된 값만 같은 그룹으로 묶기 때문에 정렬을 먼저 해 준다.
    sorted_sales = sorted(sales, key=lambda sale: sale["region"])

    # 각 region 그룹 안에서 amount만 더해 최종 결과를 {지역: 총매출} 형태로 만든다.
    return {
        region: sum(sale["amount"] for sale in region_sales)
        for region, region_sales in groupby(
            sorted_sales,
            key=lambda sale: sale["region"],
        )
    }


def count_by_region(sales):
    """
    Counter를 이용해 지역별 거래 건수를 계산한다.
    """
    # 거래 행에서 region 값만 꺼내 Counter에 넘기면 지역별 개수가 바로 계산된다.
    return Counter(sale["region"] for sale in sales)


def group_amounts_by_category(sales):
    """
    defaultdict(list)를 이용해 카테고리별 amount 목록을 모은다.
    """
    category_amounts = defaultdict(list)

    # category를 key로 사용하고, 해당 거래의 amount를 같은 카테고리 리스트에 추가한다.
    for sale in sales:
        category_amounts[sale["category"]].append(sale["amount"])
    return category_amounts


def iter_sales_over_amount(sales, minimum):
    """
    amount가 minimum보다 큰 거래를 하나씩 yield하는 제너레이터 함수.
    """
    # yield를 사용했기 때문에 이 함수는 호출 즉시 전체 결과를 저장하지 않는다.
    for sale in sales:
        if sale["amount"] > minimum:
            yield sale


def filter_sales_over_amount_list(sales, minimum):
    """
    제너레이터와 비교하기 위한 리스트 버전의 필터링 함수.
    조건은 iter_sales_over_amount와 같지만, 이 함수는 통과한 거래를 모두 리스트에 담는다.
    """
    # 비교 기준을 맞추기 위해 제너레이터 함수와 같은 amount > minimum 조건을 사용한다.
    return [sale for sale in sales if sale["amount"] > minimum]


def build_month_category_total(sales):
    """
    month와 category를 함께 기준으로 삼아 월별 카테고리 매출 합계를 만든다.
    누적 단계에서는 defaultdict를 사용해 없는 key를 자연스럽게 만들고,
    반환 단계에서는 딕셔너리 컴프리헨션으로 일반 dict 형태로 정리한다.
    """
    # grouped["2024-01"]["전자"]처럼 접근하면 바로 0부터 누적할 수 있다.
    grouped = defaultdict(lambda: defaultdict(int))

    # 1차 key는 month, 2차 key는 category로 두고 amount를 누적한다.
    for sale in sales:
        grouped[sale["month"]][sale["category"]] += sale["amount"]

    # 제출 출력이 매번 같은 순서로 보이도록 month와 category를 정렬해서 일반 dict로 바꾼다.
    return {
        month: {
            category: amount for category, amount in sorted(category_totals.items())
        }
        for month, category_totals in sorted(grouped.items())
    }


def top3_by_amount(sales):
    """
    amount가 큰 거래 3개를 내림차순으로 반환한다.
    Checkpoint에서 top3 금액 정렬이 맞는지 확인해야 하므로,
    sorted의 reverse=True 옵션으로 큰 금액이 앞에 오게 했다.
    """
    # [:3]으로 앞의 세 건만 잘라 top3 결과로 사용한다.
    return sorted(sales, key=lambda sale: sale["amount"], reverse=True)[:3]


def run_checkpoint_asserts(
    region_total,
    region_counter,
    category_amounts,
    month_category_total,
    generator,
    list_version,
    top3,
):
    """
    과제 Checkpoint 조건을 assert로 한 번에 확인한다.
    main()에서 계산한 결과를 그대로 받아 검증하므로 같은 계산을 반복하지 않는다.
    실패 시 어떤 항목이 틀렸는지 알 수 있도록 assert 메시지도 함께 작성했다.
    """
    # region_total 값 정확성 확인
    expected_region_total = {
        "광주": 4830,
        "대구": 8320,
        "대전": 6300,
        "부산": 4550,
        "서울": 17670,
        "세종": 5750,
        "울산": 7270,
        "인천": 11950,
    }
    assert region_total == expected_region_total, (
        f"region_total mismatch: expected {expected_region_total}, got {region_total}"
    )

    # Counter.most_common()의 거래 건수와 나열 순서가 모두 정확한지 확인한다.
    expected_most_common = [
        ("서울", 14),
        ("부산", 13),
        ("대구", 13),
        ("인천", 12),
        ("광주", 12),
        ("대전", 12),
        ("울산", 12),
        ("세종", 12),
    ]
    expected_region_counts = dict(expected_most_common)
    ranked_counts = region_counter.most_common()
    assert ranked_counts == expected_most_common, (
        f"most_common order mismatch: expected {expected_most_common}, "
        f"got {ranked_counts}"
    )
    count_values = [count for _, count in ranked_counts]
    assert count_values == sorted(count_values, reverse=True), (
        f"most_common is not in descending order: {ranked_counts}"
    )
    assert dict(region_counter) == expected_region_counts, (
        f"region count mismatch: expected {expected_region_counts}, "
        f"got {dict(region_counter)}"
    )

    # 카테고리별 amount 리스트(defaultdict 결과)가 올바르게 그룹핑됐는지 확인한다.
    # 카테고리별 합계가 기대값과 같으면 amount가 알맞은 key에 담긴 것으로 본다.
    expected_category_sums = {"전자": 55100, "의류": 33220, "식품": 13140}
    category_sums = {
        category: sum(amounts) for category, amounts in category_amounts.items()
    }
    assert category_sums == expected_category_sums, (
        f"category amount sum mismatch: expected {expected_category_sums}, "
        f"got {category_sums}"
    )

    # 월별 카테고리 총매출의 모든 칸을 더하면 전체 amount 합과 같아야 한다.
    expected_grand_total = 101460
    grand_total = sum(
        amount
        for category_totals in month_category_total.values()
        for amount in category_totals.values()
    )
    assert grand_total == expected_grand_total, (
        f"month_category_total grand total mismatch: "
        f"expected {expected_grand_total}, got {grand_total}"
    )

    # 제너레이터는 결과 전체를 담지 않으므로 리스트보다 얕은 메모리 크기가 작아야 한다.
    generator_size = sys.getsizeof(generator)
    list_size = sys.getsizeof(list_version)
    assert generator_size < list_size, (
        f"generator memory check failed: generator={generator_size}, list={list_size}"
    )

    # top3가 amount 기준 내림차순으로 정렬되었는지 확인
    top3_amounts = [sale["amount"] for sale in top3]
    expected_top3_amounts = [2500, 2200, 2200]
    assert top3_amounts == expected_top3_amounts, (
        f"top3 amount order mismatch: expected {expected_top3_amounts}, got {top3_amounts}"
    )


def main():
    """
    실습 1의 전체 흐름을 순서대로 실행한다.
    데이터 로딩부터 각 요구사항 계산, Checkpoint 검증, 결과 출력까지 한 곳에서 관리한다.
    예외가 발생하면 실행을 중단하고 오류 메시지를 출력한다.
    """
    try:
        sales = load_sales()
    except (FileNotFoundError, ValueError) as error:
        print(f"[오류] 데이터 로딩 실패: {error}")
        return

    # 1) amount >= 1000 거래만 남긴 뒤, 그 거래들로 지역별 총매출을 계산한다.
    high_value_sales = filter_sales_min_amount(sales, 1000)
    region_total = build_region_total(high_value_sales)

    # 2) Counter는 거래 건수, defaultdict는 카테고리별 amount 목록에 사용한다.
    region_counter = count_by_region(sales)
    category_amounts = group_amounts_by_category(sales)

    # 3) 같은 조건의 제너레이터와 리스트를 만들어 메모리 크기 차이를 확인한다.
    generator = iter_sales_over_amount(sales, 1000)
    list_version = filter_sales_over_amount_list(sales, 1000)

    # 4) 월별 카테고리 매출 집계와 금액 기준 top3 정렬 결과를 만든다.
    month_category_total = build_month_category_total(sales)
    top3 = top3_by_amount(sales)

    # 제출 전 Checkpoint가 모두 통과하는지 확인
    try:
        run_checkpoint_asserts(
            region_total=region_total,
            region_counter=region_counter,
            category_amounts=category_amounts,
            month_category_total=month_category_total,
            generator=generator,
            list_version=list_version,
            top3=top3,
        )
    except AssertionError as error:
        print(f"[오류] Checkpoint 검증 실패: {error}")
        return

    print("1) amount >= 1000 rows:", len(high_value_sales))
    print("1) 지역별 총 매출:", region_total)
    print("2) 지역별 거래 건수:", region_counter.most_common())
    print("2) 카테고리별 amount 리스트:", dict(category_amounts))
    generator_size = sys.getsizeof(generator)
    list_size = sys.getsizeof(list_version)
    print(f"3) generator_size: {generator_size} bytes")
    print(f"3) list_size: {list_size} bytes")
    print(
        f"3) 메모리 비교: 제너레이터가 리스트보다 {list_size - generator_size} bytes 작다"
    )
    print("4) month_category_total:", month_category_total)
    print("Checkpoint top3:", [(sale["region"], sale["amount"]) for sale in top3])
    print("All checkpoint asserts passed.")


if __name__ == "__main__":
    main()
