#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""평가 창 지표 → MCDM 표현 계층 인스턴스 (실데이터, 온톨로지 v0.3).

입력  data/interim/ntis/indicators/window_main_2021_2023.csv (주 평가 창, 41개 사업 중 included=Y 32개)
      data/interim/ntis/candidates_2023.csv (사업 → ex:PRG_ IRI 복원용)
출력  data/rdf/nrdp-mcdm.ttl        의사결정문제·대안·기준·지표·평가값·정규화값·시나리오·가중치·기법·평가결과·설명·평가 활동
      data/rdf/mcdm_results.csv     시나리오×기법×대안 점수·순위 (검토용)

설계
  - 대안 41개 = 선정 세부사업 전부. 평가값(CriterionValue)은 평가 창 안에 존속 연도가 있는 사업만 갖고,
    연구비 증감률(C_CAGR)은 창 안 2개 연도 이상에 연구비가 있을 때만 존재 → 결측은 CQ12·CQ13 이 탐지한다.
  - 완전평가 대안(FULL) = 8개 리프 기준 전부에 값이 있는 사업. 정규화·순위는 FULL 안에서만 계산한다.
  - 기법: WSM(min-max), TOPSIS(벡터), PROMETHEE II(V-shape, q=0, p=0.5). gen_data.py 의 계산식과 동일.
  - 출처: CriterionValue → prov:wasDerivedFrom → 창 안 연도의 IndicatorObservation / BudgetAllocation (ntis_to_rdf.py 가 만든 개체).
