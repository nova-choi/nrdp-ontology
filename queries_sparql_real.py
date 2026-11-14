#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""역량질문(CQ) SPARQL — 온톨로지 v0.3 + NTIS 실데이터(data/rdf/*.ttl).

queries_sparql.py(v0.2 샘플)의 CQ1~CQ25 를 v0.3 어휘와 실데이터 IRI 로 옮기고,
실데이터에서만 검증할 수 있는 CQ26~CQ30(부처 개편·분야 배정 판·연속과제·성과 귀속·별칭 병합)을 추가했다.
실행: python queries_sparql_real.py  → data/rdf/sparql-results-real.txt
      (rdflib, 트리플 약 107만 건 — 적재 30초 내외, 전체 질의 수 분)
"""
import os, sys, time, hashlib, re

ROOT = os.path.dirname(os.path.abspath(__file__))
RDFD = os.path.join(ROOT, "data", "rdf")

def h8(s): return hashlib.sha1(re.sub(r"\s", "", s).encode("utf-8")).hexdigest()[:8]
# 질의에 쓰는 고정 개체 (실데이터 IRI 규칙: ntis_to_rdf.py)
P_BIO = "PRG_" + h8("바이오의료기술개발")                       # 첨단바이오, 장기 존속 사업 (S1/WSM 1위)
P_SEMI = "PRG_" + h8("차세대지능형반도체기술개발(소자)")         # 반도체, 별칭 병합 사업
P_AI = "PRG_" + h8("인공지능중심산업융합집적단지조성(R&D)")      # S1/WSM 4위 — 반사실 대상
MIN_MSIT = "ORG_MIN_" + h8("과학기술정보통신부")
MIN_MSIP = "ORG_MIN_" + h8("미래창조과학부")

PREFIX = """
PREFIX nrdp: <https://w3id.org/nrdp/ontology#>
PREFIX mcdm: <https://w3id.org/nrdp/mcdm#>
PREFIX kosv: <https://w3id.org/nrdp/kosv#>
PREFIX ex:   <https://w3id.org/nrdp/data#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX org:  <http://www.w3.org/ns/org#>
"""

CQ = {}

# ══════════════════ A. 도메인 조회 (CQ1–CQ7) ══════════════════

CQ[1] = ("2023년 기준 과학기술정보통신부가 소관하는 사업의 목록과 각 예산액(과제 협약 정부연구비 합산)은?", f"""
SELECT ?사업명 ?예산액_백만원 ?예산코드 WHERE {{
  ?prog a nrdp:RnDProgram ; rdfs:label ?사업명 ; nrdp:fundedBy ex:{MIN_MSIT} .
  ?ba nrdp:ofProgram ?prog ; nrdp:inFiscalYear ex:FY2023 ; nrdp:hasAmount ?예산액_백만원 .
  OPTIONAL {{ ?ba nrdp:budgetCode ?예산코드 }}
}} ORDER BY DESC(?예산액_백만원) ?사업명
""")

CQ[2] = ("첨단바이오 분야 사업에 배정된 총 정부연구비의 연도별 추이는?", """
SELECT ?연도 (SUM(?amt) AS ?총예산_백만원) (COUNT(DISTINCT ?prog) AS ?사업수) WHERE {
  ?prog a nrdp:RnDProgram ; nrdp:strategicTechnology ex:NST_050000 .
  ?ba nrdp:ofProgram ?prog ; nrdp:inFiscalYear ?fy ; nrdp:hasAmount ?amt .
  ?fy nrdp:yearValue ?연도 .
} GROUP BY ?연도 ORDER BY ?연도
""")

CQ[3] = ("두 개 이상의 부처가 동일 국가전략기술 분야에 투자하고 있는 사례는?", """
SELECT ?분야 (COUNT(DISTINCT ?min) AS ?부처수)
       (GROUP_CONCAT(DISTINCT ?부처명; SEPARATOR=" / ") AS ?부처목록) WHERE {
  { SELECT ?nst ?분야 ?min ?부처명 WHERE {
      ?prog a nrdp:RnDProgram ; nrdp:strategicTechnology ?nst ; nrdp:fundedBy ?min .
      ?nst rdfs:label ?분야 . ?min rdfs:label ?부처명 .
    } ORDER BY ?부처명 }
} GROUP BY ?nst ?분야
  HAVING (COUNT(DISTINCT ?min) >= 2)
  ORDER BY DESC(?부처수) ?분야
