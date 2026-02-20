"""
KRX OPEN API 클라이언트 (출력명 그대로 일별 데이터 조회·저장)
API 키는 .env의 KRX_API_KEY로 설정. 없으면 호출하지 않고 None 반환.
당일 전체 종목은 JSON 스냅샷 1파일로 저장·캐시하고, 재수집 조건 시에만 API 호출.
"""
import json
import logging
import time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# 유가증권 일별매매정보(OPPUSES002_S2) 출력명 그대로 (번호 순)
KRX_OUTPUT_KEYS = [
    "BAS_DD", "ISU_CD", "ISU_NM", "MKT_NM", "SECT_TP_NM", "TDD_CLSPRC",
    "CMPPREVDD_PRC", "FLUC_RT", "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC",
    "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS",
]

# 메모리 캐시: 마지막 로드한 스냅샷 (ensure_latest_snapshot 결과)
_snapshot_cache: dict | None = None

KST = timezone(timedelta(hours=9))


def _get_kst_now() -> datetime:
    """현재 시각을 한국시간(KST)으로 반환."""
    return datetime.now(KST)


def _get_snapshot_path() -> Path:
    """스냅샷 JSON 파일 경로 (설정 또는 기본값)."""
    path = getattr(settings, "KRX_DAILY_SNAPSHOT_PATH", None)
    if path is None:
        from pathlib import Path as P
        base = P(settings.BASE_DIR)
        path = str(base / "data" / "krx_daily_snapshot.json")
    return Path(path)


