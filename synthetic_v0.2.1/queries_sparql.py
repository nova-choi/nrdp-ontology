#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""역량질문(CQ) 25개의 SPARQL 질의 및 실행 검증."""

PREFIX = """
PREFIX nrdp: <https://w3id.org/nrdp/ontology#>
PREFIX mcdm: <https://w3id.org/nrdp/mcdm#>
PREFIX ex:   <https://w3id.org/nrdp/data#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX prov: <http://www.w3.org/ns/prov#>
"""

CQ = {}

# ══════════════════ A. 도메인 조회 (CQ1–CQ7) ══════════════════

CQ[1] = ("2023년 기준 특정 부처가 소관하는 사업의 목록과 각 예산액은?", """
SELECT ?사업명 ?예산액_백만원 WHERE {
  ?prog a nrdp:RnDProgram ;
        rdfs:label ?사업명 ;
        nrdp:fundedBy ex:MIN_MSIT ;
        nrdp:hasAllocation ?ba .
  ?ba nrdp:inFiscalYear ex:FY2023 ;
      nrdp:hasAmount ?예산액_백만원 .
} ORDER BY DESC(?예산액_백만원)
""")

CQ[2] = ("특정 기술분야에 배정된 총 R&D 예산의 연도별 추이는?", """
SELECT ?연도 (SUM(?amt) AS ?총예산_백만원) (COUNT(DISTINCT ?prog) AS ?사업수) WHERE {
  ?prog a nrdp:RnDProgram ;
        nrdp:belongsToField ex:TF_BIO ;
        nrdp:hasAllocation ?ba .
  ?ba nrdp:inFiscalYear ?fy ; nrdp:hasAmount ?amt .
  ?fy nrdp:yearValue ?연도 .
} GROUP BY ?연도 ORDER BY ?연도
""")

CQ[3] = ("두 개 이상의 부처가 동일 기술분야에 투자하고 있는 사례는?", """
SELECT ?기술분야 (COUNT(DISTINCT ?min) AS ?부처수)
       (GROUP_CONCAT(DISTINCT ?부처명; SEPARATOR=" / ") AS ?부처목록) WHERE {
  ?prog a nrdp:RnDProgram ;
        nrdp:belongsToField ?tf ;
        nrdp:fundedBy ?min .
  ?tf rdfs:label ?기술분야 .
  ?min rdfs:label ?부처명 .
} GROUP BY ?tf ?기술분야
  HAVING (COUNT(DISTINCT ?min) >= 2)
  ORDER BY DESC(?부처수) ?기술분야
""")

CQ[4] = ("특정 사업이 기여하는 것으로 선언된 정책목표는 무엇인가?", """
SELECT ?사업명 ?정책목표 WHERE {
  ex:P05 rdfs:label ?사업명 ; nrdp:contributesTo ?pg .
  ?pg rdfs:label ?정책목표 .
} ORDER BY ?정책목표
""")

CQ[5] = ("어떤 정책목표에도 연결되지 않은 사업이 존재하는가?", """
SELECT ?사업코드 ?사업명 ?부처명 WHERE {
  ?prog a nrdp:RnDProgram ;
        nrdp:programCode ?사업코드 ;
        rdfs:label ?사업명 ;
        nrdp:fundedBy ?min .
  ?min rdfs:label ?부처명 .
  FILTER NOT EXISTS { ?prog nrdp:contributesTo ?anyGoal }
}
""")

# partOfProgram 은 OWL TransitiveProperty 이지만 질의 시점에 추론이 없으면
# property path(+) 로 명시해야 한다 → 논문 3.7절 '그래프 계층 위임'의 실례
CQ[6] = ("특정 사업의 하위 과제 수와 총 수행기관 수는? (추이적 관계)", """
SELECT ?사업명 (COUNT(DISTINCT ?proj) AS ?과제수)
       (COUNT(DISTINCT ?org) AS ?수행기관수) WHERE {
  ex:P01 rdfs:label ?사업명 .
  ?proj a nrdp:RnDProject ;
        nrdp:partOfProgram+ ex:P01 ;
        nrdp:performedBy ?org .
} GROUP BY ?사업명
""")

