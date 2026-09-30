"""Channel backends for DCP: fixture, AT-SPI, vision stub."""
from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from aios_common.errors import AiosError, ErrorCode
from aios_dcpd.models import ActResult, Bounds, Target, Widget

log = logging.getLogger("aios.dcp.channels")


class Channel:
    name = "base"

    def list_targets(self) -> list[Target]:
        return []

    def snapshot(self, target_id: str) -> Target:
        raise AiosError(ErrorCode.NOT_FOUND, f"target {target_id}")

    def find(self, target_id: str, query: dict) -> list[Widget]:
        t = self.snapshot(target_id)
        return match_widgets(t.widgets, query)

    def act(self, target_id: str, action: str, args: dict) -> ActResult:
        raise AiosError(ErrorCode.CHANNEL_UNAVAILABLE, f"{self.name} cannot act")


def match_widgets(widgets: list[Widget], query: dict) -> list[Widget]:
    out = []
    for w in widgets:
        if not w.visible:
            continue
        ok = True
        if "id" in query and w.id != query["id"]:
            ok = False
        if "role" in query and w.role.lower() != str(query["role"]).lower():
            ok = False
        if "name" in query and query["name"].lower() not in (w.name or "").lower():
            ok = False
        if "text" in query and query["text"].lower() not in (w.text or "").lower():
            ok = False
        if "contains" in query:
            needle = str(query["contains"]).lower()
            blob = f"{w.name} {w.text} {w.role}".lower()
            if needle not in blob:
                ok = False
        if ok:
            out.append(w)
    return out


class FixtureChannel(Channel):
    """Headless synthetic UI tree for CI and daily builds."""

    name = "fixture"

    def __init__(self):
        self._targets: dict[str, Target] = {}
        self._load_default()
        self._load_from_disk()

    def _load_default(self) -> None:
        tid = "fixture:hello"
        widgets = [
            Widget("w_win", None, "window", name="Hello luminOS", text="Hello luminOS", actions=[]),
            Widget(
                "w_label",
                "w_win",
                "label",
                name="status",
                text="Ready",
                bounds=Bounds(20, 20, 200, 24),
                actions=[],
            ),
            Widget(
                "w_entry",
                "w_win",
                "entry",
                name="input",
                text="",
                bounds=Bounds(20, 60, 240, 32),
                actions=["set_text", "click"],
            ),
            Widget(
                "w_btn_ok",
                "w_win",
                "button",
                name="OK",
                text="OK",
                bounds=Bounds(20, 110, 80, 32),
                actions=["click"],
            ),
            Widget(
                "w_btn_send",
                "w_win",
                "button",
                name="Send",
                text="发送",
                bounds=Bounds(120, 110, 80, 32),
                actions=["click"],
            ),
            Widget(
                "w_pwd",
                "w_win",
                "password_text",
                name="password",
                text="",
                bounds=Bounds(20, 160, 240, 32),
                actions=["set_text"],
                sensitive_value=True,
            ),
        ]
        self._targets[tid] = Target(
            id=tid,
            title="Hello luminOS",
            app_id="org.luminos.fixture.hello",
            pid=os.getpid(),
            channel_hint="fixture",
            focused=True,
            bounds=Bounds(100, 100, 400, 300),
            widgets=widgets,
        )

    def _load_from_disk(self) -> None:
        fixtures = Path(__file__).resolve().parents[3] / "fixtures" / "synthetic"
        tree = fixtures / "tree.json"
        if not tree.exists():
            return
        data = json.loads(tree.read_text())
        for item in data.get("targets", []):
            widgets = []
            for w in item.get("widgets", []):
                b = w.get("bounds")
                widgets.append(
                    Widget(
                        id=w["id"],
                        parent_id=w.get("parent_id"),
                        role=w.get("role", "unknown"),
                        name=w.get("name", ""),
                        text=w.get("text", ""),
                        bounds=Bounds(**b) if b else None,
                        visible=w.get("visible", True),
                        enabled=w.get("enabled", True),
                        actions=w.get("actions", ["click"]),
                        sensitive_value=w.get("sensitive_value", False),
                    )
                )
            t = Target(
                id=item["id"],
                title=item.get("title", ""),
                app_id=item.get("app_id", ""),
                pid=item.get("pid", 0),
                channel_hint="fixture",
                focused=bool(item.get("focused")),
                widgets=widgets,
            )
            self._targets[t.id] = t

    def list_targets(self) -> list[Target]:
        return list(self._targets.values())

    def snapshot(self, target_id: str) -> Target:
        if target_id not in self._targets:
            raise AiosError(ErrorCode.NOT_FOUND, f"target {target_id}")
        return self._targets[target_id]

    def act(self, target_id: str, action: str, args: dict) -> ActResult:
        t = self.snapshot(target_id)
        tx = f"tx_{uuid.uuid4().hex[:8]}"
        node_id = args.get("node") or args.get("node_id")
        widget = next((w for w in t.widgets if w.id == node_id), None) if node_id else None
        if action == "click":
            if not widget:
                raise AiosError(ErrorCode.NOT_FOUND, "node not found")
            if widget.sensitive_value or widget.role == "password_text":
                raise AiosError(ErrorCode.DENIED_UI, "sensitive UI denied")
            if widget.id == "w_btn_ok":
                for w in t.widgets:
                    if w.id == "w_label":
                        entry = next((x for x in t.widgets if x.id == "w_entry"), None)
                        w.text = f"OK:{entry.text if entry else ''}"
                        w.rev += 1
            if widget.id == "w_btn_send":
                for w in t.widgets:
                    if w.id == "w_label":
                        w.text = "SENT"
                        w.rev += 1
            return ActResult(True, "MODE_A", "MODE_A", tx, True, {"node": widget.id})
        if action in ("ime_commit", "set_text"):
            if not widget:
                raise AiosError(ErrorCode.NOT_FOUND, "node not found")
            if widget.sensitive_value or widget.role == "password_text":
                raise AiosError(ErrorCode.DENIED_UI, "sensitive UI denied")
            text = args.get("text", "")
            widget.text = text
            widget.rev += 1
            return ActResult(True, "MODE_A", "MODE_A", tx, True, {"node": widget.id, "text_len": len(text)})
        if action == "scroll":
            return ActResult(True, "MODE_A", "MODE_A", tx, True, {"dx": args.get("dx", 0), "dy": args.get("dy", 0)})
        if action == "key":
            return ActResult(True, "MODE_C", "MODE_C", tx, True, {"key": args.get("key")})
        raise AiosError(ErrorCode.NOT_FOUND, f"unknown action {action}")


