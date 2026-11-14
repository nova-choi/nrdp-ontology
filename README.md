# nrdp: 국가 R&D 포트폴리오 평가를 위한 방법 중립적 MCDM 온톨로지

국가 R&D 포트폴리오 평가의 의사결정 구조(기준, 가중치, 정책 시나리오, 정규화, 집계기법, 결과와 설명)를 특정 MCDM 기법에 종속되지 않게 표현하는 OWL 2 DL 온톨로지와, NTIS 공개 자료로 구축한 지식그래프입니다.

- 문서: https://nova-choi.github.io/nrdp-ontology/
- 영구 IRI: `https://w3id.org/nrdp/` (내용 협상 지원)
- 보관본(DOI): 10.5281/zenodo.24217214
- 관련 학위논문: 최혜석, 「국가 R&D 포트폴리오 평가를 위한 방법 중립적 MCDM 온톨로지 설계 및 검증」, 성균관대학교 정보통신대학원 빅데이터학과 석사학위논문(작성 중)

## 자원

| 자원 | IRI | 현재 버전 | 파일 | 라이선스 |
|---|---|---|---|---|
| MCDM 표현 계층 | `https://w3id.org/nrdp/mcdm` | 0.3.5 | `ontology/mcdm-core.ttl` | CC BY 4.0 |
| 도메인 계층 | `https://w3id.org/nrdp/ontology` | 0.3.5 | `ontology/nrdp-ontology.ttl` | CC BY 4.0 |
| 분류 판 관리 모듈 | `https://w3id.org/nrdp/kosv` | 0.1.2 | `ontology/kos-versioning.ttl` | CC BY 4.0 |
| SHACL shape (M1~M7) | `https://w3id.org/nrdp/shapes/mcdm` | 0.3.5 | `ontology/mcdm-shapes.ttl` | CC BY 4.0 |
| SHACL shape (K1~K5) | `https://w3id.org/nrdp/shapes/kosv` | 0.1.2 | `ontology/kosv-shapes.ttl` | CC BY 4.0 |
| 실데이터 지식그래프 | `https://w3id.org/nrdp/data` | 0.3.4 | `data/rdf/`, 설명 `data/void.ttl` | CC BY 4.0 (원자료 공공누리 제1유형, 출처표시) |
| 역량질문 세트 (CQ1~CQ30) | `https://w3id.org/nrdp/cq` | 0.3.4 | `cq/`, `queries_sparql_real.py`, `queries_real.cypher` | 문안 CC BY 4.0, 질의 코드 MIT |
| 구축·검증 코드 | - | 0.3.5 | `pipeline/`, `analysis/`, `tools/`, 루트 `*.py` | MIT |

- 0.3.5는 0.3.4에 공개용 메타데이터(설명, 수정일, 선호 접두어)만 더한 것이며, 메타데이터를 제외한 트리플은 0.3.4와 같습니다. 학위논문의 검증 결과는 0.3.4 기준이고, 그 파일은 `ontology/releases/0.3.4/`에 그대로 두었습니다.
- 이전 버전은 버전 IRI로 접근합니다. 예: `https://w3id.org/nrdp/mcdm/0.3.4`, `https://w3id.org/nrdp/ontology/0.2.1`(합성 데이터 결과 기준 단일 파일).

## 재현

```bash
pip install rdflib pyshacl owlready2 neo4j scipy
gunzip -k data/rdf/nrdp-domain.ttl.gz
python ontology/tests/axiom_tests.py ontology        # 공리 단위 테스트 (HermiT, Java 필요)
python ontology/tests/mcdm_shacl_tests.py ontology   # SHACL M1~M7
python ontology/tests/kosv_shacl_tests.py ontology   # SHACL K1~K5
python queries_sparql_real.py                        # CQ1~CQ30 SPARQL → data/rdf/sparql-results-real.txt
python load_neo4j_real.py                            # Neo4j 5.x 적재 (NEO4J_URI·NEO4J_USERNAME·NEO4J_PASSWORD)
python run_cypher.py queries_real.cypher --out data/rdf/neo4j-results-real.txt
python compare_results.py data/rdf/sparql-results-real.txt data/rdf/neo4j-results-real.txt
```

NTIS 원자료 수집(`pipeline/ntis_collect.py`)은 NTIS OpenAPI 인증키(`.env`의 `NTIS_API_KEY`)가 필요합니다. 원본 응답과 과제 단위 중간 산출물은 저장소에 두지 않았습니다(`data/README.md`).

## 버전 관리와 유지보수

- 버전 번호는 `주.부.수`입니다. 기존 용어의 의미나 공리를 바꾸면 부 번호를, 메타데이터·레이블·문서만 고치면 수 번호를 올립니다. 기존 IRI는 지우지 않고 `owl:deprecated`로 표시합니다.
- 버전마다 `owl:versionIRI`와 `owl:priorVersion`을 선언하고, 이전 버전 파일을 `ontology/releases/`에 남겨 버전 IRI가 계속 응답하게 합니다.
- GitHub 릴리스(태그 `v<버전>`)마다 Zenodo가 보관본과 DOI를 발급합니다. 문제 제보와 제안은 저장소 Issues로 받습니다.

## 인용

`CITATION.cff`를 참고하십시오.

## 라이선스

온톨로지·SHACL shape·데이터·문서는 [CC BY 4.0](LICENSE), 코드는 [MIT](LICENSE-CODE)입니다. 데이터를 이용할 때는 `data/README.md`의 출처 문구를 함께 표시해야 합니다.
