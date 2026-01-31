#!/usr/bin/env python
"""
현금흐름표 파싱 테스트: 연도 + 표 본문 + rows JSON 출력.

사용법 (프로젝트 루트에서):
  python debug_paste_parser_cash.py [현금흐름표.txt]
  파일 안 주면 cash.txt 참고.
"""
import json
import os
import sys


def run():
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django
        django.setup()

    from apps.service.paste_parser import (
        _extract_years_from_text,
        _trim_from_first_marker,
        parse_cash_flow,
    )

    args = [a for a in sys.argv[1:] if not a.startswith("-") and os.path.isfile(a)]
    path = args[0] if args else "cash.txt"
    if not os.path.isfile(path):
        print(f"[오류] 파일 없음: {path}")
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    print(f"[입력] {path}\n")

    # 1) 연도 어떻게 저장했는지 출력
    print("=" * 60)
    print("1. 연도 저장 방식")
    print("=" * 60)
    years = _extract_years_from_text(text)
    print(f"  텍스트에서 맨 처음 나오는 202X를 당기로 사용 -> [당기, 전기, 전전기]")
    print(f"  결과: years = {years}\n")

    # 2) 표 본문(영업 포함 줄부터) 분리 결과 txt 출력
    print("=" * 60)
    print("2. 표 본문 (영업 포함 첫 줄부터 분리된 txt)")
    print("=" * 60)
    trimmed = _trim_from_first_marker(text, "영업", exact_line=False, contains=True)
    print(trimmed)
    print("=" * 60)

    # 3) rows JSON (전체)
    print("3. rows JSON (전체)")
    print("=" * 60)
    result = parse_cash_flow(text)
    rows = result.get("rows", [])
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    run()
