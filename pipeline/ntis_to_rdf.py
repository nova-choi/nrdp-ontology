#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NTIS 실데이터(panel·results·indicators CSV) → 온톨로지 v0.3 도메인 계층 인스턴스(Turtle).

입력  data/interim/ntis/candidates_2023.csv            (selected=Y 41개 세부사업, 분야, 별칭)
      data/interim/ntis/panel/project_years.csv         (과제연도기록 전수)
      data/interim/ntis/results/rpaper.csv, rpatent.csv (연계 성과)
      data/interim/ntis/indicators/program_year.csv     (사업×연도 지표, ntis_rollup.py 산출)
      data/interim/ntis/indicators/rollup_rules.json    (집계 규칙 서술)
      data/interim/ntis/alias_overrides.csv             (별칭 수작업 판정)
출력  data/rdf/nrdp-schemes.ttl   개념체계(연구수행주체·연구개발단계·신규계속·성과유형·국가전략기술·표준분류 판·집계 규칙), 기관, 회계연도
      data/rdf/nrdp-domain.ttl    세부사업·내역사업·과제·과제연도기록·분야배정·성과물·귀속·예산배분·성과관측치·출처 활동
      data/rdf/build_report.json  건수·제외 사유 요약

포함 범위(ntis_rollup.py 와 동일)
  - canonical_program 이 선정 사업이고, 기록의 program_name 이 정본 또는 채택 별칭인 과제연도기록만 포함.
    (연속과제 추적으로만 들어온 trace_* 기록은 정본 사업이 없어 제외 — R5)
  - 성과물은 포함된 과제연도기록에 귀속되는 것만 포함. 성과 ID 가 같으면 하나의 ResearchOutput, 귀속은 과제연도기록마다 OutputAttribution.
  - 'SECRET PROJECT' 로 가려진 기록은 제외.

