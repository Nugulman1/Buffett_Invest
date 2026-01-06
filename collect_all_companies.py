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
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from apps.utils.utils import should_collect_company, save_company_to_db


def parse_stock_codes_file(stock_codes_file: Path) -> list:
    """종목코드.md 파일 파싱 (모든 종목코드 반환)"""
    if not stock_codes_file.exists():
        print(f'[ERROR] 파일을 찾을 수 없습니다: {stock_codes_file}')
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
    print(f'\n[필터링 통계]')
    print(f'  확인한 종목코드: {skip_stats["total_checked"]}개')
    print(f'  수집 대상: {len(filtered)}개')
    print(f'  스킵: {total_skipped}개')
    print(f'    - 종목코드 변환 실패: {skip_stats["no_corp_code"]}개')
    print(f'    - 이미 수집됨 (4월 1일 기준): {skip_stats["already_collected"]}개')
    print(f'    - 변환 예외 발생: {skip_stats["conversion_error"]}개')
    if skip_stats['total_checked'] < len(stock_codes):
        print(f'  미확인: {len(stock_codes) - skip_stats["total_checked"]}개 (limit 도달로 중단)')
    
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
    passed_filters_file = BASE_DIR / 'passed_filters_stock_codes.txt'
    
    # 종목코드.md 파일 파싱 (모든 종목코드)
    all_stock_codes = parse_stock_codes_file(stock_codes_file)
    
    if not all_stock_codes:
        print('[WARNING] 종목코드 파일이 비어있거나 찾을 수 없습니다.')
        return
    
    print(f'총 {len(all_stock_codes)}개 종목코드 확인 중...')
    
    # 초기화
    dart_client = DartClient()
    
    # XML 캐시 미리 로드 (한 번만 다운로드)
    print('기업 고유번호 XML 파일 로딩 중...')
    dart_client.load_corp_code_xml()
    print(f'[SUCCESS] XML 로드 완료 (총 {len(dart_client._corp_code_mapping_cache)}개 매핑)')
    
    # DB 체크로 수집 필요한 종목코드만 필터링
    print('DB 체크로 수집 필요한 종목코드 필터링 중...')
    stock_code_to_corp_code, skip_stats = filter_stock_codes_by_db(all_stock_codes, dart_client, limit)
    
    if not stock_code_to_corp_code:
        print('[INFO] 수집할 종목코드가 없습니다. (모두 최근에 수집되었거나 DB에 존재)')
        return
    
    total_skipped = skip_stats['no_corp_code'] + skip_stats['already_collected'] + skip_stats['conversion_error']
    print(f'\n수집 대상: {len(stock_code_to_corp_code)}개 (limit: {limit})')
    print(f'스킵: {total_skipped}개 (확인한 {skip_stats["total_checked"]}개 중)')
    if skip_stats['total_checked'] < len(all_stock_codes):
        print(f'미확인: {len(all_stock_codes) - skip_stats["total_checked"]}개 (limit 도달로 중단)')
    print(f'병렬 처리: {max_workers}개 스레드 사용\n')
    
    orchestrator = DataOrchestrator()
    
    # 통계
    success_count = 0
    fail_count = 0
    passed_filter_stock_codes = []  # 필터 통과한 종목코드
    results = []  # 모든 결과 저장
    
    # API 호출 횟수 초기화 (XML 로드 전 호출 횟수 저장)
    initial_dart_calls = DartClient._api_call_count
    initial_ecos_calls = EcosClient._api_call_count
    
    # 전체 처리 시간 측정 시작
    start_time = time.time()
    
    # 병렬 처리
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 모든 작업 제출
        future_to_stock_code = {
            executor.submit(process_single_company, stock_code, corp_code, orchestrator): stock_code
            for stock_code, corp_code in stock_code_to_corp_code.items()
        }
        
        # 완료된 작업 처리
        completed = 0
        total_count = len(stock_code_to_corp_code)
        for future in as_completed(future_to_stock_code):
            completed += 1
            stock_code = future_to_stock_code[future]
            
            try:
                result = future.result()
                results.append(result)
                
                if result['status'] == 'success':
                    success_count += 1
                    company_name = result.get('company_name', '')
                    print(f'[{completed}/{total_count}] {stock_code} → [SUCCESS] 성공 ({company_name})')
                    
                    if result.get('passed_all_filters', False):
                        passed_filter_stock_codes.append(stock_code)
                        print(f'   [필터 통과] {stock_code} ({company_name})')
                else:
                    fail_count += 1
                    error = result.get('error', '알 수 없는 오류')
                    print(f'[{completed}/{total_count}] {stock_code} → [ERROR] {error}')
                    
            except Exception as e:
                fail_count += 1
                print(f'[{completed}/{total_count}] {stock_code} → [ERROR] 예외 발생: {str(e)}')
                results.append({
                    'stock_code': stock_code,
                    'status': 'failed',
                    'error': f'Future 처리 중 오류: {str(e)}'
                })
    
    # 성공한 기업 데이터를 순차적으로 DB에 저장 (SQLite 동시 쓰기 문제 방지)
    print('\nDB 저장 중...')
    db_save_success = 0
    db_save_fail = 0
    for result in results:
        if result['status'] == 'success' and 'company_data' in result:
            try:
                save_company_to_db(result['company_data'])
                db_save_success += 1
            except Exception as e:
                db_save_fail += 1
                print(f'경고: {result["stock_code"]} DB 저장 실패: {e}')
    
    if db_save_success > 0:
        print(f'[SUCCESS] DB 저장 완료: {db_save_success}개')
    if db_save_fail > 0:
        print(f'[WARNING] DB 저장 실패: {db_save_fail}개')
    
    # 필터 통과 기업 저장
    if passed_filter_stock_codes:
        # 기존 파일 로드 (중복 방지)
        existing_passed = set()
        if passed_filters_file.exists():
            with open(passed_filters_file, 'r', encoding='utf-8') as f:
                existing_passed = set(line.strip() for line in f if line.strip())
        
        # 새로 통과한 것만 추가 (중복 제거)
        new_passed = [
            code for code in passed_filter_stock_codes 
            if code not in existing_passed
        ]
        
        if new_passed:
            # 파일에 추가 (append 모드)
            with open(passed_filters_file, 'a', encoding='utf-8') as f:
                for stock_code in new_passed:
                    f.write(f"{stock_code}\n")
            
            print(f'[SUCCESS] 필터 통과 기업 {len(new_passed)}개 저장 완료: {passed_filters_file}')
    
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
    print('\n' + '=' * 60)
    print('[SUCCESS] 수집 완료!')
    print(f'  성공: {success_count}개')
    print(f'  실패: {fail_count}개')
    print(f'  필터 통과: {len(passed_filter_stock_codes)}개')
    print(f'  처리 총계: {success_count + fail_count}개')
    print('=' * 60)
    
    # 상세 통계 출력
    print('\n' + '=' * 60)
    print('[상세 통계]')
    print(f'  전체 처리 시간: {total_time:.2f}초 ({total_time/60:.2f}분)')
    print(f'  기업당 평균 처리 시간: {avg_time_per_company:.2f}초')
    if success_count > 0:
        print(f'  성공 기업당 평균 처리 시간: {avg_time_per_success:.2f}초')
    print(f'\n  API 호출 횟수 (이번 실행):')
    print(f'    DART API: {dart_api_calls}회')
    print(f'    ECOS API: {ecos_api_calls}회')
    print(f'    총 API 호출: {total_api_calls}회')
    if success_count > 0:
        print(f'    성공 기업당 평균 API 호출: {total_api_calls/success_count:.1f}회')
    print(f'\n  일별 API 호출 통계 (오늘):')
    print(f'    DART API: {daily_dart_calls}회')
    print(f'    ECOS API: {daily_ecos_calls}회')
    print(f'    총 API 호출: {daily_total_calls}회')
    print('=' * 60)


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

