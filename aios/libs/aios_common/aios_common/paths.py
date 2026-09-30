"""Runtime / state / config path helpers."""
from __future__ import annotations

import os
from pathlib import Path

from aios_common import (
    CONFIG_DIR_ENV,
    DEFAULT_CONFIG_DIR,
    DEFAULT_RUNTIME_DIR,
    DEFAULT_STATE_DIR,
    RUNTIME_DIR_ENV,
    STATE_DIR_ENV,
)


def runtime_dir() -> Path:
    p = Path(os.environ.get(RUNTIME_DIR_ENV, DEFAULT_RUNTIME_DIR)).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_dir() -> Path:
    p = Path(os.environ.get(STATE_DIR_ENV, DEFAULT_STATE_DIR)).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    p = Path(os.environ.get(CONFIG_DIR_ENV, DEFAULT_CONFIG_DIR)).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def sock_path(name: str) -> Path:
    return runtime_dir() / f"{name}.sock"


def audit_log_path() -> Path:
    return state_dir() / "audit.jsonl"


def skills_dir() -> Path:
    p = state_dir() / "skills"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profiles_dir() -> Path:
    # Prefer packaged profiles, fall back to state
    here = Path(__file__).resolve().parents[3] / "profiles"
    if here.is_dir():
        return here
    p = state_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p