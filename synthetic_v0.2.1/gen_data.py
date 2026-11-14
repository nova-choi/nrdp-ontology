#!/usr/bin/env python3
"""샘플 인스턴스 데이터 생성기.
WSM / TOPSIS / PROMETHEE II 를 실제로 계산하여 DecisionResult 를 만든다.
따라서 CQ18~21(시나리오·기법 간 순위 비교)이 실제 수치로 검증된다.
"""
import math
from collections import OrderedDict

# ---------------- 기술분야 / 부처 / 정책목표 ----------------
FIELDS = {
    "TF_AI":   ("인공지능", "EF01"),
    "TF_SEMI": ("반도체·디스플레이", "EF02"),
    "TF_BIO":  ("첨단바이오", "EF03"),
}
MINISTRIES = {"MIN_MSIT": "과학기술정보통신부", "MIN_MOTIE": "산업통상자원부"}
AGENCIES = {"AG_IITP": "정보통신기획평가원", "AG_KEIT": "한국산업기술평가관리원"}
PERFORMERS = {
    "OR_KAIST": "한국과학기술원", "OR_ETRI": "한국전자통신연구원",
    "OR_SNU": "서울대학교", "OR_KRIBB": "한국생명공학연구원",
    "OR_SKKU": "성균관대학교",
}
# 세부사업 → 사업, 과제 → 세부사업 (partOfProgram 추이성 검증용)
SUBPROGRAMS = {"SP01": ("AI원천기술", "P01"), "SP02": ("AI응용실증", "P01"),
               "SP03": ("합성생물학플랫폼", "P05")}
PROJECTS = {
    "PJ01": ("초거대모델경량화", "SP01", ["OR_KAIST", "OR_ETRI"]),
    "PJ02": ("멀티모달추론기술", "SP01", ["OR_SNU"]),
    "PJ03": ("제조AI실증",       "SP02", ["OR_ETRI", "OR_SKKU"]),
    "PJ04": ("유전자회로설계",   "SP03", ["OR_KRIBB"]),
    "PJ05": ("바이오파운드리",   "SP03", ["OR_KRIBB", "OR_SNU"]),
}
GOALS = {
    "PG_TECH": "기술주권 확보",
    "PG_GROWTH": "혁신성장 견인",
    "PG_SOCIAL": "사회문제 해결",
}

# ---------------- 사업 (9개: 8개 완전평가 + 1개 불완전) ----------------
# code, 명칭, 부처, 전문기관, 기술분야, 정책목표들
PROGRAMS = OrderedDict([
    ("P01", ("차세대AI핵심기술개발", "MIN_MSIT",  "AG_IITP", "TF_AI",   ["PG_TECH", "PG_GROWTH"])),
    ("P02", ("AI반도체첨단공정실증", "MIN_MSIT",  "AG_IITP", "TF_SEMI", ["PG_TECH"])),
    ("P03", ("산업용AI융합확산",     "MIN_MOTIE", "AG_KEIT", "TF_AI",   ["PG_GROWTH"])),
    ("P04", ("차세대반도체소재부품",  "MIN_MOTIE", "AG_KEIT", "TF_SEMI", ["PG_TECH", "PG_GROWTH"])),
    ("P05", ("합성생물학기반구축",    "MIN_MSIT",  "AG_IITP", "TF_BIO",  ["PG_TECH", "PG_SOCIAL"])),
    ("P06", ("디지털치료기기개발",    "MIN_MSIT",  "AG_IITP", "TF_BIO",  ["PG_SOCIAL"])),
    ("P07", ("첨단바이오제조혁신",    "MIN_MOTIE", "AG_KEIT", "TF_BIO",  ["PG_GROWTH"])),
    ("P08", ("공공AI서비스고도화",    "MIN_MSIT",  "AG_IITP", "TF_AI",   [])),          # CQ5: 정책목표 미연결
    ("P09", ("차세대통신핵심기술",    "MIN_MSIT",  "AG_IITP", "TF_SEMI", ["PG_TECH"])),  # 불완전 평가
])

