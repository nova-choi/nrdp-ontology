// ═══════════════════════════════════════════════════════════════════════
//  역량질문(CQ) 25개 — Neo4j 5.x Cypher
//  국가 R&D 포트폴리오 MCDM 온톨로지 / 최혜석
//
//  OWL → 속성그래프 변환 규칙 (논문 4.2절)
//    OWL Class            → 노드 레이블
//    OWL ObjectProperty   → 관계 타입
//    OWL DatatypeProperty → 노드 속성
//    rdfs:subClassOf      → 다중 레이블 (예: :Criterion:CostCriterion)
//    n-ary 재화 클래스     → 노드로 유지 (관계로 접히지 않음)
//    TransitiveProperty   → 가변길이 경로 [:R*] 또는 추론 물리화
//
//  검증 표기
//    [V] Neo4j 5.x 본체에서 v0.2 데이터(노드 452 / 관계 1,057)로 실행하여
//        SPARQL 결과(sparql-results.txt)와 값 일치 확인 — 2026-10-10, neo4j-results.txt
//    [△] 질의 단독 수행 불가 (입력 회수까지만 질의로 수행)
//
//  SPARQL 대응 규칙 (2026-10-10)
//    반환 열 이름·순서, 정렬 키(동률 시 보조 키 포함), 수치 반올림을 queries_sparql.py 와
//    맞추어 두 결과 파일을 compare_results.py 로 CQ 단위 대조할 수 있게 한다.
// ═══════════════════════════════════════════════════════════════════════

// ───────────────────── A. 도메인 조회 ─────────────────────

// CQ1 [V] 특정 부처 소관 사업 목록과 2023년 예산액
MATCH (p:Program)-[:FUNDED_BY]->(m:Ministry {id:'MIN_MSIT'}),
      (p)-[:HAS_ALLOCATION]->(ba:BudgetAllocation)-[:IN_FY]->(:FiscalYear {id:'FY2023'})
RETURN p.label AS `사업명`, ba.amount AS `예산액_백만원`
ORDER BY `예산액_백만원` DESC;

// CQ2 [V] 특정 기술분야 총예산의 연도별 추이
MATCH (p:Program)-[:BELONGS_TO_FIELD]->(:TechField {id:'TF_BIO'}),
      (p)-[:HAS_ALLOCATION]->(ba:BudgetAllocation)-[:IN_FY]->(fy:FiscalYear)
RETURN fy.year AS `연도`, sum(ba.amount) AS `총예산_백만원`,
       count(DISTINCT p) AS `사업수`
ORDER BY `연도`;

// CQ3 [V] 2개 이상 부처가 동일 기술분야에 투자하는 사례
MATCH (p:Program)-[:BELONGS_TO_FIELD]->(tf:TechField),
      (p)-[:FUNDED_BY]->(m:Ministry)
WITH tf, count(DISTINCT m) AS `부처수`, collect(DISTINCT m.label) AS ms
WHERE `부처수` >= 2
RETURN tf.label AS `기술분야`, `부처수`,
       reduce(s = '', x IN ms | CASE s WHEN '' THEN x ELSE s + ' / ' + x END) AS `부처목록`
ORDER BY `부처수` DESC, `기술분야`;

// CQ4 [V] 특정 사업이 기여하는 정책목표
MATCH (p:Program {id:'P05'})-[:CONTRIBUTES_TO]->(pg:PolicyGoal)
RETURN p.label AS `사업명`, pg.label AS `정책목표`
ORDER BY `정책목표`;

// CQ5 [V] 어떤 정책목표에도 연결되지 않은 사업
MATCH (p:Program)-[:FUNDED_BY]->(m:Ministry)
WHERE NOT (p)-[:CONTRIBUTES_TO]->(:PolicyGoal)
RETURN p.code AS `사업코드`, p.label AS `사업명`, m.label AS `부처명`;

