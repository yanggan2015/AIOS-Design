"""Risk levels, capability tokens, audit append-only log."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

from aios_common.errors import AiosError, ErrorCode
from aios_common.paths import audit_log_path, config_dir, state_dir


class Risk(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3


# tool / action → default risk
DEFAULT_RISKS: dict[str, Risk] = {
    "dcp.list_targets": Risk.L0,
    "dcp.snapshot": Risk.L0,
    "dcp.find": Risk.L0,
    "dcp.act.click": Risk.L1,
    "dcp.act.ime_commit": Risk.L1,
    "dcp.act.scroll": Risk.L1,
    "dcp.act.key": Risk.L1,
    "dcp.act.screenshot": Risk.L2,
    "dcp.assert": Risk.L0,
    "dcp.freeze": Risk.L0,
    "dcp.invoke": Risk.L1,
    "fs.read": Risk.L1,
    "fs.write": Risk.L2,
    "fs.delete": Risk.L3,
    "notify.show": Risk.L0,
    "pkg.install": Risk.L2,
    "agent.run": Risk.L1,
    "agent.abort": Risk.L0,
    "sys.power.suspend": Risk.L3,
    "sys.power.reboot": Risk.L3,
    "sys.power.poweroff": Risk.L3,
    "sys.audio.set_volume": Risk.L1,
    "sys.audio.set_mute": Risk.L1,
    "sys.net.set_wifi": Risk.L2,
    "sys.session.lock": Risk.L1,
    "sys.svc.status": Risk.L0,
    "sys.svc.restart": Risk.L3,
    "secret.use": Risk.L3,
}


SENSITIVE_ROLES = {"password_text", "password", "payment", "auth_dialog"}


@dataclass
class Capability:
    token: str
    action: str
    risk: Risk
    target: Optional[str]
    uid: int
    issued_at: float
    expires_at: float
    confirmed: bool = False
    meta: dict = field(default_factory=dict)

    def alive(self) -> bool:
        return time.time() < self.expires_at

    def to_public(self) -> dict:
        return {
            "token": self.token,
            "action": self.action,
            "risk": int(self.risk),
            "target": self.target,
            "expires_at": self.expires_at,
            "confirmed": self.confirmed,
        }


@dataclass
class PolicyDecision:
    allow: bool
    risk: Risk
    need_confirm: bool
    reason: str
    capability: Optional[Capability] = None
    code: ErrorCode = ErrorCode.OK

    def to_dict(self) -> dict:
        d = {
            "allow": self.allow,
            "risk": int(self.risk),
            "need_confirm": self.need_confirm,
            "reason": self.reason,
            "code": int(self.code),
        }
        if self.capability:
            d["capability"] = self.capability.to_public()
        return d


class AuditLog:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or audit_log_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict) -> None:
        event = dict(event)
        event.setdefault("ts", time.time())
        event.setdefault("id", str(uuid.uuid4()))
        line = json.dumps(event, ensure_ascii=False) + "\n"
        # append-only, O_APPEND
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())


class CapabilityStore:
    def __init__(self, secret: Optional[bytes] = None):
        self._caps: dict[str, Capability] = {}
        self._secret = secret or self._load_or_create_secret()

    def _load_or_create_secret(self) -> bytes:
        p = state_dir() / "cap_secret"
        if p.exists():
            return p.read_bytes()
        secret = secrets.token_bytes(32)
        p.write_bytes(secret)
        os.chmod(p, 0o600)
        return secret

    def mint(
        self,
        action: str,
        risk: Risk,
        target: Optional[str],
        uid: int,
        ttl: float,
        confirmed: bool = False,
        meta: Optional[dict] = None,
    ) -> Capability:
        raw = f"{action}|{target}|{uid}|{time.time()}|{secrets.token_hex(8)}"
        token = hmac.new(self._secret, raw.encode(), hashlib.sha256).hexdigest()
        cap = Capability(
            token=token,
            action=action,
            risk=risk,
            target=target,
            uid=uid,
            issued_at=time.time(),
            expires_at=time.time() + ttl,
            confirmed=confirmed,
            meta=meta or {},
        )
        self._caps[token] = cap
        return cap

    def get(self, token: str) -> Capability:
        cap = self._caps.get(token)
        if not cap:
            raise AiosError(ErrorCode.REVOKED, "unknown capability")
        if not cap.alive():
            self._caps.pop(token, None)
            raise AiosError(ErrorCode.REVOKED, "capability expired")
        return cap

    def revoke(self, token: str) -> None:
        self._caps.pop(token, None)

    def revoke_all(self) -> int:
        n = len(self._caps)
        self._caps.clear()
        return n


class PolicyEngine:
    """In-process policy used by aios-policy daemon and tests."""

    def __init__(
        self,
        auto_confirm_max: Risk = Risk.L1,
        allow_remote_confirm: bool = False,
        headless_auto_confirm: bool = False,
    ):
        self.auto_confirm_max = auto_confirm_max
        self.allow_remote_confirm = allow_remote_confirm
        self.headless_auto_confirm = headless_auto_confirm or os.environ.get("AIOS_HEADLESS") == "1"
        self.caps = CapabilityStore()
        self.audit = AuditLog()
        self._pending_confirms: dict[str, dict] = {}
        self._trust: dict[str, float] = {}  # key -> expires
        self.ttl = {Risk.L0: 3600.0, Risk.L1: 600.0, Risk.L2: 120.0, Risk.L3: 60.0}

    def risk_for(self, action: str) -> Risk:
        if action in DEFAULT_RISKS:
            return DEFAULT_RISKS[action]
        if action.startswith("dcp.act."):
            return Risk.L1
        if action.startswith("sys.power."):
            return Risk.L3
        return Risk.L2

    def check_sensitive_ui(self, node: Optional[dict]) -> None:
        if not node:
            return
        role = (node.get("role") or "").lower()
        if role in SENSITIVE_ROLES or node.get("sensitive_value"):
            raise AiosError(ErrorCode.DENIED_UI, "sensitive UI denied")

    def authorize(
        self,
        action: str,
        *,
        target: Optional[str] = None,
        uid: Optional[int] = None,
        node: Optional[dict] = None,
        confirmed: bool = False,
        confirm_id: Optional[str] = None,
        transport: str = "local",
        client_id: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> PolicyDecision:
        uid = os.getuid() if uid is None else uid
        risk = self.risk_for(action)
        try:
            self.check_sensitive_ui(node)
        except AiosError as e:
            self.audit.append(
                {
                    "type": "deny",
                    "action": action,
                    "target": target,
                    "code": int(e.code),
                    "reason": e.reason,
                    "transport": transport,
                    "client_id": client_id,
                }
            )
            return PolicyDecision(False, risk, False, e.reason, code=e.code)

        need = risk > self.auto_confirm_max
        trust_key = f"{uid}:{action}:{target or '*'}"
        if trust_key in self._trust and self._trust[trust_key] > time.time() and risk <= Risk.L1:
            need = False

        if confirm_id and confirm_id in self._pending_confirms:
            pending = self._pending_confirms.pop(confirm_id)
            if pending.get("action") == action:
                confirmed = True
                need = False

        if need and not confirmed:
            if self.headless_auto_confirm and risk <= Risk.L2:
                # CI/dev: auto-confirm L2 max when AIOS_HEADLESS=1; L3 still blocked unless confirmed
                if risk < Risk.L3:
                    confirmed = True
                    need = False
                else:
                    cid = str(uuid.uuid4())
                    self._pending_confirms[cid] = {"action": action, "target": target, "risk": int(risk)}
                    self.audit.append(
                        {
                            "type": "need_confirm",
                            "action": action,
                            "target": target,
                            "risk": int(risk),
                            "confirm_id": cid,
                            "transport": transport,
                            "client_id": client_id,
                        }
                    )
                    return PolicyDecision(
                        False,
                        risk,
                        True,
                        "NEED_CONFIRM",
                        code=ErrorCode.NEED_CONFIRM,
                        capability=None,
                    )
            else:
                cid = str(uuid.uuid4())
                self._pending_confirms[cid] = {"action": action, "target": target, "risk": int(risk)}
                self.audit.append(
                    {
                        "type": "need_confirm",
                        "action": action,
                        "target": target,
                        "risk": int(risk),
                        "confirm_id": cid,
                        "transport": transport,
                        "client_id": client_id,
                    }
                )
                cap = None
                return PolicyDecision(
                    False,
                    risk,
                    True,
                    "NEED_CONFIRM",
                    code=ErrorCode.NEED_CONFIRM,
                    capability=cap,
                )

        cap = self.caps.mint(
            action=action,
            risk=risk,
            target=target,
            uid=uid,
            ttl=self.ttl[risk],
            confirmed=confirmed or not need,
            meta=meta or {},
        )
        self.audit.append(
            {
                "type": "allow",
                "action": action,
                "target": target,
                "risk": int(risk),
                "token": cap.token[:12],
                "transport": transport,
                "client_id": client_id,
            }
        )
        return PolicyDecision(True, risk, False, "OK", capability=cap)

    def confirm(self, confirm_id: str, approved: bool = True) -> dict:
        pending = self._pending_confirms.get(confirm_id)
        if not pending:
            raise AiosError(ErrorCode.NOT_FOUND, "unknown confirm_id")
        if not approved:
            self._pending_confirms.pop(confirm_id, None)
            self.audit.append({"type": "confirm_denied", "confirm_id": confirm_id})
            return {"ok": False}
        # Keep pending so authorize(confirm_id=...) can consume; mark approved
        pending["approved"] = True
        self.audit.append({"type": "confirm_ok", "confirm_id": confirm_id})
        return {"ok": True, "pending": pending}

    def grant_trust(self, action: str, target: Optional[str], ttl: float = 300.0) -> None:
        key = f"{os.getuid()}:{action}:{target or '*'}"
        self._trust[key] = time.time() + ttl

    def freeze_all(self) -> int:
        n = self.caps.revoke_all()
        self.audit.append({"type": "freeze", "revoked": n})
        return n

    def list_pending(self) -> list:
        return [{"confirm_id": k, **v} for k, v in self._pending_confirms.items()]


def load_policy_config() -> dict:
    p = config_dir() / "policy.yaml"
    if not p.exists():
        return {}
    import yaml

    return yaml.safe_load(p.read_text()) or {}