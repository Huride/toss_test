#!/usr/bin/env bash
# 프로젝트 초기 세팅: 가상환경 생성 + 의존성 설치 + .env 준비
# 사용법:  bash setup.sh
set -e

cd "$(dirname "$0")"

echo "[1/3] 가상환경(.venv) 생성"
python3 -m venv .venv

echo "[2/3] 의존성 설치"
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

echo "[3/3] .env 준비"
if [ -f .env ]; then
  echo "  .env 가 이미 존재합니다 (건너뜀)"
else
  cp .env.example .env
  echo "  .env 생성 완료 → 편집기로 열어 TOSS_API_KEY / TOSS_SECRET_KEY 를 입력하세요"
fi

echo
echo "완료. 다음 명령으로 확인:"
echo "  . .venv/bin/activate"
echo "  python -m backtest.run_quant   # 외부 키 불필요(합성 데이터 백테스트)"
echo "  python poc_readonly.py         # .env 에 키 입력 후 실데이터 조회"