실행: python pipeline/mcdm_eval.py [프로젝트 루트]
"""
import os, sys, re, csv, math, json, hashlib, datetime
from collections import OrderedDict

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NT = os.path.join(ROOT, "data", "interim", "ntis")
OUT = os.path.join(ROOT, "data", "rdf")
WINDOW = ("window_main_2021_2023.csv", 2021, 2023)

def rd(p): return list(csv.DictReader(open(p, encoding="utf-8-sig")))
def nospace(s): return re.sub(r"\s", "", s or "")
def h8(s): return hashlib.sha1(nospace(s).encode("utf-8")).hexdigest()[:8]
def lit(s, lang=None):
    s = str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"' + (f"@{lang}" if lang else "")
def dec(v, nd=6): return f'"{round(float(v), nd)}"^^xsd:decimal'
def num(s):
    try: return float(s)
    except (TypeError, ValueError): return None

rows = rd(os.path.join(NT, "indicators", WINDOW[0]))
cand = {r["program_name"]: r for r in rd(os.path.join(NT, "candidates_2023.csv")) if r.get("selected", "").upper() == "Y"}
PRG = OrderedDict((r["canonical_program"], f"PRG_{h8(r['canonical_program'])}") for r in rows if r["canonical_program"] in cand)
W = {r["canonical_program"]: r for r in rows}

# ───────── 기준 (리프 8 · 상위 3) ─────────
# id: (라벨, 방향, 척도, 지표 id, 지표 라벨, 단위, window 열, 상위기준, 연간 관측치 지표 접미사 or 'BA')
CRITERIA = OrderedDict([
    ("C_INPUT",     ("투입 규모·추세", None, None, None, None, None, None, None, None)),
    ("C_FUND",      ("연평균 정부연구비", "Cost", "RatioScale", "IND_W_FUND", "연평균 정부연구비(평가 창)", "억원", "avg_gov_funds_100m", "C_INPUT", "BA")),
    ("C_CAGR",      ("연구비 연평균 증감률", "Benefit", "RatioScale", "IND_W_CAGR", "정부연구비 연평균 증감률(창 안 첫·끝 연도)", "비율", "funds_cagr", "C_INPUT", "BA")),
    ("C_OUTPUT",    ("성과 규모", None, None, None, None, None, None, None, None)),
    ("C_SCI",       ("SCI 논문 연평균", "Benefit", "RatioScale", "IND_W_SCI", "SCI 논문 수 연평균(시차 1년)", "건", "avg_sci_papers", "C_OUTPUT", "SCI")),
    ("C_PAT",       ("특허 연평균", "Benefit", "RatioScale", "IND_W_PAT", "특허 출원·등록 수 연평균(시차 1년)", "건", "avg_patents", "C_OUTPUT", "PATENT")),
    ("C_PATREG",    ("등록특허 연평균", "Benefit", "RatioScale", "IND_W_PATREG", "특허 등록 수 연평균(시차 1년)", "건", "avg_patent_registered", "C_OUTPUT", "PATREG")),
    ("C_EFF",       ("투자 효율", None, None, None, None, None, None, None, None)),
    ("C_SCI_EFF",   ("연구비 1억원당 SCI 논문", "Benefit", "RatioScale", "IND_W_SCI_EFF", "창 합계 SCI 논문 / 창 합계 정부연구비(억원)", "건/억원", "sci_per_100m", "C_EFF", "SCI")),
    ("C_PAT_EFF",   ("연구비 1억원당 특허", "Benefit", "RatioScale", "IND_W_PAT_EFF", "창 합계 특허 / 창 합계 정부연구비(억원)", "건/억원", "patents_per_100m", "C_EFF", "PATENT")),
    ("C_CONT",      ("계속과제 비율", "Benefit", "RatioScale", "IND_W_CONT", "계속과제 수 / 과제 수(창 합계)", "비율", "continuing_ratio", None, "CONT")),
])
LEAVES = [c for c, v in CRITERIA.items() if v[1]]
DIRECTION = {c: CRITERIA[c][1] for c in LEAVES}

SCENARIOS = OrderedDict([
    ("S1", ("균형형", "8개 리프 기준 균등 가중", {c: 0.125 for c in LEAVES})),
    ("S2", ("효율중심", "연구비당 성과와 투입 규모 관리를 우선",
            {"C_FUND": 0.20, "C_CAGR": 0.05, "C_SCI": 0.05, "C_PAT": 0.05, "C_PATREG": 0.05, "C_SCI_EFF": 0.25, "C_PAT_EFF": 0.25, "C_CONT": 0.10})),
    ("S3", ("성과규모중심", "절대 성과 규모와 투자 확대 추세를 우선",
            {"C_FUND": 0.05, "C_CAGR": 0.15, "C_SCI": 0.20, "C_PAT": 0.20, "C_PATREG": 0.20, "C_SCI_EFF": 0.05, "C_PAT_EFF": 0.05, "C_CONT": 0.10})),
])
for sid, (_, _, w) in SCENARIOS.items():
    assert abs(sum(w.values()) - 1) < 1e-9, sid

# ───────── 평가값 ─────────
RAW = {c: {} for c in LEAVES}
for name, pid in PRG.items():
    r = W[name]
    for c in LEAVES:
        v = num(r.get(CRITERIA[c][6]))
        if v is not None:
            RAW[c][pid] = v
FULL = [pid for pid in PRG.values() if all(pid in RAW[c] for c in LEAVES)]

def normalize_minmax(vals, direction):
    lo, hi = min(vals.values()), max(vals.values())
    return {k: (1.0 if hi == lo else ((v - lo) / (hi - lo) if direction == "Benefit" else (hi - v) / (hi - lo))) for k, v in vals.items()}
def normalize_vector(vals, direction):
    d = math.sqrt(sum(v * v for v in vals.values()))
    out = {k: (v / d if d else 0.0) for k, v in vals.items()}
    return {k: 1.0 - v for k, v in out.items()} if direction == "Cost" else out
NORM_MINMAX = {c: normalize_minmax({p: RAW[c][p] for p in FULL}, DIRECTION[c]) for c in LEAVES}
NORM_VECTOR = {c: normalize_vector({p: RAW[c][p] for p in FULL}, DIRECTION[c]) for c in LEAVES}

def wsm(w): return {p: sum(w[c] * NORM_MINMAX[c][p] for c in LEAVES) for p in FULL}
def topsis(w):
    wv = {c: {p: w[c] * NORM_VECTOR[c][p] for p in FULL} for c in LEAVES}
    best = {c: max(wv[c].values()) for c in LEAVES}; worst = {c: min(wv[c].values()) for c in LEAVES}
    out = {}
    for p in FULL:
        dp = math.sqrt(sum((wv[c][p] - best[c]) ** 2 for c in LEAVES)); dn = math.sqrt(sum((wv[c][p] - worst[c]) ** 2 for c in LEAVES))
        out[p] = dn / (dp + dn) if (dp + dn) else 0.0
    return out
PREF_Q, PREF_P = 0.0, 0.5
def promethee2(w):
    def pref(c, a, b):
        d = NORM_MINMAX[c][a] - NORM_MINMAX[c][b]
        return 0.0 if d <= PREF_Q else (1.0 if d >= PREF_P else (d - PREF_Q) / (PREF_P - PREF_Q))
    n = len(FULL); phi = {}
    for a in FULL:
        plus = sum(sum(w[c] * pref(c, a, b) for c in LEAVES) for b in FULL if b != a)
        minus = sum(sum(w[c] * pref(c, b, a) for c in LEAVES) for b in FULL if b != a)
        phi[a] = (plus - minus) / (n - 1)
    return phi
METHODS = OrderedDict([
    ("M_WSM",    ("가중합법(WSM)", "ValueFunctionMethod", "FullCompensation", True, True, "NM_MinMax", wsm)),
    ("M_TOPSIS", ("TOPSIS", "DistanceBasedMethod", "FullCompensation", True, False, "NM_Vector", topsis)),
    ("M_PRO2",   ("PROMETHEE II", "OutrankingMethod", "PartialCompensation", True, True, "NM_MinMax", promethee2)),
])
def ranked(scores):
    order = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return {p: i + 1 for i, (p, _) in enumerate(order)}
RESULTS = {}
for sid, (_, _, w) in SCENARIOS.items():
    for mid, (*_x, fn) in METHODS.items():
        sc = fn(w); rk = ranked(sc)
        RESULTS[(sid, mid)] = {p: (sc[p], rk[p]) for p in FULL}

def counterfactuals(sid="S1", mid="M_WSM", target_rank=3):
    w = SCENARIOS[sid][2]; res = RESULTS[(sid, mid)]
    ordered = sorted(res.items(), key=lambda kv: kv[1][1])
    third = ordered[target_rank - 1][1][0]
    cands = [p for p, (s, r) in res.items() if r == target_rank + 1]
    if not cands: return []
    tgt = cands[0]; gap = third - res[tgt][0]; out = []
    for c in LEAVES:
        need = NORM_MINMAX[c][tgt] + gap / w[c]
        vals = {p: RAW[c][p] for p in FULL}; lo, hi = min(vals.values()), max(vals.values())
        cl = min(need, 1.0)
        raw = lo + cl * (hi - lo) if DIRECTION[c] == "Benefit" else hi - cl * (hi - lo)
        out.append((tgt, c, round(gap, 6), round(need, 4), round(raw, 4), need <= 1.0))
    return out
CF = counterfactuals()

def reversal_conditions(sid="S1", mid="M_WSM"):
    """CQ25 (v0.3.4, 2026-10-23): 1위 A 와 2위 B 의 순위를 뒤집는 단일 기준 가중치 조정.
    기준 k 의 가중치를 w_k + Δ 로 바꾸고 나머지는 합 1 을 유지하도록 비례 재조정할 때
      d_i = r_Ai − r_Bi, D = Σ w_i d_i, R = D − w_k d_k,
      D'(Δ) = D + Δ·(d_k − R/(1 − w_k))  →  Δ*_k = −D / (d_k − R/(1 − w_k))      (본문 식 (1)·(2))
    분모가 0 이면 조정으로 역전되지 않으므로 실현 불가. 0 ≤ w_k + Δ* ≤ 1 이어야 실현 가능."""
    w = SCENARIOS[sid][2]; res = RESULTS[(sid, mid)]
    A = next(p for p, (s, r) in res.items() if r == 1); B = next(p for p, (s, r) in res.items() if r == 2)
    d = {c: NORM_MINMAX[c][A] - NORM_MINMAX[c][B] for c in LEAVES}
    D = sum(w[c] * d[c] for c in LEAVES); out = []
    for k in LEAVES:
        R = D - w[k] * d[k]; den = d[k] - R / (1 - w[k])
        if abs(den) < 1e-12:
            out.append((A, B, k, None, False)); continue
        delta = -D / den; nw = w[k] + delta; feas = 0.0 <= nw <= 1.0
        if feas:   # 검산: 조정된 가중치로 두 대안의 WSM 점수가 같아져야 한다
            w2 = {c: (nw if c == k else w[c] * (1 - nw) / (1 - w[k])) for c in LEAVES}
            assert abs(sum(w2.values()) - 1) < 1e-9
            assert abs(sum(w2[c] * d[c] for c in LEAVES)) < 1e-9, (k, delta)
        out.append((A, B, k, nw, feas))
    return out
CF25 = reversal_conditions()

# ───────── TTL ─────────
L = []
w = L.append
w("""@prefix nrdp:    <https://w3id.org/nrdp/ontology#> .
@prefix mcdm:    <https://w3id.org/nrdp/mcdm#> .
@prefix ex:      <https://w3id.org/nrdp/data#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .
@prefix prov:    <http://www.w3.org/ns/prov#> .
@prefix dcterms: <http://purl.org/dc/terms/> .""")
w(f"# MCDM 표현 계층 인스턴스 (NTIS 실데이터, 주 평가 창 {WINDOW[1]}–{WINDOW[2]}). 생성: pipeline/mcdm_eval.py, {datetime.datetime.now().isoformat(timespec='seconds')}")
w("")
w("### 의사결정문제 / 대안")
w(f'ex:DP_MAIN a mcdm:DecisionProblem ; rdfs:label "국가전략기술 3개 분야(반도체·디스플레이, 첨단바이오, 인공지능) 세부사업 포트폴리오 평가 — 주 평가 창 {WINDOW[1]}–{WINDOW[2]}"@ko ;')
w(f'    nrdp:assessmentStartYear "{WINDOW[1]}"^^xsd:integer ; nrdp:assessmentEndYear "{WINDOW[2]}"^^xsd:integer ;')
w('    rdfs:comment "대안 41개(선정 세부사업 전부). 창 안 2개 연도 이상 존속한 사업만 완전평가 대상이며, 나머지는 평가값 결측으로 남긴다."@ko ;')
w("    mcdm:hasAlternative " + ", ".join(f"ex:ALT_{p}" for p in PRG.values()) + " ;")
w("    mcdm:hasCriterion " + ", ".join(f"ex:{c}" for c in CRITERIA) + " .")
for name, pid in PRG.items():
    w(f'ex:ALT_{pid} a mcdm:Alternative ; rdfs:label {lit(name, "ko")} ; mcdm:inProblem ex:DP_MAIN ; mcdm:representsEntity ex:{pid} .')
