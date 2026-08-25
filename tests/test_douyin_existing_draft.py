"""抖音已填稿续发必须跳过重复上传并只点击表单按钮。"""

import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.cdp_client import CDPError
from douyin.existing_draft import (
    ExistingDraftPublishOutcomeUnknown,
    click_existing_draft_once,
    verify_existing_draft,
)


class _DraftCDP:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.sent = []

    def evaluate(self, _expression):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def send(self, method, params):
        self.sent.append((method, params))


def _draft_snapshot(*, title="正确标题", content="正确正文"):
    return {
        "url": "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
        "inputs": [title, "2026-08-25 17:00"],
        "editorText": content + "\u200b #OPC",
        "publishButtons": [
            {"text": "发布", "x": 100, "y": 700, "width": 80, "height": 32}
        ],
    }


def test_existing_draft_requires_exact_title_and_body():
    cdp = _DraftCDP([_draft_snapshot(title="其他标题")])

    with pytest.raises(CDPError, match="标题.*不匹配"):
        verify_existing_draft(
            cdp,
            expected_title="正确标题",
            expected_content="正确正文",
        )

    assert cdp.sent == []


def test_existing_draft_clicks_exactly_once_and_accepts_submit_transition():
    cdp = _DraftCDP(
        [
            _draft_snapshot(),
            {
                "url": "https://creator.douyin.com/creator-micro/content/manage?enter_from=publish",
                "successText": True,
            },
        ]
    )

    result = click_existing_draft_once(
        cdp,
        expected_title="正确标题",
        expected_content="正确正文",
        timeout_seconds=0.1,
    )

    click_events = [
        params["type"]
        for method, params in cdp.sent
        if method == "Input.dispatchMouseEvent"
        and params["type"] in {"mousePressed", "mouseReleased"}
    ]
    assert click_events == ["mousePressed", "mouseReleased"]
    assert result["submitted"] is True


def test_existing_draft_unknown_outcome_never_clicks_twice():
    cdp = _DraftCDP([_draft_snapshot()])

    with pytest.raises(ExistingDraftPublishOutcomeUnknown, match="禁止重试"):
        click_existing_draft_once(
            cdp,
            expected_title="正确标题",
            expected_content="正确正文",
            timeout_seconds=0,
        )

    click_events = [
        params["type"]
        for method, params in cdp.sent
        if method == "Input.dispatchMouseEvent"
        and params["type"] in {"mousePressed", "mouseReleased"}
    ]
    assert click_events == ["mousePressed", "mouseReleased"]
