from pydantic import ValidationError

from coo.schemas.brief import Brief
from coo.schemas.export import MODELS, dump_json_schemas
from coo.schemas.plan import Plan
from coo.schemas.strategy import Strategy
from tests.factories import valid_brief, valid_plan, valid_strategy


def test_brief_rejects_bad_question_status():
    payload = valid_brief("cmp-20260101-abcd1234")
    payload["open_questions"] = [
        {
            "id": "q1",
            "question": "Budget?",
            "status": "maybe",
            "answer": None,
            "defer_reason": None,
        }
    ]
    try:
        Brief.model_validate(payload)
        raise AssertionError("expected validation error")
    except ValidationError:
        pass


def test_strategy_forbids_tactic_keys():
    payload = valid_strategy("cmp-20260101-abcd1234")
    payload["channels"] = ["tv"]
    try:
        Strategy.model_validate(payload)
        raise AssertionError("expected extra-field rejection")
    except ValidationError:
        pass


def test_plan_roundtrip():
    plan = Plan.model_validate(valid_plan("cmp-20260101-abcd1234"))
    assert plan.tactics[0].kpi_id == "kpi_awareness"


def test_dump_json_schemas(tmp_path):
    written = dump_json_schemas(tmp_path)
    names = {path.name for path in written}
    assert names == {f"{key}.json" for key in MODELS}
    for path in written:
        assert path.stat().st_size > 20