""")

CQ[4] = ("특정 사업이 선정된 국가전략기술 분야와 사업 수준 기술분야(집계 파생), 그 판정 활동은?", f"""
SELECT ?사업명 ?국가전략기술 ?표준분류_대분류 ?판 ?판정활동 WHERE {{
  ex:{P_SEMI} rdfs:label ?사업명 ; nrdp:strategicTechnology ?nst ; nrdp:belongsToField ?tf ;
              prov:wasGeneratedBy ?act .
  ?nst rdfs:label ?국가전략기술 . ?tf rdfs:label ?표준분류_대분류 ; skos:inScheme ?ed . ?ed rdfs:label ?판 .
  ?act rdfs:label ?판정활동 .
}}
""")

CQ[5] = ("어떤 정책목표에도 연결되지 않은 사업이 존재하는가? (GoalAlignment 부재 탐지)", """
SELECT (COUNT(DISTINCT ?prog) AS ?미연결_사업수) (COUNT(DISTINCT ?all) AS ?전체_사업수) WHERE {
  ?all a nrdp:RnDProgram .
  OPTIONAL { ?prog a nrdp:RnDProgram .
             FILTER NOT EXISTS { ?ga a nrdp:GoalAlignment ; nrdp:ofProgram ?prog } }
}
""")

CQ[6] = ("특정 사업의 과제연도기록 수·과제 수·주관기관 수는? (partOfProgram 추이적 관계, 내역사업 경유)", f"""
SELECT ?사업명 (COUNT(DISTINCT ?pyr) AS ?과제연도기록수) (COUNT(DISTINCT ?proj) AS ?과제수)
       (COUNT(DISTINCT ?org) AS ?주관기관수) (COUNT(DISTINCT ?sp) AS ?내역사업수) WHERE {{
  ex:{P_BIO} rdfs:label ?사업명 .
  ?pyr nrdp:partOfProgram+ ex:{P_BIO} . ?pyr nrdp:ofProject ?proj ; nrdp:leadPerformer ?org .
  OPTIONAL {{ ?pyr nrdp:partOfProgram ?sp . ?sp a nrdp:RnDSubProgram }}
}} GROUP BY ?사업명
""")

CQ[7] = ("연구비는 증가했으나 SCI 논문 수는 감소한 사업이 있는가? (2022→2023)", """
SELECT ?사업명 ?연구비_2022 ?연구비_2023 ?SCI_2022 ?SCI_2023 WHERE {
  ?ob22 nrdp:forIndicator ex:IND_SCI ; nrdp:inFiscalYear ex:FY2022 ; nrdp:ofProgram ?prog ; nrdp:hasObservedValue ?SCI_2022 .
  ?ob23 nrdp:forIndicator ex:IND_SCI ; nrdp:inFiscalYear ex:FY2023 ; nrdp:ofProgram ?prog ; nrdp:hasObservedValue ?SCI_2023 .
  ?ba22 a nrdp:BudgetAllocation ; nrdp:ofProgram ?prog ; nrdp:inFiscalYear ex:FY2022 ; nrdp:hasAmount ?연구비_2022 .
  ?ba23 a nrdp:BudgetAllocation ; nrdp:ofProgram ?prog ; nrdp:inFiscalYear ex:FY2023 ; nrdp:hasAmount ?연구비_2023 .
  ?prog rdfs:label ?사업명 .
  FILTER (?연구비_2023 > ?연구비_2022 && ?SCI_2023 < ?SCI_2022)
} ORDER BY ?사업명
""")

# ══════════════════ B. MCDM 구조 (CQ8–CQ15) ══════════════════

CQ[8] = ("의사결정 문제에 포함된 대안의 수와 기준의 수는?", """
SELECT ?문제명 ?대안수 ?기준수 ?리프기준수 WHERE {
  ex:DP_MAIN rdfs:label ?문제명 .
  { SELECT (COUNT(DISTINCT ?a) AS ?대안수) WHERE { ex:DP_MAIN mcdm:hasAlternative ?a } }
  { SELECT (COUNT(DISTINCT ?c) AS ?기준수) WHERE { ex:DP_MAIN mcdm:hasCriterion ?c } }
  { SELECT (COUNT(DISTINCT ?c2) AS ?리프기준수) WHERE { ex:DP_MAIN mcdm:hasCriterion ?c2 . ?c2 a mcdm:LeafCriterion } }
}
""")

CQ[9] = ("어떤 기준이 하위기준을 가지며, 그 깊이는 얼마인가?", """
SELECT ?상위기준 ?하위기준 ?깊이 WHERE {
  ?parent mcdm:hasSubCriterion ?child ; rdfs:label ?상위기준 .
  ?child rdfs:label ?하위기준 .
  { SELECT ?child (COUNT(?mid) AS ?깊이) WHERE { ?mid mcdm:hasSubCriterion+ ?child . } GROUP BY ?child }
} ORDER BY ?상위기준 ?하위기준
""")

CQ[10] = ("비용형(cost) 기준으로 분류된 기준의 목록은?", """
SELECT ?기준 ?척도 WHERE {
  ?c a mcdm:CostCriterion ; rdfs:label ?기준 ; mcdm:hasScale ?sc . ?sc rdfs:label ?척도 .
} ORDER BY ?기준
""")

CQ[11] = ("각 기준이 측정되는 성과지표는 무엇이며 단위는?", """
SELECT ?기준 ?성과지표 ?단위 WHERE {
  ?c a mcdm:LeafCriterion ; rdfs:label ?기준 ; mcdm:measuredBy ?ind .
  ?ind rdfs:label ?성과지표 ; nrdp:indicatorUnit ?단위 .
} ORDER BY ?기준
""")

CQ[12] = ("원시값은 있으나 정규화값이 없는 평가값이 존재하는가? (불완전 평가 대안 탐지)", """
SELECT ?대안명 (COUNT(?cv) AS ?정규화없는_평가값수) WHERE {
  ?cv a mcdm:CriterionValue ; mcdm:ofAlternative ?alt ; mcdm:hasRawValue ?v .
  ?alt rdfs:label ?대안명 .
  FILTER NOT EXISTS { ?cv mcdm:hasNormalization ?nv }
} GROUP BY ?alt ?대안명 ORDER BY ?대안명
""")

CQ["12b"] = ("[보조] 동일 평가값이 정규화방법별로 다른 값을 갖는가?", f"""
SELECT ?대안명 ?기준 ?정규화방법 ?정규화값 WHERE {{
  ex:CV_{P_BIO}_C_FUND mcdm:ofAlternative ?alt ; mcdm:onCriterion ?c ; mcdm:hasNormalization ?nv .
  ?nv mcdm:normalizedBy ?nm ; mcdm:hasValue ?정규화값 .
  ?alt rdfs:label ?대안명 . ?c rdfs:label ?기준 . ?nm rdfs:label ?정규화방법 .
}} ORDER BY ?정규화방법
""")

CQ[13] = ("어떤 대안이 특정 기준에서 평가값을 결여하고 있는가? (결측 탐지)", """
SELECT ?대안명 ?결측기준 WHERE {
  ex:DP_MAIN mcdm:hasAlternative ?alt ; mcdm:hasCriterion ?c .
  ?c a mcdm:LeafCriterion ; rdfs:label ?결측기준 . ?alt rdfs:label ?대안명 .
  FILTER NOT EXISTS { ?cv a mcdm:CriterionValue ; mcdm:ofAlternative ?alt ; mcdm:onCriterion ?c . }
} ORDER BY ?대안명 ?결측기준
""")

CQ[14] = ("각 집계기법이 요구하는 파라미터의 인스턴스화 상태는?", """
SELECT ?기법 ?집계논리 ?보상수준 ?정규화필요 ?가법분해 ?정규화방법 ?선호함수 WHERE {
  ?m a ?cls ; rdfs:label ?기법 ; mcdm:hasCompensationLevel ?cl ;
     mcdm:requiresNormalization ?정규화필요 ; mcdm:supportsAdditiveDecomposition ?가법분해 .
  ?cls rdfs:subClassOf mcdm:AggregationMethod ; rdfs:label ?집계논리 . FILTER(lang(?집계논리) = "ko")
  ?cl rdfs:label ?보상수준 .
  OPTIONAL { ?m mcdm:usesNormalization ?nm . ?nm rdfs:label ?정규화방법 }
  OPTIONAL { ?m mcdm:usesPreferenceFunction ?pf . ?pf rdfs:label ?선호함수 }
} ORDER BY ?기법
""")

CQ[15] = ("열위관계형(outranking) 집계기법의 목록과 각 선호함수·임계값은?", """
SELECT ?기법 ?선호함수 ?임계값q ?임계값p WHERE {
  ?m a mcdm:OutrankingMethod ; rdfs:label ?기법 ; mcdm:usesPreferenceFunction ?pf .
  ?pf rdfs:label ?선호함수 ; mcdm:preferenceThresholdQ ?임계값q ; mcdm:preferenceThresholdP ?임계값p .
}
""")

# ══════════════════ C. 시나리오 비교 (CQ16–CQ21) ══════════════════

CQ[16] = ("정의된 정책 시나리오의 목록과 각 시나리오의 가중치 분포는?", """
SELECT ?시나리오 ?설명 ?기준 ?가중치 WHERE {
  ?s a mcdm:DecisionScenario ; rdfs:label ?시나리오 ; mcdm:scenarioLabel ?설명 ; mcdm:hasWeight ?w .
  ?w mcdm:assignedToCriterion ?c ; mcdm:hasWeightValue ?가중치 . ?c rdfs:label ?기준 .
} ORDER BY ?시나리오 DESC(?가중치) ?기준
""")

CQ[17] = ("시나리오 S2(효율중심)와 S3(성과규모중심) 사이에서 가중치 차이가 가장 큰 기준은?", """
SELECT ?기준 ?효율중심 ?성과규모중심 ?차이 WHERE {
  ex:S2 mcdm:hasWeight ?w2 . ?w2 mcdm:assignedToCriterion ?c ; mcdm:hasWeightValue ?효율중심 .
  ex:S3 mcdm:hasWeight ?w3 . ?w3 mcdm:assignedToCriterion ?c ; mcdm:hasWeightValue ?성과규모중심 .
  ?c rdfs:label ?기준 .
  BIND(ABS(?성과규모중심 - ?효율중심) AS ?차이)
} ORDER BY DESC(?차이) ?기준
""")

CQ[18] = ("동일 대안이 시나리오 S2와 S3에서 각각 몇 위인가? (WSM 기준)", """
SELECT ?대안명 ?순위_효율중심 ?순위_성과규모중심 ?순위변동 WHERE {
  ?dr2 mcdm:forScenario ex:S2 ; mcdm:byMethod ex:M_WSM ; mcdm:forAlternative ?alt ; mcdm:hasRank ?순위_효율중심 .
  ?dr3 mcdm:forScenario ex:S3 ; mcdm:byMethod ex:M_WSM ; mcdm:forAlternative ?alt ; mcdm:hasRank ?순위_성과규모중심 .
  ?alt rdfs:label ?대안명 .
  BIND(?순위_효율중심 - ?순위_성과규모중심 AS ?순위변동)
} ORDER BY ?순위_효율중심
""")

CQ[19] = ("모든 시나리오에서 상위 5위 내를 유지하는 대안은? (강건 대안, WSM)", """
SELECT ?대안명 (COUNT(DISTINCT ?s) AS ?상위5위_시나리오수) (MAX(?r) AS ?최악순위) WHERE {
  ?dr mcdm:forScenario ?s ; mcdm:byMethod ex:M_WSM ; mcdm:forAlternative ?alt ; mcdm:hasRank ?r .
  ?alt rdfs:label ?대안명 .
  FILTER (?r <= 5)
} GROUP BY ?alt ?대안명
  HAVING (COUNT(DISTINCT ?s) = 3)
  ORDER BY ?최악순위 ?대안명