w("")
w("### 평가 창 지표 (PerformanceIndicator, 창 단위 파생)")
for c in LEAVES:
    lb, d, sc, iid, ilb, unit, col, parent, obs = CRITERIA[c]
    w(f'ex:{iid} a nrdp:PerformanceIndicator ; rdfs:label {lit(ilb, "ko")} ; nrdp:indicatorUnit {lit(unit)} ; '
      f'rdfs:comment {lit("ntis_rollup.py window() 열 " + col + " (규칙 R7)", "ko")} .')
w("")
w("### 평가기준")
for c, (lb, d, sc, iid, ilb, unit, col, parent, obs) in CRITERIA.items():
    if d:
        w(f'ex:{c} a mcdm:LeafCriterion , mcdm:{d}Criterion ; rdfs:label {lit(lb, "ko")} ; mcdm:hasDirection mcdm:{d} ; '
          f'mcdm:hasScale mcdm:{sc} ; mcdm:measuredBy ex:{iid} .')
    else:
        w(f'ex:{c} a mcdm:CompositeCriterion ; rdfs:label {lit(lb, "ko")} .')
for c, v in CRITERIA.items():
    if v[7]:
        w(f"ex:{v[7]} mcdm:hasSubCriterion ex:{c} .")
w("")
w("### 정규화방법 / 선호함수 / 집계기법 / 정규화 활동")
w('ex:NM_MinMax a mcdm:NormalizationMethod ; rdfs:label "min-max 정규화"@ko ; mcdm:normalizedLowerBound "0"^^xsd:decimal ; mcdm:normalizedUpperBound "1"^^xsd:decimal .')  # v0.3.2 (2026-10-19, 논문 세션): 허용 범위, SHACL M6. 벡터 정규화는 원시값 부호에 따라 범위가 달라 경계 없음
w('ex:NM_Vector a mcdm:NormalizationMethod ; rdfs:label "벡터 정규화"@ko .')
w(f'ex:PF_VShape a mcdm:PreferenceFunction ; rdfs:label "V-shape 선호함수"@ko ; mcdm:preferenceThresholdQ {dec(PREF_Q)} ; mcdm:preferenceThresholdP {dec(PREF_P)} .')
w('ex:ACT_NORM_MinMax a mcdm:NormalizationActivity ; rdfs:label "min-max 정규화 수행 (완전평가 대안 집합 기준)"@ko ; prov:used ex:NM_MinMax .')
w('ex:ACT_NORM_Vector a mcdm:NormalizationActivity ; rdfs:label "벡터 정규화 수행 (완전평가 대안 집합 기준)"@ko ; prov:used ex:NM_Vector .')
for mid, (lb, cls, comp, rn, add, nm, _f) in METHODS.items():
    extra = " ; mcdm:usesPreferenceFunction ex:PF_VShape" if mid == "M_PRO2" else ""
    w(f'ex:{mid} a mcdm:{cls} ; rdfs:label {lit(lb, "ko")} ; mcdm:hasCompensationLevel mcdm:{comp} ; '
      f'mcdm:requiresNormalization "{str(rn).lower()}"^^xsd:boolean ; mcdm:supportsAdditiveDecomposition "{str(add).lower()}"^^xsd:boolean ; '
      f'mcdm:usesNormalization ex:{nm}{extra} .')
