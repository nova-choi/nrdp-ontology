"""실데이터 포함 HermiT 추론 (v0.3.1 스키마 3모듈 + data/rdf 3파일).
1) 병합하여 owl:imports 를 제거한 N-Triples 생성  2) owlready2 내장 HermiT 로 일관성·만족가능성 검사
3) 추론 전후 개체 유형(rdf:type) 비교.  비일관이면 파일 단위로 나누어 다시 검사할 것.
옵션 --exclude-values FILE : FILE 에 적힌 IRI 의 mcdm:hasValue 문장을 제외하고 검사(원인 확인용)
실행: python analysis/hermit_real.py [프로젝트 루트] [--exclude-values FILE] [--java-mem 5200]
필요: rdflib, owlready2, Java. 1,066,292 트리플 기준 메모리 약 5GB, 수 분~수십 분 소요.
"""
import sys, os, time, argparse
from collections import Counter
import rdflib
from rdflib.namespace import OWL
import owlready2

ap = argparse.ArgumentParser()
ap.add_argument('root', nargs='?', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ap.add_argument('--exclude-values'); ap.add_argument('--java-mem', type=int, default=5200)
ap.add_argument('--files', default='schemes,domain,mcdm')
a = ap.parse_args()
SCHEMA = ['ontology/mcdm-core.ttl', 'ontology/kos-versioning.ttl', 'ontology/nrdp-ontology.ttl']
DATA = {k: f'data/rdf/nrdp-{k}.ttl' for k in ('schemes', 'domain', 'mcdm')}
files = SCHEMA + [DATA[k] for k in a.files.split(',') if k]
g = rdflib.Graph()
for f in files: g.parse(os.path.join(a.root, f))
g.remove((None, OWL.imports, None))
if a.exclude_values:
    MV = rdflib.URIRef('https://w3id.org/nrdp/mcdm#hasValue')
    for iri in open(a.exclude_values).read().split():
        g.remove((rdflib.URIRef(iri), MV, None))
out = os.path.abspath('hermit_input.nt'); g.serialize(out, format='nt', encoding='utf-8')
print('입력 트리플', len(g), flush=True)
owlready2.reasoning.JAVA_MEMORY = a.java_mem
w = owlready2.World(); onto = w.get_ontology('file://' + out).load()
NS = ('https://w3id.org/nrdp/', 'http://www.w3.org/ns/prov#', 'http://www.w3.org/2004/02/skos/core#', 'http://rdf-vocabulary.ddialliance.org/xkos#')
def types():
    q = "SELECT ?s ?c WHERE { ?s a ?c . FILTER(isIRI(?c)) }"
    return {(str(s), str(c)) for s, c in w.as_rdflib_graph().query(q)
            if str(s).startswith('https://w3id.org/nrdp/data#') and str(c).startswith(NS)}
before = types(); print('유형 선언 개체', len({s for s, _ in before}), '유형 문장', len(before), flush=True)
t = time.time()
try:
    with onto: owlready2.sync_reasoner_hermit(w, infer_property_values=False, debug=0)
    status = '일관'
except owlready2.OwlReadyInconsistentOntologyError:
    status = '비일관'
print('HermiT', status, f'{time.time() - t:.0f}초')
if status == '일관':
    print('만족불가능 클래스', [c.iri for c in w.inconsistent_classes()])
    after = types(); new, gone = after - before, before - after
    print('추론으로 추가된 유형', len(new), Counter(c.rsplit('#', 1)[-1] for _, c in new).most_common(20))
    print('더 구체적 유형으로 대체된 선언', len(gone), Counter(c.rsplit('#', 1)[-1] for _, c in gone).most_common(20))