// CQ6 [V] 특정 사업의 하위 과제 수와 수행기관 수 (추이적 관계 → 가변길이 경로)
//      ※ OWL TransitiveProperty 는 Cypher 에서 [*1..] 로 표현하거나
//        추론 결과를 물리화해야 한다 (논문 3.7절 / 4.3절)
MATCH (pj:Project)-[:PART_OF*1..3]->(p:Program {id:'P01'}),
      (pj)-[:PERFORMED_BY]->(o:Performer)
RETURN p.label AS `사업명`, count(DISTINCT pj) AS `과제수`,
       count(DISTINCT o) AS `수행기관수`;

// CQ7 [V] 예산은 증가했으나 성과지표는 감소한 사업 (2022→2023)
MATCH (p:Program)-[:HAS_ALLOCATION]->(b22:BudgetAllocation)-[:IN_FY]->(:FiscalYear {id:'FY2022'}),
      (p)-[:HAS_ALLOCATION]->(b23:BudgetAllocation)-[:IN_FY]->(:FiscalYear {id:'FY2023'}),
      (p)-[:HAS_OBSERVATION]->(o22:Observation)-[:IN_FY]->(:FiscalYear {id:'FY2022'}),
      (o22)-[:FOR_INDICATOR]->(:Indicator {id:'IND_EFF'}),
      (p)-[:HAS_OBSERVATION]->(o23:Observation)-[:IN_FY]->(:FiscalYear {id:'FY2023'}),
      (o23)-[:FOR_INDICATOR]->(:Indicator {id:'IND_EFF'})
WHERE b23.amount > b22.amount AND o23.value < o22.value
RETURN p.label AS `사업명`, b22.amount AS `예산_2022`, b23.amount AS `예산_2023`,
       o22.value AS `논문_2022`, o23.value AS `논문_2023`;

// ───────────────────── B. MCDM 구조 ─────────────────────

// CQ8 [V] 의사결정 문제의 대안 수 / 기준 수 / 리프기준 수
MATCH (dp:DecisionProblem {id:'DP1'})
OPTIONAL MATCH (dp)-[:HAS_ALTERNATIVE]->(a:Alternative)
WITH dp, count(DISTINCT a) AS `대안수`
OPTIONAL MATCH (dp)-[:HAS_CRITERION]->(c:Criterion)
WITH dp, `대안수`, count(DISTINCT c) AS `기준수`
OPTIONAL MATCH (dp)-[:HAS_CRITERION]->(leaf:Criterion)
WHERE NOT (leaf)-[:HAS_SUBCRITERION]->()
RETURN dp.label AS `문제명`, `대안수`, `기준수`, count(DISTINCT leaf) AS `리프기준수`;

// CQ9 [V] 하위기준을 가진 기준과 계층 깊이
MATCH path = (root:Criterion)-[:HAS_SUBCRITERION*1..]->(leaf:Criterion)
WHERE NOT ()-[:HAS_SUBCRITERION]->(root)
RETURN root.label AS `상위기준`, leaf.label AS `하위기준`,
       length(path) AS `깊이`
ORDER BY `상위기준`, `하위기준`;

// CQ10 [V] 비용형 기준 목록  (다중 레이블 활용 — OWL 하위클래스의 직접 대응)
MATCH (c:CostCriterion)
RETURN c.label AS `기준`, c.scale AS `척도`
ORDER BY `기준`;

// CQ11 [V] 각 기준이 측정되는 성과지표와 단위
MATCH (c:Criterion)-[:MEASURED_BY]->(i:Indicator)
RETURN c.label AS `기준`, i.label AS `성과지표`, i.unit AS `단위`
ORDER BY `기준`;

// CQ12 [V] 원시값은 있으나 정규화값이 없는 평가값 (v0.2: HAS_NORMALIZATION 부재로 판정)
MATCH (cv:CriterionValue)-[:OF_ALTERNATIVE]->(a:Alternative),
      (cv)-[:ON_CRITERION]->(c:Criterion)
WHERE NOT (cv)-[:HAS_NORMALIZATION]->(:NormalizedValue)
RETURN a.label AS `대안명`, c.label AS `기준`, cv.raw AS `원시값`
ORDER BY `대안명`, `기준`;