CQ[7] = ("예산은 증가했으나 성과지표는 감소한 사업이 있는가? (2022→2023)", """
SELECT ?사업명 ?예산_2022 ?예산_2023 ?논문_2022 ?논문_2023 WHERE {
  ?prog a nrdp:RnDProgram ; rdfs:label ?사업명 .
  ?prog nrdp:hasAllocation ?ba22, ?ba23 .
  ?ba22 nrdp:inFiscalYear ex:FY2022 ; nrdp:hasAmount ?예산_2022 .
  ?ba23 nrdp:inFiscalYear ex:FY2023 ; nrdp:hasAmount ?예산_2023 .
  ?prog nrdp:hasObservation ?ob22, ?ob23 .
  ?ob22 nrdp:inFiscalYear ex:FY2022 ; nrdp:forIndicator ex:IND_EFF ;
        nrdp:hasObservedValue ?논문_2022 .
  ?ob23 nrdp:inFiscalYear ex:FY2023 ; nrdp:forIndicator ex:IND_EFF ;
        nrdp:hasObservedValue ?논문_2023 .
  FILTER (?예산_2023 > ?예산_2022 && ?논문_2023 < ?논문_2022)
}
""")

# ══════════════════ B. MCDM 구조 (CQ8–CQ15) ══════════════════

CQ[8] = ("특정 의사결정 문제에 포함된 대안의 수와 기준의 수는?", """
SELECT ?문제명 ?대안수 ?기준수 ?리프기준수 WHERE {
  ex:DP1 rdfs:label ?문제명 .
  { SELECT (COUNT(DISTINCT ?a) AS ?대안수) WHERE { ex:DP1 mcdm:hasAlternative ?a } }
  { SELECT (COUNT(DISTINCT ?c) AS ?기준수) WHERE { ex:DP1 mcdm:hasCriterion ?c } }
  { SELECT (COUNT(DISTINCT ?c2) AS ?리프기준수) WHERE {
      ex:DP1 mcdm:hasCriterion ?c2 .
      FILTER NOT EXISTS { ?c2 mcdm:hasSubCriterion ?sub } } }
}
""")

CQ[9] = ("어떤 기준이 하위기준을 가지며, 그 깊이는 얼마인가?", """
SELECT ?상위기준 ?하위기준 ?깊이 WHERE {
  ?parent mcdm:hasSubCriterion ?child ; rdfs:label ?상위기준 .
  ?child rdfs:label ?하위기준 .
  { SELECT ?child (COUNT(?mid) AS ?깊이) WHERE {
      ?mid mcdm:hasSubCriterion+ ?child .
    } GROUP BY ?child }
} ORDER BY ?상위기준 ?하위기준
""")

CQ[10] = ("비용형(cost) 기준으로 분류된 기준의 목록은?", """
SELECT ?기준 ?척도 WHERE {
  ?c a mcdm:CostCriterion ; rdfs:label ?기준 ; mcdm:hasScale ?sc .
  ?sc rdfs:label ?척도 .
} ORDER BY ?기준
""")

CQ[11] = ("각 기준이 측정되는 성과지표는 무엇이며 단위는?", """
SELECT ?기준 ?성과지표 ?단위 WHERE {
  ?c a/rdfs:subClassOf* mcdm:Criterion ; rdfs:label ?기준 ; mcdm:measuredBy ?ind .
  ?ind rdfs:label ?성과지표 ; nrdp:indicatorUnit ?단위 .
} ORDER BY ?기준
""")

CQ[12] = ("원시값은 있으나 정규화값이 없는 평가값이 존재하는가?", """
SELECT ?대안명 ?기준 ?원시값 WHERE {
  ?cv a mcdm:CriterionValue ;
      mcdm:ofAlternative ?alt ;
      mcdm:onCriterion ?c ;
      mcdm:hasRawValue ?원시값 .
  ?alt rdfs:label ?대안명 . ?c rdfs:label ?기준 .
  FILTER NOT EXISTS { ?cv mcdm:hasNormalization ?nv }
} ORDER BY ?대안명 ?기준
""")

