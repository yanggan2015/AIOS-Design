"""DCP fusion engine: Mode-A → Mode-B → Mode-C with freeze & assert."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from aios_common.errors import AiosError, ErrorCode
from aios_common.ipc import call as rpc_call
from aios_dcpd.channels import AtsPiChannel, FixtureChannel, VisionChannel, match_widgets
from aios_dcpd.models import ActResult, Target, Widget

log = logging.getLogger("aios.dcp.engine")


class DcpEngine:
    def __init__(self, use_policy: bool = True):
        self.fixture = FixtureChannel()
        self.atspi = AtsPiChannel()
        self.vision = VisionChannel(self.fixture)
        self.frozen = False
        self.use_policy = use_policy
        self._tx_log: list[dict] = []
        self._local_stats: dict[str, dict] = {}

    def list_targets(self) -> list[dict]:
        seen = {}
        for ch in (self.fixture, self.atspi):
            for t in ch.list_targets():
                seen[t.id] = t.to_dict(False)
        return list(seen.values())

    def _resolve_channel(self, target_id: str):
        if target_id.startswith("fixture:") or target_id in {t.id for t in self.fixture.list_targets()}:
            return self.fixture, "MODE_A"
        try:
            self.atspi.snapshot(target_id)
            return self.atspi, "MODE_A"
        except AiosError:
            pass
        # last resort vision over fixture id
        return self.vision, "MODE_C"

    def snapshot(self, target_id: str) -> dict:
        ch, _mode = self._resolve_channel(target_id)
        t = ch.snapshot(target_id)
        return t.to_dict(include_widgets=True)

    def find(self, target_id: str, query: dict) -> list[dict]:
        ch, _ = self._resolve_channel(target_id)
        widgets = ch.find(target_id, query)
        return [w.to_dict() for w in widgets]

    async def _authorize(self, action: str, target: Optional[str], node: Optional[dict], confirmed: bool = False) -> dict:
        if not self.use_policy:
            return {"allow": True, "reason": "OK", "code": 0}
        try:
            return await rpc_call(
                "policy",
                "authorize",
                {
                    "action": action,
                    "target": target,
                    "node": node,
                    "confirmed": confirmed,
                    "transport": "local",
                },
            )
        except Exception as e:  # noqa: BLE001
            # If policy daemon down in early boot, deny side-effects
            log.warning("policy unavailable: %s", e)
            if action.startswith("dcp.list") or action.startswith("dcp.snapshot") or action.startswith("dcp.find"):
                return {"allow": True, "reason": "POLICY_DOWN_READONLY", "code": 0}
            raise AiosError(ErrorCode.FORBIDDEN, "policy unavailable") from e

    async def act(self, target_id: str, action: str, args: dict, confirmed: bool = False) -> dict:
        if self.frozen:
            raise AiosError(ErrorCode.BUSY, "DCP frozen")
        node = None
        node_id = args.get("node") or args.get("node_id")
        if node_id:
            found = self.find(target_id, {"id": node_id})
            node = found[0] if found else {"id": node_id}
        policy_action = f"dcp.act.{action}"
        decision = await self._authorize(policy_action, target_id, node, confirmed=confirmed)
        if not decision.get("allow"):
            raise AiosError(
                ErrorCode(decision.get("code", ErrorCode.FORBIDDEN)),
                decision.get("reason", "FORBIDDEN"),
                decision,
            )
        ch, preferred = self._resolve_channel(target_id)
        try:
            result = ch.act(target_id, action, args)
        except AiosError as e:
            if e.code == ErrorCode.CHANNEL_UNAVAILABLE and ch is not self.vision:
                log.info("degrade %s -> MODE_C: %s", preferred, e.reason)
                result = self.vision.act(target_id, action, args)
            else:
                raise
        self._tx_log.append({"tx": result.tx, "action": action, "target": target_id, "ts": time.time()})
        app_id = self.snapshot(target_id).get("app_id", "unknown")
        st = self._local_stats.setdefault(app_id, {"ok": 0, "fail": 0, "mode": {}})
        st["ok"] += 1
        st["mode"][result.mode] = st["mode"].get(result.mode, 0) + 1
        out = result.to_dict()
        if decision.get("capability"):
            out["capability"] = decision["capability"]
        return out

    async def assert_cond(self, target_id: str, condition: dict, timeout_ms: int = 3000) -> dict:
        deadline = time.time() + timeout_ms / 1000.0
        last = None
        while time.time() < deadline:
            if "text_equals" in condition:
                node = condition.get("node")
                widgets = self.find(target_id, {"id": node} if node else {"contains": condition["text_equals"]})
                last = widgets
                for w in widgets:
                    if w.get("text") == condition["text_equals"] or condition["text_equals"] in (w.get("text") or ""):
                        return {"ok": True, "matched": w}
            elif "exists" in condition:
                widgets = self.find(target_id, condition["exists"])
                last = widgets
                if widgets:
                    return {"ok": True, "matched": widgets[0]}
            else:
                raise AiosError(ErrorCode.NOT_FOUND, "unknown assert condition")
            time.sleep(0.05)
        raise AiosError(ErrorCode.TIMEOUT, "assert timeout", {"last": last})

    def freeze(self) -> dict:
        self.frozen = True
        return {"frozen": True}

    def unfreeze(self) -> dict:
        self.frozen = False
        return {"frozen": False}

    def stats(self) -> dict:
        return dict(self._local_stats)
