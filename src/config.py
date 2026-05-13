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
        if clean_key.startswith("OPENROUTER_") or clean_key.startswith("PHOENIX_") or clean_key in {
            "MODEL",
            "AGENT_MODEL",
            "MODEL_FLASH",
            "AGENT_MODEL_FLASH",
            "MODEL_PRO",
            "AGENT_MODEL_PRO",
            "DATA_PATH",
            "CACHE_DIR",
            "PROMPT_CHAR_BUDGET",
            "DUFFEL_API_TOKEN",
        }:
            os.environ[clean_key] = clean_value
        else:
            os.environ.setdefault(clean_key, clean_value)


@dataclass(frozen=True)
class AppConfig:
    data_path: Path
    cache_dir: Path
    openrouter_api_key: str | None
    openrouter_provider_order: str
    model: str
    agent_model: str
    prompt_char_budget: int
    admin_password: str | None
    phoenix_api_key: str | None
    phoenix_project_name: str
    duffel_api_token: str | None = None
    max_preview_rows: int = 100

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv_if_present()
        cache_dir = Path(os.getenv("CACHE_DIR", ".cache/chatbot")).resolve()
        
        # DuckDB requires a home directory to install extensions like 'excel'.
        # If HOME is missing (e.g. in some container/restricted environments), 
        # we default it to the cache directory.
        if not os.environ.get("HOME") and not os.environ.get("USERPROFILE"):
            os.environ["HOME"] = str(cache_dir)
            
        return cls(
            data_path=Path(os.getenv("DATA_PATH", "/Users/rajasekharbandreddy/Downloads/sourcedata.csv")),
            cache_dir=cache_dir,
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
            openrouter_provider_order=os.getenv("OPENROUTER_PROVIDER_ORDER", "DeepSeek"),
            model=os.getenv("MODEL", "openrouter/deepseek/deepseek-v4-pro"),
            agent_model=os.getenv("AGENT_MODEL", "openrouter/deepseek/deepseek-v4-pro"),
            prompt_char_budget=int(os.getenv("PROMPT_CHAR_BUDGET", "24000")),
            admin_password=os.getenv("ADMIN_PASSWORD") or None,
            phoenix_api_key=os.getenv("PHOENIX_API_KEY") or None,
            phoenix_project_name=os.getenv("PHOENIX_PROJECT_NAME", "data-analysis-chatbot"),
            duffel_api_token=os.getenv("DUFFEL_API_TOKEN") or None,
        )
