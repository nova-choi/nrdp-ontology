# 역량질문 세트 (CQ1~CQ30, v0.3.4)

IRI: `https://w3id.org/nrdp/cq` · 질문 문안 CC BY 4.0 · 질의 코드 MIT

`competency-questions.csv`(UTF-8, Excel 호환)와 `competency-questions.json`은 같은 내용이다. 질의 32개(역량질문 30개와 보조 질의 CQ12b·CQ24b)마다 다음 열을 둔다.

| 열 | 내용 |
|---|---|
| `id`, `category`, `auxiliary` | 번호, 범주(A 도메인 조회, B MCDM 구조, C 시나리오 비교, D 설명, E 실데이터 구조), 보조 질의 여부 |
| `question_general_ko` | 일반형 질문 (CQ1~CQ25, 학위논문 [표 3-2]) |
| `question_instantiated_ko` | 실데이터에 맞춘 구체형 질문 |
| `derivation_source` | 도출 원천 S1~S5 (아래) |
| `research_question` | 대응 연구질문 |
| `answer_mode_real_v0.3.4` | 질의 단독 / 절차적 계산 후 재적재한 결과를 질의로 조회 |
| `result_rows_real_v0.3.4`, `sparql_cypher_match` | 실데이터 결과 행 수, SPARQL·Cypher 결과 일치 여부 |
| `sparql`, `cypher` | 질의문 전문 |

도출 원천: S1 국가연구개발혁신법 시행규칙 별지 서식 및 NTIS 사업·예산·성과 항목 / S2 과학기술기본계획의 정책목표 체계 / S3 WSM·TOPSIS·PROMETHEE II의 요구 파라미터 / S4 정책 선호의 교체·비교 요구(연구질문 2) / S5 평가 결과 수용자의 설명 요구(연구질문 3).

CQ26~CQ30은 실데이터에서만 검증할 수 있는 질문(부처 개편, 분류 판, 연속과제, 성과 귀속, 사업명 별칭 병합)으로 실데이터 단계에서 더하였다. 범주 E와 원천 S1 배정은 이 세트에서 새로 붙인 것이다.

생성: `tools/build_cq.py`(질의 파일과 대조 결과에서 추출).
