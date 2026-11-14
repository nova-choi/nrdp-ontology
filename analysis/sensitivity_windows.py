#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""평가 창 민감도: 주 평가 창(2021–2023)과 민감도 창 A(2022–2024)·B(2023 단년)의 순위 비교.

계산식은 pipeline/mcdm_eval.py 와 같다(WSM min-max, TOPSIS 벡터, PROMETHEE II V-shape q=0 p=0.5, 시나리오 S1~S3).
  - 평가 대상: 창 파일의 included=Y 이고 사용 기준 전부에 값이 있는 사업.
      주 평가 32개(2개 연도 이상 존속), 민감도 A 26개(3개년 모두 존속), 민감도 B 41개(2023 존속 전원).
  - 민감도 B 는 연도가 하나라 '연구비 연평균 증감률(C_CAGR)'을 정의할 수 없다. 이 기준을 빼고
    나머지 7개 기준의 가중치를 비례 재조정(합 = 1)한다.
  - 정규화는 창마다 그 창의 평가 대상 집합 안에서 한다. 따라서 창 간 순위 차이에는 (1) 지표값의 변화와
    (2) 대안 집합의 변화가 함께 들어 있다. (2)를 떼어 보기 위해 주 평가 창을 각 민감도 창의 대상 집합으로
    좁혀 다시 계산한 '통제' 순위도 함께 낸다(주 평가 창 지표 + 민감도 창 대안 집합).
  - 비교 통계: 공통 사업으로 좁힌 뒤 다시 매긴 순위의 Kendall's tau-b, 상위 5위 중복 수, 순위 변동 최대값.
