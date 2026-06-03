# 네이버 증권 종목토론 발견 방식

## 현재 구현

**엔드포인트**
```
GET https://finance.naver.com/item/board.naver?code={종목코드}&page={N}
```

**동작 방식**
- 단순 HTTP GET, JS 실행 불필요
- keyword 는 종목코드 (예: `005930`)
- `a[href*='board_read.naver']` 셀렉터로 게시글 URL 추출
- `nid` 기준 중복 제거 (같은 게시글이 여러 `<a>` 태그에 노출됨)
- 추출된 URL: `https://finance.naver.com/item/board_read.naver?code={code}&nid={nid}`

**구현 파일**: `adapters/naver_stock.py` — `NaverStockAdapter`

## 수집량

페이지당 ~19~20건, 기본 `max_pages=5` 기준 최대 ~100건/회.

## 키워드 등록

뉴스 검색 키워드(삼성전자)와 달리 **종목코드**를 사용한다.  
`--display-name` 으로 종목명을 함께 등록하면 DB 조회 시 가독성이 높아진다.

```bash
python scripts/add_keyword.py --keyword "005930" --portal naver_stock --display-name "삼성전자"
python scripts/add_keyword.py --keyword "000660" --portal naver_stock --display-name "SK하이닉스"
```

종목코드는 네이버 금융 종목 상세 URL(`/item/main.naver?code=XXXXXX`)에서 확인한다.
