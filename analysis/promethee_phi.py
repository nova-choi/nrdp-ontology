"""PROMETHEE II 순흐름의 기준별 분해 (phi = sum_j w_j * phi_j).
입력은 그래프(nrdp-mcdm.ttl)에서 SPARQL로 조회한 min-max 정규화값·가중치·선호함수 임계값이며,
조회값으로 다시 계산한 phi 가 그래프에 기록된 PROMETHEE II 점수(hasScore)와 일치하는지 먼저 확인한다.
실행: python promethee_phi.py <nrdp-mcdm.ttl> [시나리오 id ...]   출력: promethee_phi_<S>.csv
"""
import sys, csv
from collections import defaultdict
from rdflib import Graph
g = Graph().parse(sys.argv[1])
SC = sys.argv[2:] or ['S1', 'S2', 'S3']
P = """PREFIX mcdm: <https://w3id.org/nrdp/mcdm#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ex: <https://w3id.org/nrdp/data#>
"""
# 선호함수 임계값
q, p = [float(x) for x in next(iter(g.query(P + """SELECT ?q ?p WHERE { ex:M_PRO2 mcdm:usesPreferenceFunction ?f .
  ?f mcdm:preferenceThresholdQ ?q ; mcdm:preferenceThresholdP ?p }""")))]
# 정규화값 (min-max), 기준 라벨
norm = defaultdict(dict); label = {}
for alt, c, cl, v in g.query(P + """SELECT ?alt ?c ?cl ?v WHERE {
    ?nv mcdm:ofCriterionValue ?cv ; mcdm:normalizedBy ex:NM_MinMax ; mcdm:hasValue ?v .
    ?cv mcdm:ofAlternative ?alt ; mcdm:onCriterion ?c . ?c rdfs:label ?cl }"""):
    norm[str(c)][str(alt)] = float(v); label[str(c)] = str(cl)
alts = sorted(set.intersection(*[set(d) for d in norm.values()]))
alabel = {str(a): str(l) for a, l in g.query(P + "SELECT ?a ?l WHERE { ?a a mcdm:Alternative ; rdfs:label ?l }")}
def pref(d): return 0.0 if d <= q else (1.0 if d >= p else (d - q) / (p - q))
n = len(alts)
phij = {c: {a: sum(pref(norm[c][a] - norm[c][b]) - pref(norm[c][b] - norm[c][a]) for b in alts if b != a) / (n - 1)
            for a in alts} for c in norm}
for s in SC:
    w = {str(c): float(v) for c, v in g.query(P + f"""SELECT ?c ?v WHERE {{ ex:{s} mcdm:hasWeight ?w .
        ?w mcdm:assignedToCriterion ?c ; mcdm:hasWeightValue ?v }}""")}
    rec = {str(a): (float(sc), int(rk)) for a, sc, rk in g.query(P + f"""SELECT ?a ?s ?r WHERE {{ ?dr mcdm:forScenario ex:{s} ;
        mcdm:byMethod ex:M_PRO2 ; mcdm:forAlternative ?a ; mcdm:hasScore ?s ; mcdm:hasRank ?r }}""")}
    phi = {a: sum(w[c] * phij[c][a] for c in w) for a in alts}
    err = max(abs(phi[a] - rec[a][0]) for a in alts)
    print(f'{s}: q={q} p={p} 대안 {n}개, 재계산 phi 와 기록 점수의 최대 차 {err:.2e}')
    crit = sorted(w, key=lambda c: c)
    with open(f'promethee_phi_{s}.csv', 'w', newline='', encoding='utf-8-sig') as f:
        wr = csv.writer(f); wr.writerow(['rank', 'alternative', 'phi'] + [f'w*phi_j:{label[c]}' for c in crit] + [f'phi_j:{label[c]}' for c in crit])
        for a in sorted(alts, key=lambda a: rec[a][1]):
            wr.writerow([rec[a][1], alabel[a], round(phi[a], 6)] + [round(w[c] * phij[c][a], 6) for c in crit] + [round(phij[c][a], 6) for c in crit])
    for a in sorted(alts, key=lambda a: rec[a][1])[:3]:
        parts = sorted(((w[c] * phij[c][a], label[c], phij[c][a]) for c in crit), reverse=True)
        print(f'  {rec[a][1]}위 {alabel[a]} phi={phi[a]:.4f} :: ' + ', '.join(f'{l} {x:+.4f}(phi_j {pj:+.3f})' for x, l, pj in parts))