// CQ12-b [V] 동일 평가값이 정규화방법별로 다른 값을 갖는가 (v0.2 검증)
MATCH (cv:CriterionValue {id:'CV_P01_C1'})-[:HAS_NORMALIZATION]->(nv:NormalizedValue)
      -[:NORMALIZED_BY]->(nm:Normalization),
      (cv)-[:OF_ALTERNATIVE]->(a:Alternative), (cv)-[:ON_CRITERION]->(c:Criterion)
RETURN a.label AS `대안명`, c.label AS `기준`, nm.label AS `정규화방법`, nv.value AS `정규화값`
ORDER BY `정규화방법`;

// CQ13 [V] 리프 기준에서 평가값이 결여된 대안 (결측 탐지)
MATCH (dp:DecisionProblem {id:'DP1'})-[:HAS_ALTERNATIVE]->(a:Alternative),
      (dp)-[:HAS_CRITERION]->(c:Criterion)
WHERE NOT (c)-[:HAS_SUBCRITERION]->()
  AND NOT (a)<-[:OF_ALTERNATIVE]-(:CriterionValue)-[:ON_CRITERION]->(c)
RETURN a.label AS `대안명`, c.label AS `결측기준`
ORDER BY `대안명`, `결측기준`;

// CQ14 [V] 각 집계기법의 파라미터 인스턴스화 상태
MATCH (m:AggregationMethod)
OPTIONAL MATCH (m)-[:USES_NORM]->(nm:Normalization)
OPTIONAL MATCH (m)-[:USES_PREFFN]->(pf:PreferenceFunction)
RETURN m.label AS `기법`, m.prefModel AS `선호모델`,
       m.requiresNorm AS `정규화필요`, nm.label AS `정규화방법`,
       pf.label AS `선호함수`        // 미인스턴스화는 null → 출력 시 '-' (SPARQL OPTIONAL 미결합과 동일)
ORDER BY `기법`;

// CQ15 [V] 비보상형 기법의 선호함수와 임계값
MATCH (m:OutrankingMethod)-[:USES_PREFFN]->(pf:PreferenceFunction)
RETURN m.label AS `기법`, pf.label AS `선호함수`,
       pf.q AS `임계값q`, pf.p AS `임계값p`;

// ───────────────────── C. 시나리오 비교 ─────────────────────

// CQ16 [V] 시나리오 목록과 가중치 분포
MATCH (s:Scenario)-[:HAS_WEIGHT]->(w:Weight)-[:ASSIGNED_TO]->(c:Criterion)
RETURN s.label AS `시나리오`, s.descr AS `설명`, c.label AS `기준`, w.value AS `가중치`
ORDER BY `시나리오`, `가중치` DESC, `기준`;

// CQ17 [V] 두 시나리오 간 가중치 차이가 가장 큰 기준
MATCH (:Scenario {id:'S2'})-[:HAS_WEIGHT]->(w2:Weight)-[:ASSIGNED_TO]->(c:Criterion),
      (:Scenario {id:'S3'})-[:HAS_WEIGHT]->(w3:Weight)-[:ASSIGNED_TO]->(c)
RETURN c.label AS `기준`, w2.value AS `효율중심`, w3.value AS `혁신중심`,
       round(abs(w3.value - w2.value), 6) AS `차이`
ORDER BY `차이` DESC, `기준`;

// CQ18 [V] 동일 대안의 시나리오별 순위와 변동
MATCH (d2:DecisionResult)-[:FOR_SCENARIO]->(:Scenario {id:'S2'}),
      (d2)-[:BY_METHOD]->(:Method {id:'M_WSM'}),
      (d2)-[:OF_ALTERNATIVE]->(a:Alternative),
      (d3:DecisionResult)-[:FOR_SCENARIO]->(:Scenario {id:'S3'}),
      (d3)-[:BY_METHOD]->(:Method {id:'M_WSM'}),
      (d3)-[:OF_ALTERNATIVE]->(a)
RETURN a.label AS `대안명`, d2.rank AS `순위_효율중심`, d3.rank AS `순위_혁신중심`,
       d2.rank - d3.rank AS `순위변동`
ORDER BY `순위_효율중심`;

