"""
 파일명 : 광주_1반_이인우.py
 작성자 : 이인우
 작성 목적 : 파일 I/O, 예외 처리, Pydantic 검증 파이프라인 실습

 파일 설명
 - 이 파일은 Python_Practice2_Data.json의 Sales 데이터를 입력으로 삼아
   안전한 파일 읽기(try-except-finally), Pydantic v2 스키마 검증,
   valid/errors 분리 파이프라인, 결과 파일 저장·재로딩 확인을
   한 번에 실습하기 위한 제출용 Python 실행 파일이다.
 - 실행 시 각 단계 결과를 출력한 뒤 assert 기반 Checkpoint로 검증한다.

 주요 기능
 - safe_load_csv() : CSV 파일을 dict 리스트로 읽고, 실패 시 None을 반환한다.
 - SalesRecord     : month/region/amount/category 규칙을 정의한 Pydantic v2 모델
 - validate_records() : raw_data를 순회하며 valid와 errors로 분리한다.
 - convert_json_to_csv() : 원본 JSON 전체를 CSV 파일로 변환한다.
 - save_valid_csv() / save_errors_json() : 검증 결과를 각각 CSV·JSON으로 저장한다.

 프로그램 전체 설명
 - 원본 JSON(Python_Practice2_Data.json)에서 정상 레코드 4건을 읽어오고,
   여기에 검증 실패를 유도하는 잘못된 레코드 3건을 붙여 raw_data(7건)를 만든다.
   (원본 JSON은 100건 모두 유효하여 Checkpoint의 errors 3건이 나올 수 없으므로, 오류 케이스는 실습 목적에 맞게 의도적으로 추가했다.)
 - 원본 JSON 전체는 별도 CSV(Python_Practice2_Data.csv)로 변환해 파일 입출력 흐름을 확인한다.
 - raw_data를 SalesRecord로 변환하며 성공은 valid, 실패는 errors로 분리한다.
 - valid는 CSV로, errors는 JSON(ensure_ascii=False)으로 저장한다.
 - 저장한 CSV를 safe_load_csv()로 다시 읽어 건수가 보존됐는지 확인한다.
 - 마지막에 assert로 Checkpoint 조건(None 반환, 4건/3건, 재로딩 4건)을 검증한다.

 변경내역
 - 2026-07-20 : 실습 2 최초 작성 (safe_load_csv, SalesRecord, 검증 파이프라인, 저장·재로딩)
 - 2026-07-20 : Optional import를 제거하고 category 타입 표기를 str | None으로 간결화
 - 2026-07-20 : 저장 함수의 중복 except를 OSError로 정리, 원본 JSON 로딩 실패 시 조기 종료 추가, 진행 단계 출력을 logger.info로 통일
 - 2026-07-20 : Python_Practice2_Data.json 전체를 CSV로 변환하는 convert_json_to_csv 추가
"""
import csv
import json
import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SOURCE_JSON = "Python_Practice2_Data.json"
SOURCE_CSV = "Python_Practice2_Data.csv"
VALID_CSV = "valid_records.csv"
ERRORS_JSON = "errors.json"
MISSING_CSV = "not_exists.csv"

# 테스트용 검증 실패를 유도하기 위해 의도적으로 규칙을 어긴 레코드들.
INVALID_SAMPLES = [
    {"region": "", "category": "전자", "amount": 500, "month": "2024-01"},
    {"region": "부산", "category": "의류", "amount": -100, "month": "2024-02"},
    {"region": "대구", "category": "식품", "amount": 300},
]


