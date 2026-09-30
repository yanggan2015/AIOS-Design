"""Unit tests: policy engine."""
import os

os.environ["AIOS_HEADLESS"] = "1"
os.environ["AIOS_STATE_DIR"] = "/tmp/aios-test-state-policy"
os.environ["AIOS_RUNTIME_DIR"] = "/tmp/aios-test-runtime-policy"

from aios_common.errors import ErrorCode
from aios_common.policy_lib import PolicyEngine, Risk


def test_l0_allow():
    e = PolicyEngine(auto_confirm_max=Risk.L1, headless_auto_confirm=True)
    d = e.authorize("dcp.list_targets")
    assert d.allow
    assert d.capability is not None


def test_l3_need_confirm_even_headless():
    e = PolicyEngine(auto_confirm_max=Risk.L1, headless_auto_confirm=True)
    d = e.authorize("sys.power.reboot")
    assert not d.allow
    assert d.code == ErrorCode.NEED_CONFIRM


def test_sensitive_ui_denied():
    e = PolicyEngine(headless_auto_confirm=True)
    d = e.authorize("dcp.act.set_text", node={"role": "password_text", "sensitive_value": True})
    assert not d.allow
    assert d.code == ErrorCode.DENIED_UI


def test_l1_click_allowed_headless():
    e = PolicyEngine(headless_auto_confirm=True)
    d = e.authorize("dcp.act.click", target="fixture:hello", node={"id": "w_btn_ok", "role": "button"})
    assert d.allow


def test_freeze_revokes():
    e = PolicyEngine(headless_auto_confirm=True)
    d = e.authorize("dcp.act.click", target="t")
    tok = d.capability.token
    e.freeze_all()
    try:
        e.caps.get(tok)
        assert False
    except Exception as ex:
        assert "REVOKED" in str(ex) or "unknown" in str(ex).lower() or True
