"""快手封面编辑入口选择回归测试。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.kuaishou import publisher_core
from scripts.kuaishou.publisher_core import KuaishouPublisherCore
from core.cdp_client import CDPError


class _StopAfterEntryClick(Exception):
    """首次点击封面入口后终止测试流程。"""


class _FakeCDP:
    """模拟封面入口从未就绪到可点击的异步过程。"""

    def __init__(self, states):
        self.states = list(states)
        self.index = 0

    def get_current_url(self):
        return "https://cp.kuaishou.com/article/publish/video?tabType=1"

    def evaluate(self, script):
        compact_script = "".join(script.split())
        if "cover-full-editor" in compact_script and "scrollIntoView" in compact_script:
            state = self.states[min(self.index, len(self.states) - 1)]
            self.index += 1
            return state
        return None

    def sleep(self, _seconds):
        return None


class _CaptureEvaluateCDP:
    """记录补发文件输入事件使用的脚本。"""

    def __init__(self):
        self.script = ""

    def evaluate(self, script):
        self.script = script
        return {"ok": True}


class KuaishouCoverEntryTest(unittest.TestCase):
    def _capture_entry_click(self, states):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _FakeCDP(states)
        clicked = []

        def stop_after_click(rect):
            clicked.append(rect)
            raise _StopAfterEntryClick

        publisher._click_rect_center = stop_after_click

        with self.assertRaises(_StopAfterEntryClick):
            publisher._upload_cover("/tmp/cover.png")

        return clicked

    def test_upload_cover_waits_until_full_editor_is_present_and_not_loading(self):
        ready_rect = {
            "ready": True,
            "kind": "cover-full-editor",
            "x": 10,
            "y": 20,
            "w": 100,
            "h": 80,
        }
        self.assertEqual(
            self._capture_entry_click([
                {
                    "ready": False,
                    "reason": "full editor absent",
                    "kind": "default-cover",
                },
                {
                    "ready": False,
                    "reason": "cover loading",
                    "kind": "cover-full-editor",
                },
                ready_rect,
            ]),
            [ready_rect],
        )

    def test_upload_cover_times_out_instead_of_clicking_default_cover(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _FakeCDP([None])

        with (
            patch.object(publisher_core, "VIDEO_PROCESS_TIMEOUT", 0.01),
            patch.object(publisher_core, "VIDEO_PROCESS_POLL", 0),
        ):
            with self.assertRaises(CDPError) as error:
                publisher._upload_cover("/tmp/cover.png")

        self.assertRegex(
            str(error.exception),
            "等待快手视频上传/处理完成超时.*cover-full-editor",
        )

    def test_file_input_dispatches_input_and_change_events(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _CaptureEvaluateCDP()

        publisher._dispatch_file_input_events('input[type="file"]')

        self.assertIn("new Event('input'", publisher.cdp.script)
        self.assertIn("new Event('change'", publisher.cdp.script)


if __name__ == "__main__":
    unittest.main()
