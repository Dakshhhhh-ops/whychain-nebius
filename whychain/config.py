"""Settings, loaded from environment variables (.env in development). No secrets live in code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def utf8_output() -> None:
    """Command-line tools print UTF-8 (names like São Paulo, the "·" separator) even when Windows pipes their output
    in its legacy code page (Git Bash then showed mojibake). The Windows console itself is unaffected."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    thinking: bool | None = None  # for reasoning models (e.g. Nemotron 3.5): None = leave the model's default

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model) and not is_placeholder(self.api_key)


def is_placeholder(value: str) -> bool:
    return not value or "your-" in value or value == "change-me"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data" / "generated"
    runs_dir: Path = field(default_factory=lambda: Path(env("WHYCHAIN_RUNS_DIR") or ROOT / "runs"))
    harness: str = field(default_factory=lambda: env("WHYCHAIN_HARNESS", "local"))
    zetaris_url: str = field(default_factory=lambda: env("ZETARIS_REST_URL") or "http://localhost:8888/api/v1.0")
    zetaris_api_key: str = field(default_factory=lambda: env("ZETARIS_API_KEY"))
    zetaris_org_id: str = field(default_factory=lambda: env("ZETARIS_ORG_ID"))
    pg_dsn: str = field(default_factory=lambda: (
        f"host={env('POSTGRES_HOST', 'localhost')} port={env('POSTGRES_PORT', '5433')} "
        f"dbname={env('POSTGRES_DB', 'erp')} user={env('POSTGRES_USER', 'whychain')} "
        f"password={env('POSTGRES_PASSWORD', 'whychain-local')}"))
    # optional Meterless engines bridge (an external memory service); empty = WhyChain's own memory
    meterless_url: str = field(default_factory=lambda: env("METERLESS_BRIDGE_URL"))
    # read documents only on this machine (Meterless Nightshift), for runs that don't say otherwise
    private_docs: bool = field(default_factory=lambda: env("WHYCHAIN_PRIVATE_DOCS", "false").lower() == "true")
    max_rounds: int = field(default_factory=lambda: int(env("WHYCHAIN_MAX_ROUNDS", "2")))
    approval_threshold_inr: float = field(
        default_factory=lambda: float(env("WHYCHAIN_APPROVAL_THRESHOLD_INR", "300000")))

    def providers(self) -> dict[str, Provider]:
        return {
            # ---- Nebius Token Factory: the default for every model call (NVIDIA Nemotron, OpenAI-compatible) ----
            # Nemotron 3 Super, thinking off, for fast data and document work ...
            "tf": Provider("tf", _tf_url(), env("NEBIUS_API_KEY"), env("TF_MODEL", TF_SUPER),
                           thinking=env("TF_THINKING", "false").lower() == "true"),
            # ... the same model with reasoning switched on for planning, judging and writing ...
            "tf-reason": Provider("tf-reason", _tf_url(), env("NEBIUS_API_KEY"), env("TF_REASON_MODEL", TF_SUPER),
                                  thinking=env("TF_REASON_THINKING", "true").lower() == "true"),
            # ... and a DIFFERENT Nemotron model on Token Factory when the main one is overloaded or failing
            "tf-backup": Provider("tf-backup", _tf_url(), env("NEBIUS_API_KEY"), env("TF_BACKUP_MODEL", TF_ULTRA),
                                  thinking=False),
            # ---- optional overrides, off unless their keys are set ----
            # NVIDIA NIM: used only if NVIDIA_API_KEY is set, after Token Factory
            "nim": Provider("nim", env("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                            env("NVIDIA_API_KEY"), env("NIM_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
                            thinking=env("NIM_THINKING", "false").lower() == "true"),
            "nim-reason": Provider("nim-reason", env("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                                   env("NVIDIA_API_KEY"),
                                   env("NIM_REASON_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
                                   thinking=env("NIM_REASON_THINKING", "true").lower() == "true"),
            "nim-backup": Provider("nim-backup", env("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                                   env("NVIDIA_API_KEY"), env("NIM_BACKUP_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
                                   thinking=False),
            "xai": Provider("xai", env("XAI_BASE_URL", "https://api.x.ai/v1"), env("XAI_API_KEY"),
                            env("XAI_MODEL", "grok-4-fast")),
            "nightshift": Provider("nightshift", env("NIGHTSHIFT_BASE_URL"), env("NIGHTSHIFT_API_KEY"),
                                   env("NIGHTSHIFT_MODEL", "meterless/local")),
            # Meterless Nightshift as the gateway: the same Nemotron models, reached through Nightshift (a signed
            # receipt per call). Configured only with NIGHTSHIFT_PRIMARY=true; direct NIM stays the fallback.
            "ns-work": Provider("ns-work", env("NIGHTSHIFT_BASE_URL") if _ns_primary() else "",
                                env("NIGHTSHIFT_API_KEY"),
                                env("NIGHTSHIFT_GATEWAY_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")),
            "ns-reason": Provider("ns-reason", env("NIGHTSHIFT_BASE_URL") if _ns_primary() else "",
                                  env("NIGHTSHIFT_API_KEY"),
                                  env("NIGHTSHIFT_GATEWAY_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")),
            "ollama": Provider("ollama", env("OLLAMA_BASE_URL", "http://localhost:11434/v1"), "ollama",
                               env("OLLAMA_MODEL", "qwen3:8b")),
        }


# Nebius Token Factory (https://tokenfactory.nebius.com): model ids exactly as Token Factory serves them
TF_BASE_URL = "https://api.tokenfactory.us-central1.nebius.com/v1/"
TF_SUPER = "nvidia/nemotron-3-super-120b-a12b"
TF_ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
TF_EMBED = "Qwen/Qwen3-Embedding-8B"   # Token Factory serves no Nemotron embedder


def _tf_url() -> str:
    return env("NEBIUS_BASE_URL", TF_BASE_URL)


def _ns_primary() -> bool:
    return env("NIGHTSHIFT_PRIMARY", "false").lower() == "true"


def data_as_of() -> str:
    """The snapshot date of the generated data ("today" for the agents)."""
    try:
        import json
        return json.loads((ROOT / "data" / "generated" / "manifest.json").read_text(encoding="utf-8"))["as_of"]
    except Exception:
        return "2026-10-21"


SETTINGS = Settings()
AS_OF = data_as_of()
