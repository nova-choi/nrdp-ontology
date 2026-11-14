"""v0.3 공리 단위 테스트 (v0.3.4 갱신 2026-10-23: 예산 코드 복수 사례 / v0.3.2 갱신 2026-10-19: 보상 수준 배정, 7번 정규화값 사례 / v0.3.3 갱신 2026-10-20: partOfProgram 순환 사례 2건) — HermiT(owlready2 내장)로 추론·일관성 검사.

각 케이스는 (이름, 추가 ABox turtle, 기대: 'consistent' | 'inconsistent', 확인할 추론 목록)
추론 확인은 (개체, 기대 클래스) 쌍. 실행: python3 axiom_tests.py <ontology_dir>
"""
import sys, os, tempfile, subprocess
from rdflib import Graph, URIRef, OWL, RDF

ONT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PFX = """
@prefix nrdp: <https://w3id.org/nrdp/ontology#> .
@prefix mcdm: <https://w3id.org/nrdp/mcdm#> .
@prefix ex:   <https://w3id.org/nrdp/data#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix kosv: <https://w3id.org/nrdp/kosv#> .
@prefix xkos: <http://rdf-vocabulary.ddialliance.org/xkos#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
"""

def schema_graph():
    g = Graph()
    for f in ("mcdm-core.ttl", "kos-versioning.ttl", "nrdp-ontology.ttl"):
        g.parse(os.path.join(ONT, f))
    for s, p, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p, o))
    return g

BASE_ABOX = """
ex:C2  a mcdm:Criterion ; mcdm:hasSubCriterion ex:C2a .
ex:C2a a mcdm:Criterion ; mcdm:hasDirection mcdm:Benefit .
ex:C4  a mcdm:Criterion ; mcdm:hasDirection mcdm:Cost .
ex:WSM a mcdm:ValueFunctionMethod ; mcdm:hasCompensationLevel mcdm:FullCompensation .
ex:TOPSIS a mcdm:DistanceBasedMethod ; mcdm:hasCompensationLevel mcdm:FullCompensation .
ex:PROM a mcdm:OutrankingMethod ; mcdm:hasCompensationLevel mcdm:PartialCompensation .
ex:ELEC a mcdm:OutrankingMethod ; mcdm:hasCompensationLevel mcdm:NonCompensation .
ex:P01 a nrdp:RnDProgram .
ex:G1  a nrdp:PolicyGoal .
ex:GA1 a nrdp:GoalAlignment ; nrdp:ofProgram ex:P01 ; nrdp:toGoal ex:G1 .
ex:PYR1 a nrdp:ProjectYearRecord ; nrdp:ntisProjectId "1711041912" .
ex:FA1 a nrdp:FieldAssignment ; nrdp:assignmentOf ex:PYR1 ; nrdp:assignedField ex:ED0404 ;
       nrdp:assignmentRank 1 .
ex:ED0404 a nrdp:TechnologyField ; skos:inScheme ex:E2018 .
ex:E2018 a kosv:ClassificationEdition . ex:E2023 a kosv:ClassificationEdition . ex:E2099 a kosv:ClassificationEdition .
[] a owl:AllDifferent ; owl:distinctMembers ( ex:E2018 ex:E2023 ex:E2099 ) .
ex:E2023 xkos:supersedes ex:E2018 .
ex:CR1 a xkos:Correspondence ; kosv:sourceEdition ex:E2018 ; kosv:targetEdition ex:E2023 ;
       kosv:correspondenceBasis kosv:OfficialTable ; xkos:madeOf ex:AS1 .
ex:AS1 a xkos:ConceptAssociation ; kosv:changeType kosv:Rename .
ex:H1 a kosv:HarmonizationActivity ; prov:used ex:CR1 .
ex:FA2 a nrdp:FieldAssignment ; prov:wasGeneratedBy ex:H1 ; prov:wasDerivedFrom ex:FA1 ;
       nrdp:assignmentOf ex:PYR1 ; nrdp:assignedField ex:ED0404 ; nrdp:assignmentRank 1 .
"""

