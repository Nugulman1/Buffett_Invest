#!/usr/bin/env python
"""
기업 수집 테스트 스크립트

다중회사 주요계정 + 다중회사 주요재무지표(지표명 포함) 수집을 소수 기업으로 실행하고
DB 저장·지표(idx_nm) 반영 여부를 확인합니다.

사용법:
    python test_company_collect.py [--count N] [--save]
    python test_company_collect.py --stock 005930 [--save]
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

# 다중회사 주요재무지표.md 기준 수익성지표(M210000) 예상 목록
EXPECTED_INDICATOR_CODES = [
    'M211100', 'M211200', 'M211250', 'M211300', 'M211400', 'M211550',
    'M211800', 'M212000', 'M212100', 'M212200', 'M212300', 'M212400',
    'M212500', 'M212600', 'M212700',
]


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
    """종목코드 시드 + 종목코드.md에서 count개 corp_code 확보"""
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


def _fmt_val(val):
    if val is None:
        return "(없음)"
    if isinstance(val, float) and 0 < abs(val) < 1:
        return "{:.4f} ({:.2f}%)".format(val, val * 100)
    return str(val)


def _report_expected_vs_actual(actual_all: set, by_corp: dict) -> None:
    """예상 지표 vs 실제 수집된 지표 비교 후 콘솔 출력"""
    expected_set = set(EXPECTED_INDICATOR_CODES)
    found = sorted(expected_set & actual_all)
    missing = sorted(expected_set - actual_all)
    extra = sorted(actual_all - expected_set)
    print("[검증] 다중회사 주요재무지표.md 기준 (수익성지표 15개)")
    print("[검증]   예상: {}개, 실제 수집: {}개".format(len(expected_set), len(actual_all)))
    print("[검증]   들어온 지표 ({}개): {}".format(len(found), found))
    if missing:
        print("[검증]   안 들어온 지표 ({}개): {}".format(len(missing), missing))
    if extra:
        print("[검증]   예상 외 수집 ({}개): {}".format(len(extra), extra))


def verify_db_saved(corp_codes_success: list[str], verbose: bool = True) -> None:
    """배치 저장 후 주요계정(YearlyFinancialData) + 주요재무지표(YearlyFinancialIndicator) 로그 출력"""
    if not corp_codes_success:
        return
    CompanyModel = django_apps.get_model('apps', 'Company')
    YearlyDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    IndicatorModel = django_apps.get_model('apps', 'YearlyFinancialIndicator')

    for corp_code in corp_codes_success:
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            print("[로그] corp_code={}: DB에 Company 없음".format(corp_code))
            continue

        name_short = (company.company_name or '')[:35]
        print("[로그] ----- 회사 {} ({}) -----".format(corp_code, name_short))

        # 주요계정(연간 재무) 로그
        yd_list = list(YearlyDataModel.objects.filter(company=company).order_by('year'))
        print("[로그] [주요계정] 연도별 데이터 {}건".format(len(yd_list)))
        for yd in yd_list:
            print("[로그]   연도 {}: revenue={}, operating_income={}, net_income={}, total_assets={}, total_equity={}".format(
                yd.year, _fmt_val(yd.revenue), _fmt_val(yd.operating_income),
                _fmt_val(yd.net_income), _fmt_val(yd.total_assets), _fmt_val(yd.total_equity),
            ))
            if verbose:
                print("[로그]     operating_margin={}, roe={}".format(
                    _fmt_val(yd.operating_margin), _fmt_val(yd.roe),
                ))

        # 주요재무지표(지표명·값) 로그
        indicators = list(
            IndicatorModel.objects.filter(company=company).order_by('year', 'idx_code')
        )
        print("[로그] [주요재무지표] 지표 {}건 (idx_code, 지표명, 값)".format(len(indicators)))
        by_year = {}
        for ind in indicators:
            by_year.setdefault(ind.year, []).append(ind)
        for year in sorted(by_year.keys()):
            rows = by_year[year]
            print("[로그]   연도 {}: {}건".format(year, len(rows)))
            for r in rows:
                nm = r.idx_nm or r.idx_code
                print("[로그]     {} | {} | {}".format(r.idx_code, nm, _fmt_val(r.idx_val)))
        print("[로그] -----")


def verify_numeric_consistency(corp_codes_success: list[str]) -> None:
    """
    수치 검증: 지표값(idx_val)이 비율 소수 범위(-2~2) 내인지 확인.
    ROE는 DART M211550에서 채우므로 별도 계산 비교 없음.
    """
    if not corp_codes_success:
        return
    CompanyModel = django_apps.get_model('apps', 'Company')
    IndicatorModel = django_apps.get_model('apps', 'YearlyFinancialIndicator')
    print("[수치검증] 지표값(idx_val) 비율 범위 확인 (소수 -2~2 예상)")
    out_of_range = 0
    for corp_code in corp_codes_success:
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            continue
        for ind in IndicatorModel.objects.filter(company=company):
            if ind.idx_val is not None:
                v = float(ind.idx_val)
                if v < -2.0 or v > 2.0:
                    out_of_range += 1
                    print("[수치검증]   {} 연도 {} {}: idx_val={} (범위 밖)".format(
                        corp_code, ind.year, ind.idx_code, ind.idx_val
                    ))
    if out_of_range == 0:
        print("[수치검증] 모든 지표값이 -2~2 범위 내")
    else:
        print("[수치검증] 범위 밖 지표 {}건 (퍼센트 100 초과 등 확인)".format(out_of_range))


def main():
    parser = argparse.ArgumentParser(description='기업 수집 테스트 (주요계정 + 주요재무지표)')
    parser.add_argument('--count', type=int, default=2, help='테스트할 회사 수 (기본 2)')
    parser.add_argument('--save', action='store_true', help='배치 실행 및 DB 저장 후 지표 저장 확인')
    parser.add_argument('--stock', type=str, default='', help='특정 종목코드만 테스트 (예: 005930)')
    args = parser.parse_args()

    count = max(1, min(args.count, 100))
    print("[테스트] 기업 수집 테스트 시작 (회사 수={}, --save={})".format(count, args.save))
    print("-" * 60)

    dart_client = DartClient()
    print("[테스트] 기업 고유번호 XML 로딩 중...")
    dart_client.load_corp_code_xml()
    print("[테스트] XML 로드 완료")

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
        print("[테스트] 오류: corp_code를 1개도 확보하지 못했습니다.")
        return 1
    print("[테스트] corp_codes: {} ({}개)".format(corp_codes, len(corp_codes)))

    dart_service = DartDataService()
    years = dart_service._get_recent_years(5)
    print("[테스트] 수집 대상 연도: {}".format(years))
    print("-" * 60)

    if not args.save:
        print("[테스트] --save 미지정: API 호출만 수행 후 수신 데이터 로그 출력 (DB 저장 없음)")
        try:
            company_data_map = dart_service.fill_basic_indicators_multi(corp_codes, years)
            print("[로그] fill_basic_indicators_multi 반환: {}개 회사".format(len(company_data_map)))
            for cc, data in company_data_map.items():
                yd_list = getattr(data, 'yearly_data', []) or []
                print("[로그]   corp_code={}: 연도 {}개, 샘플(첫 연도) revenue={}, total_assets={}".format(
                    cc, len(yd_list),
                    getattr(yd_list[0], 'revenue', None) if yd_list else None,
                    getattr(yd_list[0], 'total_assets', None) if yd_list else None,
                ))
            values_map, names_map = dart_service.fill_financial_indicators_multi(corp_codes, years)
            print("[로그] fill_financial_indicators_multi 반환: 값 {}개 회사, 지표명 {}개 회사".format(
                len(values_map), len(names_map),
            ))
            for cc in list(values_map.keys())[:3]:
                by_year = values_map.get(cc, {})
                total_indicators = sum(len(v) for v in by_year.values())
                print("[로그]   corp_code={}: 연도 {}개, 지표 총 {}건".format(cc, len(by_year), total_indicators))
                for y in sorted(by_year.keys())[:1]:
                    inds = by_year[y]
                    names = names_map.get(cc, {}).get(y, {})
                    for idx_code, val in list(inds.items())[:5]:
                        nm = names.get(idx_code, idx_code)
                        print("[로그]     연도 {} | {} | {} | {}".format(y, idx_code, nm, _fmt_val(val)))
            actual_all = set()
            by_corp = {}
            for cc, by_year in values_map.items():
                s = set()
                for inds in by_year.values():
                    s.update(inds.keys())
                actual_all.update(s)
                by_corp[cc] = s
            _report_expected_vs_actual(actual_all, by_corp)
        except Exception as e:
            print("[테스트] 오류:", e)
            traceback.print_exc()
            return 1
        print("-" * 60)
        print("[테스트] DB 저장을 하려면 --save 를 붙여 실행하세요.")
        return 0

    print("[테스트] 배치 실행 (주요계정 + 주요재무지표 수집 및 DB 저장)...")
    orchestrator = DataOrchestrator()
    try:
        batch_results = orchestrator.collect_companies_data_batch(corp_codes)
    except Exception as e:
        print("[테스트] 오류: collect_companies_data_batch 실패:", e)
        traceback.print_exc()
        return 1

    for r in batch_results:
        print("[테스트] 결과: corp_code={}, status={}, passed={}, name={}, error={}".format(
            r.get('corp_code'),
            r.get('status'),
            r.get('passed_all_filters'),
            (r.get('company_name') or '')[:25],
            r.get('error'),
        ))
    success_corp_codes = [
        r.get('corp_code') for r in batch_results
        if r.get('status') == 'success' and r.get('corp_code')
    ]
    print("[테스트] 성공 {}개, 실패 {}개".format(
        len(success_corp_codes),
        len(batch_results) - len(success_corp_codes),
    ))
    print("-" * 60)
    print("[로그] DB 저장 내용 확인 (주요계정 + 주요재무지표)")
    verify_db_saved(success_corp_codes, verbose=True)
    IndicatorModel = django_apps.get_model('apps', 'YearlyFinancialIndicator')
    CompanyModel = django_apps.get_model('apps', 'Company')
    actual_all = set()
    by_corp = {}
    for corp_code in success_corp_codes:
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            continue
        codes = set(
            IndicatorModel.objects.filter(company=company)
            .values_list('idx_code', flat=True)
            .distinct()
        )
        actual_all.update(codes)
        by_corp[corp_code] = codes
    _report_expected_vs_actual(actual_all, by_corp)
    print("-" * 60)
    verify_numeric_consistency(success_corp_codes)
    print("-" * 60)
    print("[테스트] 기업 수집 테스트 종료")
    return 0


if __name__ == '__main__':
    sys.exit(main())
