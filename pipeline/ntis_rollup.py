"""과제연도기록·성과 → 세부사업×연도 지표, 평가 창(window) 지표 집계 (RollupActivity 의 구현).

입력  data/interim/ntis/panel/project_years.csv, data/interim/ntis/results/rpaper.csv, rpatent.csv,
      data/interim/ntis/candidates_2023.csv (selected=Y, 분야, 별칭)
출력  data/interim/ntis/indicators/
      program_year.csv            사업×연도 지표(별칭 병합)
      program_year_noalias.csv    같은 지표, 별칭 병합 없이(정본 이름 기록만) — 동일성 판정 효과 비교용
      window_main_2021_2023.csv   주 평가: 2021–2023 창, 창 안 2년 이상 존속 사업
      window_sens_2022_2024.csv   민감도 A: 2022–2024 창, 3개년 모두 존속 사업
      window_sens_2023.csv        민감도 B: 2023 단년, 41개 전원
      alias_effect.csv            주 평가 창에서 별칭 병합 켬/끔 비교
      rollup_rules.json           집계 규칙(온톨로지 rollupRule 로 옮길 서술)

집계 규칙
  R1 단위: 정본 사업(canonical_program) × 과제 기준연도. 별칭(표기 변형)으로 수집한 기록은 정본으로 합산.
  R2 연구비: 과제연도기록의 정부연구비(GovernmentFunds) 합.
  R3 성과 귀속: 성과의 (과제고유번호, 과제기준연도)가 가리키는 과제연도기록의 정본 사업·연도로 귀속.
     성과 ID 기준 사업 내 중복 제거(사업 간 중복은 허용).
  R4 성과 시차: 과제연도 t 의 성과는 등록연도 t·t+1 분만 집계(연도별 미등록 성과 비율을 맞추기 위함).
     전체 기간 누적값은 *_all 열에 따로 둔다.
  R5 연속과제 추적(via=trace_*)으로만 들어온 기록은 정본 사업이 없으므로 집계 제외.
  R6 기여율은 공개 API에 없어 전량 귀속(기여율 1). OutputAttribution.contributionRate 는 비움.
  R8 별칭: candidates 의 aliases 열(판정 규칙 + alias_overrides.csv 수작업 판정)에 있는 이름의 기록만 정본으로 합산.
  R7 평가 창: 창 안 존속 연도의 연평균(연구비·성과), 효율 지표는 창 합계 성과 / 창 합계 연구비(억 원).
     이력 기준: 연구비 연평균 증감률(창 안 첫·끝 존속 연도), 계속과제 비율(ContinuousFlag=2), 사업 연차(2023 − 패널 첫 연도, 2015 하한).
실행: python pipeline/ntis_rollup.py [프로젝트 루트]
"""
import os, sys, re, csv, json, datetime
from collections import defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NT = os.path.join(ROOT, "data", "interim", "ntis")
OUT = os.path.join(NT, "indicators")
LAG = 1

def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))

def nospace(s):
    return re.sub(r"\s", "", s or "")

def wr(name, rows):
    if not rows:
        return
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def program_year(pj, results, cand):
    key = {(r["project_id"], r["year"]): r["canonical_program"] for r in pj}
    agg = defaultdict(lambda: defaultdict(float))
    for r in pj:
        a = agg[(r["canonical_program"], r["year"])]
        a["n_project_years"] += 1
        a["n_continuing"] += r["continuous_flag"] == "2"
        a["gov_funds_won"] += float(r["gov_funds"] or 0)
    seen, unmatched = set(), defaultdict(int)
    for coll, rows in results.items():
        for r in rows:
            c = key.get((r["project_id"], r["project_year"]))
            if not c:
                unmatched[coll] += 1
                continue
            sk = (c, r["project_year"], coll, r["result_id"])
            if sk in seen:
                continue
            seen.add(sk)
            a = agg[(c, r["project_year"])]
            try:
                in_lag = 0 <= int(r["result_year"]) - int(r["project_year"]) <= LAG
            except ValueError:
                in_lag = False
            if coll == "rpaper":
                sci = r["sci_type"] == "01"
                a["papers_all"] += 1; a["sci_all"] += sci
                if in_lag:
                    a["papers"] += 1; a["sci"] += sci
            else:
                reg = r["regist_type"] == "등록"
                a["patents_all"] += 1; a["pat_reg_all"] += reg
                if in_lag:
                    a["patents"] += 1; a["pat_reg"] += reg
    rows = []
    for (c, y), a in sorted(agg.items()):
        rows.append({"field": cand[c]["field_name"], "canonical_program": c, "year": int(y),
                     "n_project_years": int(a["n_project_years"]), "n_continuing": int(a["n_continuing"]),
                     "gov_funds_100m": round(a["gov_funds_won"] / 1e8, 3),
                     "papers": int(a["papers"]), "papers_sci": int(a["sci"]),
                     "patents": int(a["patents"]), "patent_registered": int(a["pat_reg"]),
                     "papers_all": int(a["papers_all"]), "papers_sci_all": int(a["sci_all"]),
                     "patents_all": int(a["patents_all"]), "patent_registered_all": int(a["pat_reg_all"])})
    return rows, dict(unmatched)