CQ["12b"] = ("[보조] 동일 평가값이 정규화방법별로 다른 값을 갖는가? (v0.2 검증)", """
SELECT ?대안명 ?기준 ?정규화방법 ?정규화값 WHERE {
  ex:CV_P01_C1 mcdm:ofAlternative ?alt ; mcdm:onCriterion ?c ;
               mcdm:hasNormalization ?nv .
  ?nv mcdm:normalizedBy ?nm ; mcdm:hasValue ?정규화값 .
  ?alt rdfs:label ?대안명 . ?c rdfs:label ?기준 . ?nm rdfs:label ?정규화방법 .
} ORDER BY ?정규화방법
""")

CQ[13] = ("어떤 대안이 특정 기준에서 평가값을 결여하고 있는가? (결측 탐지)", """
SELECT ?대안명 ?결측기준 WHERE {
  ex:DP1 mcdm:hasAlternative ?alt ; mcdm:hasCriterion ?c .
  ?alt rdfs:label ?대안명 . ?c rdfs:label ?결측기준 .
  FILTER NOT EXISTS { ?c mcdm:hasSubCriterion ?sub }      # 리프 기준만
  FILTER NOT EXISTS {
    ?cv a mcdm:CriterionValue ; mcdm:ofAlternative ?alt ; mcdm:onCriterion ?c .
  }
} ORDER BY ?대안명 ?결측기준
""")

CQ[14] = ("각 집계기법이 요구하는 파라미터의 인스턴스화 상태는?", """
SELECT ?기법 ?선호모델 ?정규화필요 ?정규화방법 ?선호함수 WHERE {
  ?m a/rdfs:subClassOf* mcdm:AggregationMethod ;
     rdfs:label ?기법 ;
     mcdm:hasPreferenceModel ?선호모델 ;
     mcdm:requiresNormalization ?정규화필요 .
  OPTIONAL { ?m mcdm:usesNormalization ?nm . ?nm rdfs:label ?정규화방법 }
  OPTIONAL { ?m mcdm:usesPreferenceFunction ?pf . ?pf rdfs:label ?선호함수 }
} ORDER BY ?기법
""")

CQ[15] = ("비보상형으로 분류된 집계기법의 목록과 각 선호함수·임계값은?", """
SELECT ?기법 ?선호함수 ?임계값q ?임계값p WHERE {
  ?m a mcdm:OutrankingMethod ; rdfs:label ?기법 ;
     mcdm:usesPreferenceFunction ?pf .
  ?pf rdfs:label ?선호함수 ;
      mcdm:preferenceThresholdQ ?임계값q ;
      mcdm:preferenceThresholdP ?임계값p .
}
""")

# ══════════════════ C. 시나리오 비교 (CQ16–CQ21) ══════════════════

CQ[16] = ("정의된 정책 시나리오의 목록과 각 시나리오의 가중치 분포는?", """
SELECT ?시나리오 ?설명 ?기준 ?가중치 WHERE {
  ?s a mcdm:DecisionScenario ; rdfs:label ?시나리오 ;
     mcdm:scenarioLabel ?설명 ; mcdm:hasWeight ?w .
  ?w mcdm:assignedToCriterion ?c ; mcdm:hasWeightValue ?가중치 .
  ?c rdfs:label ?기준 .
} ORDER BY ?시나리오 DESC(?가중치) ?기준
""")

CQ[17] = ("시나리오 S2와 S3 사이에서 가중치 차이가 가장 큰 기준은?", """
SELECT ?기준 ?효율중심 ?혁신중심 ?차이 WHERE {
  ex:S2 mcdm:hasWeight ?w2 . ?w2 mcdm:assignedToCriterion ?c ;
                                mcdm:hasWeightValue ?효율중심 .
  ex:S3 mcdm:hasWeight ?w3 . ?w3 mcdm:assignedToCriterion ?c ;
                                mcdm:hasWeightValue ?혁신중심 .
  ?c rdfs:label ?기준 .
  BIND(ABS(?혁신중심 - ?효율중심) AS ?차이)
} ORDER BY DESC(?차이) ?기준
""")

