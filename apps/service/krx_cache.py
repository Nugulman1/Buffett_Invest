"""
KRX 스냅샷 파일 캐싱 (일별 전체 종목 JSON 파일 저장·재수집 판단·병합 로드)

krx_client.py에서 분리(파일 I/O·스냅샷 관리만 여기, API 호출부·시총 조회/직렬화는 krx_client.py에 남음).
krx_client.py가 이 모듈의 심볼을 재수출(re-export)해 기존 참조 경로
(예: apps.service.krx_client.ensure_latest_snapshot, patch 대상 등)를 그대로 유지한다.

순환 import 방지: krx_client.py의 상수/함수(MARKET_ORDER, _get_api_path, _get_snapshot_path,
_get_kst_now, KrxClient)가 필요한 곳은 전부 함수 내부 lazy import.
"""
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 메모리 캐시: 마지막 로드한 스냅샷 (ensure_latest_snapshot 결과)
_snapshot_cache: dict | None = None


def _should_refresh_snapshot(path) -> bool:
    """
    재수집 필요 여부.
    1. JSON 파일이 없으면 True.
    2. 저장된 bas_dd를 파싱할 수 없거나 형식이 잘못되면 True.
    3. 저장된 bas_dd가 오늘보다 미래(시스템 날짜 오류 등)면 True.
    4. 저장된 bas_dd가 어제(한국날짜)보다 이전이면 True.
    (어제 또는 오늘 데이터가 이미 있으면 재수집하지 않음.)
    """
    from apps.service.krx_client import _get_kst_now

    if not path.exists():
        return True
    now = _get_kst_now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (json.JSONDecodeError, OSError):
        return True
    stored_bas_dd = (obj.get("bas_dd") or "").strip()
    if not stored_bas_dd or len(stored_bas_dd) != 8:
        return True
    try:
        stored_date = datetime.strptime(stored_bas_dd, "%Y%m%d").date()
    except ValueError:
        return True
    if stored_date > today:
        return True
    if stored_date < yesterday:
        logger.warning(
            "KRX 스냅샷이 오래됨 (저장 bas_dd=%s < 어제=%s) → 재수집 시도",
            stored_bas_dd, yesterday.strftime("%Y%m%d"),
        )
        return True
    return False


def _load_snapshot_json(path) -> dict | None:
    """스냅샷 JSON 로드. 없거나 깨지면 None."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_snapshot_json(path, bas_dd: str, rows: list) -> None:
    """collected_at(KST ISO8601), bas_dd, rows로 JSON 저장. 15개 필드 그대로."""
    from pathlib import Path
    from apps.service.krx_client import _get_kst_now

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    collected_at = _get_kst_now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    payload = {"collected_at": collected_at, "bas_dd": bas_dd, "rows": rows}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_merged_snapshot() -> dict | None:
    """유가 -> 코스닥 -> 코넥스 순으로 시장별 스냅샷 파일 로드 후 rows 병합. 조회 시 같은 순서로 찾으면 데이터 얻었으면 break."""
    from apps.service.krx_client import MARKET_ORDER, _get_snapshot_path, _get_kst_now

    all_rows = []
    collected_at = None
    bas_dd = None
    for market in MARKET_ORDER:
        path = _get_snapshot_path(market)
        snap = _load_snapshot_json(path)
        if snap and snap.get("rows"):
            all_rows.extend(snap["rows"])
            if collected_at is None:
                collected_at = snap.get("collected_at")
                bas_dd = snap.get("bas_dd")
    if not all_rows:
        return None
    now = _get_kst_now()
    return {
        "collected_at": collected_at or now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "bas_dd": bas_dd or now.strftime("%Y%m%d"),
        "rows": all_rows,
    }


def ensure_latest_snapshot() -> dict | None:
    """
    최신 스냅샷 확보. 재수집 조건 만족 시에만 API 호출(유가/코스닥/코넥스, 하루 전→이틀 전 순).
    아니면 시장별 파일 로드·병합 후 반환. 반환: {"collected_at", "bas_dd", "rows"}.
    """
    global _snapshot_cache
    from apps.service.krx_client import MARKET_ORDER, _get_api_path, _get_snapshot_path, _get_kst_now, KrxClient

    need_refresh = any(
        _should_refresh_snapshot(_get_snapshot_path(m)) for m in MARKET_ORDER if _get_api_path(m)
    )
    if not need_refresh:
        snap = _load_merged_snapshot()
        if snap is not None:
            _snapshot_cache = snap
        return snap

    now = _get_kst_now()
    client = KrxClient()
    all_rows = []
    bas_dd_used = None
    # data-dbg가 최근일 빈 배열 반환 시 대비, 최대 14일 전까지 시도
    bas_dd_candidates = [(now - timedelta(days=d)).strftime("%Y%m%d") for d in range(1, 15)]
    for market in MARKET_ORDER:
        if not _get_api_path(market):
            continue
        rows = None
        market_bas_dd = None
        for bas_dd in bas_dd_candidates:
            rows = client.get_all_daily_data(bas_dd, market=market)
            if rows:
                market_bas_dd = bas_dd
                break
        if rows and market_bas_dd:
            if bas_dd_used is None:
                bas_dd_used = market_bas_dd
            path = _get_snapshot_path(market)
            _save_snapshot_json(path, market_bas_dd, rows)
            all_rows.extend(rows)
    if not all_rows:
        snap = _load_merged_snapshot()
        if snap is not None:
            _snapshot_cache = snap
        return snap
    _snapshot_cache = {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "bas_dd": bas_dd_used or bas_dd_candidates[0],
        "rows": all_rows,
    }
    return _snapshot_cache
