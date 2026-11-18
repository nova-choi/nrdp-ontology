# 공개 절차 (저자 작업)

이 폴더는 그대로 GitHub 저장소가 되도록 준비되어 있다. 계정이 필요한 다섯 단계만 남아 있다. 순서대로 하면 1~2시간이면 끝나고, w3id 병합만 며칠 걸린다.

`w3id.org/nrdp` 경로는 2026-10-31 기준 비어 있다(perma-id/w3id.org master에 `ids/nrdp/` 없음).

## 1. 자리표시자 채우기

```bash
python tools/configure_release.py --github-user <GitHub 계정> --email <w3id에 적을 연락처>
```

`nova-choi`, `novachoi95@gmail.com`이 docs/, w3id/, README, CITATION.cff, .zenodo.json, data/void.ttl에서 한 번에 바뀐다. 사이트를 다시 만들 필요는 없다(만들려면 `python tools/build_site.py`).

## 2. GitHub 저장소와 Pages

1. GitHub에서 공개 저장소 `nrdp-ontology`를 만든다(README·LICENSE 자동 생성은 끈다).
2. 이 폴더를 올린다.
   ```bash
   git init && git add . && git commit -m "nrdp v0.3.5" && git branch -M main
   git remote add origin https://github.com/<계정>/nrdp-ontology.git && git push -u origin main
   ```
3. Settings → Pages → Source: *Deploy from a branch*, Branch: `main`, 폴더 `/docs` → Save.
4. 몇 분 뒤 `https://<계정>.github.io/nrdp-ontology/`가 열리는지 확인한다.

## 3. Zenodo 연동과 첫 릴리스

1. https://zenodo.org 에 GitHub 계정으로 로그인 → 계정 메뉴 GitHub → `nrdp-ontology` 스위치를 켠다.
2. GitHub에서 Releases → *Draft a new release* → 태그 `v0.3.5`, 제목 `nrdp v0.3.5` → Publish.
3. Zenodo가 `.zenodo.json`의 메타데이터로 보관본을 만들고 DOI를 발급한다. 버전 DOI와 개념 DOI(모든 버전을 대표) 두 개가 나오며, 논문에는 개념 DOI를 적는 것이 일반적이다.
4. DOI를 반영해 다시 올린다.
   ```bash
   python tools/configure_release.py --github-user <계정> --doi 10.5281/zenodo.NNNNNNN
   git commit -am "DOI 기재" && git push
   ```

## 4. w3id.org 등록

1. https://github.com/perma-id/w3id.org 를 포크한다.
2. 포크의 `ids/` 아래에 `nrdp/` 폴더(`ids/nrdp/`)를 만들고 이 저장소의 `w3id/nrdp/.htaccess`와 `w3id/nrdp/README.md`를 넣는다.
3. Pull Request를 올린다. 제목 예: `Add nrdp (national R&D portfolio MCDM ontology)`. 보통 며칠 안에 병합된다.
4. 병합 후 확인:
   ```bash
   curl -sI https://w3id.org/nrdp/mcdm | grep -i location                              # → .../mcdm/
   curl -sI -H "Accept: text/turtle" https://w3id.org/nrdp/mcdm | grep -i location     # → .../mcdm/ontology.ttl
   curl -sI -H "Accept: text/turtle" https://w3id.org/nrdp/mcdm/0.3.4 | grep -i location
   ```

`.htaccess`의 규칙 24개는 로컬 Apache(mod_rewrite)에서 브라우저·Turtle·RDF/XML·JSON-LD·N-Triples·CSV 요청과 버전 IRI에 대해 모두 의도한 주소로 303 응답하는 것을 확인했고, 연결 대상 26개가 `docs/`에 있는 것도 확인했다.

## 5. 논문에 채울 것

- 제3장 제10절 [표 3-12]와 가용성 진술: 저장소 URL, Zenodo 개념 DOI
- 제4장 제1절의 [작성 필요]: 저장소 URL, 태그 `v0.3.5`(학위논문 결과는 `ontology/releases/0.3.4/` 파일 기준)

## 선택 사항

- ORCID가 있으면 `CITATION.cff`의 저자에 `orcid:`를, 세 모듈 머리에 `dcterms:creator`로 ORCID IRI를 추가한다(다음 수 버전 0.3.6).
- 영문 레이블은 일부 용어에만 있다(MCDM 계층 레이블 123개 중 영문 37개). 국외 학회 투고 전에 채우면 문서와 재사용성이 나아진다.
- SHACL shape 개체의 IRI가 `mcdm:` 네임스페이스에 있어 `https://w3id.org/nrdp/mcdm#ScenarioWeightSumShape`는 MCDM 계층 문서로 연결된다. shape 그래프 IRI(`/nrdp/shapes/mcdm`)는 따로 응답한다. 다음 부 버전에서 shape 개체를 `https://w3id.org/nrdp/shapes/mcdm#` 아래로 옮기는 것을 검토한다.