def window(py, cand, years, min_years, label):
    by = defaultdict(dict)
    for r in py:
        by[r["canonical_program"]][r["year"]] = r
    first = {c: min(v) for c, v in by.items()}
    out = []
    for c in sorted(cand, key=lambda c: (cand[c]["field_name"], c)):
        act = sorted(y for y in years if y in by.get(c, {}))
        rec = {"window": label, "field": cand[c]["field_name"], "canonical_program": c,
               "active_years": len(act), "first_active": act[0] if act else "", "last_active": act[-1] if act else "",
               "included": "Y" if len(act) >= min_years else ""}
        if act:
            rs = [by[c][y] for y in act]
            s = lambda k: sum(r[k] for r in rs)
            funds = s("gov_funds_100m"); n = len(act)
            f0, f1 = by[c][act[0]]["gov_funds_100m"], by[c][act[-1]]["gov_funds_100m"]
            span = act[-1] - act[0]
            rec.update({
                "avg_gov_funds_100m": round(funds / n, 2),
                "avg_projects": round(s("n_project_years") / n, 1),
                "avg_sci_papers": round(s("papers_sci") / n, 2),
                "avg_patents": round(s("patents") / n, 2),
                "avg_patent_registered": round(s("patent_registered") / n, 2),
                "sci_per_100m": round(s("papers_sci") / funds, 4) if funds else "",
                "patents_per_100m": round(s("patents") / funds, 4) if funds else "",
                "funds_cagr": round((f1 / f0) ** (1 / span) - 1, 4) if span and f0 > 0 and f1 > 0 else "",
                "continuing_ratio": round(s("n_continuing") / s("n_project_years"), 3) if s("n_project_years") else "",
                "program_age_2023": 2023 - max(first[c], 2015),
            })
        out.append(rec)
    return out

def main():
    os.makedirs(OUT, exist_ok=True)
    cand = {r["program_name"]: r for r in rd(os.path.join(NT, "candidates_2023.csv")) if r.get("selected", "").upper() == "Y"}
    names = {c: {nospace(c)} | {nospace(a) for a in (r.get("aliases") or "").split(";") if a.strip()} for c, r in cand.items()}
    pj_raw = [r for r in rd(os.path.join(NT, "panel", "project_years.csv")) if r["canonical_program"] in cand]
    # R8 현재 판정된 별칭만 채택: 수집 당시 별칭이었다가 검토에서 기각된 이름의 기록은 집계에서 뺀다
    pj_all = [r for r in pj_raw if nospace(r["program_name"]) in names[r["canonical_program"]]]
    dropped = len(pj_raw) - len(pj_all)
    results = {c: rd(os.path.join(NT, "results", f"{c}.csv")) for c in ("rpaper", "rpatent")}
    py, unmatched = program_year(pj_all, results, cand)
    pj_noalias = [r for r in pj_all if nospace(r["program_name"]) == nospace(r["canonical_program"])]
    py_na, _ = program_year(pj_noalias, results, cand)
    wr("program_year.csv", py); wr("program_year_noalias.csv", py_na)
    main_w = window(py, cand, range(2021, 2024), 2, "main_2021_2023")
    sens_a = window(py, cand, range(2022, 2025), 3, "sens_2022_2024")
    sens_b = window(py, cand, [2023], 1, "sens_2023")
    wr("window_main_2021_2023.csv", main_w); wr("window_sens_2022_2024.csv", sens_a); wr("window_sens_2023.csv", sens_b)
    na_w = {r["canonical_program"]: r for r in window(py_na, cand, range(2021, 2024), 2, "main_noalias")}
    eff = []
    for r in main_w:
        n = na_w[r["canonical_program"]]
        eff.append({"field": r["field"], "canonical_program": r["canonical_program"],
                    "active_years_alias": r["active_years"], "active_years_noalias": n["active_years"],
                    "included_alias": r["included"], "included_noalias": n["included"],
                    "avg_gov_funds_alias": r.get("avg_gov_funds_100m", ""), "avg_gov_funds_noalias": n.get("avg_gov_funds_100m", ""),
                    "funds_cagr_alias": r.get("funds_cagr", ""), "funds_cagr_noalias": n.get("funds_cagr", ""),
                    "sci_per_100m_alias": r.get("sci_per_100m", ""), "sci_per_100m_noalias": n.get("sci_per_100m", "")})
    wr("alias_effect.csv", eff)
    summ = {k: sum(1 for r in w if r["included"]) for k, w in
            (("main_2021_2023", main_w), ("sens_2022_2024", sens_a), ("sens_2023", sens_b))}
    summ["main_noalias"] = sum(1 for r in na_w.values() if r["included"])
    yr_rec = defaultdict(lambda: [0, 0])
    for r in pj_all:
        yr_rec[r["year"]][0] += 1
        yr_rec[r["year"]][1] += nospace(r["program_name"]) != nospace(r["canonical_program"])
    json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"),
               "rules": [l.strip() for l in __doc__.split("집계 규칙")[1].split("실행:")[0].strip().splitlines()],
               "unmatched_results": unmatched, "records_dropped_rejected_alias": dropped, "programs": len(cand), "program_year_rows": len(py),
               "included_alternatives": summ,
               "alias_share_by_year": {y: f"{v[1]}/{v[0]}" for y, v in sorted(yr_rec.items())}},
              open(os.path.join(OUT, "rollup_rules.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("포함 대안 수:", summ, "| 패널 밖 성과:", unmatched, "| 기각 별칭 기록 제외:", dropped)

if __name__ == "__main__":
    main()