# ---------------- 예산 (백만원) 2021~2023 ----------------
BUDGET = {
    "P01": [48000, 61000, 78000],
    "P02": [32000, 41000, 55000],
    "P03": [21000, 24000, 26000],
    "P04": [67000, 72000, 76000],
    "P05": [15000, 23000, 34000],
    "P06": [9000, 12000, 14000],
    "P07": [28000, 31000, 37000],
    "P08": [18000, 22000, 19000],
    "P09": [40000, 52000, 64000],
}
# 성과: 논문수 / 특허출원수  (CQ7: P04 는 예산 증가 후 감소 → 예산↑성과↓ 사례)
PAPERS = {
    "P01": [120, 155, 190], "P02": [64, 78, 96],  "P03": [38, 41, 45],
    "P04": [210, 198, 176], "P05": [45, 71, 104], "P06": [22, 31, 40],
    "P07": [80, 88, 97],    "P08": [30, 34, 31],  "P09": [95, 118, 141],
}
PATENTS = {
    "P01": [45, 62, 81],  "P02": [28, 37, 49],  "P03": [12, 14, 17],
    "P04": [88, 81, 70],  "P05": [16, 27, 42],  "P06": [7, 11, 15],
    "P07": [33, 38, 44],  "P08": [9, 11, 10],   "P09": [40, 51, 63],
}

# ---------------- 평가기준 ----------------
# 최상위: C1 투자효율성, C2 혁신역량(하위 2개), C3 사회적파급, C4 예산규모, C5 수행위험
# 리프 기준 6개만 평가값을 가짐
CRITERIA = OrderedDict([
    ("C1",  ("투자효율성",   "Benefit", "RatioScale",   "IND_EFF",   "건/십억원", None)),
    ("C2",  ("혁신역량",     None,      None,           None,        None,        None)),
    ("C2a", ("특허창출규모", "Benefit", "RatioScale",   "IND_PAT",   "건",         "C2")),
    ("C2b", ("기술이전율",   "Benefit", "RatioScale",   "IND_TT",    "%",         "C2")),
    ("C3",  ("사회적파급효과", "Benefit", "IntervalScale", "IND_SOC", "점",        None)),
    ("C4",  ("예산규모",     "Cost",    "RatioScale",   "IND_BUD",   "백만원",    None)),
    ("C5",  ("수행위험도",   "Cost",    "IntervalScale", "IND_RISK", "점",        None)),
])
LEAVES = ["C1", "C2a", "C2b", "C3", "C4", "C5"]

INDICATORS = {
    "IND_EFF":  ("논문건수당투자효율", "건/십억원"),
    "IND_PAT":  ("특허출원건수",       "건"),
    "IND_TT":   ("기술이전성공률",     "%"),
    "IND_SOC":  ("사회적파급효과평점", "점"),
    "IND_BUD":  ("당해연도예산액",     "백만원"),
    "IND_RISK": ("수행위험도평점",     "점"),
}

# ---------------- 평가값 (2023 기준) ----------------
def eff(p):  return round(PAPERS[p][2] / (BUDGET[p][2] / 1000.0), 2)
def pat(p):  return float(PATENTS[p][2])   # 절대 규모 → 대형사업에 유리

TT   = {"P01": 18.5, "P02": 24.1, "P03": 31.2, "P04": 15.8,
        "P05": 12.4, "P06": 27.9, "P07": 22.6, "P08": 8.3, "P09": 19.7}
SOC  = {"P01": 72, "P02": 58, "P03": 61, "P04": 55,
        "P05": 79, "P06": 88, "P07": 64, "P08": 83, "P09": 51}
RISK = {"P01": 46, "P02": 62, "P03": 33, "P04": 41,
        "P05": 71, "P06": 58, "P07": 44, "P08": 29, "P09": 67}

def raw_value(p, c):
    if c == "C1":  return eff(p)
    if c == "C2a": return pat(p)
    if c == "C2b": return TT[p]
    if c == "C3":  return float(SOC[p])
    if c == "C4":  return float(BUDGET[p][2])
    if c == "C5":  return float(RISK[p])
    raise KeyError(c)

DIRECTION = {c: CRITERIA[c][1] for c in LEAVES}

# ---------------- 시나리오 (가중치 합 = 1) ----------------
SCENARIOS = OrderedDict([
    ("S1", ("균형형", "모든 정책목표를 균등 반영", ["PG_TECH", "PG_GROWTH", "PG_SOCIAL"],
            {"C1": 0.18, "C2a": 0.17, "C2b": 0.15, "C3": 0.20, "C4": 0.15, "C5": 0.15})),
    ("S2", ("효율중심", "재정효율성과 투자규모 관리를 우선", ["PG_GROWTH"],
            {"C1": 0.32, "C2a": 0.13, "C2b": 0.10, "C3": 0.08, "C4": 0.27, "C5": 0.10})),
    ("S3", ("혁신중심", "기술주권과 사회적 파급효과를 우선", ["PG_TECH", "PG_SOCIAL"],
            {"C1": 0.10, "C2a": 0.26, "C2b": 0.22, "C3": 0.30, "C4": 0.05, "C5": 0.07})),
])

