// ═══════════════════════════════════════════════════════════════════
//  역량질문(CQ) Cypher — 온톨로지 v0.3 + NTIS 실데이터 (load_neo4j_real.py 적재본)
//  queries_sparql_real.py 의 CQ1~CQ30 과 1:1 대응. 결과는 compare_results.py 로 대조.
//  명명 규칙: 레이블 = 클래스 지역명, 관계 = 속성 지역명 UPPER_SNAKE, 노드 id = IRI 지역명
//  실행: python run_cypher.py queries_real.cypher --out data/rdf/neo4j-results-real.txt
// ═══════════════════════════════════════════════════════════════════

// CQ1. 2023년 기준 과학기술정보통신부가 소관하는 사업의 목록과 각 예산액(과제 협약 정부연구비 합산)은?
MATCH (p:RnDProgram)-[:FUNDED_BY]->(:Ministry {id: 'ORG_MIN_891684ea'}),
      (ba:BudgetAllocation)-[:OF_PROGRAM]->(p), (ba)-[:IN_FISCAL_YEAR]->(:FiscalYear {id: 'FY2023'})
RETURN p.label AS `사업명`, ba.hasAmount AS `예산액_백만원`, ba.budgetCode AS `예산코드`
ORDER BY `예산액_백만원` DESC, `사업명`;

// CQ2. 첨단바이오 분야 사업에 배정된 총 정부연구비의 연도별 추이는?
MATCH (p:RnDProgram)-[:STRATEGIC_TECHNOLOGY]->(:Concept {id: 'NST_050000'}),
      (ba:BudgetAllocation)-[:OF_PROGRAM]->(p), (ba)-[:IN_FISCAL_YEAR]->(fy:FiscalYear)
RETURN fy.yearValue AS `연도`, sum(ba.hasAmount) AS `총예산_백만원`, count(DISTINCT p) AS `사업수`
ORDER BY `연도`;

// CQ3. 두 개 이상의 부처가 동일 국가전략기술 분야에 투자하고 있는 사례는?
MATCH (p:RnDProgram)-[:STRATEGIC_TECHNOLOGY]->(nst), (p)-[:FUNDED_BY]->(m:Ministry)
WITH nst, m ORDER BY m.label
WITH nst, count(DISTINCT m) AS n, collect(DISTINCT m.label) AS ms
WHERE n >= 2
RETURN nst.label AS `분야`, n AS `부처수`, reduce(s = '', x IN ms | CASE s WHEN '' THEN x ELSE s + ' / ' + x END) AS `부처목록`
ORDER BY `부처수` DESC, `분야`;

// CQ4. 특정 사업이 선정된 국가전략기술 분야와 사업 수준 기술분야(집계 파생), 그 판정 활동은?
MATCH (p:RnDProgram {id: 'PRG_cf048767'})-[:STRATEGIC_TECHNOLOGY]->(nst), (p)-[:BELONGS_TO_FIELD]->(tf)-[:IN_SCHEME]->(ed),
      (p)-[:WAS_GENERATED_BY]->(act)
RETURN p.label AS `사업명`, nst.label AS `국가전략기술`, tf.label AS `표준분류_대분류`, ed.label AS `판`, act.label AS `판정활동`;

// CQ5. 어떤 정책목표에도 연결되지 않은 사업이 존재하는가? (GoalAlignment 부재 탐지)
MATCH (p:RnDProgram)
WITH p, exists { (:GoalAlignment)-[:OF_PROGRAM]->(p) } AS linked
RETURN sum(CASE WHEN linked THEN 0 ELSE 1 END) AS `미연결_사업수`, count(p) AS `전체_사업수`;

