
"""DCP data models: targets, widgets, snapshots."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Bounds:
    x: float
    y: float
    w: float
    h: float
    scale: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Widget:
    id: str
    parent_id: Optional[str]
    role: str
    name: str = ""
    text: str = ""
    bounds: Optional[Bounds] = None
    visible: bool = True
    enabled: bool = True
    focused: bool = False
    checked: Optional[bool] = None
    actions: list[str] = field(default_factory=lambda: ["click"])
    rev: int = 0
    sensitive_value: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.bounds:
            d["bounds"] = self.bounds.to_dict()
        return d


@dataclass
class Target:
    id: str
    title: str
    app_id: str = ""
    pid: int = 0
    channel_hint: str = "fixture"  # mirror|atspi|protocol|vision|fixture
    focused: bool = False
    visible: bool = True
    bounds: Optional[Bounds] = None
    widgets: list[Widget] = field(default_factory=list)

    def to_dict(self, include_widgets: bool = False) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "app_id": self.app_id,
            "pid": self.pid,
            "channel_hint": self.channel_hint,
            "focused": self.focused,
            "visible": self.visible,
        }
        if self.bounds:
            d["bounds"] = self.bounds.to_dict()
        if include_widgets:
            d["widgets"] = [w.to_dict() for w in self.widgets]
        return d


@dataclass
class ActResult:
    ok: bool
    mode: str
    reason: str
    tx: str
    assert_ok: Optional[bool] = None
    data: Any = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "reason": self.reason,
            "tx": self.tx,
            "assert": "ok" if self.assert_ok else ("fail" if self.assert_ok is False else None),
            "data": self.data,
        }
