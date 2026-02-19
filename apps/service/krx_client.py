"""
KRX OPEN API 클라이언트 (출력명 그대로 일별 데이터 조회·저장)
API 키는 .env의 KRX_API_KEY로 설정. 없으면 호출하지 않고 None 반환.
"""
import logging
from datetime import date

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# KRX 출력명 그대로 (번호 순)
KRX_OUTPUT_KEYS = [
    "BAS_DD", "IDX_CLSS", "IDX_NM", "CLSPRC_IDX", "CMPPREVDD_IDX", "FLUC_RT",
    "OPNPRC_IDX", "HGPRC_IDX", "LWPRC_IDX", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP",
]


class KrxClient:
    """KRX OPEN API 클라이언트 (AUTH_KEY 헤더 방식)"""

    def __init__(self, api_key=None):
        self.api_key = api_key or getattr(settings, "KRX_API_KEY", "")
        self.base_url = getattr(settings, "KRX_BASE_URL", "https://openapi.krx.co.kr").rstrip("/")

    def _headers(self):
        return {"AUTH_KEY": self.api_key} if self.api_key else {}

    def get_daily_data(self, stock_code: str, bas_dd: str | None = None) -> dict | None:
        """
        종목코드(6자리)로 KRX API 호출 후 출력명 그대로 한 행 반환.
        Returns:
            { BAS_DD, IDX_CLSS, IDX_NM, CLSPRC_IDX, CMPPREVDD_IDX, FLUC_RT,
              OPNPRC_IDX, HGPRC_IDX, LWPRC_IDX, ACC_TRDVOL, ACC_TRDVAL, MKTCAP } 또는 None
        """
        if not self.api_key:
            logger.debug("KRX_API_KEY 없음, 조회 생략")
            return None
        if not stock_code or len(stock_code) != 6:
            logger.warning("KRX 조회: 종목코드 6자리 필요 (got %s)", stock_code)
            return None

        bas_dd = bas_dd or date.today().strftime("%Y%m%d")
        service_path = getattr(
            settings,
            "KRX_MARKET_CAP_PATH",
            "/contents/OPP/USES/service/OPPUSES001_S2.cmd",
        )
        url = f"{self.base_url}{service_path}"
        params = {"basDd": bas_dd, "isuCd": stock_code}

        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_full_row(data)
        except requests.exceptions.RequestException as e:
            hint = ""
            if hasattr(e, "response") and e.response is not None and getattr(e.response, "status_code", None) == 403:
                hint = " (KRX_API_KEY 및 openapi.krx.co.kr 사용 안내 확인)"
            logger.warning("KRX API 요청 실패 (stock_code=%s): %s%s", stock_code, e, hint)
            return None
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("KRX 응답 파싱 실패 (stock_code=%s): %s", stock_code, e)
            return None

    def _parse_full_row(self, data: dict) -> dict | None:
        """응답에서 첫 행을 출력명(BAS_DD, IDX_CLSS, ... MKTCAP) 그대로 추출."""
        if not data:
            return None
        block = data.get("outBlock") or data.get("output") or data.get("block1") or data.get("OutBlock")
        if isinstance(block, list):
            block = block[0] if block else {}
        if not isinstance(block, dict):
            return None
        row = {}
        for key in KRX_OUTPUT_KEYS:
            val = block.get(key)
            row[key] = str(val).strip() if val is not None else ""
        return row

    def get_market_cap(self, stock_code: str, bas_dd: str | None = None) -> int | None:
        """시가총액만 반환 (get_daily_data 후 MKTCAP 정수 변환)."""
        row = self.get_daily_data(stock_code, bas_dd)
        if not row or not row.get("MKTCAP"):
            return None
        try:
            return int(row["MKTCAP"].replace(",", ""))
        except (TypeError, ValueError):
            return None


def fetch_and_save_company_market_cap(corp_code: str) -> int | None:
    """
    corp_code 해당 기업으로 KRX 호출 후 출력명 그대로 KrxDailyData에 저장하고,
    Company.market_cap / market_cap_updated_at 갱신. 시가총액(원) 반환.
    """
    from django.apps import apps as django_apps
    from django.utils import timezone

    from apps.service.corp_code import get_stock_code_by_corp_code

    stock_code = get_stock_code_by_corp_code(corp_code)
    if not stock_code:
        logger.warning("KRX 시가총액 조회: corp_code=%s에 대한 종목코드 없음", corp_code)
        return None

    client = KrxClient()
    row = client.get_daily_data(stock_code)
    if not row:
        logger.warning(
            "KRX 시가총액 조회 실패: corp_code=%s stock_code=%s (API 키 없음 또는 API 오류)",
            corp_code, stock_code,
        )
        return None

    CompanyModel = django_apps.get_model("apps", "Company")
    KrxDailyDataModel = django_apps.get_model("apps", "KrxDailyData")
    now = timezone.now()

    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return None

    KrxDailyDataModel.objects.update_or_create(
        company=company,
        BAS_DD=row.get("BAS_DD", ""),
        defaults={
            "IDX_CLSS": row.get("IDX_CLSS") or None,
            "IDX_NM": row.get("IDX_NM") or None,
            "CLSPRC_IDX": row.get("CLSPRC_IDX") or None,
            "CMPPREVDD_IDX": row.get("CMPPREVDD_IDX") or None,
            "FLUC_RT": row.get("FLUC_RT") or None,
            "OPNPRC_IDX": row.get("OPNPRC_IDX") or None,
            "HGPRC_IDX": row.get("HGPRC_IDX") or None,
            "LWPRC_IDX": row.get("LWPRC_IDX") or None,
            "ACC_TRDVOL": row.get("ACC_TRDVOL") or None,
            "ACC_TRDVAL": row.get("ACC_TRDVAL") or None,
            "MKTCAP": row.get("MKTCAP") or None,
        },
    )

    mktcap_str = row.get("MKTCAP")
    market_cap = None
    if mktcap_str:
        try:
            market_cap = int(mktcap_str.replace(",", ""))
        except (TypeError, ValueError):
            pass

    CompanyModel.objects.filter(corp_code=corp_code).update(
        market_cap=market_cap,
        market_cap_updated_at=now,
    )
    return market_cap
