#!/usr/bin/env python3
"""GitHub Pages용 공개 사이트(docs/) 생성기.

- 온톨로지 모듈별 HTML 문서(용어마다 지역명 앵커 → 해시 IRI가 그대로 문서 위치가 됨)
- 직렬화 4종(Turtle, RDF/XML, JSON-LD, N-Triples), 현재 버전과 버전별 사본
- SHACL shape, 데이터셋 설명(VoID/DCAT), 역량질문 세트 페이지, 첫 화면

실행: python tools/build_site.py            (저장소 루트에서)
설정: tools/configure_release.py 로 nova-choi, ZENODO_DOI 를 실제 값으로 바꾼 뒤 실행한다.
"""
import csv, html, json, os, shutil, sys
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS = os.path.join(ROOT, "docs")
SH = Namespace("http://www.w3.org/ns/shacl#")
VANN = Namespace("http://purl.org/vocab/vann/")

MODULES = [  # (경로 이름, 파일, 이전 버전 사본 폴더)
    ("mcdm", "ontology/mcdm-core.ttl"),
    ("ontology", "ontology/nrdp-ontology.ttl"),
    ("kosv", "ontology/kos-versioning.ttl"),
]
SHAPES = [("mcdm", "ontology/mcdm-shapes.ttl"), ("kosv", "ontology/kosv-shapes.ttl")]
RELEASES = os.path.join(ROOT, "ontology", "releases")  # releases/<버전>/<파일>

