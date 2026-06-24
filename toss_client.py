"""토스증권 Open API 클라이언트 (읽기 전용 PoC).

이 모듈은 인증과 조회(read-only) 엔드포인트만 구현합니다.
주문(매수/매도/정정/취소)은 의도적으로 포함하지 않습니다.

주의해야 할 API 특성:
- OAuth2 Client Credentials Grant 로 access token 을 발급받아
  Authorization: Bearer 헤더로 사용합니다.
- 클라이언트당 유효한 access token 은 "단 1개" 입니다. 토큰을 재발급하면
  기존 토큰이 즉시 무효화됩니다. 따라서 토큰을 디스크에 캐시하고
  만료 전까지 재사용합니다.
- 레이트리밋(429) 시 Retry-After 헤더를 존중하여 재시도합니다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

TOKEN_CACHE_PATH = Path(__file__).resolve().parent / ".token_cache.json"

# 토큰 만료 직전 재발급을 피하기 위한 여유 시간(초)
_EXPIRY_SKEW_SECONDS = 60
# 429 발생 시 최대 재시도 횟수
_MAX_RETRIES = 4


class TossApiError(RuntimeError):
    """API 가 4xx/5xx 를 반환했을 때 발생."""

    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Toss API error {status_code}: {payload}")


class TossClient:
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str = "https://openapi.tossinvest.com",
        account_seq: int | None = None,
        timeout: float = 10.0,
    ):
        if not api_key or not secret_key:
            raise ValueError("api_key 와 secret_key 가 필요합니다.")
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.account_seq = account_seq
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._load_cached_token()

    # ------------------------------------------------------------------
    # 토큰 관리
    # ------------------------------------------------------------------
    def _load_cached_token(self) -> None:
        """디스크 캐시에서 유효한 토큰을 불러옵니다(있다면)."""
        try:
            data = json.loads(TOKEN_CACHE_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return
        # 다른 클라이언트 ID 로 발급된 캐시는 무시
        if data.get("client_id") != self.api_key:
            return
        if data.get("expires_at", 0) > time.time() + _EXPIRY_SKEW_SECONDS:
            self._access_token = data.get("access_token")
            self._token_expires_at = data.get("expires_at", 0)

    def _save_cached_token(self) -> None:
        TOKEN_CACHE_PATH.write_text(
            json.dumps(
                {
                    "client_id": self.api_key,
                    "access_token": self._access_token,
                    "expires_at": self._token_expires_at,
                }
            )
        )
        # 토큰 파일 권한을 소유자만 읽기로 제한
        try:
            TOKEN_CACHE_PATH.chmod(0o600)
        except OSError:
            pass

    def _issue_token(self) -> None:
        """새 access token 을 발급받습니다. 기존 토큰은 즉시 무효화됩니다."""
        resp = self._client.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise TossApiError(resp.status_code, _safe_json(resp))
        body = resp.json()
        self._access_token = body["access_token"]
        # expires_in 만큼 뒤를 만료 시각으로 기록
        self._token_expires_at = time.time() + int(body.get("expires_in", 0))
        self._save_cached_token()

    def _ensure_token(self) -> str:
        if (
            self._access_token is None
            or self._token_expires_at <= time.time() + _EXPIRY_SKEW_SECONDS
        ):
            self._issue_token()
        assert self._access_token is not None
        return self._access_token

    # ------------------------------------------------------------------
    # 공통 요청 래퍼
    # ------------------------------------------------------------------
    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        with_account: bool = False,
    ) -> Any:
        """인증된 GET 요청. ApiResponse.result 를 반환합니다."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        for attempt in range(_MAX_RETRIES + 1):
            token = self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            if with_account:
                if self.account_seq is None:
                    raise ValueError(
                        "이 엔드포인트는 account_seq 가 필요합니다. "
                        "TossClient(account_seq=...) 로 설정하세요."
                    )
                headers["X-Tossinvest-Account"] = str(self.account_seq)

            resp = self._client.get(path, params=params, headers=headers)

            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 1))
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
                    continue
                raise TossApiError(429, _safe_json(resp))

            if resp.status_code == 401 and attempt < _MAX_RETRIES:
                # 토큰이 무효화됐을 수 있으니 강제 재발급 후 1회 재시도
                self._access_token = None
                continue

            if resp.status_code != 200:
                raise TossApiError(resp.status_code, _safe_json(resp))

            return resp.json().get("result")

        raise TossApiError(0, "최대 재시도 횟수를 초과했습니다.")

    # ------------------------------------------------------------------
    # 읽기 전용 엔드포인트
    # ------------------------------------------------------------------
    def get_accounts(self) -> list[dict]:
        """보유 계좌 목록. accountSeq 를 여기서 얻습니다."""
        return self._get("/api/v1/accounts")

    def get_holdings(self, symbol: str | None = None) -> dict:
        """계좌 잔고/보유 종목 개요. account_seq 헤더 필요."""
        return self._get(
            "/api/v1/holdings", {"symbol": symbol}, with_account=True
        )

    def get_prices(self, symbols: list[str] | str) -> list[dict]:
        """현재가 조회 (최대 200개). symbols 는 리스트 또는 콤마 구분 문자열."""
        if isinstance(symbols, (list, tuple)):
            symbols = ",".join(symbols)
        return self._get("/api/v1/prices", {"symbols": symbols})

    def get_orderbook(self, symbol: str) -> dict:
        """호가 조회."""
        return self._get("/api/v1/orderbook", {"symbol": symbol})

    def get_candles(
        self,
        symbol: str,
        interval: str = "1d",
        count: int | None = None,
        before: str | None = None,
        adjusted: bool | None = None,
    ) -> Any:
        """분봉/일봉 차트. interval: '1m' 또는 '1d' (최대 200개)."""
        if interval not in ("1m", "1d"):
            raise ValueError("interval 은 '1m' 또는 '1d' 여야 합니다.")
        return self._get(
            "/api/v1/candles",
            {
                "symbol": symbol,
                "interval": interval,
                "count": count,
                "before": before,
                "adjusted": adjusted,
            },
        )

    def get_exchange_rate(
        self, base_currency: str = "USD", quote_currency: str = "KRW"
    ) -> dict:
        """환율 조회."""
        return self._get(
            "/api/v1/exchange-rate",
            {"baseCurrency": base_currency, "quoteCurrency": quote_currency},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TossClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.text
