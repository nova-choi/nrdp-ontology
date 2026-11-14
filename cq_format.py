#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""역량질문 결과 출력 서식 (SPARQL 실행기와 Cypher 실행기 공용).

queries_sparql.py 와 run_cypher.py 가 같은 규칙으로 셀을 출력하도록 하여,
sparql-results.txt 와 neo4j-results.txt 를 CQ 단위로 그대로 대조할 수 있게 한다.
  - 빈 값(None)       → "-"
  - 불리언            → "true" / "false"
  - 수치(정수·실수·decimal) → 소수 6자리 반올림, 뒤쪽 0 제거, 정수값은 소수점 없이
  - 목록              → "[a, b]"
  - rdflib Literal    → 파이썬 값으로 변환 후 위 규칙 적용
  - rdflib URIRef     → '#' 또는 '/' 뒤 지역명
  - 행 수 제한 없이 전체 출력
"""
from decimal import Decimal
import re

DIGITS = 6


def fmt(v):
    try:                                   # rdflib 객체 처리 (rdflib 미설치 환경에서도 동작)
        from rdflib.term import Literal, URIRef
        if isinstance(v, Literal):
            v = v.toPython()
        elif isinstance(v, URIRef):
            s = str(v)
            return re.split(r"[#/]", s)[-1]
    except ImportError:
        pass
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (float, Decimal)):
        r = round(float(v), DIGITS)
        if r == 0:
            return "0"
        if r == int(r):
            return str(int(r))
        return f"{r:.{DIGITS}f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(fmt(x) for x in v) + "]"
    return str(v)


def table(keys, rows, limit=None):
    """rows: dict 목록 또는 keys 순서의 튜플 목록"""
    lines = ["  " + " | ".join(keys), "  " + "-" * 70]
    shown = rows if limit is None else rows[:limit]
    for r in shown:
        cells = [r[k] for k in keys] if isinstance(r, dict) else list(r)
        lines.append("  " + " | ".join(fmt(c) for c in cells))
    if limit is not None and len(rows) > limit:
        lines.append(f"  ... 총 {len(rows)}행")
    if not rows:
        lines.append("  (빈 결과)")
    return "\n".join(lines)


def cq_id(title):
    """'CQ12-b [V] ...' / 'CQ12b. [보조] ...' → 'CQ12B' (대조용 식별자)"""
    m = re.match(r"\s*CQ\s*(\d+)\s*-?\s*([a-zA-Z])?", title or "")
    if not m:
        return None
    return "CQ" + m.group(1) + (m.group(2) or "").upper()