FORMATS = [("ttl", "turtle"), ("owl", "xml"), ("jsonld", "json-ld"), ("nt", "nt")]

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mute:#5d5b55;--line:#dedad2;--acc:#1f5f8b;--chip:#eef2f5}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#e9e6df;--mute:#a7a39a;--line:#34322e;--acc:#7fb4dc;--chip:#23292e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 "Noto Sans KR","Apple SD Gothic Neo",system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:32px 16px 80px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:40px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:16px;margin:26px 0 4px}a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.meta{color:var(--mute);font-size:13.5px}table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{font-weight:600;white-space:nowrap}
code{font:13px/1.4 ui-monospace,Menlo,Consolas,monospace;background:var(--chip);padding:1px 4px;border-radius:3px;word-break:break-all}
.term{border-top:1px solid var(--line);padding:10px 0}.term h3{margin:0}.kv{display:grid;grid-template-columns:140px 1fr;gap:2px 12px;font-size:14px;margin-top:4px}
.kv div:nth-child(odd){color:var(--mute)}.toc a{display:inline-block;margin:0 10px 4px 0}.wrap{overflow-x:auto}
"""


def esc(x):
    return html.escape(str(x))


def page(title, body):
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<style>{CSS}</style></head><body><main>{body}</main></body></html>')


def lit(g, s, p):
    vals = list(g.objects(s, p))
    by = {}
    for v in vals:
        by.setdefault(getattr(v, "language", None), []).append(str(v))
    return by


def label(g, s):
    by = lit(g, s, RDFS.label)
    ko, en = (by.get("ko") or [""])[0], (by.get("en") or [""])[0]
    return ko, en


def qname(g, u):
    try:
        return g.namespace_manager.normalizeUri(u)
    except Exception:
        return str(u)


def render(g, n, base):
    """클래스 식을 간단한 DL 표기로."""
    if isinstance(n, URIRef):
        s = str(n)
        if s.startswith(base + "#"):
            return f'<a href="#{esc(s.split("#")[1])}">{esc(qname(g, n))}</a>'
        return f"<code>{esc(qname(g, n))}</code>"
    if isinstance(n, Literal):
        return f"<code>{esc(n)}</code>"
    for op, sym in ((OWL.intersectionOf, " ⊓ "), (OWL.unionOf, " ⊔ ")):
        lst = g.value(n, op)
        if lst is not None:
            return "(" + sym.join(render(g, x, base) for x in Collection(g, lst)) + ")"
    lst = g.value(n, OWL.oneOf)
    if lst is not None:
        return "{" + ", ".join(render(g, x, base) for x in Collection(g, lst)) + "}"
    p = g.value(n, OWL.onProperty)
    if p is not None:
        P = render(g, p, base)
        for k, sym in ((OWL.someValuesFrom, "∃"), (OWL.allValuesFrom, "∀")):
            v = g.value(n, k)
            if v is not None:
                return f"{sym}{P}.{render(g, v, base)}"
        v = g.value(n, OWL.hasValue)
        if v is not None:
            return f"∃{P}.{{{render(g, v, base)}}}"
        for k, sym in ((OWL.qualifiedCardinality, "="), (OWL.minQualifiedCardinality, "≥"), (OWL.maxQualifiedCardinality, "≤"),
                       (OWL.cardinality, "="), (OWL.minCardinality, "≥"), (OWL.maxCardinality, "≤")):
            v = g.value(n, k)
            if v is not None:
                c = g.value(n, OWL.onClass) or g.value(n, OWL.onDataRange)
                return f"{sym}{v} {P}" + (f".{render(g, c, base)}" if c is not None else "")
    dt = g.value(n, OWL.onDatatype)
    if dt is not None:
        parts = []
        lst = g.value(n, OWL.withRestrictions)
        if lst is not None:
            for r in Collection(g, lst):
                for k, v in g.predicate_objects(r):
                    parts.append(f"{qname(g, k).split(':')[-1]} {v}")
        return f"{render(g, dt, base)}[{', '.join(parts)}]"
    return "<i>익명 식</i>"


def module_doc(key, path):
    g = Graph().parse(os.path.join(ROOT, path))
    onto = next(g.subjects(RDF.type, OWL.Ontology))
    base = str(onto)
    ver = str(g.value(onto, OWL.versionInfo))
    title = lit(g, onto, DCTERMS.title)
    desc = lit(g, onto, DCTERMS.description)
    outdir = os.path.join(DOCS, key)
    os.makedirs(outdir, exist_ok=True)

    def terms(t):
        xs = [s for s in g.subjects(RDF.type, t) if isinstance(s, URIRef) and str(s).startswith(base + "#")]
        return sorted(set(xs), key=lambda u: str(u).split("#")[1])

    groups = [("클래스", terms(OWL.Class)), ("객체 속성", terms(OWL.ObjectProperty)),
              ("데이터 속성", terms(OWL.DatatypeProperty)), ("명명 개체", terms(OWL.NamedIndividual))]
    files = " · ".join(f'<a href="ontology.{e}">{e.upper()}</a>' for e, _ in FORMATS)
    head = (f'<p class="meta"><a href="../index.html">nrdp 자원 목록</a></p>'
            f'<h1>{esc((title.get("ko") or [""])[0])}</h1>'
            f'<p class="meta">{esc((title.get("en") or [""])[0])}</p>'
            f'<div class="kv"><div>IRI</div><div><code>{esc(base)}</code></div>'
            f'<div>버전</div><div>{esc(ver)} (<code>{esc(g.value(onto, OWL.versionIRI))}</code>)</div>'
            f'<div>이전 버전</div><div><code>{esc(g.value(onto, OWL.priorVersion) or "-")}</code></div>'
            f'<div>작성자</div><div>{esc(g.value(onto, DCTERMS.creator) or "")}</div>'
            f'<div>라이선스</div><div><a href="{esc(g.value(onto, DCTERMS.license))}">CC BY 4.0</a></div>'
            f'<div>접두어</div><div><code>{esc(g.value(onto, VANN.preferredNamespacePrefix) or "")}:</code> '
            f'<code>{esc(g.value(onto, VANN.preferredNamespaceUri) or "")}</code></div>'
            f'<div>가져오기</div><div>{", ".join(f"<code>{esc(i)}</code>" for i in g.objects(onto, OWL.imports)) or "-"}</div>'
            f'<div>내려받기</div><div>{files}</div></div>'
            + "".join(f"<p>{esc(d)}</p>" for d in (desc.get("ko") or []) + (desc.get("en") or []))
            + '<p class="toc">' + "".join(f'<a href="#sec{i}">{n} ({len(xs)})</a>' for i, (n, xs) in enumerate(groups) if xs) + "</p>")
    body = [head]
    for i, (name, xs) in enumerate(groups):
        if not xs:
            continue
        body.append(f'<h2 id="sec{i}">{name}</h2>')
        for u in xs:
            ln = str(u).split("#")[1]
            ko, en = label(g, u)
            rows = [("IRI", f"<code>{esc(u)}</code>")]
            if en:
                rows.append(("영문 레이블", esc(en)))
            for c in g.objects(u, RDFS.comment):
                rows.append(("설명", esc(c)))
            sup = [render(g, x, base) for x in g.objects(u, RDFS.subClassOf)]
            if sup:
                rows.append(("상위 클래스·제약", "<br>".join(sup)))
            eq = [render(g, x, base) for x in g.objects(u, OWL.equivalentClass)]
            if eq:
                rows.append(("동치", "<br>".join(eq)))
            dj = [render(g, x, base) for x in g.objects(u, OWL.disjointWith)]
            if dj:
                rows.append(("배타", ", ".join(dj)))
            sp = [render(g, x, base) for x in g.objects(u, RDFS.subPropertyOf)]
            if sp:
                rows.append(("상위 속성", ", ".join(sp)))
            for k, nm in ((RDFS.domain, "도메인"), (RDFS.range, "레인지"), (OWL.inverseOf, "역속성")):
                v = [render(g, x, base) for x in g.objects(u, k)]
                if v:
                    rows.append((nm, ", ".join(v)))
            ch = [qname(g, t).split(":")[-1] for t in g.objects(u, RDF.type)
                  if t in (OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.TransitiveProperty,
                           OWL.SymmetricProperty, OWL.AsymmetricProperty, OWL.ReflexiveProperty, OWL.IrreflexiveProperty)]
            if ch:
                rows.append(("특성", ", ".join(ch)))
            if (u, OWL.deprecated, Literal(True)) in g:
                rows.append(("상태", "폐기(deprecated)"))
            kv = "".join(f"<div>{a}</div><div>{b}</div>" for a, b in rows)
            body.append(f'<div class="term" id="{esc(ln)}"><h3>{esc(ko or ln)} <span class="meta">'
                        f'<code>{esc(qname(g, u))}</code></span></h3><div class="kv">{kv}</div></div>')
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(f"{(title.get('ko') or [key])[0]} {ver}", "".join(body)))
    serialize(g, outdir, "ontology")
    vdir = os.path.join(outdir, ver)
    os.makedirs(vdir, exist_ok=True)
    serialize(g, vdir, "ontology")
    return dict(key=key, iri=base, ver=ver, title_ko=(title.get("ko") or [""])[0], n=[len(x) for _, x in groups])


def serialize(g, outdir, stem):
    for ext, fmt in FORMATS:
        g.serialize(destination=os.path.join(outdir, f"{stem}.{ext}"), format=fmt, encoding="utf-8")


def releases():
    """ontology/releases/<버전>/ 의 이전 버전 파일을 해당 버전 IRI 경로로 복사."""
    out = []
    if not os.path.isdir(RELEASES):
        return out
    for ver in sorted(os.listdir(RELEASES)):
        for fn in sorted(os.listdir(os.path.join(RELEASES, ver))):
            if not fn.endswith(".ttl"):
                continue
            g = Graph().parse(os.path.join(RELEASES, ver, fn))
            heads = list(g.subjects(RDF.type, OWL.Ontology))
            key = {"https://w3id.org/nrdp/mcdm": "mcdm", "https://w3id.org/nrdp/ontology": "ontology",
                   "https://w3id.org/nrdp/kosv": "kosv", "https://w3id.org/nrdp/shapes/mcdm": "shapes/mcdm",
                   "https://w3id.org/nrdp/shapes/kosv": "shapes/kosv"}.get(str(heads[0]) if heads else "")
            if fn.startswith("mcdm-shapes"):
                key = "shapes/mcdm"
            elif fn.startswith("kosv-shapes"):
                key = "shapes/kosv"
            if not key:
                continue
            fv = str(g.value(heads[0], OWL.versionInfo)) if heads and key in ("mcdm", "ontology", "kosv") else ver.replace("kosv-", "")
            d = os.path.join(DOCS, key, fv)
            os.makedirs(d, exist_ok=True)
            serialize(g, d, "shapes" if key.startswith("shapes") else "ontology")
            out.append((key, fv))
    return out


def shapes_doc():
    out = []
    for key, path in SHAPES:
        g = Graph().parse(os.path.join(ROOT, path))
        head = next(s for s in g.subjects(RDF.type, OWL.Ontology) if "/shapes/" in str(s))
        ver = str(g.value(head, OWL.versionInfo))
        d = os.path.join(DOCS, "shapes", key)
        os.makedirs(os.path.join(d, ver), exist_ok=True)
        serialize(g, d, "shapes")
        serialize(g, os.path.join(d, ver), "shapes")
        rows = []
        for s in sorted(set(g.subjects(RDF.type, SH.NodeShape)), key=str):
            msgs = [str(m) for c in g.objects(s, SH.sparql) for m in g.objects(c, SH.message)]
            msgs += [str(m) for m in g.objects(s, SH.message)]
            sev = g.value(s, SH.severity)
            tgt = g.value(s, SH.targetClass)
            rows.append(f"<tr><td><code>{esc(qname(g, s))}</code></td><td><code>{esc(qname(g, tgt) if tgt else '')}</code></td>"
                        f"<td>{esc(qname(g, sev).split(':')[-1] if sev else 'Violation')}</td><td>{'<br>'.join(esc(m) for m in msgs)}</td></tr>")
        t = lit(g, head, DCTERMS.title)
        body = (f'<p class="meta"><a href="../../index.html">nrdp 자원 목록</a></p><h1>{esc(t.get("ko", [""])[0])}</h1>'
                f'<div class="kv"><div>IRI</div><div><code>{esc(head)}</code></div><div>버전</div><div>{esc(ver)}</div>'
                f'<div>대상 어휘</div><div><code>{esc(g.value(head, DCTERMS.requires))}</code></div>'
                f'<div>내려받기</div><div>' + " · ".join(f'<a href="shapes.{e}">{e.upper()}</a>' for e, _ in FORMATS) + "</div></div>"
                f'<div class="wrap"><table><tr><th>shape</th><th>대상 클래스</th><th>심각도</th><th>메시지</th></tr>{"".join(rows)}</table></div>')
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(page(f"{t.get('ko', [key])[0]} {ver}", body))
        out.append(dict(key=f"shapes/{key}", iri=str(head), ver=ver, title_ko=t.get("ko", [""])[0], n=len(rows)))
    return out


def data_doc():
    d = os.path.join(DOCS, "data")
    os.makedirs(d, exist_ok=True)
    g = Graph().parse(os.path.join(ROOT, "data", "void.ttl"))
    serialize(g, d, "void")
    DCAT = Namespace("http://www.w3.org/ns/dcat#")
    VOID = Namespace("http://rdfs.org/ns/void#")
    ds = URIRef("https://w3id.org/nrdp/data")
    t = lit(g, ds, DCTERMS.title)
    rows = []
    for dist in g.objects(ds, DCAT.distribution):
        rows.append(f"<tr><td>{esc(g.value(dist, DCTERMS.title) or '')}</td><td>{int(g.value(dist, VOID.triples)):,}</td>"
                    f"<td><a href=\"{esc(g.value(dist, DCAT.downloadURL))}\">{esc(str(g.value(dist, DCAT.downloadURL)).rsplit('/', 1)[-1])}</a></td></tr>")
    kv = [("IRI", f"<code>{ds}</code>"), ("버전", esc(g.value(ds, DCAT.version))), ("라이선스", "CC BY 4.0 (원자료 공공누리 제1유형, 출처표시)"),
          ("출처", esc(g.value(ds, DCTERMS.source) and g.value(g.value(ds, DCTERMS.source), DCTERMS.title) or "")),
          ("트리플", f"{int(g.value(ds, VOID.triples)):,}"), ("기록 보관", esc(g.value(ds, DCTERMS.isReferencedBy) or "Zenodo DOI (발급 후 기재)"))]
    body = (f'<p class="meta"><a href="../index.html">nrdp 자원 목록</a></p><h1>{esc(t.get("ko", [""])[0])}</h1>'
            '<div class="kv">' + "".join(f"<div>{a}</div><div>{b}</div>" for a, b in kv) + "</div>"
            + "".join(f"<p>{esc(x)}</p>" for x in lit(g, ds, DCTERMS.description).get("ko", []))
            + f'<h2>배포 파일</h2><div class="wrap"><table><tr><th>파일</th><th>트리플</th><th>내려받기</th></tr>{"".join(rows)}</table></div>'
            + '<p class="meta">데이터셋 설명: <a href="void.ttl">void.ttl</a> (VoID·DCAT)</p>')
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(t.get("ko", ["데이터"])[0], body))
    return dict(key="data", iri=str(ds), ver=str(g.value(ds, DCAT.version)), title_ko=t.get("ko", [""])[0])


def cq_doc():
    d = os.path.join(DOCS, "cq")
    os.makedirs(d, exist_ok=True)
    for fn in ("competency-questions.csv", "competency-questions.json"):
        shutil.copy(os.path.join(ROOT, "cq", fn), d)
    rows = list(csv.DictReader(open(os.path.join(ROOT, "cq", "competency-questions.csv"), encoding="utf-8-sig")))
    tr = "".join(f'<tr id="{esc(r["id"])}"><td>{esc(r["id"])}</td><td>{esc(r["category"])}</td>'
                 f'<td>{esc(r["question_general_ko"] or r["question_instantiated_ko"])}</td><td>{esc(r["derivation_source"])}</td>'
                 f'<td>{esc(r["answer_mode_real_v0.3.4"])}</td><td>{esc(r["sparql_cypher_match"])}</td></tr>' for r in rows)
    body = ('<p class="meta"><a href="../index.html">nrdp 자원 목록</a></p><h1>역량질문 세트</h1>'
            '<div class="kv"><div>IRI</div><div><code>https://w3id.org/nrdp/cq</code></div><div>버전</div><div>0.3.4 (실데이터 기준)</div>'
            '<div>라이선스</div><div>질문 문안 CC BY 4.0, 질의 코드 MIT</div>'
            '<div>내려받기</div><div><a href="competency-questions.csv">CSV</a> · <a href="competency-questions.json">JSON</a> '
            '(SPARQL·Cypher 질의문 포함)</div></div>'
            '<p>도출 원천 S1: 혁신법 시행규칙 서식·NTIS 항목, S2: 과학기술기본계획 정책목표, S3: 세 기법의 요구 파라미터, '
            'S4: 정책 선호 교체·비교(연구질문 2), S5: 설명 요구(연구질문 3).</p>'
            f'<div class="wrap"><table><tr><th>ID</th><th>범주</th><th>역량질문</th><th>원천</th><th>응답 방식</th><th>SPARQL–Cypher 일치</th></tr>{tr}</table></div>')
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(page("역량질문 세트", body))
    return dict(key="cq", iri="https://w3id.org/nrdp/cq", ver="0.3.4", title_ko="역량질문 세트", n=len(rows))


def landing(mods, shp, data, cq, rel):
    gh = "https://github.com/nova-choi/nrdp-ontology"
    rows = []
    for m in mods:
        rows.append((m["title_ko"], m["iri"], m["ver"], f'{m["key"]}/index.html', f"클래스 {m['n'][0]}, 객체 속성 {m['n'][1]}, 데이터 속성 {m['n'][2]}"))
    for s in shp:
        rows.append((s["title_ko"], s["iri"], s["ver"], f'{s["key"]}/index.html', f"shape {s['n']}"))
    rows.append((data["title_ko"], data["iri"], data["ver"], "data/index.html", "VoID·DCAT 설명 포함"))
    rows.append((cq["title_ko"], cq["iri"], cq["ver"], "cq/index.html", f"질의 {cq['n']}개(보조 2 포함)"))
    tr = "".join(f'<tr><td><a href="{h}">{esc(t)}</a></td><td><code>{esc(i)}</code></td><td>{esc(v)}</td><td>{esc(n)}</td></tr>' for t, i, v, h, n in rows)
    old = ", ".join(sorted({f"{k} {v}" for k, v in rel})) or "-"
    body = ('<h1>국가 R&amp;D 포트폴리오 MCDM 온톨로지 (nrdp)</h1>'
            '<p class="meta">방법 중립적 MCDM 표현 계층, 국가 R&amp;D 도메인 계층, NTIS 실데이터 지식그래프</p>'
            f'<h2>자원</h2><div class="wrap"><table><tr><th>자원</th><th>IRI</th><th>버전</th><th>구성</th></tr>{tr}</table></div>'
            f'<p class="meta">이전 버전 사본: {esc(old)}. 버전 IRI(예: <code>https://w3id.org/nrdp/mcdm/0.3.4</code>)로 접근한다.</p>'
            '<h2>이용</h2><p>모든 IRI는 w3id.org에서 내용 협상(content negotiation)으로 응답한다. '
            '브라우저는 이 문서로, <code>Accept: text/turtle</code>·<code>application/rdf+xml</code>·<code>application/ld+json</code>·'
            '<code>application/n-triples</code> 요청은 해당 직렬화로 연결된다.</p>'
            f'<p>소스·릴리스: <a href="{gh}">{gh}</a> · 보관본: Zenodo DOI (ZENODO_DOI)</p>'
            '<p class="meta">온톨로지·SHACL·데이터·문서: CC BY 4.0 / 코드: MIT. 데이터 원자료는 NTIS OpenAPI 과제검색·성과검색(공공누리 제1유형).</p>')
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(page("nrdp 온톨로지", body))


if __name__ == "__main__":
    if os.path.isdir(DOCS):
        shutil.rmtree(DOCS)
    os.makedirs(DOCS)
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    rel = releases()
    mods = [module_doc(k, p) for k, p in MODULES]
    shp = shapes_doc()
    data = data_doc()
    cq = cq_doc()
    landing(mods, shp, data, cq, rel)
    print("docs/ 생성:", [m["key"] + " " + m["ver"] for m in mods], [s["key"] + " " + s["ver"] for s in shp], "이전 버전:", rel)