// CQ6. 특정 사업의 과제연도기록 수·과제 수·주관기관 수는? (partOfProgram 추이적 관계, 내역사업 경유)
MATCH (p:RnDProgram {id: 'PRG_a845330b'})
MATCH (pyr:ProjectYearRecord)-[:PART_OF_PROGRAM*1..3]->(p), (pyr)-[:OF_PROJECT]->(proj), (pyr)-[:LEAD_PERFORMER]->(org)
OPTIONAL MATCH (pyr)-[:PART_OF_PROGRAM]->(sp:RnDSubProgram)
RETURN p.label AS `사업명`, count(DISTINCT pyr) AS `과제연도기록수`, count(DISTINCT proj) AS `과제수`,
       count(DISTINCT org) AS `주관기관수`, count(DISTINCT sp) AS `내역사업수`;

// CQ7. 연구비는 증가했으나 SCI 논문 수는 감소한 사업이 있는가? (2022→2023)
MATCH (ob22:IndicatorObservation)-[:FOR_INDICATOR]->(:PerformanceIndicator {id: 'IND_SCI'}), (ob22)-[:IN_FISCAL_YEAR]->(:FiscalYear {id: 'FY2022'}),
      (ob22)-[:OF_PROGRAM]->(p:RnDProgram),
      (ob23:IndicatorObservation)-[:FOR_INDICATOR]->(:PerformanceIndicator {id: 'IND_SCI'}), (ob23)-[:IN_FISCAL_YEAR]->(:FiscalYear {id: 'FY2023'}),
      (ob23)-[:OF_PROGRAM]->(p),
      (ba22:BudgetAllocation)-[:OF_PROGRAM]->(p), (ba22)-[:IN_FISCAL_YEAR]->(:FiscalYear {id: 'FY2022'}),
      (ba23:BudgetAllocation)-[:OF_PROGRAM]->(p), (ba23)-[:IN_FISCAL_YEAR]->(:FiscalYear {id: 'FY2023'})
WHERE ba23.hasAmount > ba22.hasAmount AND ob23.hasObservedValue < ob22.hasObservedValue
RETURN p.label AS `사업명`, ba22.hasAmount AS `연구비_2022`, ba23.hasAmount AS `연구비_2023`,
       ob22.hasObservedValue AS `SCI_2022`, ob23.hasObservedValue AS `SCI_2023`
ORDER BY `사업명`;

// CQ8. 의사결정 문제에 포함된 대안의 수와 기준의 수는?
MATCH (dp:DecisionProblem {id: 'DP_MAIN'})
OPTIONAL MATCH (dp)-[:HAS_ALTERNATIVE]->(a)
WITH dp, count(DISTINCT a) AS na
OPTIONAL MATCH (dp)-[:HAS_CRITERION]->(c)
WITH dp, na, count(DISTINCT c) AS nc, count(DISTINCT CASE WHEN c:LeafCriterion THEN c END) AS nl
RETURN dp.label AS `문제명`, na AS `대안수`, nc AS `기준수`, nl AS `리프기준수`;

// CQ9. 어떤 기준이 하위기준을 가지며, 그 깊이는 얼마인가?
MATCH (parent)-[:HAS_SUB_CRITERION]->(child)
MATCH (mid)-[:HAS_SUB_CRITERION*1..]->(child)
WITH parent, child, count(DISTINCT mid) AS depth
RETURN parent.label AS `상위기준`, child.label AS `하위기준`, depth AS `깊이`
ORDER BY `상위기준`, `하위기준`;

// CQ10. 비용형(cost) 기준으로 분류된 기준의 목록은?
MATCH (c:CostCriterion)-[:HAS_SCALE]->(sc)
RETURN c.label AS `기준`, sc.label AS `척도` ORDER BY `기준`;

// CQ11. 각 기준이 측정되는 성과지표는 무엇이며 단위는?
MATCH (c:LeafCriterion)-[:MEASURED_BY]->(ind)
RETURN c.label AS `기준`, ind.label AS `성과지표`, ind.indicatorUnit AS `단위` ORDER BY `기준`;

