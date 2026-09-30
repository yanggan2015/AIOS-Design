"""Unit tests: fixture DCP channel without daemons."""
import os

os.environ["AIOS_HEADLESS"] = "1"
os.environ["AIOS_STATE_DIR"] = "/tmp/aios-test-state-dcp"
os.environ["AIOS_RUNTIME_DIR"] = "/tmp/aios-test-runtime-dcp"

from aios_dcpd.channels import FixtureChannel
from aios_dcpd.engine import DcpEngine
from aios_common.errors import AiosError, ErrorCode


def test_fixture_hello_tree():
    ch = FixtureChannel()
    targets = ch.list_targets()
    assert any(t.id == "fixture:hello" for t in targets)
    snap = ch.snapshot("fixture:hello")
    assert any(w.id == "w_btn_ok" for w in snap.widgets)


def test_fixture_type_and_click():
    ch = FixtureChannel()
    r = ch.act("fixture:hello", "ime_commit", {"node": "w_entry", "text": "你好"})
    assert r.ok and r.mode == "MODE_A"
    r2 = ch.act("fixture:hello", "click", {"node": "w_btn_ok"})
    assert r2.ok
    snap = ch.snapshot("fixture:hello")
    label = next(w for w in snap.widgets if w.id == "w_label")
    assert label.text == "OK:你好"


def test_password_denied():
    ch = FixtureChannel()
    try:
        ch.act("fixture:hello", "ime_commit", {"node": "w_pwd", "text": "secret"})
        assert False
    except AiosError as e:
        assert e.code == ErrorCode.DENIED_UI


def test_engine_list_without_policy():
    eng = DcpEngine(use_policy=False)
    ts = eng.list_targets()
    assert ts
