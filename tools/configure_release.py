#!/usr/bin/env python3
"""공개 전 자리표시자를 실제 값으로 바꾼다.

사용: python tools/configure_release.py --github-user <계정> [--email <연락처>] [--doi 10.5281/zenodo.NNNNNNN]

GITHUB_USER, CONTACT_EMAIL, ZENODO_DOI 자리표시자를 저장소의 텍스트 파일 전체(docs/, w3id/ 포함)에서 바꾼다.
DOI는 Zenodo에서 첫 릴리스가 보관된 뒤에 받으므로, 처음에는 --github-user 만 주고 실행하고
DOI를 받은 뒤 --doi 로 다시 실행한다.
"""
import argparse, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = {".md", ".ttl", ".html", ".json", ".jsonld", ".nt", ".owl", ".cff", ".csv", ".py", ".htaccess", ".txt", ".cypher"}
ap = argparse.ArgumentParser()
ap.add_argument("--github-user", required=True)
ap.add_argument("--doi")
ap.add_argument("--email", help="w3id 관리자 연락처 (w3id/nrdp/README.md)")
a = ap.parse_args()
rep = {"GITHUB_USER": a.github_user}
if a.doi:
    rep["ZENODO_DOI"] = a.doi
if a.email:
    rep["CONTACT_EMAIL"] = a.email
n = 0
for d, _, fs in os.walk(ROOT):
    if "/.git" in d:
        continue
    for f in fs:
        p = os.path.join(d, f)
        if os.path.splitext(f)[1] not in EXT and f != ".htaccess":
            continue
        if p == os.path.abspath(__file__):
            continue
        s = open(p, encoding="utf-8").read()
        t = s
        for k, v in rep.items():
            t = t.replace(k, v)
        if t != s:
            open(p, "w", encoding="utf-8").write(t); n += 1
print(f"{n}개 파일 갱신:", rep)