w("")
w("### 평가값 (CriterionValue) — 출처: 창 안 연도의 성과관측치/예산배분")
def active_years(name):
    r = W[name]
    return list(range(int(r["first_active"]), int(r["last_active"]) + 1)) if r.get("first_active") else []
n_cv = 0
for name, pid in PRG.items():
    yrs = active_years(name)
    for c in LEAVES:
        if pid not in RAW[c]: continue
        n_cv += 1
        obs = CRITERIA[c][8]
        src = [f"ex:BA_{pid}_{y}" if obs == "BA" else f"ex:OB_{pid}_{obs}_{y}" for y in yrs]
        extra = (" ; prov:wasDerivedFrom " + ", ".join(src)) if src else ""
        w(f'ex:CV_{pid}_{c} a mcdm:CriterionValue ; mcdm:ofAlternative ex:ALT_{pid} ; mcdm:onCriterion ex:{c} ; '
          f'mcdm:hasRawValue {dec(RAW[c][pid])} ; mcdm:hasUnit {lit(CRITERIA[c][5])} ; prov:wasGeneratedBy ex:ACT_ROLLUP{extra} .')
w("")
w("### 정규화값 (NormalizedValue) — 완전평가 대안만")
for pid in FULL:
    for c in LEAVES:
        for suf, nm, tb in (("MinMax", "NM_MinMax", NORM_MINMAX), ("Vector", "NM_Vector", NORM_VECTOR)):
            w(f'ex:NV_{pid}_{c}_{suf} a mcdm:NormalizedValue ; mcdm:ofCriterionValue ex:CV_{pid}_{c} ; mcdm:normalizedBy ex:{nm} ; '
              f'mcdm:hasValue {dec(tb[c][pid])} ; prov:wasGeneratedBy ex:ACT_NORM_{suf} .')
        w(f'ex:CV_{pid}_{c} mcdm:hasNormalization ex:NV_{pid}_{c}_MinMax , ex:NV_{pid}_{c}_Vector .')
