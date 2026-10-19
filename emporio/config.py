"""Configuração do agente (lida do .env) e utilitários de data/hora da loja."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CONVERSAS_DIR = ROOT_DIR / "conversas"
POLITICAS_PATH = DATA_DIR / "politicas_da_loja.md"

# Campo Grande/MS fica em UTC-4 (sem horário de verão).
FUSO_LOJA = ZoneInfo("America/Campo_Grande")

load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    temperature: float
    data_referencia: date | None


def get_settings() -> Settings:
    data_ref = os.getenv("DATA_REFERENCIA", "").strip()
    return Settings(
        base_url=os.getenv("LLM_BASE_URL", "https://router.huggingface.co/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        data_referencia=date.fromisoformat(data_ref) if data_ref else None,
    )


def agora_loja(data_referencia: date | None = None) -> datetime:
    """Data/hora atual no fuso da loja. Se houver data de referência, mantém a hora atual nesse dia."""
    agora = datetime.now(FUSO_LOJA)
    if data_referencia:
        agora = agora.replace(
            year=data_referencia.year, month=data_referencia.month, day=data_referencia.day
        )
    return agora
