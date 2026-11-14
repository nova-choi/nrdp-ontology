"""NTIS OpenAPI 수집기 (국가R&D 과제검색·성과검색, 전체용).

단계
  probe     검색 엔진 동작 확인: 전체 질의어, 패싯 개수 확장, 페이지 크기·깊이 한도, addQuery 다중 조건
  programs  기준연도(기본 2023) 세부사업 목록 + 사업별 국가전략기술·표준분류 분포(패싯)
            → D1 (c) 대상 사업 선정의 입력
  candidates 국가전략기술 분야별 후보 세부사업 + 존속 연도(2015–2024) 확인 → selected 열로 최종 대상 확정
  panel     대상 사업의 연도별 과제연도기록 전수 수집, 연속과제(PrePjtId) 추적으로 사업명 변경 후보 도출,
            사업×연도 집계(과제 수·정부연구비)
  aliases   이전·후속 과제 연결로 찾은 사업명 표기 변형을 별칭으로 병합(panel 이 자동 호출)
  results   panel 과제고유번호의 연계 성과(논문·특허) 수집 — 사업코드(BudgetProjectNumber)·기술분류 포함

원칙
  - 표준 라이브러리만 사용. 키는 .env 의 NTIS_API_KEY 에서 읽고 화면·파일에 남기지 않는다.
  - 모든 응답 원본을 data/raw/ntis/<단계>/ 에 gzip 으로 보존하고 manifest.jsonl 에 요청 조건·해시를 기록한다
    (온톨로지의 SourceRecord → DataSnapshot 출처 경로의 원천).
  - 같은 요청은 캐시를 재사용하므로 중간에 끊겨도 다시 실행하면 이어서 진행한다.
  - 연구책임자·참여연구원 성명, 사업자등록번호는 CSV 에 옮기지 않는다(추적표 B7·B8 범위 외).

실행 (프로젝트 루트에서)
  python pipeline/ntis_collect.py probe
  python pipeline/ntis_collect.py programs --year 2023
  python pipeline/ntis_collect.py all              # probe → programs 연속 실행
  python pipeline/ntis_collect.py candidates --fields 050000,090000,010000
  python pipeline/ntis_collect.py panel            # candidates_2023.csv 의 selected=Y 사업
옵션: --rps 4 (초당 요청 수), --refresh (캐시 무시)
"""
import os, sys, re, io, json, gzip, time, hashlib, argparse, csv, datetime
import urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "ntis")
INTERIM = os.path.join(ROOT, "data", "interim", "ntis")
BASE = "https://www.ntis.go.kr/rndopen/openApi/"
EP_PROJECT = "public_project"
NAVI_PARAMS = ("naviCount", "naviCnt", "navigationCount")
UNIVERSAL_CANDIDATES = ["", "*", "연구|개발|기술|과제|사업|시스템|분석|기반|평가|지원|구축|개선|제조|소재|모델"]

# ───────────────────────── 공통 ─────────────────────────

def now():
    return datetime.datetime.now().isoformat(timespec="seconds")

