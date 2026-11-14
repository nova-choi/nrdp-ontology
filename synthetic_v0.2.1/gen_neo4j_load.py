#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Neo4j 5.x 적재 스크립트(load_neo4j.cypher) 생성기.

queries.cypher 의 명명 규칙에 맞춘다:
  - 노드 레이블: Program, Ministry, Criterion ...
  - 관계 타입  : FUNDED_BY, HAS_WEIGHT ...
  - OWL 하위클래스 → 다중 레이블 (예: :Criterion:CostCriterion,
                                      :Method:AggregationMethod:OutrankingMethod)
  - 값이 없는 속성은 아예 만들지 않음
  - v0.2: 정규화값은 CriterionValue.norm 속성이 아니라 NormalizedValue 노드
    (HAS_NORMALIZATION/NORMALIZED_BY)로 재화 — CQ12는 관계 부재로 판정

gen_data.py 와 같은 데이터 구조에서 생성하므로 SPARQL·kuzu 검증 데이터와 동일하다.

2026-10-10: RDF 레이블 동기화 추가 (sync_labels_from_rdf).
  노드의 label 과 Criterion.scale 을 data-sample.ttl·nrdp-ontology.ttl 의 rdfs:label 로
  맞춘다. SPARQL 결과와 Cypher 결과가 값뿐 아니라 표기까지 일치하도록 하기 위함.
  rdflib 필요 (pip install rdflib).