# 완전평가 대안 8개 (P09 제외)
FULL = [p for p in PROGRAMS if p != "P09"]

# ---------------- 정규화 ----------------
def normalize_minmax(vals, direction):
    lo, hi = min(vals.values()), max(vals.values())
    out = {}
    for k, v in vals.items():
        if hi == lo:
            out[k] = 1.0
        elif direction == "Benefit":
            out[k] = (v - lo) / (hi - lo)
        else:
            out[k] = (hi - v) / (hi - lo)
    return out

def normalize_vector(vals, direction):
    denom = math.sqrt(sum(v * v for v in vals.values()))
    out = {k: v / denom for k, v in vals.items()}
    if direction == "Cost":
        out = {k: 1.0 - v for k, v in out.items()}
    return out

RAW = {c: {p: raw_value(p, c) for p in PROGRAMS} for c in LEAVES}
# v0.2: 정규화값은 (대안×기준×정규화방법)의 3항 관계이므로 두 정규화를 모두
# 모듈 수준에서 한 번씩 계산해 둔다. WSM·PROMETHEE II는 NORM_MINMAX,
# TOPSIS는 NORM_VECTOR를 쓴다 — 동일 CriterionValue라도 값이 다르다.
NORM_MINMAX = {c: normalize_minmax({p: RAW[c][p] for p in FULL}, DIRECTION[c]) for c in LEAVES}
NORM_VECTOR = {c: normalize_vector({p: RAW[c][p] for p in FULL}, DIRECTION[c]) for c in LEAVES}

# ---------------- WSM ----------------
def wsm(weights):
    return {p: sum(weights[c] * NORM_MINMAX[c][p] for c in LEAVES) for p in FULL}

# ---------------- TOPSIS ----------------
def topsis(weights):
    nv = NORM_VECTOR
    wv = {c: {p: weights[c] * nv[c][p] for p in FULL} for c in LEAVES}
    best = {c: max(wv[c].values()) for c in LEAVES}
    worst = {c: min(wv[c].values()) for c in LEAVES}
    out = {}
    for p in FULL:
        dp = math.sqrt(sum((wv[c][p] - best[c]) ** 2 for c in LEAVES))
        dn = math.sqrt(sum((wv[c][p] - worst[c]) ** 2 for c in LEAVES))
        out[p] = dn / (dp + dn) if (dp + dn) else 0.0
    return out

# ---------------- PROMETHEE II ----------------
# V-shape 선호함수, q=0, p=기준별 정규화값 범위의 50%
PREF_Q = {c: 0.0 for c in LEAVES}
PREF_P = {c: 0.5 for c in LEAVES}

def promethee2(weights):
    def pref(c, a, b):
        d = NORM_MINMAX[c][a] - NORM_MINMAX[c][b]      # 정규화 후에는 모두 "클수록 좋음"
        q, p = PREF_Q[c], PREF_P[c]
        if d <= q:   return 0.0
        if d >= p:   return 1.0
        return (d - q) / (p - q)
    n = len(FULL)
    phi = {}
    for a in FULL:
        plus = sum(sum(weights[c] * pref(c, a, b) for c in LEAVES) for b in FULL if b != a)
        minus = sum(sum(weights[c] * pref(c, b, a) for c in LEAVES) for b in FULL if b != a)
        phi[a] = (plus - minus) / (n - 1)
    return phi

METHODS = OrderedDict([
    ("M_WSM",   ("가중합법(WSM)", "CompensatoryMethod", "compensatory", True,  wsm)),
    ("M_TOPSIS",("TOPSIS",       "CompensatoryMethod", "compensatory", True,  topsis)),
    ("M_PRO2",  ("PROMETHEE II", "OutrankingMethod",   "non-compensatory", True, promethee2)),
])

def ranked(scores):
    order = sorted(scores.items(), key=lambda kv: -kv[1])
    return {p: i + 1 for i, (p, _) in enumerate(order)}