w("")
w("### 시나리오 / 가중치")
for sid, (lb, desc, wt) in SCENARIOS.items():
    w(f'ex:{sid} a mcdm:DecisionScenario ; rdfs:label {lit(lb, "ko")} ; mcdm:scenarioLabel {lit(desc)} ; '
      f'mcdm:reflectsPolicyObjective ex:NST_010000 , ex:NST_050000 , ex:NST_090000 ; mcdm:hasWeight ' + ", ".join(f"ex:W_{sid}_{c}" for c in wt) + " .")
    for c, v in wt.items():
        w(f'ex:W_{sid}_{c} a mcdm:Weight ; mcdm:assignedToCriterion ex:{c} ; mcdm:hasWeightValue {dec(v)} .')
w("")
w(f"### 평가 실행 / 평가결과 (시나리오 {len(SCENARIOS)} × 기법 {len(METHODS)} × 완전평가 대안 {len(FULL)} = {len(RESULTS)*len(FULL)}건)")
for (sid, mid), res in RESULTS.items():
    w(f'ex:ACT_EVAL_{sid}_{mid} a mcdm:EvaluationActivity ; rdfs:label {lit(SCENARIOS[sid][0] + " × " + METHODS[mid][0], "ko")} ; prov:used ex:{sid} , ex:{mid} .')
    for pid, (sc, rk) in res.items():
        w(f'ex:DR_{sid}_{mid}_{pid} a mcdm:DecisionResult ; mcdm:forProblem ex:DP_MAIN ; mcdm:forScenario ex:{sid} ; mcdm:byMethod ex:{mid} ; '
          f'mcdm:forAlternative ex:ALT_{pid} ; mcdm:hasScore {dec(sc)} ; mcdm:hasRank "{rk}"^^xsd:integer ; prov:wasGeneratedBy ex:ACT_EVAL_{sid}_{mid} .')
