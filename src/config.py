from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv_if_present(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean_key = key.strip()
        clean_value = value.strip().strip('"').strip("'")
        if clean_key.startswith("GEMINI_") or clean_key in {"DATA_PATH", "CACHE_DIR", "PROMPT_CHAR_BUDGET"}:
            os.environ[clean_key] = clean_value
        else:
            os.environ.setdefault(clean_key, clean_value)


@dataclass(frozen=True)
class AppConfig:
    data_path: Path
    cache_dir: Path
    gemini_api_key: str | None
    default_model: str
    escalation_model: str
    fallback_model: str
    prompt_char_budget: int
    max_preview_rows: int = 100

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv_if_present()
        return cls(
            data_path=Path(os.getenv("DATA_PATH", "/Users/rajasekharbandreddy/Downloads/sourcedata.csv")),
            cache_dir=Path(os.getenv("CACHE_DIR", ".cache/chatbot")),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            default_model=os.getenv("GEMINI_DEFAULT_MODEL", "gemini-3-flash-preview"),
            escalation_model=os.getenv("GEMINI_ESCALATION_MODEL", "gemini-3-flash-preview"),
            fallback_model=os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash"),
            prompt_char_budget=int(os.getenv("PROMPT_CHAR_BUDGET", "24000")),
        )
