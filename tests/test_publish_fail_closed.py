"""四平台填稿关键字段必须失败关闭。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.cdp_client import CDPError
from scripts.bilibili.publisher_core import BilibiliPublisherCore
from scripts.publish_pipeline import (
    CDPError as PipelineCDPError,
    _select_bilibili_tags,
    _upload_douyin_covers,
)


class _NoCoverEntryCDP:
    def evaluate(self, _script):
        return False


class _CaptureEvaluateCDP:
    def __init__(self):
        self.script = ""

    def evaluate(self, script):
        self.script = script
        return {"ok": True}


class _PublishButtonCDP:
    def __init__(self, states):
        self.states = list(states)
        self.evaluate_calls = 0
        self.sleep_calls = 0

    def evaluate(self, _script):
        self.evaluate_calls += 1
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def sleep(self, _seconds, minimum_seconds=None):
        self.sleep_calls += 1


class _ExistingBilibiliDraftsCDP:
    def evaluate(self, _script):
        return {
            "count": 9,
            "titles": ["OPC 视频发布测试"] * 7 + ["AI先淘汰岗位思维"] * 2,
        }


class _PersistentProcessingUI:
    def __init__(self):
        self.clicked = False

    def find_element(self, _selector, timeout=0):
        return {"nodeId": 1}

    def click_element(self, _selector):
        self.clicked = True


class PublishFailClosedTest(unittest.TestCase):
    def test_bilibili_existing_local_drafts_block_new_upload(self):
        publisher = BilibiliPublisherCore.__new__(BilibiliPublisherCore)
        publisher.cdp = _ExistingBilibiliDraftsCDP()

        with self.assertRaisesRegex(CDPError, "9 个未提交视频"):
            publisher._assert_no_existing_local_drafts()

    def test_douyin_cover_failure_blocks_ready_status(self):
        with (
            patch(
                "scripts.publish_pipeline._upload_douyin_cover_card",
                return_value=False,
            ),
            patch(
                "scripts.publish_pipeline._click_douyin_horizontal_cover_prompt",
                return_value=False,
            ),
        ):
            with self.assertRaisesRegex(PipelineCDPError, "抖音竖封面"):
                _upload_douyin_covers(
                    object(),
                    "/tmp/vertical.png",
                    "/tmp/horizontal.png",
                )

    def test_bilibili_missing_tag_blocks_ready_status(self):
        publisher = object()
        with patch(
            "scripts.publish_pipeline._evaluate_js",
            side_effect=[
                None,
                None,
                {"already": True},
                {"already": True},
                ["人工智能"],
            ],
        ):
            with self.assertRaisesRegex(PipelineCDPError, "一人公司"):
                _select_bilibili_tags(
                    publisher,
                    ["#人工智能", "#一人公司"],
                    timing_jitter=0,
                )

    def test_bilibili_missing_cover_entry_is_error(self):
        publisher = BilibiliPublisherCore.__new__(BilibiliPublisherCore)
        publisher.cdp = _NoCoverEntryCDP()

        with self.assertRaisesRegex(CDPError, "主封面"):
            publisher._upload_cover("/tmp/horizontal.png")

    def test_bilibili_cover_dispatches_file_input_events(self):
        publisher = BilibiliPublisherCore.__new__(BilibiliPublisherCore)
        publisher.cdp = _CaptureEvaluateCDP()

        dispatch = getattr(publisher, "_dispatch_cover_input_events", None)
        self.assertIsNotNone(dispatch)
        dispatch()

        self.assertIn("new Event('input'", publisher.cdp.script)
        self.assertIn("new Event('change'", publisher.cdp.script)

    def test_bilibili_ready_button_wins_over_stale_processing_node(self):
        publisher = BilibiliPublisherCore.__new__(BilibiliPublisherCore)
        publisher.cdp = _PublishButtonCDP([
            {"status": "ready", "reason": "立即投稿按钮可用"},
        ])
        publisher.ui = _PersistentProcessingUI()

        with patch("scripts.bilibili.publisher_core.VIDEO_PROCESS_TIMEOUT", 0.01):
            publisher._wait_video_processing()

        self.assertEqual(publisher.cdp.evaluate_calls, 1)

    def test_bilibili_disabled_submit_button_blocks_click(self):
        publisher = BilibiliPublisherCore.__new__(BilibiliPublisherCore)
        publisher.cdp = _PublishButtonCDP([
            {"status": "disabled", "reason": "立即投稿按钮尚未启用"},
        ])
        publisher.ui = _PersistentProcessingUI()

        with self.assertRaisesRegex(CDPError, "尚未启用"):
            publisher._click_publish()

        self.assertFalse(publisher.ui.clicked)

    def test_bilibili_ready_submit_button_is_clicked_once(self):
        publisher = BilibiliPublisherCore.__new__(BilibiliPublisherCore)
        publisher.cdp = _PublishButtonCDP([
            {"status": "clicked", "reason": "已点击立即投稿", "clicked": True},
        ])
        publisher.ui = _PersistentProcessingUI()

        publisher._click_publish()

        self.assertEqual(publisher.cdp.evaluate_calls, 1)
        self.assertFalse(publisher.ui.clicked)


if __name__ == "__main__":
    unittest.main()