// CQ12. 원시값은 있으나 정규화값이 없는 평가값이 존재하는가? (불완전 평가 대안 탐지)
MATCH (cv:CriterionValue)-[:OF_ALTERNATIVE]->(alt)
WHERE cv.hasRawValue IS NOT NULL AND NOT (cv)-[:HAS_NORMALIZATION]->()
RETURN alt.label AS `대안명`, count(cv) AS `정규화없는_평가값수` ORDER BY `대안명`;

// CQ12-b [보조] 동일 평가값이 정규화방법별로 다른 값을 갖는가?
MATCH (cv:CriterionValue {id: 'CV_PRG_a845330b_C_FUND'})-[:OF_ALTERNATIVE]->(alt), (cv)-[:ON_CRITERION]->(c),
      (cv)-[:HAS_NORMALIZATION]->(nv)-[:NORMALIZED_BY]->(nm)
RETURN alt.label AS `대안명`, c.label AS `기준`, nm.label AS `정규화방법`, nv.hasValue AS `정규화값` ORDER BY `정규화방법`;

// CQ13. 어떤 대안이 특정 기준에서 평가값을 결여하고 있는가? (결측 탐지)
MATCH (dp:DecisionProblem {id: 'DP_MAIN'})-[:HAS_ALTERNATIVE]->(alt), (dp)-[:HAS_CRITERION]->(c:LeafCriterion)
WHERE NOT exists { (cv:CriterionValue)-[:OF_ALTERNATIVE]->(alt) WHERE (cv)-[:ON_CRITERION]->(c) }
RETURN alt.label AS `대안명`, c.label AS `결측기준` ORDER BY `대안명`, `결측기준`;

// CQ14. 각 집계기법이 요구하는 파라미터의 인스턴스화 상태는?
MATCH (m)-[:HAS_COMPENSATION_LEVEL]->(cl)
WHERE m:ValueFunctionMethod OR m:DistanceBasedMethod OR m:OutrankingMethod
OPTIONAL MATCH (m)-[:USES_NORMALIZATION]->(nm)
OPTIONAL MATCH (m)-[:USES_PREFERENCE_FUNCTION]->(pf)
RETURN m.label AS `기법`,
       CASE WHEN m:ValueFunctionMethod THEN '가치함수형 기법' WHEN m:DistanceBasedMethod THEN '거리기반 기법' ELSE '아웃랭킹형 기법' END AS `집계논리`,
       cl.label AS `보상수준`, m.requiresNormalization AS `정규화필요`, m.supportsAdditiveDecomposition AS `가법분해`,
       nm.label AS `정규화방법`, pf.label AS `선호함수`
ORDER BY `기법`;

// CQ15. 열위관계형(outranking) 집계기법의 목록과 각 선호함수·임계값은?
MATCH (m:OutrankingMethod)-[:USES_PREFERENCE_FUNCTION]->(pf)
RETURN m.label AS `기법`, pf.label AS `선호함수`, pf.preferenceThresholdQ AS `임계값q`, pf.preferenceThresholdP AS `임계값p`;

// CQ16. 정의된 정책 시나리오의 목록과 각 시나리오의 가중치 분포는?
MATCH (s:DecisionScenario)-[:HAS_WEIGHT]->(w)-[:ASSIGNED_TO_CRITERION]->(c)
RETURN s.label AS `시나리오`, s.scenarioLabel AS `설명`, c.label AS `기준`, w.hasWeightValue AS `가중치`
ORDER BY `시나리오`, `가중치` DESC, `기준`;

// CQ17. 시나리오 S2(효율중심)와 S3(성과규모중심) 사이에서 가중치 차이가 가장 큰 기준은?
MATCH (:DecisionScenario {id: 'S2'})-[:HAS_WEIGHT]->(w2)-[:ASSIGNED_TO_CRITERION]->(c),
      (:DecisionScenario {id: 'S3'})-[:HAS_WEIGHT]->(w3)-[:ASSIGNED_TO_CRITERION]->(c)
RETURN c.label AS `기준`, w2.hasWeightValue AS `효율중심`, w3.hasWeightValue AS `성과규모중심`,
       abs(w3.hasWeightValue - w2.hasWeightValue) AS `차이`
