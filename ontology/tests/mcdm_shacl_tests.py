"""MCDM 표현 계층 SHACL 검사 테스트 (pyshacl). 실행: python3 mcdm_shacl_tests.py <ontology_dir>
mcdm-shapes.ttl 의 M1~M7 을 최소 데이터에 대한 정상·변형 사례로 확인한다."""
import sys, os
from rdflib import Graph
from rdflib.namespace import SH
from pyshacl import validate

ONT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PFX = """
@prefix mcdm: <https://w3id.org/nrdp/mcdm#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix ex:   <https://w3id.org/nrdp/data#> .
"""
BASE = """
ex:DP a mcdm:DecisionProblem ; mcdm:hasAlternative ex:A1 , ex:A2 ; mcdm:hasCriterion ex:C1 , ex:C2 .
ex:A1 a mcdm:Alternative ; mcdm:inProblem ex:DP .
ex:A2 a mcdm:Alternative ; mcdm:inProblem ex:DP .
ex:C1 a mcdm:Criterion . ex:C2 a mcdm:Criterion .
ex:S a mcdm:DecisionScenario ; mcdm:hasWeight ex:W1 , ex:W2 .
ex:W1 a mcdm:Weight ; mcdm:assignedToCriterion ex:C1 ; mcdm:hasWeightValue "0.6"^^xsd:decimal .
ex:W2 a mcdm:Weight ; mcdm:assignedToCriterion ex:C2 ; mcdm:hasWeightValue "0.4"^^xsd:decimal .
ex:WSM a mcdm:ValueFunctionMethod ; mcdm:supportsAdditiveDecomposition true .
ex:TOP a mcdm:DistanceBasedMethod ; mcdm:supportsAdditiveDecomposition false .
ex:MM a mcdm:NormalizationMethod ; mcdm:normalizedLowerBound "0"^^xsd:decimal ; mcdm:normalizedUpperBound "1"^^xsd:decimal .
ex:VEC a mcdm:NormalizationMethod .
ex:CV11 a mcdm:CriterionValue ; mcdm:ofAlternative ex:A1 ; mcdm:onCriterion ex:C1 .
ex:CV12 a mcdm:CriterionValue ; mcdm:ofAlternative ex:A1 ; mcdm:onCriterion ex:C2 .
ex:CV21 a mcdm:CriterionValue ; mcdm:ofAlternative ex:A2 ; mcdm:onCriterion ex:C1 .
ex:CV22 a mcdm:CriterionValue ; mcdm:ofAlternative ex:A2 ; mcdm:onCriterion ex:C2 .
ex:NV11 a mcdm:NormalizedValue ; mcdm:ofCriterionValue ex:CV11 ; mcdm:normalizedBy ex:MM ; mcdm:hasValue "0.5"^^xsd:decimal .
ex:R1 a mcdm:DecisionResult ; mcdm:forProblem ex:DP ; mcdm:forScenario ex:S ; mcdm:byMethod ex:WSM ; mcdm:forAlternative ex:A1 ; mcdm:hasRank 1 .
ex:R2 a mcdm:DecisionResult ; mcdm:forProblem ex:DP ; mcdm:forScenario ex:S ; mcdm:byMethod ex:WSM ; mcdm:forAlternative ex:A2 ; mcdm:hasRank 2 .
ex:T1 a mcdm:DecisionResult ; mcdm:forProblem ex:DP ; mcdm:forScenario ex:S ; mcdm:byMethod ex:TOP ; mcdm:forAlternative ex:A1 ; mcdm:hasRank 1 .
ex:K1 a mcdm:CriterionContribution ; mcdm:explains ex:R1 ; mcdm:contributionOf ex:C1 .
"""
# (이름, 치환 전, 치환 후, 추가 문장, 기대 적합 여부, 기대 위반 shape, 기대 경고 수)
CASES = [
    ("W1 정상", None, None, "", True, set(), 0),
    ("W2 가중치 합 0.9 → M1", '"0.4"^^xsd:decimal', '"0.3"^^xsd:decimal', "", False, {"M1"}, 0),
    ("W3 한 기준에 가중치 2개 → M1", "ex:W1 , ex:W2 .", "ex:W1 , ex:W2 , ex:W3 .",
     'ex:W3 a mcdm:Weight ; mcdm:assignedToCriterion ex:C1 ; mcdm:hasWeightValue "0.0"^^xsd:decimal .', False, {"M1"}, 0),
    ("W4 순위 중복 → M2", "ex:A2 ; mcdm:hasRank 2", "ex:A2 ; mcdm:hasRank 1", "", False, {"M2"}, 0),
    ("W5 순위가 결과 수 초과 → M2", "ex:A2 ; mcdm:hasRank 2", "ex:A2 ; mcdm:hasRank 3", "", False, {"M2"}, 0),
    ("W6 TOPSIS 결과에 기여 분해 → M3", None, None,
     "ex:K2 a mcdm:CriterionContribution ; mcdm:explains ex:T1 ; mcdm:contributionOf ex:C1 .", False, {"M3"}, 0),
    ("W7 같은 (평가값, 정규화방법)에 정규화값 2개 → M4", None, None,
     "ex:NV11b a mcdm:NormalizedValue ; mcdm:ofCriterionValue ex:CV11 ; mcdm:normalizedBy ex:MM .", False, {"M4"}, 0),
    ("W8 평가값 결측 → M5 경고만(적합)", "ex:CV22 a mcdm:CriterionValue ; mcdm:ofAlternative ex:A2 ; mcdm:onCriterion ex:C2 .", "", "", True, set(), 1),
    ("W9 min-max 정규화값 1.5 → M6", '"0.5"^^xsd:decimal .', '"1.5"^^xsd:decimal .', "", False, {"M6"}, 0),
    ("W10 경계 없는 벡터 정규화값 -0.05 → 적합", None, None,
     'ex:NV12 a mcdm:NormalizedValue ; mcdm:ofCriterionValue ex:CV12 ; mcdm:normalizedBy ex:VEC ; mcdm:hasValue "-0.05"^^xsd:decimal .', True, set(), 0),
    ("W11 기여값 합 = 점수(음의 순흐름 포함) → 적합 (v0.3.4)", None, None,
     'ex:R1 mcdm:hasScore "-0.2"^^xsd:decimal . ex:K1 mcdm:hasContributionValue "0.1"^^xsd:decimal . '
     'ex:K3 a mcdm:CriterionContribution ; mcdm:explains ex:R1 ; mcdm:contributionOf ex:C2 ; mcdm:hasContributionValue "-0.3"^^xsd:decimal .',
     True, set(), 0),
    ("W12 기여값 합 ≠ 점수 → M7 (v0.3.4)", None, None,
     'ex:R1 mcdm:hasScore "-0.2"^^xsd:decimal . ex:K1 mcdm:hasContributionValue "0.1"^^xsd:decimal . '
     'ex:K3 a mcdm:CriterionContribution ; mcdm:explains ex:R1 ; mcdm:contributionOf ex:C2 ; mcdm:hasContributionValue "-0.2"^^xsd:decimal .',
     False, {"M7"}, 0),
]

def main():
    shapes = Graph().parse(os.path.join(ONT, "mcdm-shapes.ttl"))
    ok_all = True
    for name, old, new, extra, exp_conf, exp_shapes, exp_warn in CASES:
        data = BASE if old is None else BASE.replace(old, new)
        assert old is None or old in BASE, name
        g = Graph().parse(data=PFX + data + extra, format="turtle")
        conf, rg, _ = validate(g, shacl_graph=shapes, advanced=True, inference="none", allow_warnings=True)
        viol, warn = set(), 0
        for r in rg.subjects(SH.resultSeverity, None):
            sev = rg.value(r, SH.resultSeverity)
            if sev == SH.Warning: warn += 1
            else: viol.add(str(rg.value(r, SH.resultMessage))[:2])
        ok = (conf == exp_conf and viol == exp_shapes and warn == exp_warn)
        ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}  conforms={conf} violations={sorted(viol)} warnings={warn}")
    print("ALL PASS" if ok_all else "SOME FAILED")
    return 0 if ok_all else 1

if __name__ == "__main__":
    sys.exit(main())