class KrxClient:
    """KRX OPEN API 클라이언트 (AUTH_KEY 헤더 방식)"""

    def __init__(self, api_key=None):
        self.api_key = api_key or getattr(settings, "KRX_API_KEY", "")
        self.base_url = getattr(settings, "KRX_BASE_URL", "https://openapi.krx.co.kr").rstrip("/")

    def _headers(self):
        h = {}
        if self.api_key:
            h["AUTH_KEY"] = self.api_key
        h["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return h

    def get_all_daily_data(self, bas_dd: str | None = None) -> list[dict]:
        """
        당일 전체 종목 KRX 유가증권 일별매매정보(OPPUSES002_S2) 1회 호출.
        basDd만 전달(isuCd 없음). 응답 outBlock 리스트를 15개 필드씩 파싱해 반환.
        """
        if not self.api_key:
            return []
        bas_dd = bas_dd or _get_kst_now().strftime("%Y%m%d")
        service_path = getattr(
            settings,
            "KRX_MARKET_CAP_PATH",
            "/contents/OPP/USES/service/OPPUSES002_S2.cmd",
        )
        url = f"{self.base_url}{service_path}"
        params = {"basDd": bas_dd}
        req_headers = self._headers()
        max_attempts = 3
        retry_delay_sec = 2

        for attempt in range(max_attempts):
            try:
                resp = requests.get(url, headers=req_headers, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_full_block_list(data)
            except requests.exceptions.RequestException as e:
                _res = getattr(e, "response", None)
                _status = getattr(_res, "status_code", None) if _res else None
                _body = ""
                if _res is not None:
                    _raw = getattr(_res, "content", None) or getattr(_res, "text", None)
                    if _raw is not None:
                        _body = _raw.decode("utf-8", errors="replace")[:2000] if isinstance(_raw, bytes) else (str(_raw)[:2000] or "")
                is_temp_error = _status == 403 and (
                    "일시적 접근 불안정" in _body or "서비스 제공 불가능" in _body
                )
                if is_temp_error and attempt < max_attempts - 1:
                    logger.warning(
                        "KRX API 일시 불안정 (bas_dd=%s) %s/%s회 재시도 %ss 후",
                        bas_dd, attempt + 1, max_attempts, retry_delay_sec,
                    )
                    time.sleep(retry_delay_sec)
                    continue
                hint = ""
                if _status == 403:
                    if is_temp_error:
                        hint = " (KRX 서버 일시 불안정. 잠시 후 재시도하거나 시스템 담당자 문의.)"
                    else:
                        hint = " (유가증권 일별매매정보 API 이용 신청·승인 여부 확인: openapi.krx.co.kr → 서비스 이용 → 주식 → API 이용신청)"
                logger.warning("KRX API 요청 실패 (bas_dd=%s): %s%s", bas_dd, e, hint)
                return []
            except (ValueError, KeyError, TypeError) as e:
                logger.warning("KRX 응답 파싱 실패 (bas_dd=%s): %s", bas_dd, e)
                return []

    def _parse_full_row(self, block: dict) -> dict:
        """단일 블록을 15개 출력명 그대로 딕셔너리로 변환."""
        row = {}
        for key in KRX_OUTPUT_KEYS:
            val = block.get(key)
            row[key] = str(val).strip() if val is not None else ""
        return row

    def _parse_full_block_list(self, data: dict) -> list[dict]:
        """응답에서 outBlock(리스트) 전체를 15개 필드씩 파싱해 리스트 반환."""
        if not data:
            return []
        block = data.get("outBlock") or data.get("output") or data.get("block1") or data.get("OutBlock")
        if isinstance(block, dict):
            block = [block]
        if not isinstance(block, list):
            return []
        result = []
        for item in block:
            if isinstance(item, dict):
                result.append(self._parse_full_row(item))
        return result


def _should_refresh_snapshot(path: Path) -> bool:
    """
    재수집 필요 여부.
    1. JSON 파일이 없으면 True.
    2. 저장된 bas_dd가 오늘(한국날짜)과 다르고, 현재 시각이 08:30 KST 이상이면 True.
    """
    if not path.exists():
        return True
    now = _get_kst_now()
    bas_dd_today = now.strftime("%Y%m%d")
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (json.JSONDecodeError, OSError):
        return True
    stored_bas_dd = (obj.get("bas_dd") or "").strip()
    if stored_bas_dd != bas_dd_today:
        # 08:30 이상일 때만 재수집 (조건 2)
        return now.hour > 8 or (now.hour == 8 and now.minute >= 30)
    return False


def _load_snapshot_json(path: Path) -> dict | None:
    """스냅샷 JSON 로드. 없거나 깨지면 None."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_snapshot_json(path: Path, bas_dd: str, rows: list[dict]) -> None:
    """collected_at(KST ISO8601), bas_dd, rows로 JSON 저장. 15개 필드 그대로."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    collected_at = _get_kst_now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    payload = {"collected_at": collected_at, "bas_dd": bas_dd, "rows": rows}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def ensure_latest_snapshot() -> dict | None:
    """
    최신 스냅샷 확보. 재수집 조건 만족 시 API 호출 후 저장하고 캐시 갱신.
    아니면 파일 또는 캐시에서 반환. 반환: {"collected_at", "bas_dd", "rows"} 또는 None.
    """
    global _snapshot_cache
    path = _get_snapshot_path()
    if _should_refresh_snapshot(path):
        now = _get_kst_now()
        bas_dd_today = now.strftime("%Y%m%d")
        client = KrxClient()
        rows = client.get_all_daily_data(bas_dd_today)
        if not rows:
            # API 실패 시 기존 파일 있으면 로드
            snap = _load_snapshot_json(path)
            if snap:
                _snapshot_cache = snap
            return snap
        _save_snapshot_json(path, bas_dd_today, rows)
        _snapshot_cache = {
            "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "bas_dd": bas_dd_today,
            "rows": rows,
        }
        return _snapshot_cache
    if _snapshot_cache is not None:
        return _snapshot_cache
    snap = _load_snapshot_json(path)
    if snap is not None:
        _snapshot_cache = snap
    return snap


def get_snapshot_row_by_isu_cd(isu_cd: str) -> dict | None:
    """ensure_latest_snapshot() 후 rows에서 ISU_CD가 일치하는 행 1개 반환 (15개 필드). 없으면 None."""
    snap = ensure_latest_snapshot()
    if not snap or not isu_cd:
        return None
    rows = snap.get("rows") or []
    for row in rows:
        if (row.get("ISU_CD") or "").strip() == str(isu_cd).strip():
            return row
    return None


def get_daily_data(stock_code: str, bas_dd: str | None = None) -> dict | None:
    """스냅샷에서 해당 종목(ISU_CD) 일별 행 반환. bas_dd 없으면 스냅샷의 bas_dd 사용. 없으면 None."""
    snap = ensure_latest_snapshot()
    if not snap:
        return None
    rows = snap.get("rows") or []
    target_bas_dd = bas_dd or snap.get("bas_dd") or ""
    for row in rows:
        if (row.get("ISU_CD") or "").strip() != str(stock_code).strip():
            continue
        if not target_bas_dd or (row.get("BAS_DD") or "").strip() == target_bas_dd:
            return row
    return None


def get_market_cap(stock_code: str, bas_dd: str | None = None) -> int | None:
    """스냅샷에서 get_daily_data 후 MKTCAP 정수 변환."""
    row = get_daily_data(stock_code, bas_dd)
    if not row or not row.get("MKTCAP"):
        return None
    try:
        return int((row["MKTCAP"] or "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_and_save_company_market_cap(corp_code: str) -> int | None:
    """
    corp_code에 해당하는 종목코드로 스냅샷에서 행 조회 후
    Company.market_cap / market_cap_updated_at 만 갱신. 시가총액(원) 반환.
    """
    from django.apps import apps as django_apps
    from django.utils import timezone
    from apps.service.corp_code import get_stock_code_by_corp_code

    stock_code = get_stock_code_by_corp_code(corp_code)
    if not stock_code:
        logger.warning("KRX 시가총액 조회: corp_code=%s에 대한 종목코드 없음", corp_code)
        return None

    row = get_snapshot_row_by_isu_cd(stock_code)
    if not row:
        logger.warning(
            "KRX 시가총액 조회 실패: corp_code=%s stock_code=%s (스냅샷에 종목 없음)",
            corp_code, stock_code,
        )
        return None

    CompanyModel = django_apps.get_model("apps", "Company")
    now = timezone.now()
    mktcap_str = row.get("MKTCAP")
    market_cap = None
    if mktcap_str:
        try:
            market_cap = int(mktcap_str.replace(",", ""))
        except (TypeError, ValueError):
            pass

    try:
        CompanyModel.objects.filter(corp_code=corp_code).update(
            market_cap=market_cap,
            market_cap_updated_at=now,
        )
    except Exception as e:
        logger.warning("Company 시가총액 갱신 실패 corp_code=%s: %s", corp_code, e)
        return None
    return market_cap
