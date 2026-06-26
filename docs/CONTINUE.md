# 이어서 작업하기 가이드 (Handoff)

이 문서는 원격(클라우드) 세션에서 진행한 작업을 **로컬 PC에서 내려받아 이어서**
진행하기 위한 안내입니다. 특히 토스 Open API 실데이터 연결이 막혔던
**"IP address not allowed"** 문제의 원인과 해결법을 포함합니다.

---

## 1. 내려받기 (clone)

```bash
# HTTPS
git clone https://github.com/Huride/toss_test.git
cd toss_test

# 작업 브랜치로 전환 (현재 작업 브랜치)
git fetch origin
git checkout claude/env-var-testing-48xuvc
```

> 이미 클론해 둔 저장소가 있다면 최신화만 하면 됩니다.
> ```bash
> git fetch origin
> git checkout claude/env-var-testing-48xuvc
> git pull origin claude/env-var-testing-48xuvc
> ```

---

## 2. 로컬 환경 세팅

한 번에 세팅하는 스크립트가 있습니다.

```bash
bash setup.sh
```

이 스크립트는 다음을 수행합니다.
1. 가상환경 `.venv` 생성
2. `requirements.txt` 의존성 설치 (`httpx`, `python-dotenv`)
3. `.env.example` → `.env` 복사 (이미 있으면 건너뜀)

수동으로 하려면:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 그리고 .env 편집
```

---

## 3. 환경변수(.env) 채우기

`.env` 파일을 열어 발급받은 실제 키를 입력합니다. (`.env` 는 git 에 커밋되지 않습니다)

```dotenv
TOSS_API_KEY=tsck_live_xxxxxxxxxxxxxxxxxxxx
TOSS_SECRET_KEY=tssk_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TOSS_BASE_URL=https://openapi.tossinvest.com   # 기본값, 보통 수정 불필요
```

- 키는 developers.tossinvest.com 에서 발급합니다.
- `config.py` 가 `.env` 또는 셸 환경변수에서 위 값을 읽습니다.
  값이 비어 있으면 실행 시 어떤 변수가 누락됐는지 알려줍니다.

---

## 4. 테스트 실행

### 4-A. 키/네트워크 불필요 — 백테스트 (먼저 이걸로 동작 확인 권장)

```bash
. .venv/bin/activate
python -m backtest.run_backtest          # 돈치안 단일 전략 데모
python -m backtest.run_quant             # 멀티 전략 비교
```

합성 데이터로 동작하므로 키 없이 바로 검증됩니다.
(결과 수치는 하네스 검증용이며 수익성 근거가 아님)

### 4-B. 실데이터 — 읽기 전용 PoC (키 + IP 등록 필요)

```bash
. .venv/bin/activate
python poc_readonly.py                    # 기본: 삼성전자 005930
python poc_readonly.py --symbols 005930 000660
```

성공 시 계좌·잔고·현재가·호가·일봉·환율을 순서대로 출력합니다.
**주문(매수/매도) 기능은 없습니다 — 안전한 연결 검증 전용입니다.**

---

## 5. ⚠️ 중요: "IP address not allowed" (403) 해결법

원격 클라우드 세션에서 `poc_readonly.py` 실행 시 인증 단계에서 아래 오류가 발생했습니다.

```
Toss API error 403:
{'error': 'access_denied', 'error_description': 'IP address not allowed'}
```

### 원인
- **코드/키 문제가 아닙니다.** 키가 틀렸다면 `invalid_client` 가 떴을 것입니다.
- 토스 Open API 는 **허용된 IP에서만** 호출을 받습니다(IP 화이트리스트).
- 원격 컨테이너는 IP가 고정되지 않아 등록이 불가능 → 그래서 거부됩니다.

### 해결
1. **본인 로컬 PC / 고정 IP 서버에서 실행**하세요. (가장 간단·권장)
2. developers.tossinvest.com 의 앱 설정에서 **실행 환경의 공인 IP를
   허용 목록에 등록**합니다.
   - 내 공인 IP 확인: `curl ifconfig.me` 또는 `curl https://api.ipify.org`
   - 유동 IP라면 변경 시마다 갱신 필요. 고정 IP 환경을 권장합니다.
3. 등록 후 다시 `python poc_readonly.py` 실행하면 정상 조회됩니다.

---

## 6. 토큰 관련 주의사항

- OAuth2 **Client Credentials** 방식. 발급 토큰을 `Authorization: Bearer` 로 사용.
- **클라이언트당 유효 토큰은 1개뿐** — 재발급 시 기존 토큰 즉시 무효화.
  그래서 `.token_cache.json`(gitignore 처리)에 캐시 후 만료 전까지 재사용합니다.
- 레이트리밋(429) 시 `Retry-After` 를 존중해 최대 4회 재시도합니다.

---

## 7. 보안 체크리스트

- [ ] `.env`, `.token_cache.json` 은 절대 커밋하지 않기 (`.gitignore` 에 이미 포함)
- [ ] API Key/Secret 을 채팅·이슈·코드·로그에 평문 노출 금지
- [ ] 노출됐다면 즉시 재발급(rotate)

---

## 8. 다음 작업 단계 (로드맵)

현재 1단계(읽기 전용 PoC) + 백테스트 하네스가 완료된 상태입니다. 다음 순서로 진행합니다.

1. **토스 일봉 실데이터 연동** → `get_candles()` 페이지네이션으로 히스토리 수집
   → 돈치안 전략 백테스트/파라미터 튜닝
2. **뉴스/AI 오버레이** (`NewsProvider` + Claude 다관점 `AIScorer`) — 히스토리컬 리플레이로 효과 측정
3. **봇 스켈레톤** — 토큰 관리 · 폴링 루프 · 주문 래퍼(전략 모듈 탑재)
4. **페이퍼 트레이딩 → 소액 라이브**

> 상세 전략/방법론은 [`docs/strategy.md`](strategy.md) 참고.

---

## 9. 변경사항 커밋/푸시

```bash
git add -A
git commit -m "작업 내용 설명"
git push -u origin claude/env-var-testing-48xuvc
```

> 작업 브랜치: `claude/env-var-testing-48xuvc`
> 다른 브랜치로 푸시하지 마세요.
</content>
</invoke>