// CQ19 [V] 모든 시나리오에서 상위 3위를 유지하는 강건 대안
MATCH (dr:DecisionResult)-[:FOR_SCENARIO]->(s:Scenario),
      (dr)-[:BY_METHOD]->(:Method {id:'M_WSM'}),
      (dr)-[:OF_ALTERNATIVE]->(a:Alternative)
WHERE dr.rank <= 3
WITH a, count(DISTINCT s) AS `상위3위_시나리오수`, max(dr.rank) AS `최악순위`
WHERE `상위3위_시나리오수` = 3
RETURN a.label AS `대안명`, `상위3위_시나리오수`, `최악순위`
ORDER BY `최악순위` DESC, `대안명`;

// CQ20 [V] 시나리오 변경에 가장 민감한 대안
MATCH (dr:DecisionResult)-[:FOR_SCENARIO]->(:Scenario),
      (dr)-[:BY_METHOD]->(:Method {id:'M_WSM'}),
      (dr)-[:OF_ALTERNATIVE]->(a:Alternative)
WITH a, min(dr.rank) AS `최고순위`, max(dr.rank) AS `최저순위`
RETURN a.label AS `대안명`, `최고순위`, `최저순위`,
       `최저순위` - `최고순위` AS `순위폭`
ORDER BY `순위폭` DESC, `대안명`;

// CQ21 [V] 동일 시나리오에서 TOPSIS 와 PROMETHEE II 의 순위 불일치
MATCH (dt:DecisionResult)-[:FOR_SCENARIO]->(:Scenario {id:'S3'}),
      (dt)-[:BY_METHOD]->(:Method {id:'M_TOPSIS'}),
      (dt)-[:OF_ALTERNATIVE]->(a:Alternative),
      (dq:DecisionResult)-[:FOR_SCENARIO]->(:Scenario {id:'S3'}),
      (dq)-[:BY_METHOD]->(:Method {id:'M_PRO2'}),
      (dq)-[:OF_ALTERNATIVE]->(a)
RETURN a.label AS `대안명`, dt.rank AS `TOPSIS순위`, dq.rank AS `PROMETHEE순위`,
       abs(dt.rank - dq.rank) AS `불일치`
ORDER BY `불일치` DESC, `대안명`;

// ───────────────────── D. 설명 ─────────────────────

// CQ22 [V] 특정 대안 종합점수의 기준별 기여 비율
MATCH (cc:Contribution)-[:EXPLAINS]->(dr:DecisionResult),
      (cc)-[:CONTRIBUTION_OF]->(c:Criterion),
      (dr)-[:OF_ALTERNATIVE]->(a:Alternative {id:'ALT_P01'}),
      (dr)-[:FOR_SCENARIO]->(:Scenario {id:'S1'}),
      (dr)-[:BY_METHOD]->(:Method {id:'M_WSM'})
RETURN a.label AS `대안명`, c.label AS `기준`, cc.ratio AS `기여비율`
ORDER BY `기여비율` DESC;

// CQ23 [V] 평가값의 원천 데이터 경로 (PROV 체인)
MATCH (cv:CriterionValue {id:'CV_P01_C1'})-[:WAS_GENERATED_BY]->(act:ProvActivity),
      (act)-[:USED]->(raw:ProvEntity),
      (raw)-[:WAS_DERIVED_FROM]->(rec:ProvEntity),
      (rec)-[:WAS_DERIVED_FROM]->(src:ProvEntity)
RETURN cv.raw AS `평가값`, act.label AS `정규화활동`, raw.label AS `원시통계`,
       rec.label AS `NTIS레코드`, src.label AS `원천데이터셋`;

// CQ23-b [V] 경로 전체를 가변길이로 회수하는 일반형
//   2026-10-10 수정: 종단 노드를 ProvEntity로 한정. 한정이 없으면 ProvActivity도
//   'WAS_DERIVED_FROM 출력 없음' 조건을 만족해 길이 1의 불완전 경로가 함께 반환되었다.
MATCH path = (cv:CriterionValue {id:'CV_P01_C1'})
             -[:WAS_GENERATED_BY|USED|WAS_DERIVED_FROM*1..6]->(src:ProvEntity)