ORDER BY `차이` DESC, `기준`;

// CQ18. 동일 대안이 시나리오 S2와 S3에서 각각 몇 위인가? (WSM 기준)
MATCH (d2:DecisionResult)-[:FOR_SCENARIO]->(:DecisionScenario {id: 'S2'}), (d2)-[:BY_METHOD]->(:ValueFunctionMethod {id: 'M_WSM'}),
      (d2)-[:FOR_ALTERNATIVE]->(alt),
      (d3:DecisionResult)-[:FOR_SCENARIO]->(:DecisionScenario {id: 'S3'}), (d3)-[:BY_METHOD]->(:ValueFunctionMethod {id: 'M_WSM'}),
      (d3)-[:FOR_ALTERNATIVE]->(alt)
RETURN alt.label AS `대안명`, d2.hasRank AS `순위_효율중심`, d3.hasRank AS `순위_성과규모중심`, d2.hasRank - d3.hasRank AS `순위변동`
ORDER BY `순위_효율중심`;

// CQ19. 모든 시나리오에서 상위 5위 내를 유지하는 대안은? (강건 대안, WSM)
MATCH (d:DecisionResult)-[:FOR_SCENARIO]->(s), (d)-[:BY_METHOD]->(:ValueFunctionMethod {id: 'M_WSM'}), (d)-[:FOR_ALTERNATIVE]->(alt)
WHERE d.hasRank <= 5
WITH alt, count(DISTINCT s) AS n, max(d.hasRank) AS worst
WHERE n = 3
RETURN alt.label AS `대안명`, n AS `상위5위_시나리오수`, worst AS `최악순위` ORDER BY `최악순위`, `대안명`;

// CQ20. 시나리오 변경에 순위가 가장 민감하게 반응하는 대안은? (WSM, 상위 10)
MATCH (d:DecisionResult)-[:FOR_SCENARIO]->(s), (d)-[:BY_METHOD]->(:ValueFunctionMethod {id: 'M_WSM'}), (d)-[:FOR_ALTERNATIVE]->(alt)
WITH alt, min(d.hasRank) AS best, max(d.hasRank) AS worst
RETURN alt.label AS `대안명`, best AS `최고순위`, worst AS `최저순위`, worst - best AS `순위폭`
ORDER BY `순위폭` DESC, `대안명` LIMIT 10;

// CQ21. 동일 시나리오(S3)·동일 데이터에서 TOPSIS와 PROMETHEE II의 순위는 일치하는가? (불일치 상위 10)
MATCH (dt:DecisionResult)-[:FOR_SCENARIO]->(:DecisionScenario {id: 'S3'}), (dt)-[:BY_METHOD]->(:DistanceBasedMethod {id: 'M_TOPSIS'}), (dt)-[:FOR_ALTERNATIVE]->(alt),
      (dp:DecisionResult)-[:FOR_SCENARIO]->(:DecisionScenario {id: 'S3'}), (dp)-[:BY_METHOD]->(:OutrankingMethod {id: 'M_PRO2'}), (dp)-[:FOR_ALTERNATIVE]->(alt)
RETURN alt.label AS `대안명`, dt.hasRank AS `TOPSIS순위`, dp.hasRank AS `PROMETHEE순위`, abs(dt.hasRank - dp.hasRank) AS `불일치`
ORDER BY `불일치` DESC, `대안명` LIMIT 10;

// CQ22. 특정 대안(S1/WSM 1위)의 종합점수에 각 기준이 기여한 비율은?
MATCH (cc:CriterionContribution)-[:EXPLAINS]->(dr)-[:FOR_ALTERNATIVE]->(alt:Alternative {id: 'ALT_PRG_a845330b'}),
      (dr)-[:FOR_SCENARIO]->(:DecisionScenario {id: 'S1'}), (dr)-[:BY_METHOD]->(:ValueFunctionMethod {id: 'M_WSM'}),
      (cc)-[:CONTRIBUTION_OF]->(c)