CQ[18] = ("동일 대안이 시나리오 S2와 S3에서 각각 몇 위인가? (WSM 기준)", """
SELECT ?대안명 ?순위_효율중심 ?순위_혁신중심 ?순위변동 WHERE {
  ?dr2 mcdm:forScenario ex:S2 ; mcdm:byMethod ex:M_WSM ;
       mcdm:ofAlternative ?alt ; mcdm:hasRank ?순위_효율중심 .
  ?dr3 mcdm:forScenario ex:S3 ; mcdm:byMethod ex:M_WSM ;
       mcdm:ofAlternative ?alt ; mcdm:hasRank ?순위_혁신중심 .
  ?alt rdfs:label ?대안명 .
  BIND(?순위_효율중심 - ?순위_혁신중심 AS ?순위변동)
} ORDER BY ?순위_효율중심
""")

CQ[19] = ("모든 시나리오에서 상위 3위 내를 유지하는 대안은? (강건 대안)", """
SELECT ?대안명 (COUNT(DISTINCT ?s) AS ?상위3위_시나리오수)
       (MAX(?r) AS ?최악순위) WHERE {
  ?dr mcdm:forScenario ?s ; mcdm:byMethod ex:M_WSM ;
      mcdm:ofAlternative ?alt ; mcdm:hasRank ?r .
  ?alt rdfs:label ?대안명 .
  FILTER (?r <= 3)
} GROUP BY ?alt ?대안명
  HAVING (COUNT(DISTINCT ?s) = 3)
  ORDER BY DESC(?최악순위) ?대안명
""")

CQ[20] = ("시나리오 변경에 순위가 가장 민감하게 반응하는 대안은?", """
SELECT ?대안명 (MIN(?r) AS ?최고순위) (MAX(?r) AS ?최저순위)
       ((MAX(?r) - MIN(?r)) AS ?순위폭) WHERE {
  ?dr mcdm:forScenario ?s ; mcdm:byMethod ex:M_WSM ;
      mcdm:ofAlternative ?alt ; mcdm:hasRank ?r .
  ?alt rdfs:label ?대안명 .
} GROUP BY ?alt ?대안명
  ORDER BY DESC(?순위폭) ?대안명
""")

CQ[21] = ("동일 시나리오·동일 데이터에서 TOPSIS와 PROMETHEE II의 순위는 일치하는가?", """
SELECT ?대안명 ?TOPSIS순위 ?PROMETHEE순위 ?불일치 WHERE {
  ?dt mcdm:forScenario ex:S3 ; mcdm:byMethod ex:M_TOPSIS ;
      mcdm:ofAlternative ?alt ; mcdm:hasRank ?TOPSIS순위 .
  ?dp mcdm:forScenario ex:S3 ; mcdm:byMethod ex:M_PRO2 ;
      mcdm:ofAlternative ?alt ; mcdm:hasRank ?PROMETHEE순위 .
  ?alt rdfs:label ?대안명 .
  BIND(ABS(?TOPSIS순위 - ?PROMETHEE순위) AS ?불일치)
} ORDER BY DESC(?불일치) ?대안명
""")

# ══════════════════ D. 설명 (CQ22–CQ25) ══════════════════

CQ[22] = ("특정 대안의 종합점수에 각 기준이 기여한 비율은?", """
SELECT ?대안명 ?기준 ?기여비율 WHERE {
  ?cc a mcdm:CriterionContribution ;
      mcdm:explains ?dr ;
      mcdm:contributionOf ?c ;
      mcdm:hasContributionRatio ?기여비율 .
  ?dr mcdm:ofAlternative ex:ALT_P01 ; mcdm:forScenario ex:S1 ;
      mcdm:byMethod ex:M_WSM .
  ex:ALT_P01 rdfs:label ?대안명 . ?c rdfs:label ?기준 .
} ORDER BY DESC(?기여비율)
""")