def load_key():
    key = os.environ.get("NTIS_API_KEY", "").strip()
    env = os.path.join(ROOT, ".env")
    if not key and os.path.exists(env):
        for line in open(env, encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith("NTIS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit(f"[중단] NTIS_API_KEY 없음: {env}")
    return key

class AuthError(Exception):
    pass

class Client:
    def __init__(self, key, rps=4.0, refresh=False):
        self.key, self.gap, self.refresh = key, 1.0 / max(rps, 0.1), refresh
        self.last, self.calls, self.cache_hits = 0.0, 0, 0
        os.makedirs(RAW, exist_ok=True)
        self.manifest = open(os.path.join(RAW, "manifest.jsonl"), "a", encoding="utf-8")

    def get(self, endpoint, params, cache_rel):
        """원본 XML 문자열 반환. cache_rel: RAW 기준 상대경로(.xml.gz)."""
        path = os.path.join(RAW, cache_rel)
        if os.path.exists(path) and not self.refresh:
            self.cache_hits += 1
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return f.read()
        q = dict(params, apprvKey=self.key)
        url = BASE + endpoint + "?" + urllib.parse.urlencode(q)
        text, err = None, None
        for attempt in range(5):
            wait = self.last + self.gap - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "nrdp-thesis/0.2"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    text = r.read().decode("utf-8", errors="replace")
                self.calls += 1
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                err = e
                time.sleep(2 ** (attempt + 1))
        if text is None:
            raise RuntimeError(f"요청 실패({endpoint}, {cache_rel}): {err}")
        text = text.replace(self.key, "***")
        is_error = "<TOTALHITS>" not in text and "<recode>" not in text
        if is_error and re.search(r"유효한\s*인증키가\s*아닙", text):
            raise AuthError("인증키 무효 — 이 API가 승인 목록에 있는지, .env 키가 맞는지 확인")
        if is_error and re.search(r"허용\s*IP|접근\s*허용", text):
            raise AuthError("접근 허용 IP 아님 — 현재 공인 IP와 NTIS 등록 IP 대조")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"   # 중간에 끊겨도 잘린 캐시가 남지 않도록 임시 파일에 쓴 뒤 교체
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        total = re.search(r"<TOTALHITS>(\d+)</TOTALHITS>", text)
        self.manifest.write(json.dumps({
            "ts": now(), "endpoint": endpoint, "params": params, "file": cache_rel.replace("\\", "/"),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "bytes": len(text.encode("utf-8")),
            "totalhits": int(total.group(1)) if total else None}, ensure_ascii=False) + "\n")
        self.manifest.flush()
        return text

CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
SPAN = re.compile(r"</?span[^>]*>")

def clean(s):
    return SPAN.sub("", s or "").strip()

def parse(text):
    root = ET.fromstring(CTRL.sub("", text).encode("utf-8"))
    total = int(root.findtext("TOTALHITS") or 0)
    hits_n = int(root.findtext("HITS") or 0)
    facets = {}
    nav = root.find("NAVIGATION")
    if nav is not None:
        for ent in nav.findall("NAVIGATIONENTRY"):
            vals = []
            for el in ent.iter("NAVIGATIONELEMENT"):
                nm, _, code = (el.get("NAME") or "").partition("▦")
                vals.append((clean(nm), code, int(el.get("COUNT") or 0)))
            facets[ent.get("NAME")] = vals
    return {"total": total, "hits_n": hits_n, "facets": facets, "hits": root.findall("RESULTSET/HIT"), "root": root}

def sparams(srwr, add_query="", start=1, cnt=1, navi=None, sort="", fd=""):
    p = {"collection": "project", "SRWR": srwr, "searchFd": fd, "addQuery": add_query,
         "searchRnkn": sort, "startPosition": start, "displayCnt": cnt, "userId": ""}
    if navi:
        p[navi[0]] = navi[1]
    return p

def safe_name(s):
    """addQuery 안에서 구분자로 쓰이는 & = 를 공백으로 바꾼다(예: '(R&D)' → '(R D)')."""
    return re.sub(r"[&=]", " ", s)

def slug(s, n=60):
    h = hashlib.md5(s.encode("utf-8")).hexdigest()[:8]
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", s)[:n].strip("_") + "_" + h

# ───────────────────────── probe ─────────────────────────

def probe(cl, year=2023):
    rep = {"ts": now(), "year": year}
    yq = f"PY={year}/SAME"
    # P1 전체 질의어
    p1 = []
    for i, c in enumerate(UNIVERSAL_CANDIDATES):
        try:
            r = parse(cl.get(EP_PROJECT, sparams(c, yq), f"probe/p1_universal_{i}.xml.gz"))
            p1.append({"srwr": c, "total": r["total"], "hits": r["hits_n"]})
        except AuthError:
            raise
        except Exception as e:
            p1.append({"srwr": c, "error": str(e)[:200]})
    rep["P1_universal"] = p1
    best = max((x for x in p1 if x.get("total")), key=lambda x: x["total"], default=None)
    if not best:
        rep["fatal"] = "전체 질의어 후보가 모두 0건"
        return rep
    U = best["srwr"]
    # P2 패싯 개수 확장 파라미터
    base = parse(cl.get(EP_PROJECT, sparams(U, yq), f"probe/p1_universal_{UNIVERSAL_CANDIDATES.index(U)}.xml.gz"))
    base_len = len(base["facets"].get("budgetprojectname", []))
    p2, navi = [], None
    for name in NAVI_PARAMS:
        r = parse(cl.get(EP_PROJECT, sparams(U, yq, navi=(name, 3000)), f"probe/p2_{name}.xml.gz"))
        n = len(r["facets"].get("budgetprojectname", []))
        p2.append({"param": name, "budgetprojectname_len": n, "default_len": base_len})
        if n > base_len and navi is None:
            navi = name
    rep["P2_navi"] = p2
    # P3 페이지 크기
    p3, max_cnt = [], 100
    for cnt in (100, 500, 1000):
        r = parse(cl.get(EP_PROJECT, sparams(U, yq, cnt=cnt), f"probe/p3_cnt{cnt}.xml.gz"))
        p3.append({"displayCnt": cnt, "hits": r["hits_n"]})
        if r["hits_n"] == cnt:
            max_cnt = cnt
    rep["P3_display"] = p3
    # P4 깊은 페이지
    total = best["total"]
    p4, depth_ok = [], total
    for start in (10001, 20001, 50001, max(total - 2, 1)):
        if start > total:
            continue
        r = parse(cl.get(EP_PROJECT, sparams(U, yq, start=start, cnt=1), f"probe/p4_start{start}.xml.gz"))
        p4.append({"startPosition": start, "hits": r["hits_n"]})
        if r["hits_n"] == 0:
            depth_ok = min(depth_ok, start - 1)
    rep["P4_depth"] = p4
    # P5 addQuery 다중 조건 · PB03 일치도
    prog = (base["facets"].get("budgetprojectname") or [("", "", 0)])[0]
    pname = prog[0]
    r_only = parse(cl.get(EP_PROJECT, sparams(U, "PB03=" + safe_name(pname)), "probe/p5_pb03_only.xml.gz"))
    r_and = parse(cl.get(EP_PROJECT, sparams(U, yq + "&PB03=" + safe_name(pname),
                                            navi=(navi, 3000) if navi else None), "probe/p5_pb03_and_py.xml.gz"))
    yr_cnt = sum(c for n, _, c in r_only["facets"].get("projectyear", []) if n == str(year))
    bp = r_and["facets"].get("budgetprojectname", [])
    exact = sum(c for n, _, c in bp if n == pname)
    rep["P5_addquery"] = {"program": pname, "facet_count_in_year": prog[2], "pb03_only_total": r_only["total"],
                          "pb03_only_year_facet": yr_cnt, "pb03_and_py_total": r_and["total"],
                          "and_works": 0 < r_and["total"] <= r_only["total"] and r_and["total"] != r_only["total"],
                          "purity_exact_name": round(exact / r_and["total"], 4) if r_and["total"] else None,
                          "top_programs_matched": bp[:5]}
    # P5b 대안: 사업명 일치 문자열 검색(searchFd=PB) + 연도 조건
    r_ph = parse(cl.get(EP_PROJECT, sparams('"' + pname + '"', yq, fd="PB", navi=(navi, 3000) if navi else None),
                        "probe/p5b_phrase_pb.xml.gz"))
    bp2 = r_ph["facets"].get("budgetprojectname", [])
    ex2 = sum(c for n, _, c in bp2 if n == pname)
    rep["P5b_phrase"] = {"total": r_ph["total"], "purity_exact_name": round(ex2 / r_ph["total"], 4) if r_ph["total"] else None,
                         "top_programs_matched": bp2[:5]}
    # P6 정렬 안정성(1·2쪽 중복)
    p6 = {}
    for sort in ("", "DATE/DESC", "RANK/DESC"):
        ids = []
        for start in (1, 101):
            r = parse(cl.get(EP_PROJECT, sparams(U, yq, start=start, cnt=100, sort=sort),
                             f"probe/p6_{sort.replace('/', '_') or 'none'}_{start}.xml.gz"))
            ids.append([h.findtext("ProjectNumber") for h in r["hits"]])
        p6[sort or "none"] = {"page1": len(ids[0]), "page2": len(ids[1]), "overlap": len(set(ids[0]) & set(ids[1]))}
    rep["P6_sort"] = p6
    stable = [k for k, v in p6.items() if v["overlap"] == 0 and v["page2"] > 0]
    cfg = {"universal_srwr": U, "navi_param": navi, "max_display": max_cnt, "max_depth": depth_ok,
           "and_sep": "&" if rep["P5_addquery"]["and_works"] else None,
           "sort": ("" if "none" in stable else (stable[0] if stable else "DATE/DESC"))}
    rep["config"] = cfg
    os.makedirs(os.path.join(RAW, "probe"), exist_ok=True)
    json.dump(rep, open(os.path.join(RAW, "probe", "probe_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(cfg, open(os.path.join(RAW, "probe", "probe_config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[probe] 설정:", json.dumps(cfg, ensure_ascii=False))
    return rep

# ───────────────────────── programs ─────────────────────────

def load_cfg(cl):
    p = os.path.join(RAW, "probe", "probe_config.json")
    if not os.path.exists(p):
        probe(cl)
    return json.load(open(p, encoding="utf-8"))

def facet_programs(cl, cfg, year, add_extra="", tag="all"):
    navi = (cfg["navi_param"], 5000) if cfg["navi_param"] else None
    aq = f"PY={year}/SAME" + (("&" + add_extra) if add_extra else "")
    r = parse(cl.get(EP_PROJECT, sparams(cfg["universal_srwr"], aq, navi=navi),
                     f"programs/{year}/facet_{slug(tag)}.xml.gz"))
    bp = r["facets"].get("budgetprojectname", [])
    return r, bp, sum(c for _, _, c in bp) >= r["total"]

def scan_names(cl, cfg, year, add_extra, tag):
    """패싯이 잘릴 때의 대안: 해당 부분집합을 페이지로 넘기며 사업명 집계(예산코드는 없음)."""
    cnt, step = Counter(), cfg["max_display"]
    aq = f"PY={year}/SAME" + (("&" + add_extra) if add_extra else "")
    start, total = 1, None
    while True:
        r = parse(cl.get(EP_PROJECT, sparams(cfg["universal_srwr"], aq, start=start, cnt=step, sort=cfg["sort"]),
                         f"programs/{year}/scan_{slug(tag)}_{start}.xml.gz"))
        total = r["total"] if total is None else total
        for h in r["hits"]:
            cnt[clean(h.findtext("BudgetProject/Name"))] += 1
        start += step
        if not r["hits"] or start > min(total, cfg["max_depth"]):
            break
    return [(n, "", c) for n, c in cnt.most_common()], sum(cnt.values()) >= total

def programs(cl, year=2023, limit=None):
    cfg = load_cfg(cl)
    mode = "and" if cfg.get("and_sep") else "phrase"
    if mode == "phrase":
        print("[programs] addQuery 다중 조건이 동작하지 않아 사업명 일치 문자열 검색(searchFd=PB)으로 조회합니다.")
    r0, bp, complete = facet_programs(cl, cfg, year)
    total_year = r0["total"]
    source = "facet_all"
    if not complete:   # 패싯 잘림 → 부처별로 나눠 다시
        bp, source = [], "facet_by_ministry"
        for mname, _, _ in r0["facets"].get("ministryname", []):
            _, sub, ok = facet_programs(cl, cfg, year, "PB02=" + safe_name(mname), "min_" + mname)
            if not ok:
                sub, ok = scan_names(cl, cfg, year, "PB02=" + safe_name(mname), "min_" + mname)
                source = "facet+scan"
            bp.extend(sub)
    by_name = defaultdict(lambda: {"codes": set(), "facet_count": 0})
    for n, code, c in bp:
        by_name[n]["facet_count"] += c
        if code:
            by_name[n]["codes"].add(code)
    names = sorted(by_name, key=lambda n: -by_name[n]["facet_count"])
    if limit:
        names = names[:limit]
    print(f"[programs] {year}년 과제 {total_year}건, 세부사업명 {len(by_name)}개(출처 {source}). 사업별 분포 조회 {len(names)}건")
    navi = (cfg["navi_param"], 500) if cfg["navi_param"] else None
    rows, details = [], {}
    for i, n in enumerate(names, 1):
        if mode == "and":
            prm = sparams(cfg["universal_srwr"], f"PY={year}/SAME&PB03=" + safe_name(n), navi=navi)
        else:
            prm = sparams('"' + n + '"', f"PY={year}/SAME", navi=navi, fd="PB")
        r = parse(cl.get(EP_PROJECT, prm, f"programs/{year}/prog_{mode}_{slug(n)}.xml.gz"))
        f = r["facets"]
        matched = f.get("budgetprojectname", [])
        exact = sum(c for m, _, c in matched if m == n)
        st = f.get("strategictechnique", [])
        st_total = sum(c for _, _, c in st) or 1
        top = st[0] if st else ("", "", 0)
        mins = f.get("ministryname", [])
        rows.append({
            "year": year, "program_name": n, "query_mode": mode, "budget_codes": ";".join(sorted(by_name[n]["codes"])),
            "facet_count": by_name[n]["facet_count"], "query_total": r["total"], "exact_match": exact,
            "purity": round(exact / r["total"], 4) if r["total"] else "",
            "ministry": mins[0][0] if mins else "", "n_ministries": len(mins),
            "orderagency": (f.get("orderagency") or [("", "", 0)])[0][0],
            "st_top_name": top[0], "st_top_code": top[1], "st_top_share": round(top[2] / st_total, 4),
            "st_n_classes": len(st),
            "sc_top": "|".join(f"{a}:{c}" for a, _, c in (f.get("scienceclass1") or [])[:3]),
        })
        details[n] = {"strategictechnique": st, "scienceclass1": (f.get("scienceclass1") or [])[:20],
                      "budgetprojectname": matched[:10], "ministryname": mins, "developmentphases": f.get("developmentphases", [])}
        if i % 50 == 0:
            print(f"  {i}/{len(names)}  (API {cl.calls}회, 캐시 {cl.cache_hits}회)")
    os.makedirs(INTERIM, exist_ok=True)
    out_csv = os.path.join(INTERIM, f"programs_{year}.csv")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    json.dump({"year": year, "total_projects": total_year, "source": source,
               "year_facets": {k: v for k, v in r0["facets"].items() if k != "budgetprojectname"},
               "programs": details}, open(os.path.join(INTERIM, f"programs_{year}_facets.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 전략기술(대분류)별 사업 수 요약
    agg = defaultdict(lambda: [0, 0])
    for row in rows:
        k = (row["st_top_code"][:2] + "0000" if row["st_top_code"] else "", row["st_top_name"])
        agg[k][0] += 1; agg[k][1] += row["exact_match"]
    print("[programs] 최다 국가전략기술(사업 기준) 상위:")
    for (code, nm), (np_, nj) in sorted(agg.items(), key=lambda x: -x[1][0])[:15]:
        print(f"   {code} {nm:<28} 사업 {np_:>4}  과제 {nj:>6}")
    print(f"[programs] 저장: {out_csv}")

# ───────────────────────── candidates ─────────────────────────

FIELD_NAMES = {"010000": "반도체·디스플레이", "020000": "이차전지", "030000": "첨단 모빌리티", "040000": "차세대 원자력",
               "050000": "첨단바이오", "060000": "우주항공·해양", "070000": "수소", "080000": "사이버보안",
               "090000": "인공지능", "100000": "차세대 통신", "110000": "첨단로봇·제조", "120000": "양자"}
EXCLUDE_DEFAULT = r"운영비지원|주요사업비"

def program_shares(year):
    """programs 단계 결과에서 사업별 국가전략기술 '대분류' 과제 수 비중을 계산(세부 중점기술 행은 제외해 이중계산 방지)."""
    fac = json.load(open(os.path.join(INTERIM, f"programs_{year}_facets.json"), encoding="utf-8"))
    rows = {r["program_name"]: r for r in csv.DictReader(open(os.path.join(INTERIM, f"programs_{year}.csv"), encoding="utf-8-sig"))}
    out = {}
    for n, info in fac["programs"].items():
        st = [x for x in info["strategictechnique"] if x[1].endswith("0000")]
        tot = sum(x[2] for x in st)
        codes = sorted({c for m, c, _ in info["budgetprojectname"] if m == n and c})
        out[n] = {"tot": tot, "dist": {c: k / tot for _, c, k in st} if tot else {},
                  "n": int(rows[n]["exact_match"]), "ministry": rows[n]["ministry"], "codes": codes}
    return out

def candidates(cl, cfg, year, fields, min_share, min_projects, exclude):
    sh = program_shares(year)
    navi = (cfg["navi_param"], 50) if cfg.get("navi_param") else None
    rows = []
    for n, v in sh.items():
        for f in fields:
            share = v["dist"].get(f, 0.0)
            if share < min_share or v["n"] < min_projects:
                continue
            r = parse(cl.get(EP_PROJECT, sparams(cfg["universal_srwr"], "PB03=" + safe_name(n), navi=navi),
                             f"candidates/life_{slug(n)}.xml.gz"))
            years = sorted(int(y) for y, _, c in r["facets"].get("projectyear", []) if y.isdigit() and c > 0)
            names_all = r["facets"].get("budgetprojectname", [])
            excl = bool(re.search(exclude, n)) if exclude else False
            rows.append({
                "field_code": f, "field_name": FIELD_NAMES.get(f, ""), "program_name": n, "ministry": v["ministry"],
                f"n_projects_{year}": v["n"], "field_share": round(share, 3),
                f"budget_codes_{year}": ";".join(v["codes"]),
                "first_year": years[0] if years else "", "last_year": years[-1] if years else "",
                "years_2015_2024": sum(1 for y in years if 2015 <= y <= 2024),
                "name_variants_all_years": len({m for m, _, _ in names_all}),
                "exclude_rule_hit": "Y" if excl else "", "selected": "" if excl else "Y"})
    rows.sort(key=lambda r: (r["field_code"], -r[f"n_projects_{year}"]))
    out = os.path.join(INTERIM, f"candidates_{year}.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    by = Counter(r["field_code"] for r in rows if r["selected"] == "Y")
    print("[candidates] 분야별 후보:", {FIELD_NAMES.get(k, k): c for k, c in by.items()}, "합계", sum(by.values()))
    print("[candidates] 2015–2024 중 존속 연수 분포:", Counter(r["years_2015_2024"] for r in rows if r["selected"] == "Y"))
    print(f"[candidates] 저장: {out}  (selected 열을 고쳐 최종 대상을 확정)")

# ───────────────────────── panel ─────────────────────────

def g(h, path, attr=None):
    el = h.find(path)
    if el is None:
        return ""
    return clean(el.get(attr) if attr else el.text)

def flatten(h):
    """과제연도기록 1건 → 평면 레코드. 개인 성명·사업자등록번호는 옮기지 않는다."""
    rec = {
        "project_id": g(h, "ProjectNumber"), "year": g(h, "ProjectYear"),
        "title_ko": g(h, "ProjectTitle/Korean"), "title_en": g(h, "ProjectTitle/English"),
        "ministry": g(h, "Ministry/Name"), "order_agency": g(h, "OrderAgency/Name"),
        "manage_agency": g(h, "ManageAgency/Name"), "lead_performer": g(h, "ResearchAgency/Name"),
        "program_name": g(h, "BudgetProject/Name"), "business_name": g(h, "BusinessName"),
        "subprogram_name": g(h, "BigprojectTitle"), "agency_project_no": g(h, "OrganizationPNumber"),
        "period_start": g(h, "ProjectPeriod/Start"), "period_end": g(h, "ProjectPeriod/End"),
        "total_start": g(h, "ProjectPeriod/TotalStart")[:10], "total_end": g(h, "ProjectPeriod/TotalEnd")[:10],
        "gov_funds": g(h, "GovernmentFunds"), "sbusiness_funds": g(h, "SbusinessFunds"), "total_funds": g(h, "TotalFunds"),
        "perform_agent_code": g(h, "PerformAgent", "code"), "perform_agent": g(h, "PerformAgent"),
        "dev_phase_code": g(h, "DevelopmentPhases", "code"), "dev_phase": g(h, "DevelopmentPhases"),
        "region_code": g(h, "Region", "code"), "sixtech_code": g(h, "SixTechnology", "code"),
        "apply_area1_code": g(h, "ApplyArea/First", "code"), "continuous_flag": g(h, "ContinuousFlag"),
        "policy_flag": g(h, "PolicyProjectFlag"), "pre_project_id": g(h, "SeriesProject/PrePjtId") or g(h, "PrePjtId"),
        "series_project": g(h, "SeriesProject"),
        "n_researchers_m": g(h, "Researchers/ManCount"), "n_researchers_f": g(h, "Researchers/WomanCount"),
        "kw_ko": g(h, "Keyword/Korean"),
    }
    for sc in h.findall("ScienceClass"):
        t, q = sc.get("type") or "", sc.get("sequence") or "1"
        if t not in ("new", "old"):
            continue
        for lvl, tag in (("l", "Large"), ("m", "Medium"), ("s", "Small")):
            el = sc.find(tag)
            rec[f"sc_{t}{q}_{lvl}_code"] = el.get("code", "") if el is not None else ""
            rec[f"sc_{t}{q}_{lvl}_name"] = clean(el.text) if el is not None else ""
    ms = h.find("MinistryScienceClass")
    rec["ministry_tc"] = "/".join(clean(ms.findtext(t)) for t in ("Large", "Medium", "Small")) if ms is not None else ""
    return rec

def fetch_all(cl, cfg, add_query, rel_prefix, srwr=None, fd=""):
    recs, start, step, total = [], 1, cfg["max_display"], None
    while True:
        r = parse(cl.get(EP_PROJECT, sparams(cfg["universal_srwr"] if srwr is None else srwr, add_query,
                                             start=start, cnt=step, sort=cfg["sort"], fd=fd),
                         f"{rel_prefix}_{start}.xml.gz"))
        total = r["total"] if total is None else total
        recs.extend(flatten(h) for h in r["hits"])
        start += step
        if not r["hits"] or start > total:
            break
    return recs, total

def write_csv(path, rows, keys=None):
    if not rows:
        return
    keys = keys or sorted({k for r in rows for k in r}, key=lambda k: (k.startswith("sc_"), k))
    with open(path, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def nospace(x):
    return re.sub(r"\s", "", x or "")

def successors(rec):
    m = re.search(r"after=([\d,]+)", rec.get("series_project") or "")
    return [x for x in m.group(1).split(",") if x] if m else []

def panel(cl, cfg, cand_csv, y0, y1, trace_rounds=2):
    sel = [r for r in csv.DictReader(open(cand_csv, encoding="utf-8-sig")) if r.get("selected", "").strip().upper() == "Y"]
    progs = {}
    for r in sel:
        progs.setdefault(r["program_name"], r)
    aliases = defaultdict(set)          # 정본 사업명 → 함께 수집할 별칭 사업명(alias 열, ';' 구분)
    for r in sel:
        for a_ in (r.get("aliases") or "").split(";"):
            if a_.strip():
                aliases[r["program_name"]].add(a_.strip())
    outdir = os.path.join(INTERIM, "panel"); os.makedirs(outdir, exist_ok=True)
    records, check = {}, []
    print(f"[panel] 대상 사업 {len(progs)}개 × {y0}–{y1}")
    for i, (canon, info) in enumerate(progs.items(), 1):
        for name in [canon] + sorted(aliases[canon]):
            for y in range(y0, y1 + 1):
                recs, total = fetch_all(cl, cfg, f"PY={y}/SAME&PB03=" + safe_name(name), f"panel/{slug(name)}/{y}")
                exact = 0
                for rec in recs:
                    # PB03 은 토큰 일치라 '(설계)(R&D)' 같은 형제 사업까지 잡는다 → 공백만 무시한 사업명 일치만 채택
                    if nospace(rec["program_name"]) != nospace(name):
                        continue
                    exact += 1
                    rec.update(canonical_program=canon, field_code=info.get("field_code", ""), via="program_query",
                               matched_name=name)
                    records.setdefault((rec["project_id"], rec["year"]), rec)
                check.append({"canonical_program": canon, "query_name": name, "year": y, "total": total,
                              "received": len(recs), "exact_name": exact, "dropped_sibling": len(recs) - exact})
        print(f"  {i}/{len(progs)} {canon}  (누적 과제연도 {len(records)}, API {cl.calls}회)")
    # 연속과제 추적: 수집 집합 밖의 이전과제 → 과제고유번호로 조회해 이전 사업명을 확인
    links = []
    for rnd in range(1, trace_rounds + 1):
        have = {pid for pid, _ in records}
        want = {r["pre_project_id"] for r in records.values()
                if r["pre_project_id"] and r["pre_project_id"] not in have}
        # 다음 연도 과제(after=)도 추적: 2024년에 사업명이 바뀐 경우를 잡기 위함(수집 종료연도 이전 기록만)
        want |= {s_ for r in records.values() if r["canonical_program"] and r["year"].isdigit() and int(r["year"]) < y1
                 for s_ in successors(r) if s_ not in have}
        want = sorted(want)
        if not want:
            break
        print(f"[panel] 추적 {rnd}회차: 수집 범위 밖 이전과제 {len(want)}건")
        for k in range(0, len(want), 40):
            batch = want[k:k + 40]
            q = "|".join(batch)
            r = parse(cl.get(EP_PROJECT, sparams(q, "", cnt=1000, fd="PB"),
                             f"trace/r{rnd}_{hashlib.md5(q.encode()).hexdigest()[:10]}.xml.gz"))
            got = {}
            if r["total"] <= 5 * len(batch):     # 묶음 검색이 과제번호만 잡을 때만 사용, 아니면 단건 조회
                for h in r["hits"]:
                    rec = flatten(h)
                    if rec["project_id"] in batch:
                        got[rec["project_id"]] = rec
            for pid in batch:
                if pid not in got:      # 묶음 검색에 안 잡히면 단건 조회
                    one, _ = fetch_all(cl, cfg, "CN=" + pid, f"trace/cn_{pid}")
                    for rec in one:
                        if rec["project_id"] == pid:
                            got[pid] = rec
            for pid, rec in got.items():
                rec.update(canonical_program="", field_code="", via=f"trace_r{rnd}", matched_name="")
                records.setdefault((rec["project_id"], rec["year"]), rec)
    # 이전과제 연결 → 사업명 변경 후보
    by_id = defaultdict(list)
    for (pid, y), rec in records.items():
        by_id[pid].append(rec)
    canon_of = {}
    for rec in records.values():
        if rec["canonical_program"]:
            canon_of[rec["project_id"]] = rec["canonical_program"]
    alias_cnt = defaultdict(lambda: {"n": 0, "years": set()})
    for rec in records.values():
        pre = rec["pre_project_id"]
        if not pre or not rec["canonical_program"]:
            continue
        for prec in by_id.get(pre, []):
            links.append({"project_id": rec["project_id"], "year": rec["year"], "program": rec["program_name"],
                          "pre_project_id": pre, "pre_year": prec["year"], "pre_program": prec["program_name"],
                          "canonical_program": rec["canonical_program"]})
            if prec["program_name"] != rec["program_name"] and prec["program_name"] not in progs:
                k = (rec["canonical_program"], prec["program_name"], prec["ministry"])
                alias_cnt[k]["n"] += 1; alias_cnt[k]["years"].add(prec["year"])
    for rec in records.values():        # 후속 과제 쪽 사업명 변경
        if not rec["canonical_program"]:
            continue
        for sid in successors(rec):
            for srec in by_id.get(sid, []):
                if srec["program_name"] != rec["program_name"] and srec["program_name"] not in progs \
                        and not srec["canonical_program"]:
                    k = (rec["canonical_program"], srec["program_name"], srec["ministry"])
                    alias_cnt[k]["n"] += 1; alias_cnt[k]["years"].add(srec["year"])
    alias_rows = [{"canonical_program": c, "predecessor_program_name": p, "ministry": m, "n_links": v["n"],
                   "years": ";".join(sorted(v["years"]))} for (c, p, m), v in sorted(alias_cnt.items(), key=lambda x: -x[1]["n"])]
    # 사업×연도 집계
    agg = defaultdict(lambda: {"n": 0, "gov": 0, "tot": 0, "names": Counter()})
    for rec in records.values():
        if not rec["canonical_program"]:
            continue
        a_ = agg[(rec["canonical_program"], rec["year"])]
        a_["n"] += 1; a_["names"][rec["program_name"]] += 1
        for k, fld in (("gov", "gov_funds"), ("tot", "total_funds")):
            try:
                a_[k] += int(float(rec[fld] or 0))
            except ValueError:
                pass
    py_rows = [{"canonical_program": c, "year": y, "n_project_years": v["n"], "gov_funds_won": v["gov"],
                "total_funds_won": v["tot"], "program_names_seen": ";".join(f"{n}:{k}" for n, k in v["names"].most_common())}
               for (c, y), v in sorted(agg.items())]
    write_csv(os.path.join(outdir, "project_years.csv"), list(records.values()))
    for name, rows_ in (("program_year.csv", py_rows), ("predecessor_links.csv", links),
                        ("alias_suggestions.csv", alias_rows), ("query_check.csv", check)):
        write_csv(os.path.join(outdir, name), rows_, list(rows_[0].keys()) if rows_ else None)
    print(f"[panel] 과제연도기록 {len(records)}건, 사업×연도 {len(py_rows)}행, 사업명 변경 후보 {len(alias_rows)}건 → {outdir}")

# ───────────────────────── aliases ─────────────────────────

MINISTRY_LINEAGE = {"미래창조과학부": "과학기술정보통신부", "교육과학기술부": "과학기술정보통신부",
                    "지식경제부": "산업통상자원부", "중소기업청": "중소벤처기업부", "질병관리본부": "질병관리청"}

def norm_program(n):
    """표기 변형 흡수용 정규화: 괄호 부분·공백·구두점·'다부처' 접두·'사업' 접미 제거."""
    s = re.sub(r"\([^)]*\)", "", n or "")
    s = re.sub(r"[\s·.,\-_/]", "", s)
    s = re.sub(r"^다부처", "", s)
    s = re.sub(r"사업$", "", s)
    return s

def norm_ministry(m):
    return MINISTRY_LINEAGE.get(m, m)

def name_years():
    """수집된 과제연도기록에서 사업명(공백 제거)별 존재 연도와 최빈 부처."""
    p = os.path.join(INTERIM, "panel", "project_years.csv")
    yrs, mins = defaultdict(set), defaultdict(Counter)
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r["year"].isdigit():
                k = nospace(r["program_name"])
                yrs[k].add(int(r["year"])); mins[k][r["ministry"]] += 1
    return yrs, {k: v.most_common(1)[0][0] for k, v in mins.items()}

def aliases(cand_csv):
    """alias_suggestions.csv → 별칭 판정. candidates 의 aliases 열은 매번 판정 결과로 다시 쓴다.
    A_variant(자동 병합): 정규화 이름 동일 + 부처 계보 일치 + 동시 존재 없음(전환 연도 1년 겹침만 허용)
    A_review(병합 안 함): 정규화 이름은 같지만 부처가 다르거나 같은 해에 함께 존재 → 형제 사업 가능성
    B_identity_event: 이름이 다른 이전·후속 사업(통합·분할 사건 후보)
    수작업 판정은 data/interim/ntis/alias_overrides.csv (canonical_program, alias_name, decision=accept|reject, reason)로 덮어쓴다."""
    sug = list(csv.DictReader(open(os.path.join(INTERIM, "panel", "alias_suggestions.csv"), encoding="utf-8-sig")))
    cand = list(csv.DictReader(open(cand_csv, encoding="utf-8-sig")))
    cminis = {r["program_name"]: r["ministry"] for r in cand}
    ov_path = os.path.join(INTERIM, "alias_overrides.csv")
    overrides = {}
    if os.path.exists(ov_path):
        for r in csv.DictReader(open(ov_path, encoding="utf-8-sig")):
            overrides[(r["canonical_program"], r["alias_name"])] = (r["decision"].strip().lower(), r.get("reason", ""))
    yrs, name_min = name_years()
    # 이미 채택된 별칭도 같은 규칙으로 다시 판정(후속 과제로 찾은 별칭은 채택 뒤 제안 목록에서 빠지므로)
    have = {(r["canonical_program"], r["predecessor_program_name"]) for r in sug}
    for r in cand:
        for a_ in (r.get("aliases") or "").split(";"):
            a_ = a_.strip()
            if a_ and (r["program_name"], a_) not in have:
                sug.append({"canonical_program": r["program_name"], "predecessor_program_name": a_,
                            "ministry": name_min.get(nospace(a_), ""), "n_links": "", "years": "", "source": "existing_alias"})
    out, add = [], defaultdict(set)
    for r in sug:
        c, p = r["canonical_program"], r["predecessor_program_name"]
        cy, py_ = yrs.get(nospace(c), set()), yrs.get(nospace(p), set())
        overlap = sorted(cy & py_)
        transition = len(overlap) == 1 and py_ and cy and max(py_) == min(cy) == overlap[0]
        same_min = (norm_ministry(r["ministry"]) == norm_ministry(cminis.get(c, ""))
                    or "다부처" in (r["ministry"], cminis.get(c, "")))
        if not p or "SECRET" in p.upper():
            kind, why = "skip", "비공개 과제"
        elif nospace(c) == nospace(p):
            kind, why = "A_same", "공백만 다른 같은 이름(별칭 불필요)"
        elif norm_program(c) != norm_program(p):
            kind, why = "B_identity_event", "이름이 다른 이전·후속 사업"
        elif not same_min:
            kind, why = "A_review", "부처 계보 불일치"
        elif overlap and not transition:
            kind, why = "A_review", f"같은 해 동시 존재 {overlap}"
        else:
            kind, why = "A_variant", "표기 변형" + (f"(전환 연도 {overlap[0]})" if overlap else "")
        ov = overrides.get((c, p))
        if ov:
            kind, why = ("A_variant" if ov[0] == "accept" else "A_rejected"), "수작업: " + ov[1]
        if kind == "A_variant":
            add[c].add(p)
        r.setdefault("source", "suggestion")
        out.append(dict(r, kind=kind, reason=why, years_canonical=";".join(map(str, sorted(cy))),
                        years_alias=";".join(map(str, sorted(py_))), overlap=";".join(map(str, overlap))))
    write_csv(os.path.join(INTERIM, "panel", "alias_classified.csv"), out, list(out[0].keys()) if out else None)
    n_new = 0
    for r in cand:
        cur = {x.strip() for x in (r.get("aliases") or "").split(";") if x.strip()}
        new = add.get(r["program_name"], set())
        n_new += len(new - cur)
        r["aliases"] = ";".join(sorted(new))
    keys = list(cand[0].keys())
    if "aliases" not in keys:
        keys.append("aliases")
    write_csv(cand_csv, cand, keys)
    k = Counter(r["kind"] for r in out)
    print(f"[aliases] 표기 변형 {k['A_variant']}건(새 별칭 {n_new}개), 검토(병합 안 함) {k['A_review']}건, "
          f"수작업 기각 {k['A_rejected']}건, 이름이 다른 이전·후속 사업 {k['B_identity_event']}건 → alias_classified.csv")
    return n_new

# ───────────────────────── results ─────────────────────────

EP_RESULT = "public_result"
RESULT_COLS = {"rpaper": "PAP", "rpatent": "PAT"}

def flatten_result(h, coll):
    rec = {"result_id": g(h, "ResultID"), "result_year": g(h, "Year"), "project_id": g(h, "ProjectID"),
           "project_year": g(h, "ProjectYear"), "ntis_program_no": g(h, "BudgetProjectNumber"),
           "program_name": g(h, "BudgetProject"), "ministry": g(h, "MinistryName"),
           "tech_roadmap_code": g(h, "TechnologyRoadMap", "code"), "tech_roadmap": g(h, "TechnologyRoadMap"),
           "sc1_code": g(h, "ScienceClass1", "code"), "title": g(h, "ResultTitle")}
    if coll == "rpaper":
        rec.update(pub_year=g(h, "PubYear"), journal=g(h, "JournalName"), issn=g(h, "IssnNumber"),
                   paper_type_code=g(h, "PaperType", "code"), paper_type=g(h, "PaperType"), sci_type=g(h, "SciType"),
                   nation_type=g(h, "NationType"), jc_type=g(h, "JCType"))
    else:
        rec.update(country_code=g(h, "RegistCountry", "code"), regist_no=g(h, "RegistNumber"),
                   regist_type_code=g(h, "RegistType", "code"), regist_type=g(h, "RegistType"),
                   ipr_type_code=g(h, "IprType", "code"), ipr_type=g(h, "IprType"))
    return rec

def results(cl, batch=80, min_year=0):
    """panel 의 과제고유번호로 연계 성과(논문·특허)를 수집. 과제번호 OR 묶음 검색(searchFd=TI) → 묶음이 부정확하면 단건(TI03)."""
    pj = list(csv.DictReader(open(os.path.join(INTERIM, "panel", "project_years.csv"), encoding="utf-8-sig")))
    pids = sorted({r["project_id"] for r in pj if r["canonical_program"] and r["year"].isdigit() and int(r["year"]) >= min_year})
    outdir = os.path.join(INTERIM, "results"); os.makedirs(outdir, exist_ok=True)
    print(f"[results] 과제고유번호 {len(pids)}개, 묶음 {batch}개씩")
    for coll, dbt in RESULT_COLS.items():
        recs, stats = {}, Counter()
        for k in range(0, len(pids), batch):
            ids = pids[k:k + batch]; idset = set(ids)
            q = "|".join(ids)
            tag = hashlib.md5(q.encode()).hexdigest()[:10]
            start, total, got, other = 1, None, 0, 0
            while True:
                r = parse(cl.get(EP_RESULT, {"collection": coll, "SRWR": q, "searchFd": "TI", "addQuery": f"DBT={dbt}",
                                             "searchRnkn": "", "startPosition": start, "displayCnt": 1000, "userId": ""},
                                 f"results/{coll}/b_{tag}_{start}.xml.gz"))
                total = r["total"] if total is None else total
                if total > 30000:           # 묶음 검색이 과제번호 외 문자열까지 잡은 경우 → 단건 조회
                    break
                for h in r["hits"]:
                    rec = flatten_result(h, coll)
                    if rec["project_id"] in idset:
                        recs.setdefault(rec["result_id"], rec); got += 1
                    else:
                        other += 1
                start += 1000
                if not r["hits"] or start > total:
                    break
            if total > 30000:
                stats["fallback_batches"] += 1
                for pid in ids:
                    start = 1
                    while True:
                        r = parse(cl.get(EP_RESULT, {"collection": coll, "SRWR": "", "searchFd": "",
                                                     "addQuery": f"TI03={pid}&DBT={dbt}", "searchRnkn": "",
                                                     "startPosition": start, "displayCnt": 1000, "userId": ""},
                                         f"results/{coll}/one_{pid}_{start}.xml.gz"))
                        for h in r["hits"]:
                            rec = flatten_result(h, coll)
                            if rec["project_id"] == pid:
                                recs.setdefault(rec["result_id"], rec)
                        start += 1000
                        if not r["hits"] or start > r["total"]:
                            break
            stats["in_batch"] += got; stats["out_of_batch"] += other
            if (k // batch) % 20 == 0:
                print(f"  {coll} {min(k + batch, len(pids))}/{len(pids)}  성과 {len(recs)}건 (API {cl.calls}회)")
        rows = list(recs.values())
        write_csv(os.path.join(outdir, f"{coll}.csv"), rows, list(rows[0].keys()) if rows else None)
        print(f"[results] {coll}: {len(rows)}건, 묶음 밖 잡음 {stats['out_of_batch']}건, 단건 전환 묶음 {stats['fallback_batches']}개")

# ───────────────────────── main ─────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["probe", "programs", "all", "candidates", "panel", "aliases", "results"])
    ap.add_argument("--year", type=int, default=2023)
    ap.add_argument("--rps", type=float, default=4.0)
    ap.add_argument("--limit", type=int, default=None, help="사업별 조회 개수 제한(시험용)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--fields", default=",".join(FIELD_NAMES), help="국가전략기술 대분류 코드(쉼표 구분)")
    ap.add_argument("--min-share", type=float, default=0.5)
    ap.add_argument("--min-projects", type=int, default=10)
    ap.add_argument("--exclude", default=EXCLUDE_DEFAULT, help="제외 규칙(사업명 정규식). 빈 문자열이면 미적용")
    ap.add_argument("--candidates", default=None, help="panel 입력 CSV (기본: data/interim/ntis/candidates_<year>.csv)")
    ap.add_argument("--from-year", type=int, default=2015)
    ap.add_argument("--to-year", type=int, default=2024)
    ap.add_argument("--with-results", action="store_true", help="panel 뒤 성과(논문·특허)까지 수집")
    ap.add_argument("--alias-rounds", type=int, default=2, help="panel 뒤 표기 변형 별칭을 붙여 다시 수집하는 횟수")
    a = ap.parse_args()
    cl = Client(load_key(), rps=a.rps, refresh=a.refresh)
    t0 = time.time()
    try:
        if a.stage in ("probe", "all"):
            probe(cl, a.year)
        if a.stage in ("programs", "all"):
            programs(cl, a.year, a.limit)
        if a.stage == "candidates":
            candidates(cl, load_cfg(cl), a.year, [f.strip() for f in a.fields.split(",") if f.strip()],
                       a.min_share, a.min_projects, a.exclude)
        cand_csv = a.candidates or os.path.join(INTERIM, f"candidates_{a.year}.csv")
        if a.stage == "panel":
            panel(cl, load_cfg(cl), cand_csv, a.from_year, a.to_year)
            for rnd in range(a.alias_rounds):
                if not aliases(cand_csv):
                    break
                print(f"[panel] 별칭 반영 재수집 {rnd + 1}회차")
                panel(cl, load_cfg(cl), cand_csv, a.from_year, a.to_year)
        if a.stage == "aliases":
            aliases(cand_csv)
        if a.stage in ("results",) or (a.stage == "panel" and a.with_results):
            results(cl)
    except AuthError as e:
        sys.exit(f"[중단] {e}")
    finally:
        print(f"[끝] API 호출 {cl.calls}회, 캐시 {cl.cache_hits}회, {time.time() - t0:.0f}초")

if __name__ == "__main__":
    main()
