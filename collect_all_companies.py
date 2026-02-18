#!/usr/bin/env python
"""
전체 기업 데이터 수집 스크립트

종목코드.md 파일에서 기업 코드를 읽어서 재무 데이터를 수집합니다.

사용법:
    python collect_all_companies.py [--limit N]
"""
import os
import sys
import time
import logging
from pathlib import Path

# Django 설정
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.apps import apps as django_apps
from apps.service.orchestrator import DataOrchestrator
from apps.dart.client import DartClient
from apps.ecos.client import EcosClient
from apps.service.db import should_collect_company

logger = logging.getLogger(__name__)


def parse_stock_codes_file(stock_codes_file: Path) -> list:
    """종목코드.md 파일 파싱 (모든 종목코드 반환)"""
    if not stock_codes_file.exists():
        logger.error('파일을 찾을 수 없습니다: %s', stock_codes_file)
        return []
    
    stock_codes = []
    with open(stock_codes_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
        # 첫 줄 "종목코드" 헤더 제외
        for line in lines[1:]:
            stock_code = line.strip()
            # 빈 줄만 제외
            if stock_code:
                stock_codes.append(stock_code)
    
    return stock_codes


def filter_stock_codes_by_db(stock_codes: list, dart_client: DartClient, limit: int) -> tuple[dict, dict]:
    """
    DB 체크로 수집 필요한 종목코드만 필터링
    
    - 종목코드 → corp_code 변환
    - DB에서 수집 필요 여부 확인 (should_collect_company)
    - limit 개수만큼만 반환
    
    Returns:
        (filtered_dict, skip_stats) 튜플
    """
    filtered = {}
    
    # 스킵 통계
    skip_stats = {
        'no_corp_code': 0,  # 종목코드 변환 실패
        'already_collected': 0,  # 이미 수집됨 (4월 1일 기준)
        'conversion_error': 0,  # 변환 예외 발생
        'total_checked': 0,  # 실제 확인한 개수
    }
    
    for stock_code in stock_codes:
        skip_stats['total_checked'] += 1
        try:
            # 종목코드 → corp_code 변환
            corp_code = dart_client._get_corp_code_by_stock_code(stock_code)
            if not corp_code:
                skip_stats['no_corp_code'] += 1
                continue
            
            # DB 체크 (4월 1일 기준 재수집 로직 포함)
            if should_collect_company(corp_code):
                filtered[stock_code] = corp_code
                if len(filtered) >= limit:
                    break
            else:
                skip_stats['already_collected'] += 1
        except Exception as e:
            # 변환 실패 시 스킵
            skip_stats['conversion_error'] += 1
            continue
    
    # 스킵 통계 출력
    total_skipped = skip_stats['no_corp_code'] + skip_stats['already_collected'] + skip_stats['conversion_error']
    logger.info('필터링 통계: 확인 %s개, 수집 대상 %s개, 스킵 %s개', skip_stats['total_checked'], len(filtered), total_skipped)
    logger.info('스킵 상세: 종목코드 변환 실패 %s개, 이미 수집됨 %s개, 변환 예외 %s개',
                skip_stats['no_corp_code'], skip_stats['already_collected'], skip_stats['conversion_error'])
    if skip_stats['total_checked'] < len(stock_codes):
        logger.info('미확인: %s개 (limit 도달로 중단)', len(stock_codes) - skip_stats['total_checked'])
    
    return filtered, skip_stats


def process_single_company(stock_code: str, corp_code: str, orchestrator: DataOrchestrator):
    """
    단일 기업 데이터 수집 처리 (병렬 처리용 함수)
    
    Args:
        stock_code: 종목코드
        corp_code: 고유번호 (8자리)
        orchestrator: DataOrchestrator 인스턴스
    
    Returns:
        dict: 처리 결과 (company_data 포함)
    """
    try:
        # 데이터 수집 (DB 저장 제외 - SQLite 동시 쓰기 문제 방지)
        company_data = orchestrator.collect_company_data(corp_code, save_to_db=False)
        
        return {
            'stock_code': stock_code,
            'status': 'success',
            'company_name': company_data.company_name,
            'passed_all_filters': company_data.passed_all_filters,
            'company_data': company_data  # DB 저장을 위해 데이터도 반환
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        return {
            'stock_code': stock_code,
            'status': 'failed',
            'error': error_msg,
            'traceback': traceback_str
        }


def main(limit: int = None, max_workers: int = None):
    """메인 실행 함수"""
    # Django 설정에서 값 가져오기 (파라미터가 있으면 우선)
    from django.conf import settings
    limit = limit or settings.DATA_COLLECTION['COLLECTION_LIMIT']
    max_workers = max_workers or settings.DATA_COLLECTION['MAX_WORKERS']
    
    # 파일 경로
    stock_codes_file = BASE_DIR / '종목코드.md'

    # 종목코드.md 파일 파싱 (모든 종목코드)
    all_stock_codes = parse_stock_codes_file(stock_codes_file)
    
    if not all_stock_codes:
        logger.warning('종목코드 파일이 비어있거나 찾을 수 없습니다.')
        return
    
    logger.info('총 %s개 종목코드 확인 중...', len(all_stock_codes))
    
    # 초기화
    dart_client = DartClient()
    
    # XML 캐시 미리 로드 (한 번만 다운로드)
    logger.info('기업 고유번호 XML 파일 로딩 중...')
    dart_client.load_corp_code_xml()
    logger.info('XML 로드 완료 (총 %s개 매핑)', len(dart_client._corp_code_mapping_cache))
    
    # DB 체크로 수집 필요한 종목코드만 필터링
    logger.info('DB 체크로 수집 필요한 종목코드 필터링 중...')
    stock_code_to_corp_code, skip_stats = filter_stock_codes_by_db(all_stock_codes, dart_client, limit)
    
    if not stock_code_to_corp_code:
        logger.info('수집할 종목코드가 없습니다. (모두 최근에 수집되었거나 DB에 존재)')
        return
    
    total_skipped = skip_stats['no_corp_code'] + skip_stats['already_collected'] + skip_stats['conversion_error']
    logger.info('수집 대상: %s개 (limit: %s)', len(stock_code_to_corp_code), limit)
    logger.info('스킵: %s개 (확인한 %s개 중)', total_skipped, skip_stats['total_checked'])
    if skip_stats['total_checked'] < len(all_stock_codes):
        logger.info('미확인: %s개 (limit 도달로 중단)', len(all_stock_codes) - skip_stats['total_checked'])
    logger.info('다중회사 배치 수집: 100개씩')
    
    orchestrator = DataOrchestrator()
    
    # 통계
    success_count = 0
    fail_count = 0
    passed_filter_stock_codes = []

    # API 호출 횟수 초기화
    initial_dart_calls = DartClient._api_call_count
    initial_ecos_calls = EcosClient._api_call_count
    start_time = time.time()
    
    items = list(stock_code_to_corp_code.items())
    total_count = len(items)
    batch_size = 100
    
    for start in range(0, total_count, batch_size):
        batch = items[start:start + batch_size]
        corp_codes = [c for _, c in batch]
        corp_to_stock = {c: s for s, c in batch}
        batch_num = start // batch_size + 1
        logger.info('배치 %s: corp_codes %s개 수집 시작', batch_num, len(corp_codes))
        
        try:
            batch_results = orchestrator.collect_companies_data_batch(corp_codes)
        except Exception as e:
            logger.error('배치 %s 전체 실패: %s', batch_num, e)
            fail_count += len(corp_codes)
            continue
        
        for r in batch_results:
            corp_code = r['corp_code']
            stock_code = corp_to_stock.get(corp_code, '')
            if r['status'] == 'success':
                success_count += 1
                logger.info('[배치 %s] %s 성공 (%s)', batch_num, stock_code or corp_code, r.get('company_name', ''))
                if r.get('passed_all_filters', False):
                    passed_filter_stock_codes.append(stock_code or corp_code)
                    logger.info('필터 통과: %s (%s)', stock_code or corp_code, r.get('company_name', ''))
            else:
                fail_count += 1
                logger.warning('[배치 %s] %s 실패: %s', batch_num, stock_code or corp_code, r.get('error', ''))
        
        logger.info('배치 %s: 성공 %s, 실패 %s',
                    batch_num,
                    sum(1 for r in batch_results if r['status'] == 'success'),
                    sum(1 for r in batch_results if r['status'] == 'failed'))
    
    # 필터 통과 기업은 DB Company.passed_all_filters로 이미 저장됨 (passed API는 DB 조회)

    # 전체 처리 시간 계산
    total_time = time.time() - start_time
    
    # 대기 중인 통계를 DB에 저장
    DartClient.flush_daily_stats()
    EcosClient.flush_daily_stats()
    
    # API 호출 횟수 계산 (XML 로드 이후 호출 횟수)
    dart_api_calls = DartClient._api_call_count - initial_dart_calls
    ecos_api_calls = EcosClient._api_call_count - initial_ecos_calls
    total_api_calls = dart_api_calls + ecos_api_calls
    
    # 일별 통계 조회 및 출력
    from django.apps import apps as django_apps
    from datetime import date
    ApiCallStatsModel = django_apps.get_model('apps', 'ApiCallStats')
    today = date.today()
    try:
        daily_stats = ApiCallStatsModel.objects.get(date=today)
        daily_dart_calls = daily_stats.dart_calls
        daily_ecos_calls = daily_stats.ecos_calls
        daily_total_calls = daily_dart_calls + daily_ecos_calls
    except ApiCallStatsModel.DoesNotExist:
        daily_dart_calls = 0
        daily_ecos_calls = 0
        daily_total_calls = 0
    
    # 평균 처리 시간 계산
    avg_time_per_company = total_time / (success_count + fail_count) if (success_count + fail_count) > 0 else 0
    avg_time_per_success = total_time / success_count if success_count > 0 else 0
    
    # 최종 결과 출력
    logger.info('=' * 60)
    logger.info('수집 완료! 성공 %s개, 실패 %s개, 필터 통과 %s개, 처리 총계 %s개',
                success_count, fail_count, len(passed_filter_stock_codes), success_count + fail_count)
    logger.info('=' * 60)
    logger.info('상세 통계: 전체 처리 시간 %.2f초 (%.2f분), 기업당 평균 %.2f초',
                total_time, total_time / 60, avg_time_per_company)
    if success_count > 0:
        logger.info('성공 기업당 평균 처리 시간 %.2f초', avg_time_per_success)
    logger.info('API 호출 (이번 실행): DART %s회, ECOS %s회, 총 %s회',
                dart_api_calls, ecos_api_calls, total_api_calls)
    if success_count > 0:
        logger.info('성공 기업당 평균 API 호출 %.1f회', total_api_calls / success_count)
    logger.info('일별 API 호출 (오늘): DART %s회, ECOS %s회, 총 %s회',
                daily_dart_calls, daily_ecos_calls, daily_total_calls)
    logger.info('=' * 60)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='종목코드.md 파일에서 기업 데이터를 수집합니다.')
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='수집할 최대 기업 수 (기본값: settings.DATA_COLLECTION["COLLECTION_LIMIT"])',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='병렬 처리 스레드 수 (기본값: settings.DATA_COLLECTION["MAX_WORKERS"])',
    )
    
    args = parser.parse_args()
    main(limit=args.limit, max_workers=args.workers)

