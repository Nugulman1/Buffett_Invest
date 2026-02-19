#!/usr/bin/env python
"""
전체 기업 데이터 수집 스크립트

종목코드.md 파일에서 기업 코드를 읽어서 재무 데이터를 수집합니다.

사용법:
    python collect_all_companies.py [--limit N]
"""
import json
import os
import sys
import time
import logging
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

logger = logging.getLogger(__name__)

# #region agent log
_DEBUG_LOG_PATH = Path(__file__).resolve().parent / "debug-684b61.log"

def _debug_log(message: str, data: dict, hypothesis_id: str = ""):
    try:
        payload = {"sessionId": "684b61", "location": "collect_all_companies.py", "message": message, "data": data, "timestamp": int(time.time() * 1000)}
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion


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
    종목코드 → corp_code 변환. 변환 실패/예외만 스킵. limit개만 수집 대상으로 반환.

    Returns:
        (stock_code -> corp_code 딕셔너리, skip_stats)
    """
    skip_stats = {
        "no_corp_code": 0,
        "conversion_error": 0,
        "total_checked": 0,
    }
    ordered_pairs = []

    for stock_code in stock_codes:
        skip_stats["total_checked"] += 1
        try:
            corp_code = dart_client._get_corp_code_by_stock_code(stock_code)
            if not corp_code:
                skip_stats["no_corp_code"] += 1
                continue
            ordered_pairs.append((stock_code, corp_code))
        except Exception:
            skip_stats["conversion_error"] += 1
            continue

    if not ordered_pairs:
        logger.info("변환 통계: 확인 %s개, 수집 대상 0개", skip_stats["total_checked"])
        return {}, skip_stats

    filtered = {}
    for stock_code, corp_code in ordered_pairs:
        filtered[stock_code] = corp_code
        if len(filtered) >= limit:
            break

    total_skipped = skip_stats["no_corp_code"] + skip_stats["conversion_error"]
    logger.info(
        "변환 통계: 확인 %s개, 수집 대상 %s개, 스킵 %s개",
        skip_stats["total_checked"],
        len(filtered),
        total_skipped,
    )
    logger.info(
        "스킵 상세: 종목코드 변환 실패 %s개, 변환 예외 %s개",
        skip_stats["no_corp_code"],
        skip_stats["conversion_error"],
    )
    if len(ordered_pairs) > len(filtered):
        logger.info(
            "미수집: %s개 (limit 도달로 중단)",
            len(ordered_pairs) - len(filtered),
        )

    return filtered, skip_stats


def _run_one_batch(batch_num: int, corp_codes: list, corp_to_stock: dict) -> tuple:
    """
    단일 배치 수집 (병렬 실행용). 배치마다 새 DataOrchestrator 사용.
    Returns:
        (batch_num, corp_to_stock, batch_results) 성공 시
        (batch_num, corp_to_stock, None, error) 예외 시
    """
    # #region agent log — 병렬 시 어떤 배치가 시작/완료하는지 확인
    _debug_log("batch worker started", {"batch_num": batch_num, "corp_count": len(corp_codes)}, "perf")
    # #endregion
    try:
        orchestrator = DataOrchestrator()
        batch_results = orchestrator.collect_companies_data_batch(corp_codes)
        # #region agent log
        _debug_log("batch worker done", {"batch_num": batch_num, "status": "success", "result_count": len(batch_results)}, "perf")
        # #endregion
        return (batch_num, corp_to_stock, batch_results)
    except Exception as e:
        # #region agent log
        _debug_log("batch worker done", {"batch_num": batch_num, "status": "exception", "error": str(e)}, "perf")
        # #endregion
        return (batch_num, corp_to_stock, None, e)


def main(limit: int = None, stock_code: str = None):
    """메인 실행 함수. stock_code가 있으면 해당 종목 1건만 수집."""
    from django.conf import settings
    if stock_code:
        all_stock_codes = [stock_code.strip()]
        limit = 1
        logger.info('특정 기업 수집: 종목코드=%s', stock_code)
    else:
        limit = limit or settings.DATA_COLLECTION['COLLECTION_LIMIT']
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
    
    # 종목코드 → corp_code 변환 후 수집 대상 확정
    logger.info('종목코드 → corp_code 변환 중...')
    stock_code_to_corp_code, skip_stats = filter_stock_codes_by_db(all_stock_codes, dart_client, limit)
    
    if not stock_code_to_corp_code:
        logger.info('수집할 종목이 없습니다.')
        return

    # #region agent log
    _debug_log("collect after filter_stock_codes_by_db", {"target_count": len(stock_code_to_corp_code), "limit": limit, "total_skipped": skip_stats['no_corp_code'] + skip_stats['conversion_error']}, "perf")
    # #endregion
    total_skipped = skip_stats['no_corp_code'] + skip_stats['conversion_error']
    logger.info('수집 대상: %s개 (limit: %s)', len(stock_code_to_corp_code), limit)
    logger.info('스킵: %s개 (확인한 %s개 중)', total_skipped, skip_stats['total_checked'])
    if skip_stats['total_checked'] < len(all_stock_codes):
        logger.info('미확인: %s개 (limit 도달로 중단)', len(all_stock_codes) - skip_stats['total_checked'])
    batch_size = 100
    parallel_workers = settings.DATA_COLLECTION.get('PARALLEL_WORKERS', 1)
    # #region agent log
    _debug_log("collect batch config", {"total_count": len(stock_code_to_corp_code), "batch_size": batch_size, "parallel_workers": parallel_workers}, "perf")
    # #endregion
    if parallel_workers >= 2:
        logger.info('다중회사 배치 수집: 100개씩, 병렬 스레드 %s개', parallel_workers)
    else:
        logger.info('다중회사 배치 수집: 100개씩')
    
    success_count = 0
    fail_count = 0
    passed_filter_stock_codes = []

    with DartClient._api_call_lock:
        initial_dart_calls = DartClient._api_call_count
    with EcosClient._api_call_lock:
        initial_ecos_calls = EcosClient._api_call_count
    start_time = time.time()
    
    items = list(stock_code_to_corp_code.items())
    total_count = len(items)
    
    if parallel_workers >= 2:
        futures = []
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            for start in range(0, total_count, batch_size):
                batch = items[start:start + batch_size]
                corp_codes = [c for _, c in batch]
                corp_to_stock = {c: s for s, c in batch}
                batch_num = start // batch_size + 1
                logger.info('배치 %s: corp_codes %s개 수집 제출', batch_num, len(corp_codes))
                future = executor.submit(_run_one_batch, batch_num, corp_codes, corp_to_stock)
                futures.append(future)
            
            for future in as_completed(futures):
                result = future.result()
                batch_num = result[0]
                corp_to_stock = result[1]
                # #region agent log — 메인 스레드가 배치 완료를 받는 순서 확인
                _debug_log("main received batch", {"batch_num": batch_num, "result_len": len(result)}, "perf")
                # #endregion
                if len(result) == 4:
                    _, _, _, err = result
                    logger.error('배치 %s 전체 실패: %s', batch_num, err)
                    fail_count += len(corp_to_stock)
                    continue
                _, _, batch_results = result
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
    else:
        orchestrator = DataOrchestrator()
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
    
    total_time = time.time() - start_time
    # #region agent log
    _debug_log("collect main exit", {"total_elapsed_sec": round(total_time, 2), "success_count": success_count, "fail_count": fail_count, "passed_filter_count": len(passed_filter_stock_codes)}, "perf")
    # #endregion

    DartClient.flush_daily_stats()
    EcosClient.flush_daily_stats()
    
    with DartClient._api_call_lock:
        final_dart_calls = DartClient._api_call_count
    with EcosClient._api_call_lock:
        final_ecos_calls = EcosClient._api_call_count
    dart_api_calls = final_dart_calls - initial_dart_calls
    ecos_api_calls = final_ecos_calls - initial_ecos_calls
    total_api_calls = dart_api_calls + ecos_api_calls
    batch_count = (total_count + batch_size - 1) // batch_size if batch_size else 0
    # #region agent log — 전체 수집 시 배치/워커/API 대비 시간 비교용
    _debug_log(
        "collect summary",
        {
            "total_companies": total_count,
            "batch_size": batch_size,
            "batch_count": batch_count,
            "parallel_workers": parallel_workers,
            "total_elapsed_sec": round(total_time, 2),
            "dart_api_calls": dart_api_calls,
            "ecos_api_calls": ecos_api_calls,
            "success_count": success_count,
            "fail_count": fail_count,
        },
        "perf",
    )
    # #endregion

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
        '--stock-code',
        type=str,
        default=None,
        metavar='CODE',
        help='해당 종목코드 1건만 수집 (예: BYC=001460)',
    )
    args = parser.parse_args()
    main(limit=args.limit, stock_code=args.stock_code)