RESULTS = {}   # (sid, mid) -> {pid: (score, rank)}
for sid, (_, _, _, W) in SCENARIOS.items():
    for mid, (_, _, _, _, fn) in METHODS.items():
        sc = fn(W)
        rk = ranked(sc)
        RESULTS[(sid, mid)] = {p: (sc[p], rk[p]) for p in FULL}

# ---------------- 반사실 조건 (CQ24) ----------------
# 대상: S1/WSM 에서 3위권 밖인 대안 중 최상위 → 3위 진입에 필요한 기준별 최소 개선량
def counterfactuals(sid="S1", mid="M_WSM", target_rank=3):
    W = SCENARIOS[sid][3]
    res = RESULTS[(sid, mid)]
    ordered = sorted(res.items(), key=lambda kv: kv[1][1])
    third_score = ordered[target_rank - 1][1][0]
    cands = [p for p, (s, r) in res.items() if r == target_rank + 1]
    if not cands:
        return []
    tgt = cands[0]
    gap = third_score - res[tgt][0]
    out = []
    for c in LEAVES:
        cur = NORM_MINMAX[c][tgt]
        need_norm = cur + gap / W[c]
        feasible = need_norm <= 1.0
        # 정규화값 → 원시값 역변환
        vals = {p: RAW[c][p] for p in FULL}
        lo, hi = min(vals.values()), max(vals.values())
        clamped = min(need_norm, 1.0)
        if DIRECTION[c] == "Benefit":
            need_raw = lo + clamped * (hi - lo)
        else:
            need_raw = hi - clamped * (hi - lo)
        out.append((tgt, c, round(gap, 4), round(need_norm, 4),
                    round(need_raw, 2), feasible))
    return out

CF = counterfactuals()

# ================= TTL 출력 =================
L = []
def w(s=""): L.append(s)