w("")
w("### 기준별 기여도 (S1/WSM, 가법 분해 가능 기법)")
W1 = SCENARIOS["S1"][2]
for pid in FULL:
    total = sum(W1[c] * NORM_MINMAX[c][pid] for c in LEAVES)
    for c in LEAVES:
        ratio = (W1[c] * NORM_MINMAX[c][pid]) / total if total else 0.0
        # v0.3.4: 기여값(w_j·r_ij) 추가 — 기여값 합 = WSM 점수 (SHACL M7)
        w(f'ex:CC_S1_WSM_{pid}_{c} a mcdm:CriterionContribution ; mcdm:explains ex:DR_S1_M_WSM_{pid} ; mcdm:contributionOf ex:{c} ; mcdm:hasContributionRatio {dec(ratio, 4)} ; mcdm:hasContributionValue {dec(W1[c] * NORM_MINMAX[c][pid], 8)} .')
w("")
# v0.3.4 (2026-10-23): PROMETHEE II 순흐름의 기준별 분해 φ(a) = Σ_j w_j·φ_j(a), φ_j(a) = Σ_{b≠a}[P_j(a,b) − P_j(b,a)]/(n−1).
#   순흐름은 0 이하일 수 있어 기여비율 대신 기여값만 기록한다. analysis/promethee_phi.py 의 그래프 조회 기반 계산과 같은 식.
w("### 기준별 기여도 (S1~S3/PROMETHEE II, 단일기준 순흐름 분해 — 기여값만)")
def phi_j(c, a):
    def pref(x, y):
        d = NORM_MINMAX[c][x] - NORM_MINMAX[c][y]
        return 0.0 if d <= PREF_Q else (1.0 if d >= PREF_P else (d - PREF_Q) / (PREF_P - PREF_Q))
    return sum(pref(a, b) - pref(b, a) for b in FULL if b != a) / (len(FULL) - 1)
n_cc_pro = 0
for sid, (_, _, wt) in SCENARIOS.items():
    for pid in FULL:
        parts = {c: wt[c] * phi_j(c, pid) for c in LEAVES}
        assert abs(sum(parts.values()) - RESULTS[(sid, "M_PRO2")][pid][0]) < 1e-9, (sid, pid)
        for c in LEAVES:
            n_cc_pro += 1
            w(f'ex:CC_{sid}_PRO2_{pid}_{c} a mcdm:CriterionContribution ; mcdm:explains ex:DR_{sid}_M_PRO2_{pid} ; mcdm:contributionOf ex:{c} ; mcdm:hasContributionValue {dec(parts[c], 8)} .')
