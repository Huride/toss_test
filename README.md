# 토스증권 Open API 자동매매 — 읽기 전용 PoC

토스증권 Open API(v1.1.5)를 사용한 자동매매 프로그램의 **1단계: 읽기 전용 PoC**입니다.
인증 → 계좌/잔고 조회 → 시세 조회까지의 연결을 안전하게 검증합니다.
**주문(매수/매도) 기능은 의도적으로 포함하지 않습니다.**

## 구성

| 파일 | 설명 |
|---|---|
| `toss_client.py` | API 클라이언트 (인증 + 읽기 전용 엔드포인트) |
| `config.py` | `.env` 자격증명 로더 |
| `poc_readonly.py` | PoC 실행 스크립트 (조회 리포트 출력) |
| `.env.example` | 환경변수 템플릿 |

## 실행 방법

```bash
# 1) 의존성 설치
pip install -r requirements.txt

# 2) 자격증명 설정
cp .env.example .env
#   .env 를 열어 TOSS_API_KEY / TOSS_SECRET_KEY 입력

# 3) 실행 (기본: 삼성전자 005930)
python poc_readonly.py

# 종목 지정
python poc_readonly.py --symbols 005930 000660
```

## 구현된 조회 기능

- `get_accounts()` — 계좌 목록 / `accountSeq`
- `get_holdings()` — 잔고·보유 종목 개요
- `get_prices()` — 현재가 (최대 200종목)
- `get_orderbook()` — 호가
- `get_candles()` — 분봉(`1m`)/일봉(`1d`) 차트 (최대 200개)
- `get_exchange_rate()` — 환율

## 인증 관련 중요 특성

- OAuth2 **Client Credentials** 방식. 발급된 access token 을 `Authorization: Bearer` 헤더로 사용.
- **클라이언트당 유효 토큰은 1개뿐**입니다. 재발급 시 기존 토큰이 즉시 무효화되므로,
  이 클라이언트는 토큰을 `.token_cache.json`(gitignore 처리됨)에 캐시하고 만료 전까지 재사용합니다.
- 레이트리밋(`429`) 시 `Retry-After` 헤더를 존중하여 최대 4회 재시도합니다.

## 보안 주의

- `.env`, `.token_cache.json` 은 git 에 커밋되지 않습니다.
- **API Key/Secret 을 채팅·이슈·코드 등에 평문으로 노출하지 마세요.** 노출 시 즉시 재발급(rotate)하세요.

## 다음 단계 (예정)

- 봇 스켈레톤: 토큰 관리 · 폴링 루프 · 주문 래퍼 (전략 플러그인 구조)
- 전략 모듈: 이평선 크로스 / 변동성 돌파 / 리밸런싱 등
