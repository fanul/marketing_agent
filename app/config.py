"""Konfigurasi Vimero Agent.

Prioritas: settings di database > environment variable > default.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "vimero.db"
STATIC_DIR = BASE_DIR / "static"

load_dotenv(BASE_DIR / ".env")

ENV_DEFAULTS = {
    "api_base": os.getenv("VIMERO_API_BASE", "https://api.adacode.ai/v1"),
    "api_key": os.getenv("VIMERO_API_KEY", ""),
    "default_model": os.getenv("VIMERO_DEFAULT_MODEL", "claude-sonnet-4-6"),
    "models": os.getenv(
        "VIMERO_MODELS",
        "claude-sonnet-4-6,claude-opus-4-6,qwen3.5-plus,gpt-5.3,GLM-4.7,MiniMax-M2.5",
    ),
    "company_name": os.getenv("VIMERO_COMPANY", "Vimero Agency"),
}

PORT = int(os.getenv("VIMERO_PORT", "8021"))


def get_settings() -> dict:
    """Gabungkan default env dengan override dari tabel settings."""
    from app import db

    merged = dict(ENV_DEFAULTS)
    merged.update(db.all_settings())
    merged["model_list"] = [m.strip() for m in merged["models"].split(",") if m.strip()]
    return merged