w("@prefix nrdp: <https://w3id.org/nrdp/ontology#> .")
w("@prefix mcdm: <https://w3id.org/nrdp/mcdm#> .")
w("@prefix ex:   <https://w3id.org/nrdp/data#> .")
w("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
w("@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .")
w("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .")
w("@prefix prov: <http://www.w3.org/ns/prov#> .")
w("")
w("# 자동 생성된 샘플 데이터 (gen_data.py). 수치는 합성값이며 실제 통계가 아님.")
w("")

w("### 회계연도")
for y in (2021, 2022, 2023):
    w(f'ex:FY{y} a nrdp:FiscalYear ; nrdp:yearValue "{y}"^^xsd:integer ; rdfs:label "{y}년" .')
w("")

w("### 기술분야 (국가과학기술표준분류 예시코드)")
for k, (label, code) in FIELDS.items():
    w(f'ex:{k} a nrdp:TechnologyField ; rdfs:label "{label}"@ko ; skos:notation "{code}" .')
w("")

w("### 기관")
for k, v in MINISTRIES.items():
    w(f'ex:{k} a nrdp:Ministry ; rdfs:label "{v}"@ko .')
for k, v in AGENCIES.items():
    w(f'ex:{k} a nrdp:FundingAgency ; rdfs:label "{v}"@ko .')
w("")

w("### 연구수행기관")
for k, v in PERFORMERS.items():
    w(f'ex:{k} a nrdp:PerformingOrganization ; rdfs:label "{v}"@ko .')
w("")

w("### 세부사업 / 연구개발과제 (partOfProgram 추이적 연결)")
for sid_, (label, parent) in SUBPROGRAMS.items():
    w(f'ex:{sid_} a nrdp:RnDSubProgram ; rdfs:label "{label}"@ko ; '
      f'nrdp:partOfProgram ex:{parent} .')
for jid, (label, parent, orgs) in PROJECTS.items():
    perf = ", ".join(f"ex:{o}" for o in orgs)
    w(f'ex:{jid} a nrdp:RnDProject ; rdfs:label "{label}"@ko ; '
      f'nrdp:partOfProgram ex:{parent} ; nrdp:performedBy {perf} .')
w("")

w("### 정책목표")
for k, v in GOALS.items():
    w(f'ex:{k} a nrdp:PolicyGoal ; rdfs:label "{v}"@ko .')
w("")

w("### 성과지표")
for k, (label, unit) in INDICATORS.items():
    w(f'ex:{k} a nrdp:PerformanceIndicator ; rdfs:label "{label}"@ko ; nrdp:indicatorUnit "{unit}" .')
w("")

w("### 국가연구개발사업")
for pid, (name, min_, ag, tf, goals) in PROGRAMS.items():
    parts = [f'a nrdp:RnDProgram',
             f'rdfs:label "{name}"@ko',
             f'nrdp:programCode "{pid}"',
             f'nrdp:fundedBy ex:{min_}',
             f'nrdp:managedBy ex:{ag}',
             f'nrdp:belongsToField ex:{tf}']
    if goals:
        parts.append("nrdp:contributesTo " + ", ".join(f"ex:{g}" for g in goals))
    allocs = ", ".join(f"ex:BA_{pid}_{y}" for y in (2021, 2022, 2023))
    parts.append(f"nrdp:hasAllocation {allocs}")
    obs = []
    for y in (2021, 2022, 2023):
        obs += [f"ex:OB_{pid}_PAP_{y}", f"ex:OB_{pid}_PAT_{y}"]
    parts.append("nrdp:hasObservation " + ", ".join(obs))
    w(f"ex:{pid} " + " ;\n    ".join(parts) + " .")
w("")

w("### 예산배분 (n-ary 재화)")
for pid in PROGRAMS:
    for i, y in enumerate((2021, 2022, 2023)):
        w(f'ex:BA_{pid}_{y} a nrdp:BudgetAllocation ; nrdp:ofProgram ex:{pid} ; '
          f'nrdp:inFiscalYear ex:FY{y} ; nrdp:hasAmount "{BUDGET[pid][i]}"^^xsd:decimal .')
w("")

w("### 성과관측치 (n-ary 재화)")
for pid in PROGRAMS:
    for i, y in enumerate((2021, 2022, 2023)):
        w(f'ex:OB_{pid}_PAP_{y} a nrdp:IndicatorObservation ; nrdp:ofProgram ex:{pid} ; '
          f'nrdp:inFiscalYear ex:FY{y} ; nrdp:forIndicator ex:IND_EFF ; '
          f'nrdp:hasObservedValue "{PAPERS[pid][i]}"^^xsd:decimal .')
        w(f'ex:OB_{pid}_PAT_{y} a nrdp:IndicatorObservation ; nrdp:ofProgram ex:{pid} ; '
          f'nrdp:inFiscalYear ex:FY{y} ; nrdp:forIndicator ex:IND_PAT ; '
          f'nrdp:hasObservedValue "{PATENTS[pid][i]}"^^xsd:decimal .')
w("")

w("### 의사결정문제 및 대안 (Agent-Role ODP)")
alts = ", ".join(f"ex:ALT_{p}" for p in PROGRAMS)
crits = ", ".join(f"ex:{c}" for c in CRITERIA)
w(f'ex:DP1 a mcdm:DecisionProblem ; rdfs:label "2023년 전략기술 3개 분야 R&D 포트폴리오 평가"@ko ;')
w(f'    mcdm:hasAlternative {alts} ;')
w(f'    mcdm:hasCriterion {crits} .')
w("")
for pid, (name, *_rest) in PROGRAMS.items():
    w(f'ex:ALT_{pid} a mcdm:Alternative ; rdfs:label "{name}(대안)"@ko ; '
      f'mcdm:representsEntity ex:{pid} .')
w("")

w("### 평가기준")
for cid, (label, direction, scale, ind, unit, parent) in CRITERIA.items():
    cls = "mcdm:Criterion"
    if direction == "Benefit": cls = "mcdm:BenefitCriterion"
    elif direction == "Cost":  cls = "mcdm:CostCriterion"
    parts = [f"a {cls}", f'rdfs:label "{label}"@ko']
    if direction: parts.append(f"mcdm:hasDirection mcdm:{direction}")
    if scale:     parts.append(f"mcdm:hasScale mcdm:{scale}")
    if ind:       parts.append(f"mcdm:measuredBy ex:{ind}")
    w(f"ex:{cid} " + " ;\n    ".join(parts) + " .")
subs = [(cid, CRITERIA[cid][5]) for cid in CRITERIA if CRITERIA[cid][5]]
for cid, parent in subs:
    w(f"ex:{parent} mcdm:hasSubCriterion ex:{cid} .")
w("")

w("### 평가값 (2023 기준, 원시값만 — v0.2부터 정규화값은 별도 블록)")
for pid in PROGRAMS:
    for c in LEAVES:
        # P09: C2b 평가값 자체가 누락 (CQ13 결측 탐지 대상)
        if pid == "P09" and c == "C2b":
            continue
        cv = f"ex:CV_{pid}_{c}"
        parts = [f"a mcdm:CriterionValue",
                 f"mcdm:ofAlternative ex:ALT_{pid}",
                 f"mcdm:onCriterion ex:{c}",
                 f'mcdm:hasRawValue "{RAW[c][pid]}"^^xsd:decimal',
                 f'mcdm:hasUnit "{CRITERIA[c][4]}"']
        w(f"{cv} " + " ; ".join(parts) + " .")
w("")

w("### 정규화값 (NormalizedValue, v0.2 — (평가값×정규화방법)의 3항 관계)")
w("# P09는 FULL(완전평가 8개)에 포함되지 않으므로 두 정규화방법 모두 결여됨")
w("# → CQ12(정규화값 결여 평가값)가 P09의 5건 CriterionValue를 전부 탐지한다.")
for pid in FULL:
    for c in LEAVES:
        cv = f"ex:CV_{pid}_{c}"
        for suffix, nmid, table in (("MinMax", "NM_MinMax", NORM_MINMAX),
                                     ("Vector", "NM_Vector", NORM_VECTOR)):
            nvid = f"ex:NV_{pid}_{c}_{suffix}"
            w(f'{nvid} a mcdm:NormalizedValue ; '
              f'mcdm:ofCriterionValue {cv} ; mcdm:normalizedBy ex:{nmid} ; '
              f'mcdm:hasValue "{round(table[c][pid],4)}"^^xsd:decimal .')
        w(f'{cv} mcdm:hasNormalization ex:NV_{pid}_{c}_MinMax, ex:NV_{pid}_{c}_Vector .')
w("")

w("### 정규화방법 / 선호함수 / 집계기법")
w('ex:NM_MinMax a mcdm:NormalizationMethod ; rdfs:label "min-max 정규화"@ko .')
w('ex:NM_Vector a mcdm:NormalizationMethod ; rdfs:label "벡터 정규화"@ko .')
w('ex:PF_VShape a mcdm:PreferenceFunction ; rdfs:label "V-shape 선호함수"@ko ; '
  f'mcdm:preferenceThresholdQ "0.0"^^xsd:decimal ; mcdm:preferenceThresholdP "0.5"^^xsd:decimal .')
w("")
for mid, (label, cls, model, needs_norm, _fn) in METHODS.items():
    parts = [f"a mcdm:{cls}", f'rdfs:label "{label}"@ko',
             f'mcdm:hasPreferenceModel "{model}"',
             f'mcdm:requiresNormalization "{str(needs_norm).lower()}"^^xsd:boolean']
    parts.append("mcdm:usesNormalization " +
                 ("ex:NM_Vector" if mid == "M_TOPSIS" else "ex:NM_MinMax"))
    if mid == "M_PRO2":
        parts.append("mcdm:usesPreferenceFunction ex:PF_VShape")
    w(f"ex:{mid} " + " ;\n    ".join(parts) + " .")
w("")

w("### 시나리오 및 가중치")
for sid, (label, desc, goals, W) in SCENARIOS.items():
    ws = ", ".join(f"ex:W_{sid}_{c}" for c in W)
    parts = [f"a mcdm:DecisionScenario", f'rdfs:label "{label}"@ko',
             f'mcdm:scenarioLabel "{desc}"', f"mcdm:hasWeight {ws}"]
    if goals:
        parts.append("mcdm:reflectsPolicyGoal " + ", ".join(f"ex:{g}" for g in goals))
    w(f"ex:{sid} " + " ;\n    ".join(parts) + " .")
    for c, v in W.items():
        w(f'ex:W_{sid}_{c} a mcdm:Weight ; mcdm:assignedToCriterion ex:{c} ; '
          f'mcdm:hasWeightValue "{v}"^^xsd:decimal .')
w("")

w("### 평가결과 (시나리오 3 × 기법 3 × 대안 8 = 72건)")
for (sid, mid), rows in RESULTS.items():
    for pid, (score, rank) in rows.items():
        w(f'ex:DR_{sid}_{mid}_{pid} a mcdm:DecisionResult ; mcdm:forProblem ex:DP1 ; '
          f'mcdm:forScenario ex:{sid} ; mcdm:byMethod ex:{mid} ; '
          f'mcdm:ofAlternative ex:ALT_{pid} ; '
          f'mcdm:hasScore "{round(score,6)}"^^xsd:decimal ; '
          f'mcdm:hasRank "{rank}"^^xsd:integer .')
w("")

w("### 기준별 기여도 (S1/WSM 기준, CQ22)")
W1 = SCENARIOS["S1"][3]
for pid in FULL:
    total = sum(W1[c] * NORM_MINMAX[c][pid] for c in LEAVES)
    for c in LEAVES:
        contrib = W1[c] * NORM_MINMAX[c][pid]
        ratio = contrib / total if total else 0.0
        w(f'ex:CC_S1_WSM_{pid}_{c} a mcdm:CriterionContribution ; '
          f'mcdm:explains ex:DR_S1_M_WSM_{pid} ; mcdm:contributionOf ex:{c} ; '
          f'mcdm:hasContributionRatio "{round(ratio,4)}"^^xsd:decimal .')
w("")

w("### 출처 계층 (PROV-O) — 예시 2건 (CQ23)")
for pid in ("P01", "P05"):
    for c in ("C1", "C2a"):
        w(f'ex:CV_{pid}_{c} prov:wasGeneratedBy ex:ACT_NORM_{pid}_{c} .')
        w(f'ex:ACT_NORM_{pid}_{c} a prov:Activity ; rdfs:label "min-max 정규화 수행"@ko ; '
          f'prov:used ex:RAW_{pid}_{c} .')
        w(f'ex:RAW_{pid}_{c} a prov:Entity ; rdfs:label "원시통계값"@ko ; '
          f'prov:wasDerivedFrom ex:NTIS_{pid} .')
    w(f'ex:NTIS_{pid} a prov:Entity ; rdfs:label "NTIS 사업 레코드 {pid}"@ko ; '
      f'prov:wasDerivedFrom ex:SRC_NTIS2023 .')
w('ex:SRC_NTIS2023 a prov:Entity ; rdfs:label "NTIS 2023년 국가R&D조사분석 데이터셋"@ko .')
w("")

w("### 반사실 조건 (CQ24) — S1/WSM 에서 3위 진입 요건")
for i, (tgt, c, gap, need_norm, need_raw, feasible) in enumerate(CF, 1):
    w(f'ex:CF_{tgt}_{c} a mcdm:CounterfactualCondition ; '
      f'mcdm:explains ex:DR_S1_M_WSM_{tgt} ; mcdm:concernsCriterion ex:{c} ; '
      f'rdfs:label "{c} 기준 단독 개선으로 3위 진입"@ko ; '
      f'mcdm:requiredNormalizedValue "{need_norm}"^^xsd:decimal ; '
      f'mcdm:requiredRawValue "{need_raw}"^^xsd:decimal ; '
      f'mcdm:isFeasible "{str(feasible).lower()}"^^xsd:boolean .')
w("")

open("data-sample.ttl", "w", encoding="utf-8").write("\n".join(L) + "\n")

# 콘솔 요약
print("=== 생성 요약 ===")
print(f"사업 {len(PROGRAMS)}개 (완전평가 {len(FULL)}, 불완전 1)")
print(f"기준 {len(CRITERIA)}개 (리프 {len(LEAVES)})")
print(f"시나리오 {len(SCENARIOS)}, 기법 {len(METHODS)}, 결과 {len(RESULTS)*len(FULL)}건")
print()
print("=== 시나리오×기법별 순위 (상위 4위) ===")
for sid in SCENARIOS:
    for mid in METHODS:
        rk = RESULTS[(sid, mid)]
        top = sorted(rk.items(), key=lambda kv: kv[1][1])[:4]
        print(f"{sid}/{mid:9s}: " + "  ".join(f"{r}위 {p}" for p, (s, r) in top))
print()
print("=== 반사실 (CQ24 대상) ===")
for tgt, c, gap, nn, nr, f in CF:
    print(f"  {tgt} / {c}: 필요 정규화값 {nn} (원시 {nr}) 실현가능={f}")
print()
print("=== v0.2 검증: 동일 CriterionValue가 정규화방법별로 다른 값을 갖는가? ===")
for p, c in (("P01", "C1"), ("P05", "C4")):
    print(f"  CV_{p}_{c}: min-max={round(NORM_MINMAX[c][p],4)}  "
          f"vector={round(NORM_VECTOR[c][p],4)}  "
          f"(다르면 RQ2 충돌 해소 확인)")