CQ[23] = ("특정 대안의 특정 기준 평가값은 어떤 원천 데이터에서 유래하는가?", """
SELECT ?평가값 ?정규화활동 ?원시통계 ?NTIS레코드 ?원천데이터셋 WHERE {
  ex:CV_P01_C1 mcdm:hasRawValue ?평가값 ;
               prov:wasGeneratedBy ?act .
  ?act rdfs:label ?정규화활동 ; prov:used ?raw .
  ?raw rdfs:label ?원시통계 ; prov:wasDerivedFrom ?rec .
  ?rec rdfs:label ?NTIS레코드 ; prov:wasDerivedFrom ?src .
  ?src rdfs:label ?원천데이터셋 .
}
""")

CQ[24] = ("대안 X가 상위 3위에 진입하려면 어떤 기준이 얼마나 개선되어야 하는가? (반사실)", """
SELECT ?대안명 ?기준 ?필요_정규화값 ?필요_원시값 ?실현가능 WHERE {
  ?cf a mcdm:CounterfactualCondition ;
      mcdm:explains ?dr ;
      mcdm:concernsCriterion ?c ;
      mcdm:requiredNormalizedValue ?필요_정규화값 ;
      mcdm:requiredRawValue ?필요_원시값 ;
      mcdm:isFeasible ?실현가능 .
  ?dr mcdm:ofAlternative ?alt .
  ?alt rdfs:label ?대안명 . ?c rdfs:label ?기준 .
} ORDER BY DESC(?실현가능) ?필요_정규화값
""")

# CQ24-b : 사전 계산된 인스턴스 없이 질의만으로 '개선 필요량'을 도출하는 버전
#          (WSM 의 선형성을 이용. 비보상형 기법에는 적용 불가)
CQ["24b"] = ("[보조] 사전계산 없이 3위 점수와의 격차를 질의로 산출 (WSM 한정)", """
SELECT ?대안명 ?현재점수 ?현재순위 ?목표점수 ?필요증분 WHERE {
  ?dr mcdm:forScenario ex:S1 ; mcdm:byMethod ex:M_WSM ;
      mcdm:ofAlternative ?alt ; mcdm:hasScore ?현재점수 ; mcdm:hasRank ?현재순위 .
  ?alt rdfs:label ?대안명 .
  { SELECT (?sc AS ?목표점수) WHERE {
      ?d3 mcdm:forScenario ex:S1 ; mcdm:byMethod ex:M_WSM ;
          mcdm:hasRank 3 ; mcdm:hasScore ?sc .
  } }
  FILTER (?현재순위 > 3)
  BIND(?목표점수 - ?현재점수 AS ?필요증분)
} ORDER BY ?필요증분
""")

CQ[25] = ("두 대안의 순위 역전을 유발하는 최소 가중치 변화량은?", None)   # 질의 단독 불가

# ══════════════════ 실행 ══════════════════
if __name__ == "__main__":
    import sys
    from rdflib import Graph
    from cq_format import table   # run_cypher.py 와 같은 출력 서식 (대조용)

    g = Graph()
    g.parse("nrdp-ontology.ttl", format="turtle")
    g.parse("data-sample.ttl", format="turtle")

    ok = fail = skipped = 0
    out = []
    for key in list(CQ.keys()):
        desc, q = CQ[key]
        head = f"CQ{key}. {desc}"
        out.append("=" * 78); out.append(head)
        if q is None:
            out.append("  [△ 질의 단독 수행 불가 — 절차적 계산 필요]")
            skipped += 1
            continue
        try:
            qr = g.query(PREFIX + q)
            res = list(qr)
            cols = [str(v) for v in qr.vars]
            out.append(table(cols, [tuple(row) for row in res]))
            if not res:
                fail += 1
            else:
                ok += 1
        except Exception as e:
            out.append(f"  [오류] {type(e).__name__}: {e}")
            fail += 1

    out.append("=" * 78)
    out.append(f"실행 성공(비어있지 않음): {ok} / 실패·빈결과: {fail} / 질의불가: {skipped}")
    text = "\n".join(out)
    print(text)
    open("sparql-results.txt", "w", encoding="utf-8").write(text + "\n")
