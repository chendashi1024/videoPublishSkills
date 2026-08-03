import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "publish_pipeline", SCRIPTS / "publish_pipeline.py"
)
assert SPEC and SPEC.loader
publish_pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_pipeline)


def test_default_is_handoff_and_direct_publish_requires_explicit_flag():
    assert publish_pipeline.resolve_publish_mode(
        auto_publish=False, preview=False
    ) == "HANDOFF"
    assert publish_pipeline.resolve_publish_mode(
        auto_publish=False, preview=True
    ) == "HANDOFF"
    assert publish_pipeline.resolve_publish_mode(
        auto_publish=True, preview=False
    ) == "DIRECT_PUBLISH"

    with pytest.raises(ValueError, match="不能同时"):
        publish_pipeline.resolve_publish_mode(auto_publish=True, preview=True)


def test_direct_publish_waits_then_clicks_exactly_once():
    calls = []

    class Publisher:
        def _wait_video_processing(self):
            calls.append("wait")

        def _click_publish(self):
            calls.append("click")
            return "https://example.com/published"

    result = publish_pipeline.execute_direct_publish(Publisher(), is_video_mode=True)

    assert result == "https://example.com/published"
    assert calls == ["wait", "click"]


def test_handoff_mode_never_calls_direct_publish_executor():
    assert publish_pipeline.should_execute_direct_publish("HANDOFF") is False
    assert publish_pipeline.should_execute_direct_publish("DIRECT_PUBLISH") is True
