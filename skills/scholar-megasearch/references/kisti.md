# KISTI ScienceON OpenAPI 통합 스펙 (Bucket H)

scholar-megasearch의 국내(한국어) 소스 버킷. KCI 등재 논문·국내 R&D 보고서·국내 특허를 검색한다.
구현: `scripts/kisti_client.py` · fallback CLI: `scripts/search_local.py kisti "질의"`.

## 자격증명 (환경변수 — 절대 커밋 금지)
| 변수 | 의미 |
|------|------|
| `KISTI_CLIENT_ID` | 발급받은 client_id |
| `KISTI_AUTH_KEY` | 발급받은 인증키(=AES-256 key, 32바이트) |
| `KISTI_MAC` | 토큰 발급 시 바인딩된 MAC 주소 |
| `KISTI_TARGET` (선택) | 검색 대상 한정(`arti,report,patent` 중, 기본 전체) |

토큰은 런타임에 발급하며 저장소에 보존하지 않는다.

자격증명은 **셸 환경변수**(`$env:KISTI_...`) 또는 **`.env` 파일**로 줄 수 있다. `kisti_client.py`는
python-dotenv가 설치돼 있으면 작업 디렉토리의 `.env`를 자동 로딩한다(셸 env가 항상 우선). `.env`는
`.gitignore` 처리되어 커밋되지 않는다 — **실제 키를 넣은 .env는 절대 커밋하지 말 것**(이 리포는 공개 포크).
예시:
```
KISTI_CLIENT_ID=...
KISTI_AUTH_KEY=...32바이트...
KISTI_MAC=...
```

## 토큰 발급 (검증됨 — 공식 샘플 `_vendor_kisti_token_sample/`)
- 발급: `GET https://apigateway.kisti.re.kr/tokenrequest.do?client_id=<id>&accounts=<enc>`
- `<enc>` = AES-256-CBC(plaintext, key=인증키, iv=`jvHJ1EFA0IXBrxxz` 고정, PKCS7 pad, block 16) → `base64.urlsafe_b64encode` → `urllib.parse.quote`
- plaintext = `{"datetime":"YYYYMMDDHHMMSS","mac_address":"<MAC>"}` (공백 제거, datetime은 숫자만)
- 응답 JSON: `{access_token, access_token_expire, refresh_token, refresh_token_expire, client_id, issued_at}`
- 재발급(선택): `GET .../tokenrequest.do?refreshToken=<rt>&client_id=<id>` (파라미터명 `refreshToken` 카멜케이스)

## 검색 API 스펙 — ✅ 실응답으로 확정 (2026-07-01)
픽스처: `scripts/tests/fixtures/kisti_{arti,report,patent}_sample.xml` (실호출 응답).

**호출:**
```
GET https://apigateway.kisti.re.kr/openapicall.do
    ?client_id=<id>&token=<accessToken>&version=1.0&action=search
    &target=ARTI|REPORT|PATENT
    &searchQuery=<URL-encoded {"BI":"<질의>"}>   # BI = 기본(통합) 검색 필드
    &curPage=1&rowCount=<건수>
```
access token은 **쿼리스트링 `token=`** 으로 전달. 응답은 **XML**.

**응답 봉투:** `<MetaData><resultSummary><statusCode>200</statusCode><TotalCount>N</TotalCount>...`
`<recordList><record><item metaCode="X" metaName="..">CDATA</item>...</record></recordList></MetaData>`.
필드는 element 태그가 아니라 **`metaCode` 속성**으로 식별. statusCode≠200이면 결과 없음 처리.

**metaCode → corpus 매핑** (구현: `kisti_client._FIELD_MAP`):
| corpus | ARTI | REPORT | PATENT |
|--------|------|--------|--------|
| title | Title (→Title2) | Title (→Title2) | Title |
| authors | Author (`;`분리, →Author2) | Author + Contributors | Applicants |
| year | Pubyear | Pubyear | ApplDate(→PublDate→GrantDate)의 4자리 |
| venue | JournalName | Publisher | "특허"(상수) |
| doi | DOI | — | — |
| abstract | Abstract (→Abstract2) | Abstract (→Abstract2) | Abstract |
| url | ContentURL | ContentURL | ContentURL |

보고서·특허는 DOI가 없어 제목(한글)으로 dedup된다 → `merge_corpus.norm_title`의 한글 보존(이 브랜치 수정)이 전제.
응답 포맷: XML. 커버리지: KCI 99%, SCI(E) 99.7%, SCOPUS 69.7%.

공식 문서 페이지(참고): 논문 `…/apigateway/api/way/service/arti/serviceArtiSearchApi.do`,
특허 `…/service/patent/servicePatentSearchApi.do`, API Test `…/por/api/apiTest/arti/`.

## 출처/보존
공식 토큰 샘플 원본: `references/_vendor_kisti_token_sample/{TokenSample.py,AES256Util.py}` (KISTI 제공).