WHERE NOT (src)-[:WAS_DERIVED_FROM]->()
RETURN [n IN nodes(path) | coalesce(n.label, n.id)] AS `근거경로`,
       length(path) AS `경로길이`;

// CQ24 [V] 반사실적 설명 — 3위 진입에 필요한 기준별 개선량 (사전 계산 인스턴스)
MATCH (cf:Counterfactual)-[:EXPLAINS]->(dr:DecisionResult),
      (cf)-[:CONCERNS_CRITERION]->(c:Criterion),
      (dr)-[:OF_ALTERNATIVE]->(a:Alternative)
RETURN a.label AS `대안명`, c.label AS `기준`,
       cf.needNorm AS `필요_정규화값`, cf.needRaw AS `필요_원시값`,
       cf.feasible AS `실현가능`
ORDER BY `실현가능` DESC, `필요_정규화값`;

// CQ24-b [V] 사전 계산 없이 3위 점수와의 격차를 질의로 산출 (WSM 선형성 이용)
//        ※ 비보상형 기법(PROMETHEE/ELECTRE)에는 적용 불가
MATCH (d3:DecisionResult)-[:FOR_SCENARIO]->(:Scenario {id:'S1'}),
      (d3)-[:BY_METHOD]->(:Method {id:'M_WSM'})
WHERE d3.rank = 3
WITH d3.score AS `목표점수`
MATCH (dr:DecisionResult)-[:FOR_SCENARIO]->(:Scenario {id:'S1'}),
      (dr)-[:BY_METHOD]->(:Method {id:'M_WSM'}),
      (dr)-[:OF_ALTERNATIVE]->(a:Alternative)
WHERE dr.rank > 3
RETURN a.label AS `대안명`, dr.score AS `현재점수`, dr.rank AS `현재순위`,
       `목표점수`, round(`목표점수` - dr.score, 6) AS `필요증분`
ORDER BY `필요증분`;

// CQ25 [△] 두 대안의 순위 역전을 유발하는 최소 가중치 변화량
//   질의 단독으로 수행 불가. 가중치 벡터를 변수로 하는 최적화 문제이므로
//   그래프에서 (대안별 정규화값, 가중치) 를 회수한 뒤 절차적으로 계산해야 한다.
//   아래는 계산에 필요한 입력을 회수하는 질의까지만 제공한다.
//   ※ v0.2: 정규화값이 (평가값×정규화방법) 3항 관계가 되어 "그" 정규화값이
//     더 이상 존재하지 않는다 — 어떤 방법 기준인지 명시해야 한다.
//     아래는 WSM·PROMETHEE II가 쓰는 min-max(NM_MinMax) 기준.
MATCH (dp:DecisionProblem {id:'DP1'})-[:HAS_CRITERION]->(c:Criterion)
WHERE NOT (c)-[:HAS_SUBCRITERION]->()
MATCH (:Scenario {id:'S1'})-[:HAS_WEIGHT]->(w:Weight)-[:ASSIGNED_TO]->(c)
MATCH (cvA:CriterionValue)-[:ON_CRITERION]->(c),
      (cvA)-[:OF_ALTERNATIVE]->(:Alternative {id:'ALT_P01'}),
      (cvA)-[:HAS_NORMALIZATION]->(nvA:NormalizedValue)-[:NORMALIZED_BY]->(:Normalization {id:'NM_MinMax'})
MATCH (cvB:CriterionValue)-[:ON_CRITERION]->(c),
      (cvB)-[:OF_ALTERNATIVE]->(:Alternative {id:'ALT_P05'}),
      (cvB)-[:HAS_NORMALIZATION]->(nvB:NormalizedValue)-[:NORMALIZED_BY]->(:Normalization {id:'NM_MinMax'})
RETURN c.label AS `기준`, w.value AS `가중치`,
       nvA.value AS `A_정규화값`, nvB.value AS `B_정규화값`,
       nvA.value - nvB.value AS `격차`
ORDER BY abs(`격차`) DESC;
