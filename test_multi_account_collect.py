#!/usr/bin/env python
"""
다중회사 주요계정 수집 테스트 스크립트

fill_basic_indicators_multi 및 배치 플로우를 소수 기업으로만 호출하여
데이터 수신·파싱·결과를 로그로 확인합니다.

사용법:
    python test_multi_account_collect.py [--count N] [--save]
"""
import argparse
import os
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.apps import apps as django_apps

from apps.dart.client import DartClient
from apps.service.dart import DartDataService
from apps.service.orchestrator import DataOrchestrator


# API에서 저장하는 연간 재무 필드 (DART 주요계정 + 확장)
YEARLY_FIELDS_FROM_API = [
    'revenue', 'operating_income', 'net_income', 'total_assets', 'total_equity',
    'current_assets', 'noncurrent_assets', 'current_liabilities', 'noncurrent_liabilities',
    'total_liabilities', 'capital_stock', 'retained_earnings', 'profit_before_tax',
]


def _format_val(val):
    if val is None:
        return "(없음)"
    if isinstance(val, (int, float)) and val == 0:
        return "0"
    return str(val)


def _check_yearly_consistency(yd) -> list[str]:
    """연도별 재무 일관성 검사 (자산=유동+비유동, 부채=유동+비유동). 오차 시 경고 문자열 반환."""
    warnings = []
    # 허용 오차: 0.01% 또는 1원 (반올림/기타항목으로 인한 미세 차이 허용)
    def tol(x):
        return max(1, abs(x) // 10000) if x else 1
    ca = getattr(yd, 'current_assets', None)
    na = getattr(yd, 'noncurrent_assets', None)
    ta = getattr(yd, 'total_assets', None)
    if ca is not None and na is not None and ta is not None:
        diff = abs((ca + na) - ta)
        if diff > tol(ta):
            warnings.append("연도 {}: current_assets+noncurrent_assets != total_assets (차이 {})".format(yd.year, diff))
    cl = getattr(yd, 'current_liabilities', None)
    nl = getattr(yd, 'noncurrent_liabilities', None)
    tl = getattr(yd, 'total_liabilities', None)
    if cl is not None and nl is not None and tl is not None:
        diff = abs((cl + nl) - tl)
        if diff > tol(tl):
            warnings.append("연도 {}: current_liabilities+noncurrent_liabilities != total_liabilities (차이 {})".format(yd.year, diff))
    return warnings


def verify_db_saved(corp_codes_success: list[str]) -> None:
    """배치 저장 후 DB에 실제로 반영되었는지 조회하여, 연도별·필드별 전부 출력."""
    if not corp_codes_success:
        return
    CompanyModel = django_apps.get_model('apps', 'Company')
    print("[테스트] DB 저장 확인 (성공한 corp_code {}건)".format(len(corp_codes_success)))
    for corp_code in corp_codes_success:
        try:
            company = CompanyModel.objects.prefetch_related('yearly_data').get(corp_code=corp_code)
            yd_list = list(company.yearly_data.all().order_by('year'))
            print("  corp_code={}, company_name={}, last_collected_at={}, 연도별데이터 {}건".format(
                company.corp_code,
                (company.company_name or '')[:40],
                company.last_collected_at,
                len(yd_list),
            ))
            for yd in yd_list:
                print("    [연도 {}]".format(yd.year))
                for f in YEARLY_FIELDS_FROM_API:
                    v = getattr(yd, f, None)
                    print("      {} = {}".format(f, _format_val(v)))
            # 저장된 필드 요약: 연도 중 하나라도 값이 있는 필드
            filled = set()
            for yd in yd_list:
                for f in YEARLY_FIELDS_FROM_API:
                    v = getattr(yd, f, None)
                    if v is not None and (not isinstance(v, (int, float)) or v != 0):
                        filled.add(f)
            print("    [저장된 필드 요약] {} (총 {}개)".format(sorted(filled), len(filled)))
            # 재무 일관성 검사 (자산/부채 합계)
            all_ok = True
            for yd in yd_list:
                for w in _check_yearly_consistency(yd):
                    print("    [일관성 경고] {}".format(w))
                    all_ok = False
            if all_ok and yd_list:
                print("    [재무 일관성] 자산/부채 합계 이상 없음")
        except CompanyModel.DoesNotExist:
            print("  corp_code={}: DB에 Company 없음 (저장 실패 가능)".format(corp_code))


def parse_stock_codes_file(stock_codes_file: Path, max_count: int) -> list[str]:
    """종목코드.md에서 상위 max_count개 종목코드만 반환"""
    if not stock_codes_file.exists():
        print("[테스트] 오류: 파일을 찾을 수 없습니다:", stock_codes_file)
        return []
    stock_codes = []
    with open(stock_codes_file, 'r', encoding='utf-8') as f:
        for line in f.readlines()[1:]:
            code = line.strip()
            if code:
                stock_codes.append(code)
                if len(stock_codes) >= max_count:
                    break
    return stock_codes


def get_corp_codes_for_test(dart_client: DartClient, count: int) -> list[str]:
    """종목코드.md 상위에서 count개 corp_code 확보 (변환 실패는 스킵). 삼성전자 등 시드 우선 시도."""
    seed_stock_codes = ['005930', '000660', '035420']
    corp_codes = []
    for sc in seed_stock_codes:
        if len(corp_codes) >= count:
            break
        try:
            cc = dart_client._get_corp_code_by_stock_code(sc)
            if cc and cc not in corp_codes:
                corp_codes.append(cc)
        except Exception:
            continue
    if len(corp_codes) >= count:
        return corp_codes[:count]
    stock_codes_file = BASE_DIR / '종목코드.md'
    stock_codes = parse_stock_codes_file(stock_codes_file, max_count=count * 5)
    for sc in stock_codes:
        if len(corp_codes) >= count:
            break
        try:
            cc = dart_client._get_corp_code_by_stock_code(sc)
            if cc and cc not in corp_codes:
                corp_codes.append(cc)
        except Exception:
            continue
    return corp_codes[:count]


def main():
    parser = argparse.ArgumentParser(description='다중회사 주요계정 수집 테스트')
    parser.add_argument('--count', type=int, default=3, help='테스트할 회사 수 (기본 3)')
    parser.add_argument('--save', action='store_true', help='배치 실행 및 DB 저장까지 수행')
    parser.add_argument('--stock', type=str, default='', help='특정 종목코드만 테스트 (예: 012210)')
    args = parser.parse_args()

    count = max(1, min(args.count, 100))
    print("[테스트] 다중계정 수집 테스트 시작 (회사 수={}, --save={})".format(count, args.save))
    print("-" * 60)

    dart_client = DartClient()
    print("[테스트] 기업 고유번호 XML 로딩 중...")
    dart_client.load_corp_code_xml()
    print("[테스트] XML 로드 완료 (총 {}개 매핑)".format(len(dart_client._corp_code_mapping_cache)))

    if args.stock:
        sc = str(args.stock).strip().zfill(6)
        cc = dart_client._get_corp_code_by_stock_code(sc) if sc else None
        if not cc:
            print("[테스트] 오류: 종목코드 {}에 해당하는 corp_code를 찾을 수 없습니다.".format(args.stock))
            return 1
        corp_codes = [cc]
    else:
        corp_codes = get_corp_codes_for_test(dart_client, count)
    if not corp_codes:
        print("[테스트] 오류: corp_code를 1개도 확보하지 못했습니다. 종목코드.md 및 XML 캐시를 확인하세요.")
        return 1
    print("[테스트] corp_codes: {} ({}개)".format(corp_codes, len(corp_codes)))

    dart_service = DartDataService()
    years = dart_service._get_recent_years(5)
    print("[테스트] years: {}".format(years))
    print("-" * 60)

    try:
        company_data_map = dart_service.fill_basic_indicators_multi(corp_codes, years)
    except Exception as e:
        print("[테스트] 오류: fill_basic_indicators_multi 실패:", e)
        traceback.print_exc()
        return 1

    print("[테스트] fill_basic_indicators_multi 반환: {}개 회사".format(len(company_data_map)))
    requested_set = set(corp_codes)
    returned_set = set(company_data_map.keys())
    missing = requested_set - returned_set
    if missing:
        corp_to_stock = {v: k for k, v in dart_client._corp_code_mapping_cache.items()}
        missing_with_stock = [
            "{} (종목코드 {})".format(cc, corp_to_stock.get(cc, "?"))
            for cc in sorted(missing)
        ]
        print("[테스트] 사업보고서 없음 또는 데이터 미수신 ({}건): {}".format(
            len(missing), missing_with_stock
        ))
    for corp_code, company_data in company_data_map.items():
        yd_list = company_data.yearly_data
        years_found = [yd.year for yd in yd_list] if yd_list else []
        sample = None
        if yd_list:
            sample = yd_list[0]
        print("[테스트] 회사 {}: 연도 수 {}, 연도={}".format(
            corp_code, len(yd_list), years_found
        ))
        if sample is not None:
            print("         샘플(연도 {}): revenue={}, operating_income={}, total_assets={}, total_equity={}, current_assets={}, total_liabilities={}".format(
                sample.year,
                getattr(sample, 'revenue', None),
                getattr(sample, 'operating_income', None),
                getattr(sample, 'total_assets', None),
                getattr(sample, 'total_equity', None),
                getattr(sample, 'current_assets', None),
                getattr(sample, 'total_liabilities', None),
            ))
    print("-" * 60)

    if args.save:
        print("[테스트] 배치 실행 (DB 저장 포함)...")
        orchestrator = DataOrchestrator()
        try:
            batch_results = orchestrator.collect_companies_data_batch(corp_codes)
        except Exception as e:
            print("[테스트] 오류: collect_companies_data_batch 실패:", e)
            traceback.print_exc()
            return 1
        for r in batch_results:
            print("[테스트] 배치 결과: corp_code={}, status={}, passed_all_filters={}, company_name={}, error={}".format(
                r.get('corp_code'),
                r.get('status'),
                r.get('passed_all_filters'),
                r.get('company_name', '')[:30] if r.get('company_name') else '',
                r.get('error'),
            ))
        print("[테스트] 배치 완료: 성공 {}개, 실패 {}개".format(
            sum(1 for r in batch_results if r.get('status') == 'success'),
            sum(1 for r in batch_results if r.get('status') == 'failed'),
        ))
        success_corp_codes = [r.get('corp_code') for r in batch_results if r.get('status') == 'success' and r.get('corp_code')]
        verify_db_saved(success_corp_codes)
    else:
        print("[테스트] --save 미지정: DB 저장 생략. 배치까지 테스트하려면 --save 를 붙여 실행하세요.")

    print("-" * 60)
    print("[테스트] 다중계정 수집 테스트 종료 (오류 없음)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