# 함수명: safe_load_csv
# 기능: CSV 파일을 안전하게 읽어서 각 행을 dict 형태로 담은 리스트를 반환한다.
# 파라미터:
# - path: 읽어올 CSV 파일 경로. 문자열 경로 또는 pathlib.Path 객체를 받을 수 있다.
# 반환값:
# - 성공 시: CSV 헤더를 key로 사용하는 dict 리스트
# - 실패 시: 파일 없음, 권한 오류, 인코딩/CSV 오류가 발생하면 None
# 예외 처리:
# - FileNotFoundError, PermissionError, UnicodeDecodeError, csv.Error를 처리한다.
# - 성공/실패와 관계없이 finally에서 "로딩 종료"를 출력한다.
def safe_load_csv(path):
    try:
        with open(path, encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
    except FileNotFoundError:
        logger.error("파일을 찾을 수 없습니다: %s", path)
        return None
    except PermissionError:
        logger.error("파일을 읽을 권한이 없습니다: %s", path)
        return None
    except (UnicodeDecodeError, csv.Error) as error:
        logger.error("CSV 형식이 올바르지 않습니다: %s (%s)", path, error)
        return None
    else:
        logger.info("CSV 로딩 성공: %s (%d건)", path, len(rows))
        return rows
    finally:
        print("로딩 종료")


# 함수명: load_source_json
# 기능: 원본 JSON 파일에서 Pydantic 검증에 사용할 정상 데이터 일부를 읽어온다.
# 파라미터:
# - path: 읽어올 JSON 파일 경로. 기본값은 Python_Practice2_Data.json이다.
# - limit: 원본 데이터 중 앞에서 몇 건을 사용할지 정하는 정수값. 기본값은 4이다.
# 반환값:
# - 성공 시: JSON 데이터 리스트 중 앞에서 limit건만 자른 리스트
# - 실패 시: 파일/권한/JSON 문법 오류가 발생하면 빈 리스트
def load_source_json(path=SOURCE_JSON, limit=4):
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, PermissionError) as error:
        logger.error("원본 JSON을 읽을 수 없습니다: %s (%s)", path, error)
        return []
    except json.JSONDecodeError as error:
        logger.error("원본 JSON 문법이 올바르지 않습니다: %s (%s)", path, error)
        return []
    else:
        logger.info("원본 JSON 로딩 성공: %s (%d건 중 %d건 사용)", path, len(data), limit)
        return data[:limit]
    finally:
        print("로딩 종료")


# 함수명: convert_json_to_csv
# 기능: Python_Practice2_Data.json 전체 데이터를 CSV 파일로 변환해 저장한다.
# 반환값:
# - 성공 시: 저장한 데이터 건수
# - 실패 시: 파일/JSON/CSV 저장 오류가 발생하면 0
def convert_json_to_csv(json_path=SOURCE_JSON, csv_path=SOURCE_CSV):
    try:
        with open(json_path, encoding="utf-8") as file:
            rows = json.load(file)

        with open(csv_path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=SalesRecord.model_fields)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, json.JSONDecodeError, csv.Error) as error:
        logger.error("JSON to CSV 변환 실패: %s -> %s (%s)", json_path, csv_path, error)
        return 0

    logger.info("JSON to CSV 변환 완료: %s (%d건)", csv_path, len(rows))
    return len(rows)


# 모델명: SalesRecord
# 기능: 매출 데이터 1행이 과제 조건에 맞는지 검증하는 Pydantic v2 스키마이다.
# 필드:
# - month: 필수 문자열. 비어 있으면 ValidationError가 발생한다.
# - region: 필수 문자열. 비어 있으면 ValidationError가 발생한다.
# - amount: 필수 정수. 0보다 커야 한다.
# - category: 선택 문자열. 값이 없어도 None으로 처리된다.
class SalesRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    month: str = Field(min_length=1)
    region: str = Field(min_length=1)
    amount: int = Field(gt=0)
    category: str | None = None


# 함수명: validate_records
# 기능: raw_data 전체를 순회하면서 SalesRecord 모델로 변환하고 성공/실패를 분리한다.
# 파라미터:
# - raw_data: 검증할 원본 데이터 리스트. 각 원소는 매출 1건을 나타내는 dict여야 한다.
# 반환값:
# - valid: 검증에 성공한 SalesRecord 객체 리스트
# - errors: 검증에 실패한 행과 오류 내용을 담은 {"row": 원본 행, "error": 오류 내용} 리스트
# 예외 처리:
# - Pydantic 검증 실패만 의미하므로 ValidationError만 except로 처리한다.
def validate_records(raw_data):
    valid = []
    errors = []

    for row in raw_data:
        try:
            valid.append(SalesRecord(**row))
        except ValidationError as error:
            detail = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in error.errors()
            )
            logger.error("검증 실패 %s -> %s", row, detail)
            errors.append({"row": row, "error": detail})

    logger.info("검증 결과: valid %d건 / errors %d건", len(valid), len(errors))
    return valid, errors