검증: 주 평가 창 계산 결과가 data/rdf/mcdm_results.csv 의 순위와 모두 같아야 한다(불일치 시 중단).
출력: analysis/sensitivity_windows_ranks.csv (창×시나리오×기법×사업 순위), analysis/sensitivity_windows_summary.csv
실행: python analysis/sensitivity_windows.py [프로젝트 루트]
"""
import os, sys, csv, math, re, hashlib
from collections import OrderedDict
from scipy.stats import kendalltau

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IND = os.path.join(ROOT, "data", "interim", "ntis", "indicators")
OUT = os.path.join(ROOT, "analysis")

def rd(p): return list(csv.DictReader(open(p, encoding="utf-8-sig")))
def nospace(s): return re.sub(r"\s", "", s or "")
def h8(s): return hashlib.sha1(nospace(s).encode("utf-8")).hexdigest()[:8]
def num(s):
    try: return float(s)
    except (TypeError, ValueError): return None

COL = OrderedDict([("C_FUND", ("avg_gov_funds_100m", "Cost")), ("C_CAGR", ("funds_cagr", "Benefit")),
                   ("C_SCI", ("avg_sci_papers", "Benefit")), ("C_PAT", ("avg_patents", "Benefit")),
                   ("C_PATREG", ("avg_patent_registered", "Benefit")), ("C_SCI_EFF", ("sci_per_100m", "Benefit")),
                   ("C_PAT_EFF", ("patents_per_100m", "Benefit")), ("C_CONT", ("continuing_ratio", "Benefit"))])
SCEN = OrderedDict([
    ("S1", {c: 0.125 for c in COL}),
    ("S2", {"C_FUND": 0.20, "C_CAGR": 0.05, "C_SCI": 0.05, "C_PAT": 0.05, "C_PATREG": 0.05, "C_SCI_EFF": 0.25, "C_PAT_EFF": 0.25, "C_CONT": 0.10}),
    ("S3", {"C_FUND": 0.05, "C_CAGR": 0.15, "C_SCI": 0.20, "C_PAT": 0.20, "C_PATREG": 0.20, "C_SCI_EFF": 0.05, "C_PAT_EFF": 0.05, "C_CONT": 0.10}),
])
SCEN_LB = {"S1": "균형형", "S2": "효율중심형", "S3": "성과규모중심형"}
METH_LB = {"M_WSM": "WSM", "M_TOPSIS": "TOPSIS", "M_PRO2": "PROMETHEE II"}
Q, P = 0.0, 0.5

def evaluate(rows, leaves, members=None):
    """rows: 창 파일 행. leaves: 사용 기준. members: 평가 대상 사업명 집합(None 이면 included=Y ∩ 값 완비)."""
    raw = {c: {} for c in leaves}
    for r in rows:
        if members is None and r["included"].upper() != "Y":
            continue
        if members is not None and r["canonical_program"] not in members:
            continue
        for c in leaves:
            v = num(r[COL[c][0]])
            if v is not None:
                raw[c][r["canonical_program"]] = v
    full = sorted(set.intersection(*(set(raw[c]) for c in leaves)))
    d = {c: COL[c][1] for c in leaves}
    def mm(c):
        vals = {p: raw[c][p] for p in full}; lo, hi = min(vals.values()), max(vals.values())
        return {k: (1.0 if hi == lo else ((v - lo) / (hi - lo) if d[c] == "Benefit" else (hi - v) / (hi - lo))) for k, v in vals.items()}
    def vec(c):
        vals = {p: raw[c][p] for p in full}; n = math.sqrt(sum(v * v for v in vals.values()))
        out = {k: (v / n if n else 0.0) for k, v in vals.items()}
        return {k: 1.0 - v for k, v in out.items()} if d[c] == "Cost" else out
    MM = {c: mm(c) for c in leaves}; VE = {c: vec(c) for c in leaves}
    def wsm(w): return {p: sum(w[c] * MM[c][p] for c in leaves) for p in full}
    def topsis(w):
        wv = {c: {p: w[c] * VE[c][p] for p in full} for c in leaves}
        b = {c: max(wv[c].values()) for c in leaves}; o = {c: min(wv[c].values()) for c in leaves}; res = {}
        for p in full:
            dp = math.sqrt(sum((wv[c][p] - b[c]) ** 2 for c in leaves)); dn = math.sqrt(sum((wv[c][p] - o[c]) ** 2 for c in leaves))
            res[p] = dn / (dp + dn) if (dp + dn) else 0.0
        return res
    def prom(w):
        def pref(c, a, b_):
            x = MM[c][a] - MM[c][b_]
            return 0.0 if x <= Q else (1.0 if x >= P else (x - Q) / (P - Q))
        n = len(full); phi = {}
        for a in full:
            plus = sum(sum(w[c] * pref(c, a, b_) for c in leaves) for b_ in full if b_ != a)
            minus = sum(sum(w[c] * pref(c, b_, a) for c in leaves) for b_ in full if b_ != a)
            phi[a] = (plus - minus) / (n - 1)
        return phi
    res = {}
    for sid, w0 in SCEN.items():
        s = sum(w0[c] for c in leaves); w = {c: w0[c] / s for c in leaves}   # 기준이 빠지면 비례 재조정
        for mid, fn in (("M_WSM", wsm), ("M_TOPSIS", topsis), ("M_PRO2", prom)):
            sc = fn(w); order = sorted(sc.items(), key=lambda kv: (-kv[1], h8(kv[0])))
            res[(sid, mid)] = {p: i + 1 for i, (p, _) in enumerate(order)}
    return full, res

def rerank(rank, keep):
    order = sorted(keep, key=lambda p: rank[p])
    return {p: i + 1 for i, p in enumerate(order)}

def main():
    ALL = list(COL)
    W = {"main": (rd(os.path.join(IND, "window_main_2021_2023.csv")), ALL, "주 평가 2021–2023"),
         "A": (rd(os.path.join(IND, "window_sens_2022_2024.csv")), ALL, "민감도 A 2022–2024"),
         "B": (rd(os.path.join(IND, "window_sens_2023.csv")), [c for c in ALL if c != "C_CAGR"], "민감도 B 2023 단년")}
    R = {k: evaluate(rows, lv) for k, (rows, lv, _) in W.items()}

    # 검증: 주 평가 창 = mcdm_results.csv (사업 ID 정렬 기준이 h8 이므로 동순위 처리까지 같아야 함)
    ref = rd(os.path.join(ROOT, "data", "rdf", "mcdm_results.csv"))
    bad = [(r["scenario"], r["method"], r["program"]) for r in ref
           if R["main"][1][(r["scenario"], r["method"])].get(r["program"]) != int(r["rank"])]
    if bad or len(ref) != 9 * len(R["main"][0]):
        sys.exit(f"주 평가 창 재계산이 mcdm_results.csv 와 다름: {bad[:5]} (행 {len(ref)})")
    print(f"검증: 주 평가 창 {len(R['main'][0])}개 × 9 조합 순위가 mcdm_results.csv 와 일치")

    with open(os.path.join(OUT, "sensitivity_windows_ranks.csv"), "w", newline="", encoding="utf-8-sig") as f:
        cw = csv.writer(f); cw.writerow(["window", "scenario", "method", "program", "rank", "n_alternatives"])
        for k, (full, res) in R.items():
            for (sid, mid), rk in res.items():
                for p in sorted(full, key=lambda x: rk[x]):
                    cw.writerow([k, sid, mid, p, rk[p], len(full)])

    rows_out = []
    print(f"\n대상 수: 주 {len(R['main'][0])}, A {len(R['A'][0])}, B {len(R['B'][0])}")
    for k in ("A", "B"):
        full_s, res_s = R[k]
        common = sorted(set(R["main"][0]) & set(full_s))
        # 통제: 주 평가 창 지표를 민감도 창 대상 집합(주 평가 창에도 있는 사업)으로 좁혀 다시 계산
        ctrl_full, ctrl = evaluate(W["main"][0], W[k][1], members=set(common))
        print(f"\n[{W[k][2]}] 공통 사업 {len(common)}개 (주 평가 창에만 {len(set(R['main'][0]) - set(full_s))}, 민감도 창에만 {len(set(full_s) - set(R['main'][0]))})")
        for sid in SCEN:
            for mid in METH_LB:
                a = rerank(R["main"][1][(sid, mid)], common); b = rerank(res_s[(sid, mid)], common)
                c = ctrl[(sid, mid)]
                tau = kendalltau([a[p] for p in common], [b[p] for p in common]).statistic
                tau_set = kendalltau([a[p] for p in common], [c[p] for p in common]).statistic   # 집합·기준 변화만
                tau_val = kendalltau([c[p] for p in common], [b[p] for p in common]).statistic   # 지표값 변화만
                top_a = {p for p in common if a[p] <= 5}; top_b = {p for p in common if b[p] <= 5}
                mx = max(abs(a[p] - b[p]) for p in common)
                rows_out.append([k, len(common), sid, mid, round(tau, 3), round(tau_set, 3), round(tau_val, 3), len(top_a & top_b), mx])
                print(f"  {SCEN_LB[sid]:6s} {METH_LB[mid]:12s} tau={tau:.3f} (집합·기준 {tau_set:.3f}, 지표값 {tau_val:.3f})  상위5 중복 {len(top_a & top_b)}/5  최대 변동 {mx}")
        # 창 간 강건 사업: 공통 사업 기준 세 시나리오·세 기법 모두에서 두 창 상위 5위
        robust = [p for p in common if all(rerank(R["main"][1][(s, m)], common)[p] <= 5 and rerank(res_s[(s, m)], common)[p] <= 5
                                           for s in SCEN for m in METH_LB)]
        print(f"  두 창·9개 조합 모두 상위 5위(공통 사업 기준): {robust}")
    with open(os.path.join(OUT, "sensitivity_windows_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        cw = csv.writer(f)
        cw.writerow(["window", "n_common", "scenario", "method", "kendall_tau_main_vs_window", "tau_set_effect", "tau_value_effect", "top5_overlap", "max_rank_shift"])
        cw.writerows(rows_out)

if __name__ == "__main__":
    main()
