#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""생존 편향 규모 추정: 2015–2023년 연도별 세부사업 목록(분야 무관)과 2023년 이전 종료 사업 수.

배경  대상 사업을 2023년 과제의 국가전략기술 분류로 선정했으므로, 2023년 이전에 끝난 사업은 범위에서 빠진다
      (논문 제3장 제9절 가항, 제5장 제2절 일곱째 한계). 그 규모를 분야와 무관한 기술 통계로 보고한다.
방법  연도별 과제검색 패싯(budgetprojectname)으로 세부사업명과 과제 수를 얻는다(ntis_collect.programs 와 같은 조회,
      패싯이 잘리면 부처별 패싯 → 페이지 스캔). 사업명은 ntis_collect.norm_program 으로 정규화해 연도 간 대조하고,
      출연연 운영비(EXCLUDE_DEFAULT)는 선정 규칙과 같이 제외한다.
      '2023년 미존속'은 정규화로 흡수되지 않는 명칭 변경까지 포함하므로 종료 사업 수의 상한이다.
입력  NTIS OpenAPI (키: .env, 등록 IP 에서 실행). 캐시: data/raw/ntis/programs/<연도>/
출력  data/interim/ntis/survival/program_years_all.csv   (정규화 사업명 × 연도 × 과제 수, 집계값만)
      data/interim/ntis/survival/survival_summary.csv     (연도별 사업 수, 2023년 미존속 사업 수·과제 비중)
실행  python pipeline/ntis_survival.py [--from-year 2015] [--to-year 2023] [--rps 4]
"""
import os, sys, re, csv, argparse, time, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ntis_collect as nc

def year_programs(cl, cfg, year):
    r0, bp, complete = nc.facet_programs(cl, cfg, year)
    source = "facet_all"
    if not complete:
        bp, source = [], "facet_by_ministry"
        for mname, _, _ in r0["facets"].get("ministryname", []):
            _, sub, ok = nc.facet_programs(cl, cfg, year, "PB02=" + nc.safe_name(mname), "min_" + mname)
            if not ok:
                sub, ok = nc.scan_names(cl, cfg, year, "PB02=" + nc.safe_name(mname), "min_" + mname)
                source = "facet+scan"
            bp.extend(sub)
    cnt = defaultdict(int)
    for n, _code, c in bp:
        cnt[n] += c
    return r0["total"], source, cnt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2015); ap.add_argument("--to-year", type=int, default=2023)
    ap.add_argument("--rps", type=float, default=4.0); ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    cl = nc.Client(nc.load_key(), rps=a.rps, refresh=a.refresh); cfg = nc.load_cfg(cl)
    excl = re.compile(nc.EXCLUDE_DEFAULT)
    out = os.path.join(nc.INTERIM, "survival"); os.makedirs(out, exist_ok=True)
    years = list(range(a.from_year, a.to_year + 1)); per = {}; meta = {}
    t0 = time.time()
    try:
        for y in years:
            yp = os.path.join(out, f"year_{y}.json")   # 연도별 집계 저장 — 다시 실행하면 원본 캐시를 다시 읽지 않는다
            if os.path.exists(yp) and not a.refresh:
                d = json.load(open(yp, encoding="utf-8")); total, source, cnt = d["total"], d["source"], d["cnt"]
            else:
                total, source, cnt = year_programs(cl, cfg, y)
                json.dump({"total": total, "source": source, "cnt": cnt}, open(yp, "w", encoding="utf-8"), ensure_ascii=False)
            agg = defaultdict(lambda: [0, set()])
            for n, c in cnt.items():
                if excl.search(n):
                    continue
                k = nc.norm_program(n)
                agg[k][0] += c; agg[k][1].add(n)
            per[y] = agg; meta[y] = (total, source)
            print(f"[{y}] 과제 {total}건, 세부사업명 {len(cnt)}개 → 정규화 {len(agg)}개 (출처 {source})", flush=True)
    except nc.AuthError as e:
        sys.exit(f"[중단] {e}")
    last = a.to_year
    with open(os.path.join(out, "program_years_all.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["norm_program", "year", "n_projects", "n_name_variants"])
        for y in years:
            for k, (c, names) in sorted(per[y].items()):
                w.writerow([k, y, c, len(names)])
    rows = []
    alive_last = set(per[last])
    for y in years[:-1]:
        ks = set(per[y]); gone = ks - alive_last
        pj = sum(per[y][k][0] for k in ks); pj_gone = sum(per[y][k][0] for k in gone)
        rows.append([y, meta[y][0], len(ks), len(gone), round(len(gone) / len(ks), 4) if ks else "", pj, pj_gone, round(pj_gone / pj, 4) if pj else ""])
    # 주 평가 창 안(2021–2022)에 존속했으나 2023년에는 없는 사업 — 2023년 기준 선정으로 창에서 빠지는 규모
    win = set(per.get(2021, {})) | set(per.get(2022, {}))
    gone_w = win - alive_last
    rows.append(["2021–2022", "", len(win), len(gone_w), round(len(gone_w) / len(win), 4) if win else "",
                 sum(per[y][k][0] for y in (2021, 2022) if y in per for k in per[y]),
                 sum(per[y][k][0] for y in (2021, 2022) if y in per for k in per[y] if k in gone_w), ""])
    with open(os.path.join(out, "survival_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["year", "total_projects_api", "n_programs", f"n_absent_in_{last}", "share_programs_absent",
                    "n_projects_programs", "n_projects_absent_programs", "share_projects_absent"])
        w.writerows(rows)
    for r in rows:
        print("  ", r)
    print(f"[끝] API 호출 {cl.calls}회, 캐시 {cl.cache_hits}회, {time.time() - t0:.0f}초 → {out}")

if __name__ == "__main__":
    main()