RETURN alt.label AS `대안명`, c.label AS `기준`, cc.hasContributionRatio AS `기여비율` ORDER BY `기여비율` DESC;

// CQ23. 특정 대안의 특정 기준 평가값은 어떤 원천 데이터에서 유래하는가? (평가값→관측치→집계활동→과제연도기록→스냅샷)
MATCH (cv:CriterionValue {id: 'CV_PRG_cf048767_C_SCI'})-[:WAS_DERIVED_FROM]->(ob)-[:IN_FISCAL_YEAR]->(fy),
      (ob)-[:OF_PROGRAM]->(p), (ob)-[:WAS_GENERATED_BY]->(act),
      (pyr:ProjectYearRecord)-[:PART_OF_PROGRAM*1..3]->(p), (pyr)-[:IN_FISCAL_YEAR]->(fy), (pyr)-[:HAD_PRIMARY_SOURCE]->(snap)
RETURN cv.hasRawValue AS `평가값`, fy.yearValue AS `관측연도`, ob.hasObservedValue AS `관측값`, act.label AS `집계활동`,
       count(DISTINCT pyr) AS `원천_과제연도기록수`, snap.label AS `스냅샷`
ORDER BY `관측연도`;

// CQ24. 대안 X가 상위 3위에 진입하려면 어떤 기준이 얼마나 개선되어야 하는가? (반사실)
MATCH (cf:CounterfactualCondition)-[:EXPLAINS]->(dr)-[:FOR_ALTERNATIVE]->(alt), (cf)-[:CONCERNS_CRITERION]->(c)
WHERE cf.requiredNormalizedValue IS NOT NULL   // v0.3.4: 순위 역전 조건(CQ25)은 제외
RETURN alt.label AS `대안명`, c.label AS `기준`, cf.requiredNormalizedValue AS `필요_정규화값`, cf.requiredRawValue AS `필요_원시값`, cf.isFeasible AS `실현가능`
ORDER BY `실현가능` DESC, `필요_정규화값`;

// CQ24-b [보조] 사전계산 없이 3위 점수와의 격차를 질의로 산출 (WSM 한정, 상위 5)
MATCH (d3:DecisionResult {hasRank: 3})-[:FOR_SCENARIO]->(:DecisionScenario {id: 'S1'}), (d3)-[:BY_METHOD]->(:ValueFunctionMethod {id: 'M_WSM'})
WITH d3.hasScore AS target
MATCH (d:DecisionResult)-[:FOR_SCENARIO]->(:DecisionScenario {id: 'S1'}), (d)-[:BY_METHOD]->(:ValueFunctionMethod {id: 'M_WSM'}), (d)-[:FOR_ALTERNATIVE]->(alt)
WHERE d.hasRank > 3
RETURN alt.label AS `대안명`, d.hasScore AS `현재점수`, d.hasRank AS `현재순위`, target AS `목표점수`, target - d.hasScore AS `필요증분`
ORDER BY `필요증분` LIMIT 5;

// CQ25. 두 대안(S1/WSM 1·2위)의 순위 역전을 유발하는 최소 가중치 변화량은? (v0.3.4: 절차적 계산 후 재적재한 결과를 조회)
MATCH (cf:CounterfactualCondition)-[:CONCERNS_CRITERION]->(c), (:DecisionScenario {id: 'S1'})-[:HAS_WEIGHT]->(w)-[:ASSIGNED_TO_CRITERION]->(c)
WHERE cf.requiredWeightValue IS NOT NULL
WITH c, w, cf, cf.requiredWeightValue - w.hasWeightValue AS delta
RETURN c.label AS `기준`, w.hasWeightValue AS `현재_가중치`, cf.requiredWeightValue AS `필요_가중치`, delta AS `변화량`, cf.isFeasible AS `실현가능`
ORDER BY `실현가능` DESC, abs(delta);