""")

CQ[20] = ("시나리오 변경에 순위가 가장 민감하게 반응하는 대안은? (WSM, 상위 10)", """
SELECT ?대안명 (MIN(?r) AS ?최고순위) (MAX(?r) AS ?최저순위) ((MAX(?r) - MIN(?r)) AS ?순위폭) WHERE {
  ?dr mcdm:forScenario ?s ; mcdm:byMethod ex:M_WSM ; mcdm:forAlternative ?alt ; mcdm:hasRank ?r .
  ?alt rdfs:label ?대안명 .
} GROUP BY ?alt ?대안명
  ORDER BY DESC(?순위폭) ?대안명 LIMIT 10
""")

CQ[21] = ("동일 시나리오(S3)·동일 데이터에서 TOPSIS와 PROMETHEE II의 순위는 일치하는가? (불일치 상위 10)", """
SELECT ?대안명 ?TOPSIS순위 ?PROMETHEE순위 ?불일치 WHERE {
  ?dt mcdm:forScenario ex:S3 ; mcdm:byMethod ex:M_TOPSIS ; mcdm:forAlternative ?alt ; mcdm:hasRank ?TOPSIS순위 .
  ?dp mcdm:forScenario ex:S3 ; mcdm:byMethod ex:M_PRO2 ; mcdm:forAlternative ?alt ; mcdm:hasRank ?PROMETHEE순위 .
  ?alt rdfs:label ?대안명 .
  BIND(ABS(?TOPSIS순위 - ?PROMETHEE순위) AS ?불일치)
} ORDER BY DESC(?불일치) ?대안명 LIMIT 10
""")

# ══════════════════ D. 설명 (CQ22–CQ25) ══════════════════

CQ[22] = ("특정 대안(S1/WSM 1위)의 종합점수에 각 기준이 기여한 비율은?", f"""
SELECT ?대안명 ?기준 ?기여비율 WHERE {{
  ?cc a mcdm:CriterionContribution ; mcdm:explains ?dr ; mcdm:contributionOf ?c ; mcdm:hasContributionRatio ?기여비율 .
  ?dr mcdm:forAlternative ex:ALT_{P_BIO} ; mcdm:forScenario ex:S1 ; mcdm:byMethod ex:M_WSM .
  ex:ALT_{P_BIO} rdfs:label ?대안명 . ?c rdfs:label ?기준 .
}} ORDER BY DESC(?기여비율)
""")

CQ[23] = ("특정 대안의 특정 기준 평가값은 어떤 원천 데이터에서 유래하는가? (평가값→관측치→집계활동→과제연도기록→스냅샷)", f"""
SELECT ?평가값 ?관측연도 ?관측값 ?집계활동 (COUNT(DISTINCT ?pyr) AS ?원천_과제연도기록수) ?스냅샷 WHERE {{
  ex:CV_{P_SEMI}_C_SCI mcdm:hasRawValue ?평가값 ; prov:wasDerivedFrom ?ob .
  ?ob nrdp:inFiscalYear ?fy ; nrdp:hasObservedValue ?관측값 ; nrdp:ofProgram ?prog ; prov:wasGeneratedBy ?act .
  ?fy nrdp:yearValue ?관측연도 . ?act rdfs:label ?집계활동 .
  ?pyr nrdp:partOfProgram+ ?prog . ?pyr nrdp:inFiscalYear ?fy ; prov:hadPrimarySource ?snap .
  ?snap rdfs:label ?스냅샷 .
}} GROUP BY ?평가값 ?관측연도 ?관측값 ?집계활동 ?스냅샷 ORDER BY ?관측연도
""")

CQ[24] = ("대안 X가 상위 3위에 진입하려면 어떤 기준이 얼마나 개선되어야 하는가? (반사실)", """
SELECT ?대안명 ?기준 ?필요_정규화값 ?필요_원시값 ?실현가능 WHERE {
  ?cf a mcdm:CounterfactualCondition ; mcdm:explains ?dr ; mcdm:concernsCriterion ?c ;
      mcdm:requiredNormalizedValue ?필요_정규화값 ; mcdm:requiredRawValue ?필요_원시값 ; mcdm:isFeasible ?실현가능 .
  ?dr mcdm:forAlternative ?alt . ?alt rdfs:label ?대안명 . ?c rdfs:label ?기준 .
} ORDER BY DESC(?실현가능) ?필요_정규화값
""")

CQ["24b"] = ("[보조] 사전계산 없이 3위 점수와의 격차를 질의로 산출 (WSM 한정, 상위 5)", """
SELECT ?대안명 ?현재점수 ?현재순위 ?목표점수 ?필요증분 WHERE {
  ?dr mcdm:forScenario ex:S1 ; mcdm:byMethod ex:M_WSM ; mcdm:forAlternative ?alt ; mcdm:hasScore ?현재점수 ; mcdm:hasRank ?현재순위 .
  ?alt rdfs:label ?대안명 .
  { SELECT (?sc AS ?목표점수) WHERE { ?d3 mcdm:forScenario ex:S1 ; mcdm:byMethod ex:M_WSM ; mcdm:hasRank 3 ; mcdm:hasScore ?sc . } }
  FILTER (?현재순위 > 3)
  BIND(?목표점수 - ?현재점수 AS ?필요증분)
} ORDER BY ?필요증분 LIMIT 5
""")

CQ[25] = ("두 대안(S1/WSM 1·2위)의 순위 역전을 유발하는 최소 가중치 변화량은? (v0.3.4: 절차적 계산 후 재적재한 결과를 조회)", """
SELECT ?기준 ?현재_가중치 ?필요_가중치 ?변화량 ?실현가능 WHERE {
  ?cf a mcdm:CounterfactualCondition ; mcdm:concernsCriterion ?c ; mcdm:requiredWeightValue ?필요_가중치 ; mcdm:isFeasible ?실현가능 .
  ?c rdfs:label ?기준 .
  ex:S1 mcdm:hasWeight ?w . ?w mcdm:assignedToCriterion ?c ; mcdm:hasWeightValue ?현재_가중치 .
  BIND(?필요_가중치 - ?현재_가중치 AS ?변화량)
  BIND(IF(?변화량 < 0, -?변화량, ?변화량) AS ?크기)
} ORDER BY DESC(?실현가능) ?크기
""")

# ══════════════════ E. v0.3 실데이터 전용 (CQ26–CQ30) ══════════════════

CQ[26] = ("부처 개편(미래창조과학부→과학기술정보통신부)을 고려하면 같은 소관 계보의 연도별 과제연도기록 수는?", f"""
SELECT ?연도 (COUNT(DISTINCT ?pyr) AS ?과제연도기록수) (GROUP_CONCAT(DISTINCT ?부처명; SEPARATOR=" / ") AS ?기재된_부처명) WHERE {{
  {{ SELECT ?연도 ?pyr ?부처명 WHERE {{
      {{ ?reorg a nrdp:MinistryReorganization ; org:resultingOrganization ex:{MIN_MSIT} ; org:originalOrganization ?min }}
      UNION {{ VALUES ?min {{ ex:{MIN_MSIT} }} }}
      ?pyr a nrdp:ProjectYearRecord ; nrdp:fundedBy ?min ; nrdp:inFiscalYear ?fy .
      ?fy nrdp:yearValue ?연도 . ?min rdfs:label ?부처명 .
      FILTER(?연도 >= 2015 && ?연도 <= 2024)
    }} ORDER BY ?부처명 }}
}} GROUP BY ?연도 ORDER BY ?연도
""")

CQ[27] = ("특정 사업의 과제들이 1순위로 배정된 표준분류 중분류 분포와 그 분류의 판(edition)은? (상위 8)", f"""
SELECT ?중분류 ?판 (COUNT(DISTINCT ?pyr) AS ?과제연도기록수) WHERE {{
  ?pyr nrdp:partOfProgram+ ex:{P_BIO} .
  ?fa nrdp:assignmentOf ?pyr ; nrdp:assignmentRank ?rk ; nrdp:assignedField ?s .
  FILTER(?rk = 1)
  ?s skos:broader ?m . ?m rdfs:label ?중분류 .
  ?s skos:inScheme ?ed . ?ed rdfs:label ?판 .
}} GROUP BY ?중분류 ?판 ORDER BY DESC(?과제연도기록수) LIMIT 8
""")

CQ[28] = ("연속과제 연결(precededBy)로 가장 길게 이어지는 과제 사슬은? (상위 5)", """
SELECT ?과제명 ?마지막_과제고유번호 ?마지막연도 (COUNT(DISTINCT ?prev) AS ?사슬길이) WHERE {
  ?last nrdp:precededBy+ ?prev .
  ?last nrdp:ntisProjectId ?마지막_과제고유번호 ; nrdp:inFiscalYear ?fy ; rdfs:label ?과제명 .
  ?fy nrdp:yearValue ?마지막연도 .
  FILTER NOT EXISTS { ?next nrdp:precededBy ?last }
  FILTER(lang(?과제명) = "ko")
} GROUP BY ?과제명 ?마지막_과제고유번호 ?마지막연도 ORDER BY DESC(?사슬길이) ?마지막_과제고유번호 LIMIT 5
""")

CQ[29] = ("한 성과물이 복수의 과제연도기록에 귀속된 사례가 있는가? (사업 집계 시 중복 제거 근거)", """
SELECT ?복수귀속_성과물수 ?전체_성과물수 WHERE {
  { SELECT (COUNT(?out) AS ?복수귀속_성과물수) WHERE {
      { SELECT ?out (COUNT(?att) AS ?n) WHERE { ?att nrdp:attributedOutput ?out } GROUP BY ?out HAVING (COUNT(?att) >= 2) }
    } }
  { SELECT (COUNT(?o) AS ?전체_성과물수) WHERE { ?o a nrdp:ResearchOutput } }
}
""")

CQ[30] = ("별칭 병합으로 하나의 사업에 묶인 원천 사업명 표기는 몇 가지이며, 표기별 과제연도기록 수는?", f"""
SELECT ?사업명 ?원천표기 (COUNT(DISTINCT ?pyr) AS ?과제연도기록수) (MIN(?y) AS ?첫연도) (MAX(?y) AS ?끝연도) WHERE {{
  ex:{P_SEMI} rdfs:label ?사업명 .
  ?pyr nrdp:partOfProgram+ ex:{P_SEMI} . ?pyr nrdp:recordedProgramName ?원천표기 ; nrdp:inFiscalYear ?fy .
  ?fy nrdp:yearValue ?y .
}} GROUP BY ?사업명 ?원천표기 ORDER BY ?첫연도
""")

# ══════════════════ 실행 ══════════════════
if __name__ == "__main__":
    from rdflib import Graph
    from cq_format import table

    g = Graph()
    t0 = time.time()
    for f in ("ontology/mcdm-core.ttl", "ontology/kos-versioning.ttl", "ontology/nrdp-ontology.ttl",
              "data/rdf/nrdp-schemes.ttl", "data/rdf/nrdp-domain.ttl", "data/rdf/nrdp-mcdm.ttl"):
        g.parse(os.path.join(ROOT, f), format="turtle")
    print(f"적재 {len(g):,} 트리플 ({time.time()-t0:.0f}s)", flush=True)

    outpath = os.path.join(RDFD, "sparql-results-real.txt")
    only = []
    for a in sys.argv[1:]:
        if a.startswith("--out="): outpath = a[6:]
        else: only.append(a)
    ok = fail = skipped = 0
    out = []
    for key in list(CQ.keys()):
        if only and str(key) not in only:
            continue
        desc, q = CQ[key]
        head = f"CQ{key}. {desc}"
        out.append("=" * 78); out.append(head)
        if q is None:
            out.append("  [△ 질의 단독 수행 불가 — 절차적 계산 필요]"); skipped += 1; continue
        t1 = time.time()
        try:
            qr = g.query(PREFIX + q)
            res = list(qr)
            cols = [str(v) for v in qr.vars]
            out.append(table(cols, [tuple(row) for row in res]))
            out.append(f" ↳ {len(res)}행, {time.time()-t1:.1f}s")
            if not res: fail += 1
            else: ok += 1
        except Exception as e:
            out.append(f"  [오류] {type(e).__name__}: {e}"); fail += 1
        print(f"{head[:60]:60s} {time.time()-t1:6.1f}s", flush=True)
        open(outpath, "w", encoding="utf-8").write("\n".join(out) + "\n")   # 중간 저장

    if not only:
        out.append("=" * 78)
        out.append(f"실행 성공(비어있지 않음): {ok} / 실패·빈결과: {fail} / 질의불가: {skipped}")
    text = "\n".join(out)
    open(outpath, "w", encoding="utf-8").write(text + "\n")
    print(text[-400:])