CASES = [
    ("기준 방향·상위기준·기법 계열·속성사슬 추론", "", "consistent", [
        ("C2", "mcdm#CompositeCriterion"),
        ("C2a", "mcdm#BenefitCriterion"), ("C2a", "mcdm#LeafCriterion"),
        ("C4", "mcdm#CostCriterion"), ("C4", "mcdm#LeafCriterion"),
        ("WSM", "mcdm#CompensatoryMethod"), ("TOPSIS", "mcdm#CompensatoryMethod"),
        ("PROM", "mcdm#CompensatoryMethod"), ("ELEC", "mcdm#NonCompensatoryMethod"),
        ("PYR1", "ontology#ProjectYearRecord"),
        ("FA2", "ontology#HarmonizedFieldAssignment"),
    ]),
    ("상위기준에 방향 부여 → 비일관 기대", "ex:C2 mcdm:hasDirection mcdm:Benefit .", "inconsistent", []),
    ("리프 기준에 두 방향 → 비일관 기대", "ex:C4 mcdm:hasDirection mcdm:Benefit .", "inconsistent", []),
    ("기법이 두 집계 계열에 동시 소속 → 비일관 기대", "ex:WSM a mcdm:OutrankingMethod .", "inconsistent", []),
    ("자기 자신을 하위기준으로 → 비일관 기대", "ex:C4 mcdm:hasSubCriterion ex:C4 .", "inconsistent", []),
    ("[v0.3.3] 내역사업이 자기 자신의 상위사업 → 비일관 기대",
     "ex:SP1 a nrdp:RnDSubProgram ; nrdp:partOfProgram ex:SP1 .", "inconsistent", []),
    ("[v0.3.3] 내역사업 간 상호 소속(순환) → 비일관 기대",
     "ex:SP1 a nrdp:RnDSubProgram ; nrdp:partOfProgram ex:SP2 . ex:SP2 a nrdp:RnDSubProgram ; nrdp:partOfProgram ex:SP1 .", "inconsistent", []),
    ("분야 배정 순위 4 → 비일관 기대", 'ex:FA1 nrdp:assignmentRank 4 .', "inconsistent", []),
    ("정규화값 -0.05(벡터 정규화) → 일관 기대 (v0.3.2: 범위 검사는 SHACL M6)",
     'ex:NV1 a mcdm:NormalizedValue ; mcdm:hasValue "-0.05"^^xsd:decimal .', "consistent",
     [("NV1", "mcdm#NormalizedValue")]),
    ("가중치 -0.1 → 비일관 기대",
     'ex:W1 a mcdm:Weight ; mcdm:hasWeightValue "-0.1"^^xsd:decimal .', "inconsistent", []),
    ("[판] 연관에 변경 유형 2개 → 비일관 기대", "ex:AS1 kosv:changeType kosv:Merge .", "inconsistent", []),
    ("[판] 개념의 도입 판 2개 → 비일관 기대",
     "ex:NEW1 kosv:introducedIn ex:E2023 , ex:E2099 .", "inconsistent", []),
    ("[판] 판이 자기 자신을 계승 → 비일관 기대", "ex:E2023 xkos:follows ex:E2023 .", "inconsistent", []),
    ("[판] 대응표가 판 3개 비교 → 비일관 기대", "ex:CR1 xkos:compares ex:E2099 .", "inconsistent", []),
    ("[판] 배분 비중 1.2 → 비일관 기대",
     'ex:SH1 a kosv:AllocationShare ; kosv:shareValue "1.2"^^xsd:decimal .', "inconsistent", []),
    ("[판] 대응 근거 2개 → 비일관 기대", "ex:CR1 kosv:correspondenceBasis kosv:ResearcherAuthored .", "inconsistent", []),
    ("반사실적 설명 전용 속성 → 일관 기대",
     'ex:CF1 a mcdm:CounterfactualCondition ; mcdm:concernsCriterion ex:C4 ; '
     'mcdm:requiredNormalizedValue "1.0057"^^xsd:decimal ; mcdm:requiredRawValue "81.0"^^xsd:decimal ; '
     'mcdm:isFeasible false .', "consistent", [("CF1", "mcdm#CounterfactualCondition")]),
    ("반사실적 설명에 contributionOf 재사용(v0.2 방식) → 비일관 기대",
     'ex:CF2 a mcdm:CounterfactualCondition ; mcdm:contributionOf ex:C4 .', "inconsistent", []),
    ("반사실적 설명에 hasRawValue 재사용(v0.2 방식) → 비일관 기대",
     'ex:CF3 a mcdm:CounterfactualCondition ; mcdm:hasRawValue "81.0"^^xsd:decimal .', "inconsistent", []),
    ("[v0.3.4] 다부처 사업의 같은 연도 예산 코드 2개 → 일관 기대",
     'ex:BA1 a nrdp:BudgetAllocation ; nrdp:ofProgram ex:P01 ; '
     'nrdp:budgetCode "075111009009130003031443" , "162111015015511001138306" .', "consistent",
     [("BA1", "ontology#BudgetAllocation")]),
]

def run_case(schema, extra):
    import owlready2
    g = Graph()
    for t in schema:
        g.add(t)
    g.parse(data=PFX + BASE_ABOX + extra, format="turtle")
    tmp = tempfile.NamedTemporaryFile(suffix=".owl", delete=False)
    g.serialize(tmp.name, format="xml")
    world = owlready2.World()
    onto = world.get_ontology("file://" + tmp.name).load()
    try:
        with onto:
            owlready2.sync_reasoner_hermit(world, infer_property_values=True, debug=0)
        return "consistent", world
    except owlready2.OwlReadyInconsistentOntologyError:
        return "inconsistent", world

def main():
    schema = schema_graph()
    ok_all = True
    for name, extra, expect, checks in CASES:
        status, world = run_case(schema, extra)
        ok = status == expect
        detail = []
        if status == "consistent":
            for ind, cls in checks:
                i = world.search_one(iri="https://w3id.org/nrdp/data#" + ind)
                names = {c.iri for c in i.INDIRECT_is_a if hasattr(c, "iri")}
                hit = any(n.endswith(cls) for n in names)
                detail.append(f"{ind}⊑{cls.split('#')[1]}:{'✓' if hit else '✗'}")
                ok = ok and hit
            if name.startswith("기준 방향"):
                p = world.search_one(iri="https://w3id.org/nrdp/data#P01")
                ct = [x.name for x in getattr(p, "contributesTo", [])]
                detail.append(f"P01 contributesTo→{ct}:{'✓' if 'G1' in ct else '✗'}")
                ok = ok and 'G1' in ct
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} — {status} {' '.join(detail)}")
    print("ALL PASS" if ok_all else "SOME FAILED")
    sys.exit(0 if ok_all else 1)

if __name__ == "__main__":
    main()