// CQ26. 부처 개편(미래창조과학부→과학기술정보통신부)을 고려하면 같은 소관 계보의 연도별 과제연도기록 수는?
MATCH (target:Ministry {id: 'ORG_MIN_891684ea'})
OPTIONAL MATCH (r:MinistryReorganization)-[:RESULTING_ORGANIZATION]->(target), (r)-[:ORIGINAL_ORGANIZATION]->(orig)
WITH target, [x IN collect(DISTINCT orig) WHERE x IS NOT NULL] + target AS mins
UNWIND mins AS m
MATCH (pyr:ProjectYearRecord)-[:FUNDED_BY]->(m), (pyr)-[:IN_FISCAL_YEAR]->(fy)
WHERE fy.yearValue >= 2015 AND fy.yearValue <= 2024
WITH fy.yearValue AS y, pyr, m ORDER BY m.label
WITH y, count(DISTINCT pyr) AS n, collect(DISTINCT m.label) AS ms
RETURN y AS `연도`, n AS `과제연도기록수`, reduce(s = '', x IN ms | CASE s WHEN '' THEN x ELSE s + ' / ' + x END) AS `기재된_부처명` ORDER BY `연도`;

// CQ27. 특정 사업의 과제들이 1순위로 배정된 표준분류 중분류 분포와 그 분류의 판(edition)은? (상위 8)
MATCH (pyr:ProjectYearRecord)-[:PART_OF_PROGRAM*1..3]->(:RnDProgram {id: 'PRG_a845330b'}),
      (fa:FieldAssignment {assignmentRank: 1})-[:ASSIGNMENT_OF]->(pyr), (fa)-[:ASSIGNED_FIELD]->(s)-[:BROADER]->(m), (s)-[:IN_SCHEME]->(ed)
RETURN m.label AS `중분류`, ed.label AS `판`, count(DISTINCT pyr) AS `과제연도기록수` ORDER BY `과제연도기록수` DESC LIMIT 8;

// CQ28. 연속과제 연결(precededBy)로 가장 길게 이어지는 과제 사슬은? (상위 5)
MATCH (last:ProjectYearRecord)-[:IN_FISCAL_YEAR]->(fy)
WHERE NOT ()-[:PRECEDED_BY]->(last) AND (last)-[:PRECEDED_BY]->()
MATCH (last)-[:PRECEDED_BY*1..]->(prev)
WITH last, fy, count(DISTINCT prev) AS len
RETURN last.label AS `과제명`, last.ntisProjectId AS `마지막_과제고유번호`, fy.yearValue AS `마지막연도`, len AS `사슬길이`
ORDER BY `사슬길이` DESC, `마지막_과제고유번호` LIMIT 5;

// CQ29. 한 성과물이 복수의 과제연도기록에 귀속된 사례가 있는가? (사업 집계 시 중복 제거 근거)
CALL { MATCH (att:OutputAttribution)-[:ATTRIBUTED_OUTPUT]->(out) WITH out, count(att) AS n WHERE n >= 2 RETURN count(out) AS multi }
CALL { MATCH (o:ResearchOutput) RETURN count(o) AS total }
RETURN multi AS `복수귀속_성과물수`, total AS `전체_성과물수`;

// CQ30. 별칭 병합으로 하나의 사업에 묶인 원천 사업명 표기는 몇 가지이며, 표기별 과제연도기록 수는?
MATCH (p:RnDProgram {id: 'PRG_cf048767'})
MATCH (pyr:ProjectYearRecord)-[:PART_OF_PROGRAM*1..3]->(p), (pyr)-[:IN_FISCAL_YEAR]->(fy)
WITH p, pyr.recordedProgramName AS name, count(DISTINCT pyr) AS n, min(fy.yearValue) AS y0, max(fy.yearValue) AS y1
RETURN p.label AS `사업명`, name AS `원천표기`, n AS `과제연도기록수`, y0 AS `첫연도`, y1 AS `끝연도` ORDER BY `첫연도`;