class AtsPiChannel(Channel):
    name = "atspi"

    def list_targets(self) -> list[Target]:
        try:
            import gi

            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
        except Exception as e:  # noqa: BLE001
            log.debug("AT-SPI unavailable: %s", e)
            return []
        try:
            Atspi.init()
            desktop = Atspi.get_desktop(0)
        except Exception as e:  # noqa: BLE001
            log.warning("AT-SPI init failed: %s", e)
            return []
        targets: list[Target] = []
        try:
            n = desktop.get_child_count()
        except Exception:
            return []
        for i in range(n):
            try:
                app = desktop.get_child_at_index(i)
                if not app:
                    continue
                name = app.get_name() or f"app-{i}"
                tid = f"atspi:{i}:{name}"
                targets.append(
                    Target(id=tid, title=name, app_id=name, channel_hint="atspi", widgets=[])
                )
            except Exception:  # noqa: BLE001
                continue
        return targets

    def snapshot(self, target_id: str) -> Target:
        for t in self.list_targets():
            if t.id == target_id or t.title in target_id:
                t.widgets = [
                    Widget(
                        id=f"{t.id}:root",
                        parent_id=None,
                        role="application",
                        name=t.title,
                        text=t.title,
                        actions=["click"],
                    )
                ]
                return t
        raise AiosError(ErrorCode.NOT_FOUND, f"atspi target {target_id}")

    def act(self, target_id: str, action: str, args: dict) -> ActResult:
        raise AiosError(ErrorCode.CHANNEL_UNAVAILABLE, "ATSPI_ACT_UNBOUND")


class VisionChannel(Channel):
    """Mode-C stub: synthetic OCR anchors for fixture regression."""

    name = "vision"

    def __init__(self, fixture: FixtureChannel):
        self.fixture = fixture

    def list_targets(self) -> list[Target]:
        return []

    def snapshot(self, target_id: str) -> Target:
        # Prefer fixture pixel-less OCR nodes
        t = self.fixture.snapshot(target_id)
        # Mark channel as vision overlay
        clone = Target(
            id=t.id,
            title=t.title,
            app_id=t.app_id,
            pid=t.pid,
            channel_hint="vision",
            focused=t.focused,
            visible=t.visible,
            bounds=t.bounds,
            widgets=list(t.widgets),
        )
        return clone

    def act(self, target_id: str, action: str, args: dict) -> ActResult:
        # Coordinate click fallback without real compositor injection
        tx = f"tx_{uuid.uuid4().hex[:8]}"
        if action == "click" and ("x" in args and "y" in args):
            return ActResult(True, "MODE_C", "MODE_C", tx, True, {"x": args["x"], "y": args["y"]})
        # Fall through to fixture semantic when node given
        return self.fixture.act(target_id, action, args)
