"""
필터 통과 기업 JSON 파일 읽기/쓰기 (settings, Path, json, datetime만 사용)
"""
import json
from pathlib import Path
from datetime import datetime

from django.conf import settings


def load_passed_companies_json(file_path=None):
    """
    필터 통과 기업 JSON 파일 읽기

    Args:
        file_path: JSON 파일 경로 (없으면 기본 경로 사용)

    Returns:
        dict: {
            'last_updated': str,
            'companies': [
                {'stock_code': str, 'company_name': str, 'corp_code': str},
                ...
            ]
        }
    """
    if file_path is None:
        file_path = settings.BASE_DIR / 'passed_filters_companies.json'
    else:
        file_path = Path(file_path)

    if not file_path.exists():
        return {
            'last_updated': None,
            'companies': []
        }

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, IOError):
        return {
            'last_updated': None,
            'companies': []
        }


def save_passed_companies_json(stock_code, company_name, corp_code, file_path=None):
    """
    필터 통과 기업을 JSON 파일에 추가/업데이트

    Args:
        stock_code: 종목코드
        company_name: 기업명
        corp_code: 기업번호
        file_path: JSON 파일 경로 (없으면 기본 경로 사용)

    Returns:
        bool: 저장 성공 여부
    """
    if file_path is None:
        file_path = settings.BASE_DIR / 'passed_filters_companies.json'
    else:
        file_path = Path(file_path)

    data = load_passed_companies_json(file_path)
    existing_stock_codes = {c['stock_code'] for c in data.get('companies', [])}

    if stock_code in existing_stock_codes:
        for company in data['companies']:
            if company['stock_code'] == stock_code:
                company['company_name'] = company_name
                company['corp_code'] = corp_code
                break
    else:
        if 'companies' not in data:
            data['companies'] = []
        data['companies'].append({
            'stock_code': stock_code,
            'company_name': company_name,
            'corp_code': corp_code
        })

    data['last_updated'] = datetime.now().isoformat()

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False
