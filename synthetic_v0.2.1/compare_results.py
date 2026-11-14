#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sparql-results.txt 와 neo4j-results.txt 를 역량질문(CQ) 단위로 대조한다.

사용법:  python compare_results.py [sparql-results.txt] [neo4j-results.txt]

두 파일은 queries_sparql.py / run_cypher.py 가 공용 서식(cq_format.py)으로 출력한 것이어야 한다.
CQ 식별자는 'CQ12b.' 와 'CQ12-b [V]' 를 같은 것으로 본다. 반환 열(머리행)과 모든 행을
문자열 그대로 비교하며, 한쪽에만 있는 CQ 는 '대응 없음'으로 보고한다.
"""
import sys
from cq_format import cq_id

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse(path):
    blocks = open(path, encoding="utf-8").read().split("=" * 78)
    res = {}
    for b in blocks:
        ls = [l.rstrip() for l in b.strip("\n").split("\n")]
        if not ls or not ls[0]:
            continue
        k = cq_id(ls[0])
        if not k:
            continue
        body = [l for l in ls[1:] if l.startswith("  ")]
        if len(body) < 2 or not set(body[1].strip()) <= {"-"}:
            res[k] = None                       # 질의 단독 불가 등 표가 없는 블록
            continue
        res[k] = (body[0].strip(), [l.strip() for l in body[2:]])
    return res


def main():
    sp = sys.argv[1] if len(sys.argv) > 1 else "sparql-results.txt"
    cy = sys.argv[2] if len(sys.argv) > 2 else "neo4j-results.txt"
    A, B = parse(sp), parse(cy)
    keys = sorted(set(A) | set(B), key=lambda k: (int(''.join(c for c in k[2:] if c.isdigit())), k))
    same = diff = only = 0
    for k in keys:
        a, b = A.get(k, "없음"), B.get(k, "없음")
        if a == "없음" or b == "없음" or a is None or b is None:
            note = "SPARQL 없음" if a == "없음" else "Cypher 없음" if b == "없음" else "표 없음(질의 단독 불가)"
            print(f"  {k:6s} -  {note}")
            only += 1
            continue
        if a == b:
            print(f"  {k:6s} ✓  일치 ({len(a[1])}행)")
            same += 1
            continue
        diff += 1
        print(f"  {k:6s} ✗  불일치")
        if a[0] != b[0]:
            print(f"         열   SPARQL: {a[0]}\n              Cypher: {b[0]}")
        for i in range(max(len(a[1]), len(b[1]))):
            ra = a[1][i] if i < len(a[1]) else "(없음)"
            rb = b[1][i] if i < len(b[1]) else "(없음)"
            if ra != rb:
                print(f"         {i+1}행 SPARQL: {ra}\n              Cypher: {rb}")
    print(f"\n대조 결과: 일치 {same} / 불일치 {diff} / 대응 없음 {only}")
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