"""
import json
import gen_data as G

YEARS = (2021, 2022, 2023)
nodes = {}   # 레이블문자열 -> [props]
rels = {}    # (타입, 출발레이블, 도착레이블) -> [(id, id)]

def N(labels, **props):
    nodes.setdefault(labels, []).append({k: v for k, v in props.items() if v is not None})
def R(rtype, la, ia, lb, ib):
    rels.setdefault((rtype, la, lb), []).append((ia, ib))

# ───── 도메인 계층 ─────
for y in YEARS:                          N("FiscalYear", id=f"FY{y}", year=y)
for k, (lb, cd) in G.FIELDS.items():     N("TechField", id=k, label=lb, notation=cd)
for k, v in G.MINISTRIES.items():        N("Ministry:Organization", id=k, label=v)
for k, v in G.AGENCIES.items():          N("Agency:Organization", id=k, label=v)
for k, v in G.PERFORMERS.items():        N("Performer:Organization", id=k, label=v)
for k, v in G.GOALS.items():             N("PolicyGoal", id=k, label=v)
for k, (lb, un) in G.INDICATORS.items(): N("Indicator", id=k, label=lb, unit=un)

for pid, (name, mn, ag, tf, goals) in G.PROGRAMS.items():
    N("Program", id=pid, code=pid, label=name)
    R("FUNDED_BY", "Program", pid, "Ministry", mn)
    R("MANAGED_BY", "Program", pid, "Agency", ag)
    R("BELONGS_TO_FIELD", "Program", pid, "TechField", tf)
    for g in goals: R("CONTRIBUTES_TO", "Program", pid, "PolicyGoal", g)
    for i, y in enumerate(YEARS):
        ba = f"BA_{pid}_{y}"
        N("BudgetAllocation", id=ba, amount=float(G.BUDGET[pid][i]))
        R("HAS_ALLOCATION", "Program", pid, "BudgetAllocation", ba)
        R("IN_FY", "BudgetAllocation", ba, "FiscalYear", f"FY{y}")
        for tag, src, ind in (("PAP", G.PAPERS, "IND_EFF"), ("PAT", G.PATENTS, "IND_PAT")):
            ob = f"OB_{pid}_{tag}_{y}"
            N("Observation", id=ob, value=float(src[pid][i]))
            R("HAS_OBSERVATION", "Program", pid, "Observation", ob)
            R("IN_FY", "Observation", ob, "FiscalYear", f"FY{y}")
            R("FOR_INDICATOR", "Observation", ob, "Indicator", ind)

for sid, (lb, parent) in G.SUBPROGRAMS.items():
    N("SubProgram", id=sid, label=lb); R("PART_OF", "SubProgram", sid, "Program", parent)
for jid, (lb, parent, orgs) in G.PROJECTS.items():
    N("Project", id=jid, label=lb); R("PART_OF", "Project", jid, "SubProgram", parent)
    for o in orgs: R("PERFORMED_BY", "Project", jid, "Performer", o)

# ───── MCDM 표현 계층 ─────
N("DecisionProblem", id="DP1", label="2023년 전략기술 3개 분야 R&D 포트폴리오 평가")
for pid, (name, *_r) in G.PROGRAMS.items():
    a = f"ALT_{pid}"
    N("Alternative", id=a, label=name)
    R("REPRESENTS", "Alternative", a, "Program", pid)
    R("HAS_ALTERNATIVE", "DecisionProblem", "DP1", "Alternative", a)

for cid, (lb, direction, scale, ind, unit, parent) in G.CRITERIA.items():
    labels = "Criterion" + {"Benefit": ":BenefitCriterion", "Cost": ":CostCriterion"}.get(direction, "")
    N(labels, id=cid, label=lb, direction=direction, scale=scale)
    R("HAS_CRITERION", "DecisionProblem", "DP1", "Criterion", cid)
    if ind: R("MEASURED_BY", "Criterion", cid, "Indicator", ind)
    if parent: R("HAS_SUBCRITERION", "Criterion", parent, "Criterion", cid)

for pid in G.PROGRAMS:
    for c in G.LEAVES:
        if pid == "P09" and c == "C2b":            # CQ13: 평가값 결측
            continue
        cv = f"CV_{pid}_{c}"
        N("CriterionValue", id=cv, raw=float(G.RAW[c][pid]), unit=G.CRITERIA[c][4])
        R("OF_ALTERNATIVE", "CriterionValue", cv, "Alternative", f"ALT_{pid}")
        R("ON_CRITERION", "CriterionValue", cv, "Criterion", c)
        # v0.2: 정규화값은 (평가값×정규화방법) 3항 관계 → NormalizedValue 노드로 재화.
        # P09는 FULL 밖이라 두 방법 모두 결여 (CQ12가 P09의 5건을 전부 탐지).
        if pid in G.FULL:
            for suffix, nmid, table in (("MinMax", "NM_MinMax", G.NORM_MINMAX),
                                         ("Vector", "NM_Vector", G.NORM_VECTOR)):
                nv = f"NV_{pid}_{c}_{suffix}"
                N("NormalizedValue", id=nv, value=round(table[c][pid], 4))
                R("HAS_NORMALIZATION", "CriterionValue", cv, "NormalizedValue", nv)
                R("NORMALIZED_BY", "NormalizedValue", nv, "Normalization", nmid)

N("Normalization", id="NM_MinMax", label="min-max 정규화")
N("Normalization", id="NM_Vector", label="벡터 정규화")
N("PreferenceFunction", id="PF_VShape", label="V-shape 선호함수", q=0.0, p=0.5)
for mid, (lb, cls, model, rn, _fn) in G.METHODS.items():
    N(f"Method:AggregationMethod:{cls}", id=mid, label=lb, kind=cls, prefModel=model, requiresNorm=rn)
    R("USES_NORM", "Method", mid, "Normalization", "NM_Vector" if mid == "M_TOPSIS" else "NM_MinMax")
    if mid == "M_PRO2": R("USES_PREFFN", "Method", mid, "PreferenceFunction", "PF_VShape")

for sid, (lb, desc, goals, W) in G.SCENARIOS.items():
    N("Scenario", id=sid, label=lb, descr=desc)
    for g in goals: R("REFLECTS_GOAL", "Scenario", sid, "PolicyGoal", g)
    for c, v in W.items():
        wid = f"W_{sid}_{c}"
        N("Weight", id=wid, value=v)
        R("HAS_WEIGHT", "Scenario", sid, "Weight", wid)
        R("ASSIGNED_TO", "Weight", wid, "Criterion", c)

for (sid, mid), rows in G.RESULTS.items():
    for pid, (sc, rk) in rows.items():
        dr = f"DR_{sid}_{mid}_{pid}"
        N("DecisionResult", id=dr, score=round(sc, 6), rank=rk)
        R("FOR_PROBLEM", "DecisionResult", dr, "DecisionProblem", "DP1")
        R("FOR_SCENARIO", "DecisionResult", dr, "Scenario", sid)
        R("BY_METHOD", "DecisionResult", dr, "Method", mid)
        R("OF_ALTERNATIVE", "DecisionResult", dr, "Alternative", f"ALT_{pid}")

W1 = G.SCENARIOS["S1"][3]
for pid in G.FULL:
    total = sum(W1[c] * G.NORM_MINMAX[c][pid] for c in G.LEAVES)
    for c in G.LEAVES:
        cc = f"CC_S1_WSM_{pid}_{c}"
        N("Contribution:Explanation", id=cc,
          ratio=round((W1[c] * G.NORM_MINMAX[c][pid]) / total, 4) if total else 0.0)
        R("EXPLAINS", "Contribution", cc, "DecisionResult", f"DR_S1_M_WSM_{pid}")
        R("CONTRIBUTION_OF", "Contribution", cc, "Criterion", c)

for tgt, c, gap, nn, nr, fe in G.CF:
    cf = f"CF_{tgt}_{c}"
    N("Counterfactual:Explanation", id=cf, needNorm=nn, needRaw=nr, feasible=fe)
    R("EXPLAINS", "Counterfactual", cf, "DecisionResult", f"DR_S1_M_WSM_{tgt}")
    R("CONCERNS_CRITERION", "Counterfactual", cf, "Criterion", c)   # mcdm:concernsCriterion (v0.2.1)

# ───── 출처 계층 (PROV-O) ─────
N("ProvEntity", id="SRC_NTIS2023", label="NTIS 2023년 국가R&D조사분석 데이터셋")
for pid in ("P01", "P05"):
    N("ProvEntity", id=f"NTIS_{pid}", label=f"NTIS 사업 레코드 {pid}")
    R("WAS_DERIVED_FROM", "ProvEntity", f"NTIS_{pid}", "ProvEntity", "SRC_NTIS2023")
    for c in ("C1", "C2a"):
        N("ProvActivity", id=f"ACT_{pid}_{c}", label="min-max 정규화 수행")
        N("ProvEntity", id=f"RAW_{pid}_{c}", label="원시통계값")
        R("WAS_GENERATED_BY", "CriterionValue", f"CV_{pid}_{c}", "ProvActivity", f"ACT_{pid}_{c}")
        R("USED", "ProvActivity", f"ACT_{pid}_{c}", "ProvEntity", f"RAW_{pid}_{c}")
        R("WAS_DERIVED_FROM", "ProvEntity", f"RAW_{pid}_{c}", "ProvEntity", f"NTIS_{pid}")

# ───── RDF 레이블 동기화 ─────
#  SPARQL(sparql-results.txt)과 Cypher(neo4j-results.txt)가 같은 표기를 쓰도록
#  RDF의 rdfs:label을 단일 기준으로 삼는다. gen_data 를 import 하는 시점에
#  data-sample.ttl 이 새로 생성되므로, 아래에서 읽는 RDF는 항상 이번 실행의 데이터다.
#   ① 노드 id 가 RDF 개체 ex:<id> 와 같고 그 개체에 rdfs:label 이 있으면 label 을 덮어쓴다.
#   ② Criterion.scale 은 척도 개체(mcdm:RatioScale 등)의 rdfs:label 로 바꾸고,
#      원래 지역명은 scaleIri 속성에 보존한다.
#   id 가 RDF와 다른 노드(예: ProvActivity ACT_* ↔ ACT_NORM_*)는 기존 label 을 유지하고 보고만 한다.
def sync_labels_from_rdf(nodes, data_ttl="data-sample.ttl", onto_ttl="nrdp-ontology.ttl"):
    try:
        from rdflib import Graph, Namespace, RDFS, Literal
    except ImportError:
        raise SystemExit("rdflib 이 필요합니다: pip install rdflib  (RDF 레이블 동기화 단계)")
    EX = Namespace("https://w3id.org/nrdp/data#")
    MCDM = Namespace("https://w3id.org/nrdp/mcdm#")
    g = Graph()
    g.parse(onto_ttl, format="turtle")
    g.parse(data_ttl, format="turtle")

    def rdf_label(iri):
        labs = [o for o in g.objects(iri, RDFS.label) if isinstance(o, Literal)]
        if not labs:
            return None
        ko = [o for o in labs if o.language == "ko"]
        return str((ko or labs)[0])

    changed, unmatched = [], []
    for lb, rows in nodes.items():
        for r in rows:
            if "label" in r:
                new = rdf_label(EX[r["id"]])
                if new is None:
                    unmatched.append((lb.split(":")[0], r["id"]))
                elif new != r["label"]:
                    changed.append((r["id"], "label", r["label"], new))
                    r["label"] = new
            if lb.split(":")[0] == "Criterion" and "scale" in r:
                new = rdf_label(MCDM[r["scale"]])
                if new is not None and new != r["scale"]:
                    changed.append((r["id"], "scale", r["scale"], new))
                    r["scaleIri"] = r["scale"]
                    r["scale"] = new
    print(f"RDF 레이블 동기화: 변경 {len(changed)}건 / RDF에 같은 id가 없어 유지 {len(unmatched)}건")
    for cid, key, old, new in changed:
        print(f"  {cid}.{key}: {old} → {new}")
    for base, nid in unmatched:
        print(f"  (유지) {base} {nid}")
    return changed, unmatched

SYNC_CHANGED, SYNC_UNMATCHED = sync_labels_from_rdf(nodes)

# ═════════ Cypher 출력 ═════════
def lit(v):
    """파이썬 값 → Cypher 리터럴"""
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {lit(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)): return "[" + ", ".join(lit(x) for x in v) + "]"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"

def chunk(seq, n=40):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]

base_labels = sorted({lb.split(":")[0] for lb in nodes})
n_nodes = sum(len(v) for v in nodes.values())
n_rels = sum(len(v) for v in rels.values())

out = []
w = out.append
w("// ═══════════════════════════════════════════════════════════════════")
w("//  국가 R&D 포트폴리오 MCDM 온톨로지 — Neo4j 5.x 적재 스크립트")
w("//  gen_neo4j_load.py 가 자동 생성. 직접 수정하지 마십시오.")
w(f"//  노드 {n_nodes}개 / 관계 {n_rels}개  (합성 샘플 데이터 — 실제 통계 아님)")
w(f"//  RDF 레이블 동기화 적용: 변경 {len(SYNC_CHANGED)}건 (label·scale 을 rdfs:label 기준으로 통일)")
w("//")
w("//  실행 방법")
w("//   (권장) python run_cypher.py load_neo4j.cypher")
w("//   (대안) Neo4j Browser 에서 '여러 문장 실행' 설정을 켜고 전체 붙여넣기")
w("// ═══════════════════════════════════════════════════════════════════")
w("")
w("// ── 0. 초기화: 기존 데이터 전부 삭제 (재실행 가능) ──")
w("MATCH (n) DETACH DELETE n;")
w("")
w("// ── 1. 고유성 제약조건 (id 로 조회하므로 인덱스 역할도 함) ──")
for lb in base_labels:
    w(f"CREATE CONSTRAINT {lb.lower()}_id IF NOT EXISTS FOR (n:{lb}) REQUIRE n.id IS UNIQUE;")
w("")
w("// ── 2. 노드 ──")
for lb, rows in nodes.items():
    for part in chunk(rows):
        w(f"UNWIND {lit(part)} AS r")
        w(f"CREATE (n:{lb}) SET n = r;")
w("")
w("// ── 3. 관계 ──")
for (rt, la, lb), pairs in rels.items():
    for part in chunk(pairs, 60):
        w(f"UNWIND {lit([list(p) for p in part])} AS r")
        w(f"MATCH (a:{la} {{id: r[0]}}), (b:{lb} {{id: r[1]}})")
        w(f"CREATE (a)-[:{rt}]->(b);")
w("")
w("// ── 4. 적재 확인 ──")
w("MATCH (n) RETURN labels(n)[0] AS `레이블`, count(*) AS `노드수` ORDER BY `노드수` DESC;")

open("load_neo4j.cypher", "w", encoding="utf-8").write("\n".join(out) + "\n")

# 검증용 기대값 저장
expected = {
    "nodes": n_nodes, "rels": n_rels,
    "by_label": {lb: sum(len(v) for k, v in nodes.items() if k.split(":")[0] == lb) for lb in base_labels},
    "by_rel": {}
}
for (rt, _a, _b), pairs in rels.items():
    expected["by_rel"][rt] = expected["by_rel"].get(rt, 0) + len(pairs)
json.dump(expected, open("expected_counts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"load_neo4j.cypher 생성: 노드 {n_nodes} / 관계 {n_rels} / 문장 {sum(1 for l in out if l.rstrip().endswith(';'))}")