w("")
w("### 반사실 조건 (S1/WSM 에서 4위 대안의 3위 진입 요건)")
for tgt, c, gap, need, raw, fe in CF:
    w(f'ex:CF_{tgt}_{c} a mcdm:CounterfactualCondition ; mcdm:explains ex:DR_S1_M_WSM_{tgt} ; mcdm:concernsCriterion ex:{c} ; '
      f'rdfs:label {lit(CRITERIA[c][0] + " 단독 개선으로 3위 진입", "ko")} ; mcdm:requiredNormalizedValue {dec(need, 4)} ; '
      f'mcdm:requiredRawValue {dec(raw, 4)} ; mcdm:isFeasible "{str(fe).lower()}"^^xsd:boolean .')
w("")
w("### 순위 역전 조건 (CQ25, v0.3.4: S1/WSM 1·2위의 순위를 뒤집는 단일 기준 가중치 — 나머지는 비례 재조정)")
inv0 = {pid: name for name, pid in PRG.items()}
for A, B, k, nw, fe in CF25:
    val = f" ; mcdm:requiredWeightValue {dec(nw, 6)}" if nw is not None else ""
    w(f'ex:CF25_{A}_{B}_{k} a mcdm:CounterfactualCondition ; mcdm:explains ex:DR_S1_M_WSM_{A} , ex:DR_S1_M_WSM_{B} ; mcdm:concernsCriterion ex:{k} ; '
      f'rdfs:label {lit(CRITERIA[k][0] + " 가중치 조정으로 " + inv0[B] + "–" + inv0[A] + " 순위 역전", "ko")}{val} ; mcdm:isFeasible "{str(fe).lower()}"^^xsd:boolean .')
w("")
open(os.path.join(OUT, "nrdp-mcdm.ttl"), "w", encoding="utf-8").write("\n".join(L) + "\n")

# ───────── CSV / 요약 ─────────
inv = {pid: name for name, pid in PRG.items()}
with open(os.path.join(OUT, "mcdm_results.csv"), "w", newline="", encoding="utf-8-sig") as f:
    cw = csv.writer(f); cw.writerow(["scenario", "method", "program_id", "program", "field", "score", "rank"])
    for (sid, mid), res in RESULTS.items():
        for pid, (sc, rk) in sorted(res.items(), key=lambda kv: kv[1][1]):
            cw.writerow([sid, mid, pid, inv[pid], cand[inv[pid]]["field_name"], round(sc, 6), rk])
print(f"대안 {len(PRG)} / 완전평가 {len(FULL)} / 평가값 {n_cv} / 결과 {len(RESULTS)*len(FULL)} / PROMETHEE II 기여 분해 {n_cc_pro}")
for c in LEAVES:
    missing = [inv[p] for p in PRG.values() if p not in RAW[c]]
    print(f"  {c:10s} 결측 {len(missing):2d}" + (f"  예: {missing[0]}" if missing else ""))
for sid in SCENARIOS:
    for mid in METHODS:
        top = sorted(RESULTS[(sid, mid)].items(), key=lambda kv: kv[1][1])[:3]
        print(f"{sid}/{mid:8s}: " + " | ".join(f"{r}위 {inv[p]}" for p, (s, r) in top))
for tgt, c, gap, need, raw, fe in CF:
    print(f"  반사실 {inv[tgt]} / {c}: 필요 정규화값 {need} (원시 {raw}) 실현가능={fe}")
for A, B, k, nw, fe in CF25:
    cur = SCENARIOS["S1"][2][k]
    print(f"  역전 {inv[B]}↔{inv[A]} / {k}: 필요 가중치 {None if nw is None else round(nw, 4)} (현재 {cur}, 변화 {None if nw is None else round(nw - cur, 4)}) 실현가능={fe}")
