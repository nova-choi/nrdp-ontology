"""kos-versioning SHACL 검사 테스트 (pyshacl). 실행: python3 kosv_shacl_tests.py <ontology_dir>"""
import sys, os
from rdflib import Graph
from pyshacl import validate

ONT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PFX = """
@prefix kosv: <https://w3id.org/nrdp/kosv#> .
@prefix xkos: <http://rdf-vocabulary.ddialliance.org/xkos#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix ex:   <https://w3id.org/nrdp/data#> .
"""
BASE = """
ex:NSTSC a kosv:Classification .
ex:E2018 a kosv:ClassificationEdition ; kosv:editionOf ex:NSTSC .
ex:E2023 a kosv:ClassificationEdition ; kosv:editionOf ex:NSTSC ; xkos:supersedes ex:E2018 .
ex:o_LC0306 skos:inScheme ex:E2018 . ex:o_LC0307 skos:inScheme ex:E2018 . ex:o_LC0308 skos:inScheme ex:E2018 .
ex:o_NA0401 skos:inScheme ex:E2018 .
ex:n_LC0322 skos:inScheme ex:E2023 . ex:n_LC0323 skos:inScheme ex:E2023 . ex:n_LC0324 skos:inScheme ex:E2023 .
ex:n_NA0401 skos:inScheme ex:E2023 .
ex:C1 a xkos:Correspondence ; kosv:sourceEdition ex:E2018 ; kosv:targetEdition ex:E2023 ;
      kosv:correspondenceBasis kosv:OfficialTable ;
      xkos:madeOf ex:A1 , ex:A2 , ex:A3 .
ex:A1 a xkos:ConceptAssociation ; kosv:changeType kosv:Identity ;
      xkos:sourceConcept ex:o_NA0401 ; xkos:targetConcept ex:n_NA0401 .
ex:A2 a xkos:ConceptAssociation ; kosv:changeType kosv:Merge ;
      xkos:sourceConcept ex:o_LC0307 , ex:o_LC0308 ; xkos:targetConcept ex:n_LC0324 .
ex:A3 a xkos:ConceptAssociation ; kosv:changeType kosv:Split ;
      xkos:sourceConcept ex:o_LC0306 ; xkos:targetConcept ex:n_LC0322 , ex:n_LC0323 .
ex:S1 a kosv:AllocationShare ; kosv:shareOf ex:A3 ; kosv:fromConcept ex:o_LC0306 ; kosv:toConcept ex:n_LC0322 ; kosv:shareValue "0.5"^^xsd:decimal .
ex:S2 a kosv:AllocationShare ; kosv:shareOf ex:A3 ; kosv:fromConcept ex:o_LC0306 ; kosv:toConcept ex:n_LC0323 ; kosv:shareValue "0.5"^^xsd:decimal .
"""

CASES = [
    ("정상 대응표 (동일·통합·분할+배분)", "", "", True, 0),
    ("통합인데 원천 1개 → K2", "", 'ex:A2', False, None),
    ("대상 개념이 이전 판 소속 → K3", 'ex:A1 xkos:targetConcept ex:o_LC0306 .', "", False, None),
    ("배분 비중 합 0.8 → K4", "", 'ex:S2', False, None),
    ("대응 근거 누락 → K1", "", 'ex:C1#basis', False, None),
    ("분할에 배분 없음 → K5 경고만(적합)", "", 'ex:S1ex:S2', True, 1),
]

def build(extra, mutate):
    data = BASE
    if mutate == 'ex:A2':
        data = data.replace("xkos:sourceConcept ex:o_LC0307 , ex:o_LC0308 ;", "xkos:sourceConcept ex:o_LC0307 ;")
    if mutate == 'ex:S2':
        data = data.replace('ex:n_LC0323 ; kosv:shareValue "0.5"', 'ex:n_LC0323 ; kosv:shareValue "0.3"')
    if mutate == 'ex:C1#basis':
        data = data.replace("kosv:correspondenceBasis kosv:OfficialTable ;", "")
    if mutate == 'ex:S1ex:S2':
        data = "\n".join(l for l in data.splitlines() if not l.startswith("ex:S1") and not l.startswith("ex:S2"))
    g = Graph(); g.parse(data=PFX + data + extra, format="turtle")
    return g

def main():
    shapes = Graph().parse(os.path.join(ONT, "kosv-shapes.ttl"))
    ok_all = True
    for name, extra, mutate, expect_conforms, expect_warn in CASES:
        g = build(extra, mutate)
        conforms, rg, text = validate(g, shacl_graph=shapes, advanced=True, allow_warnings=True)
        warns = text.count("Severity: sh:Warning")
        msgs = sorted({l.strip()[9:] for l in text.splitlines() if l.strip().startswith("Message:")})
        ok = (conforms == expect_conforms) and (expect_warn is None or warns == expect_warn)
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} — conforms={conforms}, warnings={warns} {msgs[:2]}")
    print("ALL PASS" if ok_all else "SOME FAILED")
    sys.exit(0 if ok_all else 1)

if __name__ == "__main__":
    main()
