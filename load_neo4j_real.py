#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실데이터 RDF(data/rdf/*.ttl) → Neo4j 5.x 속성그래프 적재기 (OWL→LPG 변환 규칙의 구현).

변환 규칙 (논문 3.7절 '그래프 계층 위임'의 실례)
  - 개체(IRI 주어)                 → 노드. id = IRI 지역명(# 또는 마지막 / 뒤), iri = 전체 IRI
  - rdf:type 의 클래스 지역명       → 노드 레이블 (다중 타입 = 다중 레이블, 예: :LeafCriterion:BenefitCriterion)
  - 데이터타입 속성                 → 노드 속성 (지역명; 같은 속성 여러 값은 목록). rdfs:label 은 label(ko 우선)·label_en
  - 객체 속성                       → 관계. 타입 = 지역명을 UPPER_SNAKE 로 (partOfProgram → PART_OF_PROGRAM)
  - 온톨로지 어휘(클래스·속성 선언)과 빈 노드는 적재하지 않음. 온톨로지의 명명 개체(mcdm:Benefit 등)는 적재.
  - 추론 없음: partOfProgram 의 추이성, contributesTo 의 속성 사슬은 Cypher 가변 길이 경로로 질의 시점에 처리.

접속: run_cypher.py 와 같은 환경변수 (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
실행: python load_neo4j_real.py [--keep]     (--keep 없으면 기존 데이터 전부 삭제 후 적재)
출력: data/rdf/neo4j_load_report.json (레이블·관계별 건수)
"""
import os, sys, re, json, time, getpass, argparse
from collections import defaultdict, Counter
from rdflib import Graph, RDF, RDFS, OWL, Literal, URIRef, BNode
from neo4j import GraphDatabase

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except Exception: pass

ROOT = os.path.dirname(os.path.abspath(__file__))
FILES = ["ontology/mcdm-core.ttl", "ontology/kos-versioning.ttl", "ontology/nrdp-ontology.ttl",
         "data/rdf/nrdp-schemes.ttl", "data/rdf/nrdp-domain.ttl", "data/rdf/nrdp-mcdm.ttl"]
VOCAB_TYPES = {OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.Ontology,
               RDFS.Class, RDF.Property, RDFS.Datatype, OWL.Restriction, OWL.AllDifferent, OWL.AllDisjointClasses}
SKIP_PRED = {RDF.type, RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range, OWL.equivalentClass,
             OWL.disjointWith, OWL.inverseOf, OWL.imports, OWL.versionIRI, OWL.priorVersion, OWL.propertyChainAxiom,
             OWL.onProperty, OWL.someValuesFrom, OWL.allValuesFrom, OWL.hasValue, OWL.oneOf, OWL.unionOf,
             OWL.intersectionOf, OWL.members, OWL.distinctMembers}

def local(u):
    s = str(u)
    return re.split(r"[#/]", s.rstrip("/"))[-1] or s

def snake(name):
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return s.upper()

def pyval(l):
    v = l.toPython()
    if isinstance(v, Literal):          # 변환 실패 시 문자열
        return str(l)
    try:
        import decimal, datetime
        if isinstance(v, decimal.Decimal): return float(v)
        if isinstance(v, (datetime.datetime, datetime.date)): return v.isoformat()
    except Exception:
        pass
    return v

def export_csv(args, nodes, rels):
    """LOAD CSV 경로: 노드는 한 종류의 넓은 CSV(열 = 모든 속성 합집합, 빈 칸 = 없음), 관계는 (type, from, to).
    Cypher 25 의 동적 레이블·관계 타입(CREATE (n:$(list)))을 쓰므로 Neo4j 5.26 이상이 필요하다.
    같은 열의 값 타입은 파이썬 타입으로 정해 toFloat/toInteger/toBoolean 변환식을 생성한다."""
    import csv
    os.makedirs(args.csv, exist_ok=True)
    cols, ctype = [], {}
    for n in nodes.values():
        for k, v in n["props"].items():
            if k not in ctype:
                cols.append(k)
            x = v[0] if isinstance(v, list) and v else v
            kind = "bool" if isinstance(x, bool) else "int" if isinstance(x, int) else "float" if isinstance(x, float) else "str"
            prev = ctype.get(k)
            ctype[k] = kind if prev in (None, kind) else ("float" if {prev, kind} <= {"int", "float"} else "str")
    CH = 40000
    rows = list(nodes.values())
    nfiles = 0
    for i in range(0, len(rows), CH):
        nfiles += 1
        with open(os.path.join(args.csv, f"nodes_{nfiles}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["iri", "id", "labels"] + cols)
            for n in rows[i:i + CH]:
                vals = []
                for k in cols:
                    v = n["props"].get(k, "")
                    if isinstance(v, list): v = " | ".join(str(x) for x in v)
                    if isinstance(v, bool): v = "true" if v else "false"
                    vals.append(v)
                w.writerow([n["iri"], n["id"], ":".join(sorted(n["labels"] | {"Node"}))] + vals)
    rfiles = 0
    for i in range(0, len(rels), 100000):
        rfiles += 1
        with open(os.path.join(args.csv, f"rels_{rfiles}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["type", "from", "to"])
            w.writerows(rels[i:i + 100000])
    conv = {"bool": "toBoolean(row.`{k}`)", "int": "toInteger(row.`{k}`)", "float": "toFloat(row.`{k}`)", "str": "row.`{k}`"}
    sets = ", ".join(f"n.`{k}` = CASE row.`{k}` WHEN '' THEN null ELSE {conv[ctype[k]].format(k=k)} END" for k in cols)
    L = ["// load_neo4j_real.py --csv 가 생성. Neo4j 5.26+/2025.x (동적 레이블). 파일은 import 폴더의 nrdp/ 아래에 둔다.",
         "MATCH (n) DETACH DELETE n;",
         "CREATE CONSTRAINT node_iri IF NOT EXISTS FOR (n:Node) REQUIRE n.iri IS UNIQUE;",
         "CREATE INDEX node_id IF NOT EXISTS FOR (n:Node) ON (n.id);"]
    for i in range(1, nfiles + 1):
        L.append(f"LOAD CSV WITH HEADERS FROM '{args.csv_url}nodes_{i}.csv' AS row\n"
                 f"CREATE (n:$(split(row.labels, ':'))) SET n.iri = row.iri, n.id = row.id, {sets};")
    for i in range(1, rfiles + 1):
        L.append(f"LOAD CSV WITH HEADERS FROM '{args.csv_url}rels_{i}.csv' AS row\n"
                 f"MATCH (a:Node {{iri: row.from}}), (b:Node {{iri: row.to}}) CREATE (a)-[:$(row.type)]->(b);")
    open(os.path.join(args.csv, "load_csv.cypher"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"CSV 생성: 노드 파일 {nfiles} ({len(nodes):,}건, 열 {len(cols)}), 관계 파일 {rfiles} ({len(rels):,}건) → {args.csv}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="기존 데이터를 지우지 않음")
    ap.add_argument("--database", default=os.environ.get("NEO4J_DATABASE", "neo4j"))
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--dry-run", action="store_true", help="DB 접속 없이 변환 결과(노드·관계 건수)만 출력")
    ap.add_argument("--csv", metavar="DIR", help="DB 접속 대신 LOAD CSV 용 파일(nodes_*.csv, rels_*.csv)과 load_csv.cypher 를 DIR 에 생성")
    ap.add_argument("--csv-url", default="file:///nrdp/", help="load_csv.cypher 에 쓸 URL 접두(Neo4j import 폴더 기준)")
    args = ap.parse_args()

    g = Graph(); t0 = time.time()
    for f in FILES:
        g.parse(os.path.join(ROOT, f), format="turtle")
    print(f"RDF 적재 {len(g):,} 트리플 ({time.time()-t0:.0f}s)")

    # ── 노드 수집 ──
    types = defaultdict(set)
    for s, o in g.subject_objects(RDF.type):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            types[s].add(o)
    vocab = {s for s, ts in types.items() if ts & VOCAB_TYPES}
    nodes = {}                                           # iri → {id, iri, labels:set, props}
    def node(iri):
        if iri not in nodes:
            nodes[iri] = {"id": local(iri), "iri": str(iri), "labels": set(), "props": {}}
        return nodes[iri]
    for s, ts in types.items():
        if s in vocab: continue
        n = node(s)
        for t in ts: n["labels"].add(local(t))
    # 타입 없이 객체로만 등장하는 IRI(예: 온톨로지 밖 개체) → :Resource
    rels = []                                            # (type, from_iri, to_iri)
    rel_count = Counter()
    for s, p, o in g:
        if p in SKIP_PRED or isinstance(s, BNode) or s in vocab or isinstance(o, BNode):
            continue
        if isinstance(o, Literal):
            if s in vocab or s not in nodes:
                continue
            n = nodes[s]
            key = local(p)
            if p == RDFS.label:
                if o.language == "en":
                    n["props"].setdefault("label_en", str(o))
                elif "label" not in n["props"] or o.language == "ko":
                    n["props"]["label"] = str(o)
                continue
            v = pyval(o)
            if key in n["props"]:
                cur = n["props"][key]
                n["props"][key] = (cur if isinstance(cur, list) else [cur]) + [v]
            else:
                n["props"][key] = v
        elif isinstance(o, URIRef):
            if o in vocab or s not in nodes:
                continue
            if o not in nodes:
                node(o)["labels"].add("Resource")
            rt = snake(local(p))
            rels.append((rt, str(s), str(o)))
            rel_count[rt] += 1
    for n in nodes.values():
        if not n["labels"]:
            n["labels"].add("Resource")

    if args.csv:
        export_csv(args, nodes, rels)
        return

    if args.dry_run:
        lab = Counter(lb for n in nodes.values() for lb in n["labels"])
        print(f"[dry-run] 노드 {len(nodes):,} / 관계 {len(rels):,}")
        for lb, c in lab.most_common(40): print(f"  {lb:32s} {c:>8,}")
        for rt, c in rel_count.most_common(60): print(f"  -[{rt}]-> {c:,}")
        return

    # ── Neo4j 적재 ──
    uri = os.environ.get("NEO4J_URI", "neo4j://127.0.0.1:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD") or getpass.getpass(f"Neo4j 비밀번호 ({user}@{uri}): ")
    drv = GraphDatabase.driver(uri, auth=(user, pw)); drv.verify_connectivity()
    print(f"✓ 연결됨: {uri} (database={args.database})")
    by_labels = defaultdict(list)
    for n in nodes.values():
        by_labels[":".join(sorted(n["labels"]))].append(n)
    all_labels = sorted({lb for n in nodes.values() for lb in n["labels"]})
    t1 = time.time()
    with drv.session(database=args.database) as ses:
        if not args.keep:
            ses.run("MATCH (n) DETACH DELETE n").consume()
        for lb in all_labels:
            ses.run(f"CREATE CONSTRAINT {re.sub(r'[^A-Za-z0-9_]', '_', lb).lower()}_iri IF NOT EXISTS FOR (n:`{lb}`) REQUIRE n.iri IS UNIQUE").consume()
        ses.run("CREATE INDEX resource_id IF NOT EXISTS FOR (n:Resource) ON (n.id)").consume()
        # 관계 적재의 iri 매칭이 색인을 타도록 공통 레이블 :Node 를 붙인다(LOAD CSV 경로와 동일)
        ses.run("CREATE CONSTRAINT node_iri IF NOT EXISTS FOR (n:Node) REQUIRE n.iri IS UNIQUE").consume()
        ses.run("CALL db.awaitIndexes(300)").consume()
        done = 0
        for lbs, ns in by_labels.items():
            labels = ":".join(f"`{x}`" for x in lbs.split(":") + ["Node"])
            for i in range(0, len(ns), args.batch):
                rows = [dict(id=n["id"], iri=n["iri"], **n["props"]) for n in ns[i:i + args.batch]]
                ses.run(f"UNWIND $rows AS r CREATE (n:{labels}) SET n = r", rows=rows).consume()
                done += len(rows)
            print(f"\r  노드 {done:,}/{len(nodes):,}", end="", flush=True)
        print()
        by_type = defaultdict(list)
        for rt, a, b in rels:
            by_type[rt].append([a, b])
        done = 0
        for rt, pairs in by_type.items():
            for i in range(0, len(pairs), args.batch):
                ses.run(f"UNWIND $rows AS r MATCH (a:Node {{iri: r[0]}}), (b:Node {{iri: r[1]}}) CREATE (a)-[:`{rt}`]->(b)",
                        rows=pairs[i:i + args.batch]).consume()
                done += len(pairs[i:i + args.batch])
            print(f"\r  관계 {done:,}/{len(rels):,}", end="", flush=True)
        print()
        lab = [r.data() for r in ses.run("MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS n ORDER BY n DESC")]
        rel = [r.data() for r in ses.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY n DESC")]
    drv.close()
    report = {"nodes": len(nodes), "rels": len(rels), "seconds": round(time.time() - t1, 1),
              "by_label": {r["label"]: r["n"] for r in lab}, "by_rel": {r["type"]: r["n"] for r in rel}}
    json.dump(report, open(os.path.join(ROOT, "data", "rdf", "neo4j_load_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"적재 완료: 노드 {len(nodes):,} / 관계 {len(rels):,} ({report['seconds']}s)")
    for r in lab[:30]: print(f"  {r['label']:32s} {r['n']:>8,}")

if __name__ == "__main__":
    main()
