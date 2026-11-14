#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neo4j 에 .cypher 파일을 실행하는 도구 (Windows / macOS / Linux 공용)

사용법
  python run_cypher.py load_neo4j.cypher            # 데이터 적재
  python run_cypher.py queries.cypher               # 역량질문 25개 실행 → neo4j-results.txt
  python run_cypher.py --n10s nrdp-merged.ttl --database rdf   # (선택) n10s 로 TTL 직접 변환

접속 정보 (환경변수로 바꿀 수 있음)
  NEO4J_URI       기본값 neo4j://127.0.0.1:7687
                  (Windows에서 'localhost'가 IPv6로 풀려 접속 실패하는 사례가 있어
                   127.0.0.1을 기본값으로 둠 — 필요시 환경변수로 덮어쓸 수 있음)
  NEO4J_USERNAME  기본값 neo4j
  NEO4J_PASSWORD  없으면 실행 시 입력받음
  NEO4J_DATABASE  기본값 neo4j

필요 패키지:  pip install neo4j
"""
import argparse, getpass, os, re, sys, time

# Windows 콘솔(cp949)에서 한글·특수문자가 깨지거나 오류 나는 것을 방지
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import AuthError, ServiceUnavailable, Neo4jError
except ImportError:
    sys.exit("neo4j 패키지가 없습니다.  →  pip install neo4j")


def split_statements(text):
    """// 주석 줄을 제거하고, 줄 끝의 ';' 기준으로 문장을 나눈다.
    각 문장 앞의 주석 중 'CQ' 로 시작하는 제목을 함께 돌려준다."""
    stmts, buf, title = [], [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("//"):
            m = re.match(r"//\s*(CQ[\w\-]+.*)", s)
            if m and not buf:
                title = m.group(1)
            continue
        if not s:
            continue
        buf.append(line)
        if s.endswith(";"):
            q = "\n".join(buf).rstrip().rstrip(";")
            stmts.append((title, q))
            buf, title = [], None
    if buf:
        stmts.append((title, "\n".join(buf)))
    return stmts


# 결과 서식은 queries_sparql.py 와 공용 (cq_format.py) — 두 결과 파일을 그대로 대조하기 위함.
# 기존 fmt 는 실수를 소수 4자리에서 잘라 0.000969 가 0.001 로 출력되는 문제가 있었다.
from cq_format import fmt, table


def connect(args):
    uri = os.environ.get("NEO4J_URI", "neo4j://127.0.0.1:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD") or getpass.getpass(f"Neo4j 비밀번호 ({user}@{uri}): ")
    drv = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        drv.verify_connectivity()
    except AuthError:
        sys.exit("✗ 비밀번호가 틀렸습니다. Neo4j Desktop 에서 인스턴스 생성 시 정한 비밀번호를 확인하세요.")
    except ServiceUnavailable:
        sys.exit(f"✗ {uri} 에 연결할 수 없습니다. Neo4j Desktop 에서 인스턴스가 'Running' 상태인지, 포트가 맞는지 확인하세요.")
    print(f"✓ 연결됨: {uri}  (database={args.database})")
    return drv


def run_file(drv, args):
    text = open(args.file, encoding="utf-8").read()
    stmts = split_statements(text)
    is_query_file = any(t for t, _ in stmts)       # CQ 제목이 있으면 질의 파일
    out, ok, fail = [], 0, 0
    t0 = time.time()
    with drv.session(database=args.database) as ses:
        for i, (title, q) in enumerate(stmts, 1):
            try:
                res = ses.run(q)
                rows = [r.data() for r in res]
                keys = res.keys() if rows == [] else list(rows[0].keys())
                ok += 1
                if is_query_file:
                    out.append("=" * 78)
                    out.append(title or f"문장 {i}")
                    out.append(table(keys, rows))          # 전체 행 출력
                elif rows:                          # 적재 파일은 마지막 확인 결과만 표시
                    out.append(table(keys, rows, limit=40))
                else:
                    print(f"\r  적재 진행 {i}/{len(stmts)}", end="", flush=True)
            except Neo4jError as e:
                fail += 1
                msg = f"✗ [{title or f'문장 {i}'}] {e.code}\n    {e.message.splitlines()[0]}"
                out.append(msg)
                if not is_query_file:
                    print("\n" + msg)
    print()
    summary = f"완료: 성공 {ok} / 실패 {fail}  ({time.time() - t0:.1f}초)"
    out.append("=" * 78)
    out.append(summary)
    text_out = "\n".join(out)
    print(text_out)
    if is_query_file:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text_out + "\n")
        print(f"→ 결과 저장: {args.out}")


def run_n10s(drv, args):
    """n10s 로 Turtle 을 그대로 가져온다 (논문의 OWL→속성그래프 변환 시연용).
    파일 경로 설정 문제를 피하려고 inline 방식으로 내용을 직접 전달한다."""
    ttl = open(args.n10s, encoding="utf-8").read()
    with drv.session(database=args.database) as ses:
        print("기존 데이터 삭제 및 n10s 초기화 ...")
        ses.run("MATCH (n) DETACH DELETE n").consume()
        try:
            ses.run("CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS "
                    "FOR (r:Resource) REQUIRE r.uri IS UNIQUE").consume()
            ses.run("MATCH (c:_GraphConfig) DETACH DELETE c").consume()
            ses.run("CALL n10s.graphconfig.init({handleVocabUris: 'IGNORE', "
                    "handleMultival: 'OVERWRITE', keepLangTag: false})").consume()
        except Neo4jError as e:
            sys.exit(f"✗ n10s 초기화 실패: {e.message.splitlines()[0]}\n"
                     "  → Neo4j Desktop 에서 해당 인스턴스에 neosemantics 플러그인이 설치되어 있는지 확인하세요.")
        r = ses.run("CALL n10s.rdf.import.inline($ttl, 'Turtle') "
                    "YIELD terminationStatus, triplesLoaded, triplesParsed, extraInfo "
                    "RETURN terminationStatus, triplesLoaded, triplesParsed, extraInfo",
                    ttl=ttl).single()
        print(f"n10s 적재: {r['terminationStatus']}  트리플 파싱 {r['triplesParsed']} / 적재 {r['triplesLoaded']}")
        if r["extraInfo"]:
            print("  참고:", r["extraInfo"][:300])
        rows = [x.data() for x in ses.run(
            "MATCH (n) UNWIND labels(n) AS lb WITH lb WHERE lb <> 'Resource' "
            "RETURN lb AS 레이블, count(*) AS 노드수 ORDER BY 노드수 DESC LIMIT 25")]
        print(table(["레이블", "노드수"], rows, limit=25))
        rels = [x.data() for x in ses.run(
            "MATCH ()-[r]->() RETURN type(r) AS 관계타입, count(*) AS 개수 ORDER BY 개수 DESC LIMIT 25")]
        print(table(["관계타입", "개수"], rels, limit=25))
        print("\n※ n10s 는 온톨로지 원래 이름(RnDProgram, fundedBy 등)을 그대로 쓰므로\n"
              "  queries.cypher 는 이 데이터베이스에서 그대로 실행되지 않습니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Neo4j .cypher 실행기")
    ap.add_argument("file", nargs="?", help="실행할 .cypher 파일")
    ap.add_argument("--n10s", metavar="TTL", help="n10s 로 가져올 Turtle 파일")
    ap.add_argument("--database", default=os.environ.get("NEO4J_DATABASE", "neo4j"))
    ap.add_argument("--out", default="neo4j-results.txt", help="질의 결과 저장 파일")
    args = ap.parse_args()
    if not args.file and not args.n10s:
        ap.print_help(); sys.exit(1)
    drv = connect(args)
    try:
        run_n10s(drv, args) if args.n10s else run_file(drv, args)
    finally:
        drv.close()
