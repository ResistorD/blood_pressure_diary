from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

_VALID_PROFILES = {"dev", "stage", "live"}
_BOOTSTRAP: "EnvBootstrapResult | None" = None


@dataclass(frozen=True)
class EnvBootstrapResult:
    profile: str
    source: str
    loaded_files: tuple[str, ...]


def normalize_profile(raw: str | None) -> str:
    v = str(raw or "").strip().lower()
    if v in _VALID_PROFILES:
        return v
    if v in {"prod", "production"}:
        return "live"
    if v in {"staging"}:
        return "stage"
    return "dev"


def detect_profile(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = environ or os.environ

    explicit = str(env.get("APP_ENV") or env.get("PS_APP_ENV") or env.get("PS_PROFILE") or "").strip()
    if explicit:
        return normalize_profile(explicit), "APP_ENV"

    execution_mode = str(env.get("EXECUTION_MODE") or env.get("PS_EXECUTION_MODE") or "").strip().lower()
    if execution_mode == "live_stage0":
        return "live", "EXECUTION_MODE"

    ps_mode = str(env.get("PS_MODE") or "").strip().lower()
    if ps_mode in {"live", "prod", "production"}:
        return "live", "PS_MODE"
    if ps_mode in {"stage", "staging"}:
        return "stage", "PS_MODE"

    return "dev", "default"


def bootstrap_env(project_root: Path | None = None) -> EnvBootstrapResult:
    global _BOOTSTRAP
    if _BOOTSTRAP is not None:
        return _BOOTSTRAP

    root = project_root or Path(__file__).resolve().parents[1]
    loaded: list[str] = []

    base_env = root / ".env"
    if base_env.exists():
        load_dotenv(dotenv_path=base_env, override=False)
        loaded.append(str(base_env))

    profile, source = detect_profile(os.environ)
    profile_env = root / f".env.{profile}"
    if profile_env.exists():
        load_dotenv(dotenv_path=profile_env, override=False)
        loaded.append(str(profile_env))

    os.environ.setdefault("APP_ENV", profile)
    os.environ["APP_ENV_RESOLVED_FROM"] = source
    os.environ["APP_ENV_FILES"] = ",".join(loaded)

    _BOOTSTRAP = EnvBootstrapResult(
        profile=profile,
        source=source,
        loaded_files=tuple(loaded),
    )
    return _BOOTSTRAP
