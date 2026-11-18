from __future__ import annotations

import json
from io import StringIO

from coo.doctor import run_checks, run_doctor


def test_doctor_has_no_failures_in_the_repo():
    checks = run_checks()
    assert [check for check in checks if check.level == "fail"] == []
    assert any(check.name == "plugin" and check.level == "pass" for check in checks)


def test_doctor_json_report():
    stream = StringIO()
    code = run_doctor(json_output=True, stream=stream)
    payload = json.loads(stream.getvalue())
    assert payload["ok"] is True
    assert code == 0
    assert {check["name"] for check in payload["checks"]} >= {"python", "store", "plugin", "llm"}


def test_doctor_quiet_suppresses_passes():
    stream = StringIO()
    run_doctor(quiet=True, stream=stream)
    assert "PASS" not in stream.getvalue()
