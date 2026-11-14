#!/usr/bin/env python3
"""역량질문 세트(cq/) 생성: python tools/build_cq.py . <논문 MD 경로>  (논문 [표 3-2]에서 일반형 질문·원천을 읽는다)"""
import sys, re, csv, json, importlib.util, pathlib
R = pathlib.Path(sys.argv[1]); thesis = pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')
spec = importlib.util.spec_from_file_location('q', R/'queries_sparql_real.py'); q = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(R)); spec.loader.exec_module(q)
PREFIX = q.PREFIX
# Cypher 블록
cy = (R/'queries_real.cypher').read_text(encoding='utf-8')
blocks = {}
for m in re.finditer(r'^// CQ(\d+)(-b)?[\. ](.*?)(?=^// CQ\d|\Z)', cy, re.S | re.M):
    key = m.group(1) + ('b' if m.group(2) else '')
    body = m.group(0).split('\n', 1)[1].strip()
    blocks[key] = body
# 논문 [표 3-2]
tab = {}
cat = None
for line in thesis.split('\n'):
    mm = re.match(r'^\| (\*\*([A-D])\. ([^*]+)\*\*)? ?\| CQ(\d+) \| (.+?) \| (.+?) \|$', line)
    if mm:
        if mm.group(2): cat = f'{mm.group(2)}. {mm.group(3)}'
        tab[int(mm.group(4))] = (cat, mm.group(5), mm.group(6))
assert len(tab) == 25, len(tab)
# 실데이터 대조 결과
cmp = {}
for line in (R/'data/rdf/compare-results-real.txt').read_text(encoding='utf-8').split('\n'):
    mm = re.match(r'\s*CQ(\d+)(B)?\s+✓\s+일치 \((\d+)행\)', line)
    if mm: cmp[mm.group(1) + ('b' if mm.group(2) else '')] = int(mm.group(3))
RQ = {'A': '연구질문 1', 'B': '연구질문 2', 'C': '연구질문 2', 'D': '연구질문 3', 'E': '연구질문 1'}
rows = []
for key, (desc, sparql) in q.CQ.items():
    k = str(key); n = int(re.match(r'\d+', k).group())
    aux = k.endswith('b')
    if n <= 25:
        c, generic, src = tab[n]
    else:
        c, generic, src = 'E. 실데이터 구조', '', 'S1'
    if k in ('24', '25'):
        mode = '절차적 계산 후 재적재한 결과를 질의로 조회'
    else:
        mode = '질의 단독'
    rows.append({
        'id': f'CQ{n}' + ('b' if aux else ''),
        'category': c, 'auxiliary': 'Y' if aux else 'N',
        'question_general_ko': '' if aux else generic,
        'question_instantiated_ko': desc,
        'derivation_source': '' if aux else src,
        'research_question': RQ[c[0]],
        'answer_mode_real_v0.3.4': mode,
        'result_rows_real_v0.3.4': cmp.get(k, ''),
        'sparql_cypher_match': 'Y' if k in cmp else '',
        'sparql': (PREFIX + sparql).strip() if sparql else '',
        'cypher': blocks.get(k, ''),
    })
out = R/'cq'; out.mkdir(exist_ok=True)
with open(out/'competency-questions.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
json.dump(rows, open(out/'competency-questions.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(rows), sum(1 for r in rows if r['sparql_cypher_match']=='Y'), [r['id'] for r in rows if not r['cypher']])
