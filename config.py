"""환경설정 로더. .env 파일에서 자격증명을 읽습니다."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    secret_key: str
    base_url: str


def load_settings() -> Settings:
    api_key = os.getenv("TOSS_API_KEY", "").strip()
    secret_key = os.getenv("TOSS_SECRET_KEY", "").strip()
    base_url = os.getenv("TOSS_BASE_URL", "https://openapi.tossinvest.com").strip()

    missing = [
        name
        for name, val in (("TOSS_API_KEY", api_key), ("TOSS_SECRET_KEY", secret_key))
        if not val
    ]
    if missing:
        raise SystemExit(
            f"환경변수 {', '.join(missing)} 가 설정되지 않았습니다.\n"
            ".env.example 를 .env 로 복사한 뒤 값을 채워주세요."
        )
    return Settings(api_key=api_key, secret_key=secret_key, base_url=base_url)