IRI 규칙 (ex: = https://w3id.org/nrdp/data#)
  PRG_<sha1(정본 사업명)[:8]>   세부사업          SPG_<sha1(사업|내역사업명)[:8]>  내역사업
  PJ_<세부과제번호 | 과제고유번호>  과제              PYR_<과제고유번호>               과제연도기록
  FA_<과제고유번호>_<순위>        분야 배정          OUT_<성과ID>                    성과물
  ATT_<성과ID>_<과제고유번호>     성과 귀속          BA_<PRG>_<연도>                 예산배분
  OB_<PRG>_<지표>_<연도>          성과관측치         ORG_<sha1(기관명)[:8]>          기관
  표준분류 개념: <https://w3id.org/nrdp/kos/nstsc/2018/<코드>>  (pipeline/correspondence_to_rdf.py 와 같은 IRI 공간)

실행: python pipeline/ntis_to_rdf.py [프로젝트 루트]
"""
import os, sys, re, csv, json, hashlib, datetime
from collections import defaultdict, Counter, OrderedDict

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NT = os.path.join(ROOT, "data", "interim", "ntis")
OUT = os.path.join(ROOT, "data", "rdf")
os.makedirs(OUT, exist_ok=True)

EX = "https://w3id.org/nrdp/data#"
KOS_NSTSC = "https://w3id.org/nrdp/kos/nstsc/"
# v0.3.4 (2026-10-23): 표준분류 판은 과제연도기록의 연도로 정한다. NTIS SCNew 코드는 두 판이 같은 형식(영문 2자+숫자 4자리)이지만
#   2023년 입력분부터 2023 개정판 코드로 바뀐다(소분류 코드: 2022년 이전에만 267개, 2023년 이후에만 190개.
#   예: EE09 RFID/USN 소멸, EE0805~EE0811·EE1205·EE1207~EE1209 신설). 이전 판(전 연도 2018판 가정)은 코드 형식만 근거로 했다.
def nstsc_edition(year):
    return "2023" if int(year) >= 2023 else "2018"
NSTSC_EDITIONS = {"2018": (2018, 2018, 2022, "국가과학기술표준분류 2018 개정판"), "2023": (2023, 2023, None, "국가과학기술표준분류 2023 개정판")}

PREFIXES = """@prefix nrdp:    <https://w3id.org/nrdp/ontology#> .
@prefix mcdm:    <https://w3id.org/nrdp/mcdm#> .
@prefix kosv:    <https://w3id.org/nrdp/kosv#> .
@prefix xkos:    <http://rdf-vocabulary.ddialliance.org/xkos#> .
@prefix ex:      <https://w3id.org/nrdp/data#> .
@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .
@prefix prov:    <http://www.w3.org/ns/prov#> .
@prefix org:     <http://www.w3.org/ns/org#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
"""

# ───────────────────────── 유틸 ─────────────────────────

def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))

def nospace(s):
    return re.sub(r"\s", "", s or "")

def h8(s):
    return hashlib.sha1(nospace(s).encode("utf-8")).hexdigest()[:8]

def lit(s, lang=None):
    s = str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
    return f'"{s}"' + (f"@{lang}" if lang else "")

def dec(v):
    return f'"{v}"^^xsd:decimal'

def integer(v):
    return f'"{int(v)}"^^xsd:integer'

def safe_id(s):
    """IRI 지역명에 쓸 수 없는 문자를 _ 로 바꾼다."""
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", s)

def to_datetime(s):
    """'2020-07-01' | '20220101' → xsd:dateTime 리터럴, 실패 시 None"""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", s)
    if not m:
        return None
    return f'"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00"^^xsd:dateTime'

def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None

class TTL:
    def __init__(self, path, comment):
        self.f = open(path, "w", encoding="utf-8")
        self.f.write(PREFIXES + "\n# " + comment + "\n# 생성: pipeline/ntis_to_rdf.py, " +
                     datetime.datetime.now().isoformat(timespec="seconds") + "\n\n")
        self.n = 0
    def node(self, subj, *po):
        """po: ('p', 'o') 튜플 목록. o 가 None 이면 생략."""
        parts = [f"{p} {o}" for p, o in po if o is not None]
        if not parts:
            return
        self.f.write(subj + " " + " ;\n    ".join(parts) + " .\n")
        self.n += len(parts)
    def section(self, title):
        self.f.write(f"\n### {title}\n")
    def close(self):
        self.f.close()

# ───────────────────────── 입력 ─────────────────────────

cand_rows = [r for r in rd(os.path.join(NT, "candidates_2023.csv")) if r.get("selected", "").upper() == "Y"]
CAND = OrderedDict((r["program_name"], r) for r in cand_rows)
NAMES = {c: {nospace(c)} | {nospace(a) for a in (r.get("aliases") or "").split(";") if a.strip()} for c, r in CAND.items()}
overrides = rd(os.path.join(NT, "alias_overrides.csv")) if os.path.exists(os.path.join(NT, "alias_overrides.csv")) else []

pj_raw = rd(os.path.join(NT, "panel", "project_years.csv"))
report = Counter()
PJ = []
for r in pj_raw:
    if r["ministry"] == "SECRET PROJECT" or r["title_ko"] == "SECRET PROJECT":
        report["excluded_secret"] += 1; continue
    if r["canonical_program"] not in CAND:
        report["excluded_no_canonical_or_unselected"] += 1; continue
    if nospace(r["program_name"]) not in NAMES[r["canonical_program"]]:
        report["excluded_rejected_alias"] += 1; continue
    PJ.append(r)
PYR_IDS = {r["project_id"] for r in PJ}
report["project_year_records"] = len(PJ)

results = {"rpaper": rd(os.path.join(NT, "results", "rpaper.csv")),
           "rpatent": rd(os.path.join(NT, "results", "rpatent.csv"))}
py_rows = rd(os.path.join(NT, "indicators", "program_year.csv"))
rules = json.load(open(os.path.join(NT, "indicators", "rollup_rules.json"), encoding="utf-8"))

# ───────────────────────── 개념체계 정의 ─────────────────────────

PERFORMER_CAT = {"01": "국공립연구소", "02": "출연연구소", "03": "대학", "04": "대기업",
                 "05": "중소기업", "06": "정부부처", "08": "중견기업", "99": "기타"}
DEV_PHASE = {"01": "기초연구", "02": "응용연구", "03": "개발연구", "04": "기타"}
CONT_STATUS = {"1": "신규", "2": "계속"}
OUTPUT_TYPES = OrderedDict([
    ("OT_PAPER", ("논문", None)), ("OT_PAPER_JNL_INTL", ("국외전문학술지 논문", "OT_PAPER")),
    ("OT_PAPER_JNL_DOM", ("국내전문학술지 논문", "OT_PAPER")),
    ("OT_PAPER_CONF_INTL", ("국외학술대회 발표논문", "OT_PAPER")),
    ("OT_PAPER_CONF_DOM", ("국내학술대회 발표논문", "OT_PAPER")),
    ("OT_PAPER_OTHER", ("기타 논문집", "OT_PAPER")),
    ("OT_PATENT", ("특허", None)), ("OT_PATENT_APPLIED", ("특허 출원", "OT_PATENT")),
    ("OT_PATENT_REGISTERED", ("특허 등록", "OT_PATENT")),
])
PAPER_TYPE_MAP = {"국외전문학술지": "OT_PAPER_JNL_INTL", "국내전문학술지": "OT_PAPER_JNL_DOM",
                  "국외학술대회발표논문집": "OT_PAPER_CONF_INTL", "국내학술대회발표논문집": "OT_PAPER_CONF_DOM"}
AMOUNT_BASIS = ("AB_CONTRACT_SUM", "과제 협약 정부연구비 합산(과제연도기록 GovernmentFunds 합)")
INDICATORS = OrderedDict([   # (program_year.csv 열, 라벨, 단위, 시차, 측정 성과유형)
    ("IND_PROJECTS",  ("n_project_years",       "과제 수",                 "건", 0, None)),
    ("IND_CONT",      ("n_continuing",          "계속과제 수",             "건", 0, None)),
    ("IND_PAPER",     ("papers",                "논문 수(시차 1년 적용)",   "건", 1, "OT_PAPER")),
    ("IND_SCI",       ("papers_sci",            "SCI 논문 수(시차 1년 적용)", "건", 1, "OT_PAPER")),
    ("IND_PATENT",    ("patents",               "특허 출원·등록 수(시차 1년 적용)", "건", 1, "OT_PATENT")),
    ("IND_PATREG",    ("patent_registered",     "특허 등록 수(시차 1년 적용)", "건", 1, "OT_PATENT_REGISTERED")),
    ("IND_PAPER_ALL", ("papers_all",            "논문 수(전 기간 누적)",   "건", None, "OT_PAPER")),
    ("IND_PATENT_ALL",("patents_all",           "특허 수(전 기간 누적)",   "건", None, "OT_PATENT")),
])
ROLLUP_RULES = OrderedDict([
    ("RR_R1", "R1 단위: 정본 사업 × 과제 기준연도. 별칭(표기 변형) 기록은 정본으로 합산"),
    ("RR_R2", "R2 연구비: 과제연도기록 정부연구비(GovernmentFunds) 합"),
    ("RR_R3", "R3 성과 귀속: 성과의 (과제고유번호, 기준연도)가 가리키는 과제연도기록의 사업·연도로 귀속, 성과 ID 기준 사업 내 중복 제거"),
    ("RR_R4", "R4 성과 시차: 과제연도 t 의 성과는 등록연도 t·t+1 분만 집계, 누적값은 별도 지표"),
    ("RR_R5", "R5 연속과제 추적(trace)으로만 수집된 기록은 정본 사업이 없어 집계 제외"),
    ("RR_R6", "R6 기여율은 공개 API 미제공 — 전량 귀속(contributionShare 비움)"),
    ("RR_R7", "R7 평가 창: 창 안 존속 연도 연평균, 효율 지표는 창 합계 성과/창 합계 연구비"),
    ("RR_R8", "R8 별칭: 판정 규칙 + alias_overrides.csv 수작업 판정으로 채택된 이름만 정본으로 합산"),
    ("RR_FIELD", "사업 분야(belongsToField): 과제연도기록 1순위 표준분류 대분류의 최빈값"),
])
# 부처 개편 (org:ChangeEvent). (개편 전, 개편 후, 연도, 설명)
REORGS = [
    ("미래창조과학부", "과학기술정보통신부", 2017, "정부조직법 개정(2017.7) — 미래창조과학부를 과학기술정보통신부로 개편"),
    ("산업통상자원부", "산업통상부", 2025, "정부조직법 개정(2025.10) — 에너지 기능을 기후에너지환경부로 이관하며 산업통상부로 개편"),
    ("환경부", "기후에너지환경부", 2025, "정부조직법 개정(2025.10) — 환경부가 에너지 기능을 흡수하여 기후에너지환경부로 개편"),
    ("보건복지부", "질병관리청", 2020, "질병관리본부(보건복지부 소속)의 질병관리청 승격(2020.9) — 감염병 R&D 사업 이관"),
]
FIELD_L = {}   # (판, 대분류 코드) → 명칭 (데이터에서 수집)
FIELD_M = {}
FIELD_S = {}

# ───────────────────────── 기관 ─────────────────────────

orgs = {}   # (종류, 이름) → id
def org_id(kind, name):
    name = (name or "").strip()
    if not name:
        return None
    key = (kind, name)
    if key not in orgs:
        orgs[key] = f"ORG_{kind[:3].upper()}_{h8(name)}"
    return orgs[key]

# ───────────────────────── 1. 개념체계·기관·회계연도 파일 ─────────────────────────

S = TTL(os.path.join(OUT, "nrdp-schemes.ttl"), "개념체계·기관·회계연도 (NTIS 실데이터, v0.3)")

S.section("회계연도")
years = sorted({int(r["year"]) for r in PJ} | {int(r["year"]) for r in py_rows})
for y in years:
    S.node(f"ex:FY{y}", ("a", "nrdp:FiscalYear"), ("nrdp:yearValue", integer(y)), ("rdfs:label", lit(f"{y}년", "ko")))

S.section("연구수행주체 / 연구개발단계 / 신규·계속 구분 / 적용분야")
def scheme(sid, label, items, note=None):
    S.node(f"ex:{sid}", ("a", "skos:ConceptScheme"), ("rdfs:label", lit(label, "ko")), ("rdfs:comment", lit(note, "ko") if note else None))
    for cid, (code, lb) in items.items():
        S.node(f"ex:{cid}", ("a", "skos:Concept"), ("skos:inScheme", f"ex:{sid}"),
               ("skos:notation", lit(code) if code else None), ("skos:prefLabel", lit(lb, "ko")), ("rdfs:label", lit(lb, "ko")))
scheme("CS_PERFORMER", "연구수행주체 (NTIS PerformAgent)", {f"PC_{c}": (c, l) for c, l in PERFORMER_CAT.items()})
scheme("CS_DEVPHASE", "연구개발단계 (NTIS DevelopPhase)", {f"DP_{c}": (c, l) for c, l in DEV_PHASE.items()})
scheme("CS_CONT", "신규·계속 구분 (NTIS ContinuousFlag)", {f"CF_{c}": (c, l) for c, l in CONT_STATUS.items()},
       "코드 1=신규, 2=계속 (패널 자료의 연도별 분포로 확인)")
area_codes = sorted({r["apply_area1_code"] for r in PJ if r["apply_area1_code"]})
scheme("CS_APPLYAREA", "적용분야 (NTIS ApplyArea1) — 코드만 보존, 명칭은 매뉴얼 코드표 대조 필요",
       {f"AA_{safe_id(c)}": (c, c) for c in area_codes})

S.section("성과유형 (시행령 별표4 등록 성과 중 공개 API 제공분: 논문·특허)")
S.node("ex:CS_OUTPUTTYPE", ("a", "skos:ConceptScheme"), ("rdfs:label", lit("연구개발성과 유형", "ko")))
for cid, (lb, parent) in OUTPUT_TYPES.items():
    S.node(f"ex:{cid}", ("a", "skos:Concept"), ("skos:inScheme", "ex:CS_OUTPUTTYPE"), ("skos:prefLabel", lit(lb, "ko")),
           ("rdfs:label", lit(lb, "ko")), ("skos:broader", f"ex:{parent}" if parent else None))

S.section("금액 산정기준 / 집계 규칙")
S.node("ex:CS_AMOUNTBASIS", ("a", "skos:ConceptScheme"), ("rdfs:label", lit("예산배분 금액 산정기준", "ko")))
S.node(f"ex:{AMOUNT_BASIS[0]}", ("a", "skos:Concept"), ("skos:inScheme", "ex:CS_AMOUNTBASIS"),
       ("skos:prefLabel", lit(AMOUNT_BASIS[1], "ko")), ("rdfs:label", lit(AMOUNT_BASIS[1], "ko")))
S.node("ex:CS_ROLLUPRULE", ("a", "skos:ConceptScheme"), ("rdfs:label", lit("사업 단위 집계 규칙", "ko")))
for cid, lb in ROLLUP_RULES.items():
    S.node(f"ex:{cid}", ("a", "skos:Concept"), ("skos:inScheme", "ex:CS_ROLLUPRULE"), ("skos:prefLabel", lit(lb, "ko")), ("rdfs:label", lit(lb, "ko")))

S.section("국가전략기술 (12대, 2022.10 발표 · 2023년 과제정보 입력분부터 태깅) — 대상 사업 선정 축")
S.node("ex:KOS_NST", ("a", "kosv:Classification"), ("rdfs:label", lit("국가전략기술 분류", "ko")))
S.node("ex:NST_2023", ("a", "kosv:ClassificationEdition"), ("kosv:editionOf", "ex:KOS_NST"), ("kosv:announcedYear", integer(2022)),
       ("kosv:validFromYear", integer(2023)), ("rdfs:label", lit("국가전략기술 12대 분야 (2023년 입력분 적용)", "ko")))
nst = OrderedDict()
for r in cand_rows:
    nst[r["field_code"]] = r["field_name"]
for code, lb in nst.items():
    S.node(f"ex:NST_{code}", ("a", "skos:Concept"), ("skos:inScheme", "ex:NST_2023"), ("skos:notation", lit(code)),
           ("skos:prefLabel", lit(lb, "ko")), ("rdfs:label", lit(lb, "ko")))

S.section("국가과학기술표준분류 판 — NTIS SCNew 코드 체계(대·중·소분류). 2022년 이전 기록은 2018 개정판, 2023년 이후 기록은 2023 개정판")
S.node("ex:KOS_NSTSC", ("a", "kosv:Classification"), ("rdfs:label", lit("국가과학기술표준분류체계", "ko")))
def edi(ed):
    return f"<{KOS_NSTSC}{ed}>"
for ed, (ann, vfrom, vto, lb) in NSTSC_EDITIONS.items():
    S.node(edi(ed), ("a", "kosv:ClassificationEdition"), ("kosv:editionOf", "ex:KOS_NSTSC"), ("kosv:announcedYear", integer(ann)),
           ("kosv:validFromYear", integer(vfrom)), ("kosv:validToYear", integer(vto) if vto else None),
           ("xkos:supersedes", edi("2018") if ed == "2023" else None),
           ("rdfs:label", lit(lb + " (NTIS 과제검색 SCNew 코드)", "ko")),
           ("rdfs:comment", lit("판은 과제연도기록의 연도로 정한다(2022년 이전 2018판, 2023년 이후 2023판). 근거: 수집 자료에서 2022년 이전에만 나오는 소분류 코드 267개와 2023년 이후에만 나오는 코드 190개가 연도 경계에서 갈린다(예: EE09 RFID/USN 소멸, EE0811 블록체인 신설). 두 판 사이 대응표는 이 파일에 두지 않는다.", "ko")))
for r in PJ:
    ed = nstsc_edition(r["year"])
    for i in (1, 2, 3):
        sc, sn = r[f"sc_new{i}_s_code"], r[f"sc_new{i}_s_name"]
        if sc:
            FIELD_S[(ed, sc)] = sn; FIELD_M[(ed, r[f"sc_new{i}_m_code"])] = r[f"sc_new{i}_m_name"]; FIELD_L[(ed, r[f"sc_new{i}_l_code"])] = r[f"sc_new{i}_l_name"]
def firi(code, ed):
    return f"<{KOS_NSTSC}{ed}/{code}>"
for (ed, code), lb in sorted(FIELD_L.items()):
    S.node(firi(code, ed), ("a", "nrdp:TechnologyField"), ("skos:inScheme", edi(ed)), ("skos:topConceptOf", edi(ed)), ("skos:notation", lit(code)),
           ("skos:prefLabel", lit(lb, "ko")), ("rdfs:label", lit(lb, "ko")))
for (ed, code), lb in sorted(FIELD_M.items()):
    S.node(firi(code, ed), ("a", "nrdp:TechnologyField"), ("skos:inScheme", edi(ed)), ("skos:notation", lit(code)),
           ("skos:prefLabel", lit(lb, "ko")), ("rdfs:label", lit(lb, "ko")), ("skos:broader", firi(code[:2], ed)))
for (ed, code), lb in sorted(FIELD_S.items()):
    S.node(firi(code, ed), ("a", "nrdp:TechnologyField"), ("skos:inScheme", edi(ed)), ("skos:notation", lit(code)),
           ("skos:prefLabel", lit(lb, "ko")), ("rdfs:label", lit(lb, "ko")), ("skos:broader", firi(code[:4], ed)))

S.section("기관 — 중앙행정기관 / 전문기관 / 연구수행기관(주관)")
MINISTRY_NOTE = {"다부처": "NTIS 가 복수 부처 공동 소관 사업에 기재하는 표기. 개별 소관 부처는 사업명 괄호 안 표기로만 확인 가능"}
for name in sorted({r["ministry"] for r in PJ} | {r["ministry"] for r in cand_rows} | {a for a, b, _, _ in REORGS} | {b for a, b, _, _ in REORGS}):
    S.node(f"ex:{org_id('ministry', name)}", ("a", "nrdp:Ministry"), ("rdfs:label", lit(name, "ko")), ("skos:prefLabel", lit(name, "ko")),
           ("rdfs:comment", lit(MINISTRY_NOTE[name], "ko") if name in MINISTRY_NOTE else None))
for i, (a, b, y, note) in enumerate(REORGS, 1):
    S.node(f"ex:REORG_{i}", ("a", "nrdp:MinistryReorganization"), ("org:originalOrganization", f"ex:{org_id('ministry', a)}"),
           ("org:resultingOrganization", f"ex:{org_id('ministry', b)}"), ("nrdp:inFiscalYear", f"ex:FY{y}" if y in years else None),
           ("rdfs:label", lit(f"{a} → {b} ({y})", "ko")), ("rdfs:comment", lit(note, "ko")))
for name in sorted({r["manage_agency"] for r in PJ if r["manage_agency"]}):
    S.node(f"ex:{org_id('agency', name)}", ("a", "nrdp:FundingAgency"), ("rdfs:label", lit(name, "ko")))
for name in sorted({r["lead_performer"] for r in PJ if r["lead_performer"]}):
    S.node(f"ex:{org_id('performer', name)}", ("a", "nrdp:PerformingOrganization"), ("rdfs:label", lit(name, "ko")))

S.section("성과지표")
for iid, (col, lb, unit, lag, ot) in INDICATORS.items():
    S.node(f"ex:{iid}", ("a", "nrdp:PerformanceIndicator"), ("rdfs:label", lit(lb, "ko")), ("nrdp:indicatorUnit", lit(unit)),
           ("nrdp:hasLag", f'"{lag}"^^xsd:nonNegativeInteger' if lag is not None else None),
           ("nrdp:measuresOutputType", f"ex:{ot}" if ot else None))
S.close()

# ───────────────────────── 2. 도메인 인스턴스 파일 ─────────────────────────

D = TTL(os.path.join(OUT, "nrdp-domain.ttl"), "도메인 계층 인스턴스 (NTIS 실데이터, v0.3) — 세부사업 41개, 2015–2024 패널")

D.section("출처: 수집 스냅샷 / 수집 실행 / 사업 단위 집계 / 동일성 판정")
D.node("ex:SNAP_NTIS_PANEL", ("a", "nrdp:DataSnapshot"), ("rdfs:label", lit("NTIS OpenAPI 과제검색·성과검색 원본 응답 묶음 (data/raw/ntis, manifest.jsonl)", "ko")),
       ("prov:wasGeneratedBy", "ex:ACT_COLLECT"))
D.node("ex:ACT_COLLECT", ("a", "nrdp:CollectionActivity"), ("rdfs:label", lit("NTIS 수집 실행 (pipeline/ntis_collect.py programs→candidates→panel→results)", "ko")),
       ("nrdp:queryCondition", lit("collection=project, 사업명 질의(정본+별칭), 연도 2015–2024; collection=rpaper/rpatent, 과제고유번호 연계")),
       ("prov:endedAtTime", f'"{rules["generated"]}"^^xsd:dateTime'))
D.node("ex:ACT_ROLLUP", ("a", "nrdp:RollupActivity"), ("rdfs:label", lit("사업×연도 지표 집계 (pipeline/ntis_rollup.py)", "ko")),
       ("prov:endedAtTime", f'"{rules["generated"]}"^^xsd:dateTime'),
       *[("nrdp:rollupRule", f"ex:{c}") for c in ROLLUP_RULES])

PRG = OrderedDict()   # canonical → id
for name in CAND:
    PRG[name] = f"PRG_{h8(name)}"
by_prog = defaultdict(list)
for r in PJ:
    by_prog[r["canonical_program"]].append(r)

D.section("세부사업 (RnDProgram) — 정본 사업명, 별칭, 소관부처, 전담기관, 선정 축(국가전략기술), 분야(집계 파생)")
ov = {(o["canonical_program"], o["alias_name"]): o for o in overrides}
for name, cr in CAND.items():
    pid = PRG[name]
    recs = by_prog[name]
    ag = Counter(r["manage_agency"] for r in recs if r["manage_agency"]).most_common(1)
    # v0.3.4: 사업 수준 분야는 선정 기준연도 이후(2023판) 기록의 1순위 대분류 최빈값 — 판을 섞어 세지 않는다
    top_l = Counter(r["sc_new1_l_code"] for r in recs if r["sc_new1_l_code"] and nstsc_edition(r["year"]) == "2023").most_common(1)
    aliases = [a for a in (cr.get("aliases") or "").split(";") if a.strip()]
    D.node(f"ex:{pid}", ("a", "nrdp:RnDProgram"), ("rdfs:label", lit(name, "ko")), ("skos:prefLabel", lit(name, "ko")),
           *[("skos:altLabel", lit(a, "ko")) for a in aliases],
           ("nrdp:fundedBy", f"ex:{org_id('ministry', cr['ministry'])}"),
           ("nrdp:managedBy", f"ex:{org_id('agency', ag[0][0])}" if ag else None),
           ("nrdp:strategicTechnology", f"ex:NST_{cr['field_code']}"),
           ("nrdp:belongsToField", firi(top_l[0][0], "2023") if top_l else None),
           ("prov:wasGeneratedBy", "ex:ACT_IDRES_" + pid))
    # 동일성 판정 활동: 정본 + 별칭 → 하나의 사업
    notes = ["정본 사업명과 표기 변형(별칭)을 하나의 RnDProgram 으로 묶음. 판정 규칙: ntis_collect.py aliases 단계(연속과제 연결 기반) + alias_overrides.csv"]
    for a in aliases:
        o = ov.get((name, a))
        if o:
            notes.append(f"수작업 판정 '{a}': {o['decision']} — {o['reason']}")
    D.node(f"ex:ACT_IDRES_{pid}", ("a", "nrdp:ProgramIdentityResolution"), ("rdfs:label", lit(f"사업 동일성 판정: {name}", "ko")),
           ("nrdp:rollupRule", "ex:RR_R8"), *[("rdfs:comment", lit(n, "ko")) for n in notes])
    if cr.get("budget_codes_2023"):
        pass  # 예산 코드는 BudgetAllocation(2023) 에 기록

D.section("내역사업 (RnDSubProgram)")
SPG = {}
for name, recs in by_prog.items():
    for sp in sorted({r["subprogram_name"] for r in recs if r["subprogram_name"]}):
        sid = f"SPG_{h8(name + '|' + sp)}"
        SPG[(name, sp)] = sid
        D.node(f"ex:{sid}", ("a", "nrdp:RnDSubProgram"), ("rdfs:label", lit(sp, "ko")), ("nrdp:partOfProgram", f"ex:{PRG[name]}"))
report["subprograms"] = len(SPG)

D.section("연구개발과제 (RnDProject) — 세부과제번호 기준, 없으면 과제고유번호")
PJID = {}
proj_recs = defaultdict(list)
for r in PJ:
    key = r["agency_project_no"].strip() or r["project_id"]
    proj_recs[key].append(r)
for key, recs in proj_recs.items():
    jid = "PJ_" + safe_id(key)
    PJID[key] = jid
    last = max(recs, key=lambda r: r["year"])
    D.node(f"ex:{jid}", ("a", "nrdp:RnDProject"), ("rdfs:label", lit(last["title_ko"], "ko")),
           ("nrdp:agencyProjectNumber", lit(key) if last["agency_project_no"].strip() else None))
report["projects"] = len(PJID)

D.section("과제연도기록 (ProjectYearRecord) + 분야 배정 (FieldAssignment)")
n_fa = n_pre = 0
for r in PJ:
    pid = r["project_id"]; y = int(r["year"]); name = r["canonical_program"]
    key = r["agency_project_no"].strip() or pid
    pre = r["pre_project_id"].strip()
    if pre and pre in PYR_IDS and pre != pid:
        n_pre += 1
    else:
        pre = None
    sp = SPG.get((name, r["subprogram_name"]))
    D.node(f"ex:PYR_{pid}",
           ("a", "nrdp:ProjectYearRecord"), ("nrdp:ntisProjectId", lit(pid)),
           ("rdfs:label", lit(r["title_ko"], "ko")), ("rdfs:label", lit(r["title_en"], "en") if r["title_en"].strip() else None),
           ("nrdp:ofProject", f"ex:{PJID[key]}"), ("nrdp:inFiscalYear", f"ex:FY{y}"),
           ("nrdp:partOfProgram", f"ex:{sp}" if sp else f"ex:{PRG[name]}"),
           ("nrdp:recordedProgramName", lit(r["program_name"])),
           ("nrdp:agencyProjectNumber", lit(r["agency_project_no"]) if r["agency_project_no"].strip() else None),
           ("nrdp:precededBy", f"ex:PYR_{pre}" if pre else None),
           ("nrdp:fundedBy", f"ex:{org_id('ministry', r['ministry'])}"),
           ("nrdp:managedBy", f"ex:{org_id('agency', r['manage_agency'])}" if r["manage_agency"] else None),
           ("nrdp:leadPerformer", f"ex:{org_id('performer', r['lead_performer'])}" if r["lead_performer"] else None),
           ("nrdp:performerCategory", f"ex:PC_{r['perform_agent_code']}" if r["perform_agent_code"] in PERFORMER_CAT else None),
           ("nrdp:developmentPhase", f"ex:DP_{r['dev_phase_code'].zfill(2)}" if r["dev_phase_code"].zfill(2) in DEV_PHASE else None),
           ("nrdp:continuationStatus", f"ex:CF_{r['continuous_flag']}" if r["continuous_flag"] in CONT_STATUS else None),
           ("nrdp:applicationArea", f"ex:AA_{safe_id(r['apply_area1_code'])}" if r["apply_area1_code"] else None),
           ("nrdp:governmentFunds", dec(int(num(r["gov_funds"]) or 0)) if num(r["gov_funds"]) is not None else None),
           ("nrdp:nonGovernmentFunds", dec(int(num(r["sbusiness_funds"]))) if num(r["sbusiness_funds"]) is not None else None),
           ("nrdp:totalFunds", dec(int(num(r["total_funds"]))) if num(r["total_funds"]) is not None else None),
           ("nrdp:totalPeriodStart", to_datetime(r["total_start"])), ("nrdp:totalPeriodEnd", to_datetime(r["total_end"])),
           ("nrdp:annualPeriodStart", to_datetime(r["period_start"])), ("nrdp:annualPeriodEnd", to_datetime(r["period_end"])),
           ("prov:hadPrimarySource", "ex:SNAP_NTIS_PANEL"))
    for i in (1, 2, 3):
        sc = r[f"sc_new{i}_s_code"]
        if sc:
            n_fa += 1
            D.node(f"ex:FA_{pid}_{i}", ("a", "nrdp:FieldAssignment"), ("nrdp:assignmentOf", f"ex:PYR_{pid}"),
                   ("nrdp:assignedField", firi(sc, nstsc_edition(r["year"]))), ("nrdp:assignmentRank", integer(i)))
report["field_assignments"] = n_fa; report["preceded_by_links"] = n_pre

D.section("연구개발성과물 (ResearchOutput) + 성과 귀속 (OutputAttribution)")
key_pyr = {(r["project_id"], r["year"]) for r in PJ}
seen_out = set(); n_att = 0
for coll, rows in results.items():
    for r in rows:
        if (r["project_id"], r["project_year"]) not in key_pyr:
            report[f"outputs_unmatched_{coll}"] += 1; continue
        oid = "OUT_" + safe_id(r["result_id"])
        if oid not in seen_out:
            seen_out.add(oid)
            if coll == "rpaper":
                ot = PAPER_TYPE_MAP.get(r["paper_type"], "OT_PAPER_OTHER")
                D.node(f"ex:{oid}", ("a", "nrdp:ResearchOutput"), ("nrdp:outputId", lit(r["result_id"])), ("nrdp:outputType", f"ex:{ot}"),
                       ("nrdp:outputYear", integer(r["result_year"]) if r["result_year"].isdigit() else None),
                       ("nrdp:isSCI", '"true"^^xsd:boolean' if r["sci_type"] == "01" else '"false"^^xsd:boolean'),
                       ("rdfs:label", lit(r["title"])), ("dcterms:isPartOf", lit(r["journal"]) if r["journal"] else None),
                       ("prov:hadPrimarySource", "ex:SNAP_NTIS_PANEL"))
            else:
                ot = "OT_PATENT_REGISTERED" if r["regist_type"] == "등록" else "OT_PATENT_APPLIED"
                D.node(f"ex:{oid}", ("a", "nrdp:ResearchOutput"), ("nrdp:outputId", lit(r["result_id"])), ("nrdp:outputType", f"ex:{ot}"),
                       ("nrdp:outputYear", integer(r["result_year"]) if r["result_year"].isdigit() else None),
                       ("rdfs:label", lit(r["title"])), ("dcterms:identifier", lit(r["regist_no"]) if r["regist_no"] else None),
                       ("prov:hadPrimarySource", "ex:SNAP_NTIS_PANEL"))
        n_att += 1
        D.node(f"ex:ATT_{safe_id(r['result_id'])}_{r['project_id']}", ("a", "nrdp:OutputAttribution"),
               ("nrdp:attributedOutput", f"ex:{oid}"), ("nrdp:attributedTo", f"ex:PYR_{r['project_id']}"))
report["research_outputs"] = len(seen_out); report["output_attributions"] = n_att

D.section("예산배분 (BudgetAllocation, 백만원) + 성과관측치 (IndicatorObservation) — ACT_ROLLUP 파생")
n_ba = n_ob = 0
cand_code = {name: cr.get("budget_codes_2023", "") for name, cr in CAND.items()}
for r in py_rows:
    name = r["canonical_program"]
    if name not in PRG:
        continue
    pid = PRG[name]; y = int(r["year"])
    ba = f"BA_{pid}_{y}"
    # v0.3.4: 다부처 사업은 같은 연도에 부처별 예산 코드를 둘 이상 가지므로 모두 기록한다(이전: 첫 코드만 기록해 나머지가 누락됨).
    codes = [c for c in cand_code[name].split(";") if c] if y == 2023 else []
    if len(codes) > 1:
        report["budget_allocations_multi_code"] += 1
    D.node(f"ex:{ba}", ("a", "nrdp:BudgetAllocation"), ("nrdp:ofProgram", f"ex:{pid}"), ("nrdp:inFiscalYear", f"ex:FY{y}"),
           ("nrdp:hasAmount", dec(round(float(r["gov_funds_100m"]) * 100, 3))), ("nrdp:amountBasis", f"ex:{AMOUNT_BASIS[0]}"),
           *[("nrdp:budgetCode", lit(c)) for c in codes], ("prov:wasGeneratedBy", "ex:ACT_ROLLUP"))
    n_ba += 1
    for iid, (col, *_x) in INDICATORS.items():
        D.node(f"ex:OB_{pid}_{iid[4:]}_{y}", ("a", "nrdp:IndicatorObservation"), ("nrdp:ofProgram", f"ex:{pid}"),
               ("nrdp:inFiscalYear", f"ex:FY{y}"), ("nrdp:forIndicator", f"ex:{iid}"), ("nrdp:hasObservedValue", dec(r[col])),
               ("prov:wasGeneratedBy", "ex:ACT_ROLLUP"))
        n_ob += 1
report["budget_allocations"] = n_ba; report["indicator_observations"] = n_ob
report["programs"] = len(PRG); report["organizations"] = len(orgs)
report["technology_fields"] = len(FIELD_L) + len(FIELD_M) + len(FIELD_S)
D.close()

report["triples_schemes"] = S.n; report["triples_domain"] = D.n
report["generated"] = datetime.datetime.now().isoformat(timespec="seconds")
json.dump(dict(sorted(report.items())), open(os.path.join(OUT, "build_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in sorted(report.items()):
    print(f"{k:40s} {v}")
