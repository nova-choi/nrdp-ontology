#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/rdf/*.ttl 구문·어휘 검사.

  1. rdflib 로 파싱 (구문 오류 탐지), 트리플 수
  2. 데이터가 쓰는 클래스·속성이 ontology/*.ttl 또는 외부 표준 어휘(skos·prov·org·dcterms·rdfs)에 선언돼 있는지
  3. 클래스별 인스턴스 수, 속성별 사용 수 → data/rdf/check_report.txt

실행: python pipeline/rdf_check.py [프로젝트 루트] [--files a.ttl b.ttl ...]
"""
import os, sys, time
from collections import Counter
from rdflib import Graph, RDF, RDFS, OWL, Namespace, URIRef

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[1:]
if args and not args[0].startswith("--"):
    ROOT = args.pop(0)
RDFD = os.path.join(ROOT, "data", "rdf")
files = args[1:] if args and args[0] == "--files" else ["nrdp-schemes.ttl", "nrdp-domain.ttl", "nrdp-mcdm.ttl"]
files = [os.path.join(RDFD, f) if not os.path.isabs(f) else f for f in files if os.path.exists(os.path.join(RDFD, f)) or os.path.isabs(f)]

onto = Graph()
for f in ("mcdm-core.ttl", "kos-versioning.ttl", "nrdp-ontology.ttl"):
    onto.parse(os.path.join(ROOT, "ontology", f), format="turtle")
declared_classes = set(onto.subjects(RDF.type, OWL.Class)) | set(onto.subjects(RDF.type, RDFS.Class))
declared_props = set()
for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property):
    declared_props |= set(onto.subjects(RDF.type, t))
STD = ("http://www.w3.org/2004/02/skos/core#", "http://www.w3.org/ns/prov#", "http://www.w3.org/ns/org#",
       "http://purl.org/dc/terms/", "http://www.w3.org/2000/01/rdf-schema#", "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
       "http://rdf-vocabulary.ddialliance.org/xkos#")
def is_std(u):
    return any(str(u).startswith(p) for p in STD)

out = []
g = Graph()
for f in files:
    t0 = time.time()
    g.parse(f, format="turtle")
    out.append(f"파싱 OK  {os.path.basename(f):22s} 누적 트리플 {len(g):>9,}  ({time.time()-t0:.1f}s)")
cls = Counter(o for o in g.objects(None, RDF.type))
props = Counter(p for p in g.predicates(None, None))
undecl_c = sorted(c for c in cls if c not in declared_classes and not is_std(c))
undecl_p = sorted(p for p in props if p not in declared_props and not is_std(p))
out.append("")
out.append(f"미선언 클래스 {len(undecl_c)}: " + ", ".join(str(c) for c in undecl_c))
out.append(f"미선언 속성   {len(undecl_p)}: " + ", ".join(str(p) for p in undecl_p))
dep = [p for p in props if (p, OWL.deprecated, None) in onto]
out.append(f"폐기 속성 사용 {len(dep)}: " + ", ".join(str(p) for p in dep))
out.append("")
out.append("클래스별 인스턴스 수")
for c, n in sorted(cls.items(), key=lambda kv: -kv[1]):
    out.append(f"  {str(c).split('#')[-1].split('/')[-1]:32s} {n:>8,}")
out.append("")
out.append("속성별 사용 수")
for p, n in sorted(props.items(), key=lambda kv: -kv[1]):
    out.append(f"  {str(p).split('#')[-1].split('/')[-1]:32s} {n:>9,}")
text = "\n".join(out)
print(text)
open(os.path.join(RDFD, "check_report.txt"), "w", encoding="utf-8").write(text + "\n")