# 함수명: save_valid_csv
# 기능: 검증에 성공한 SalesRecord 객체들을 CSV 파일로 저장한다.
# 파라미터:
# - valid: CSV로 저장할 SalesRecord 객체 리스트
# - path: 저장할 CSV 파일 경로. 기본값은 valid_records.csv이다.
# 반환값:
# - 성공 시: True
# - 실패 시: 권한 또는 파일 시스템 오류가 발생하면 False
def save_valid_csv(valid, path=VALID_CSV):
    fieldnames = list(SalesRecord.model_fields)

    try:
        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(record.model_dump() for record in valid)
    except OSError as error:
        logger.error("CSV 저장 실패: %s (%s)", path, error)
        return False
    else:
        logger.info("CSV 저장 완료: %s (%d건)", path, len(valid))
        return True
    finally:
        print("저장 종료")


# 함수명: save_errors_json
# 기능: 검증에 실패한 데이터 목록을 JSON 파일로 저장한다.
# 파라미터:
# - errors: {"row": 원본 행, "error": 오류 내용} 형태의 dict 리스트
# - path: 저장할 JSON 파일 경로. 기본값은 errors.json이다.
# 반환값:
# - 성공 시: True
# - 실패 시: 권한 또는 파일 시스템 오류가 발생하면 False
def save_errors_json(errors, path=ERRORS_JSON):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(errors, file, ensure_ascii=False, indent=2)
    except OSError as error:
        logger.error("JSON 저장 실패: %s (%s)", path, error)
        return False
    else:
        logger.info("JSON 저장 완료: %s (%d건)", path, len(errors))
        return True
    finally:
        print("저장 종료")


# 함수명: main
# 기능: 실습 2의 전체 과정을 순서대로 실행하는 진입점 함수이다.
# 파라미터:
# - 없음. 파일 경로와 샘플 데이터는 상단 상수(SOURCE_JSON, VALID_CSV 등)를 사용한다.
# 반환값:
# - 없음. 대신 assert와 print/logger 출력으로 Checkpoint 통과 여부를 확인한다.
def main():
    missing = safe_load_csv(MISSING_CSV)
    assert missing is None, f"없는 파일은 None이어야 합니다: {missing}"
    logger.info("1) 없는 파일 로딩 결과: %s", missing)

    converted_count = convert_json_to_csv()
    assert converted_count > 0, "원본 JSON을 CSV로 변환하지 못했습니다"
    logger.info("2) 원본 JSON CSV 변환 건수: %d", converted_count)

    source = load_source_json()
    if not source:
        logger.error("원본 JSON을 읽지 못해 검증을 중단합니다: %s", SOURCE_JSON)
        return

    raw_data = source + INVALID_SAMPLES
    logger.info("3) raw_data 건수: %d", len(raw_data))

    valid, errors = validate_records(raw_data)
    assert len(valid) == 4, f"valid는 4건이어야 합니다: {len(valid)}"
    assert len(errors) == 3, f"errors는 3건이어야 합니다: {len(errors)}"
    logger.info("4) valid: %d / errors: %d", len(valid), len(errors))
    for item in errors:
        logger.info("   - 오류 내용: %s", item["error"])

    assert save_valid_csv(valid), "valid CSV 저장에 실패했습니다"
    assert save_errors_json(errors), "errors JSON 저장에 실패했습니다"

    reloaded = safe_load_csv(VALID_CSV)
    assert reloaded is not None, "저장한 CSV를 다시 읽지 못했습니다"
    assert len(reloaded) == 4, f"재로딩 건수는 4건이어야 합니다: {len(reloaded)}"
    logger.info("5) 재로딩 건수: %d", len(reloaded))

    logger.info("All checkpoint asserts passed.")


if __name__ == "__main__":
    main()
