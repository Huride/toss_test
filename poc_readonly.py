"""읽기 전용 PoC 실행 스크립트.

흐름:
  1) 인증 (토큰 발급/재사용)
  2) 계좌 목록 조회 → accountSeq 확보
  3) 잔고/보유 종목 조회
  4) 시세 조회 (현재가 / 호가 / 일봉)
  5) 환율 조회

주문 기능은 포함되어 있지 않습니다. (안전한 연결 검증용)

실행:
  pip install -r requirements.txt
  cp .env.example .env   # 그리고 실제 키 입력
  python poc_readonly.py
"""

from __future__ import annotations

import argparse

from config import load_settings
from toss_client import TossApiError, TossClient


def _fmt(v: object) -> str:
    return "-" if v is None else str(v)


def run(sample_symbols: list[str]) -> None:
    settings = load_settings()

    with TossClient(
        api_key=settings.api_key,
        secret_key=settings.secret_key,
        base_url=settings.base_url,
    ) as client:
        # 1) 인증 + 2) 계좌 조회
        print("=" * 60)
        print("[1] 계좌 목록 조회")
        print("=" * 60)
        accounts = client.get_accounts()
        if not accounts:
            print("조회된 계좌가 없습니다.")
            return
        for acc in accounts:
            print(
                f"  - accountNo={acc.get('accountNo')} "
                f"accountSeq={acc.get('accountSeq')} "
                f"type={acc.get('accountType')}"
            )
        # 첫 번째 BROKERAGE 계좌를 사용
        brokerage = next(
            (a for a in accounts if a.get("accountType") == "BROKERAGE"), accounts[0]
        )
        client.account_seq = brokerage["accountSeq"]
        print(f"\n  → 사용할 계좌 accountSeq={client.account_seq}")

        # 3) 잔고/보유 종목
        print("\n" + "=" * 60)
        print("[2] 잔고 / 보유 종목")
        print("=" * 60)
        holdings = client.get_holdings()
        items = holdings.get("items", []) if isinstance(holdings, dict) else []
        if not items:
            print("  보유 종목이 없습니다.")
        for it in items:
            print(
                f"  - {_fmt(it.get('symbol')):<8} {_fmt(it.get('name')):<16} "
                f"수량={_fmt(it.get('quantity'))} "
                f"현재가={_fmt(it.get('lastPrice'))} "
                f"평균단가={_fmt(it.get('averagePurchasePrice'))} "
                f"({_fmt(it.get('currency'))})"
            )

        # 4) 시세 - 현재가
        print("\n" + "=" * 60)
        print(f"[3] 현재가 조회 (symbols={sample_symbols})")
        print("=" * 60)
        try:
            prices = client.get_prices(sample_symbols)
            for p in prices:
                print(
                    f"  - {_fmt(p.get('symbol')):<8} "
                    f"현재가={_fmt(p.get('lastPrice'))} "
                    f"({_fmt(p.get('currency'))}) "
                    f"@ {_fmt(p.get('timestamp'))}"
                )
        except TossApiError as e:
            print(f"  현재가 조회 실패: {e}")

        # 4b) 시세 - 호가 (첫 종목)
        first = sample_symbols[0]
        print("\n" + "=" * 60)
        print(f"[4] 호가 조회 (symbol={first})")
        print("=" * 60)
        try:
            ob = client.get_orderbook(first)
            asks = ob.get("asks", [])[:3]
            bids = ob.get("bids", [])[:3]
            print(f"  매도호가(상위3): {asks}")
            print(f"  매수호가(상위3): {bids}")
        except TossApiError as e:
            print(f"  호가 조회 실패: {e}")

        # 4c) 시세 - 일봉 (첫 종목)
        print("\n" + "=" * 60)
        print(f"[5] 일봉 조회 (symbol={first}, count=5)")
        print("=" * 60)
        try:
            candles = client.get_candles(first, interval="1d", count=5)
            print(f"  {candles}")
        except TossApiError as e:
            print(f"  일봉 조회 실패: {e}")

        # 5) 환율
        print("\n" + "=" * 60)
        print("[6] 환율 조회 (USD→KRW)")
        print("=" * 60)
        try:
            fx = client.get_exchange_rate("USD", "KRW")
            print(
                f"  USD/KRW rate={_fmt(fx.get('rate'))} "
                f"mid={_fmt(fx.get('midRate'))} "
                f"({_fmt(fx.get('rateChangeType'))})"
            )
        except TossApiError as e:
            print(f"  환율 조회 실패: {e}")

        print("\n읽기 전용 PoC 완료 ✅ (주문은 실행되지 않았습니다)")


def main() -> None:
    parser = argparse.ArgumentParser(description="토스증권 Open API 읽기 전용 PoC")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["005930"],  # 삼성전자
        help="조회할 종목 심볼 (KR: 6자리 숫자, US: 티커). 기본값: 005930",
    )
    args = parser.parse_args()
    run(args.symbols)


if __name__ == "__main__":
    main()
