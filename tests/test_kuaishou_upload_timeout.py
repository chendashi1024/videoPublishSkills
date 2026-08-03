"""快手大视频上传等待时间回归测试。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.kuaishou import publisher_core
from scripts.kuaishou.publisher_core import KuaishouPublisherCore


class _UploadCDP:
    def send(self, _method, _params):
        return {}

    def evaluate(self, _script):
        return {"ok": True}

    def sleep(self, _seconds):
        return None


class _UploadUI:
    def __init__(self):
        self.timeout = None

    def find_element(self, _selector):
        return {"nodeId": 1}

    def wait_for_element(self, _selector, *, timeout, poll_interval):
        self.timeout = timeout
        return {"nodeId": 2}


class _CoverCDP:
    def __init__(self):
        self.states = [
            {"ready": False, "reason": "封面编辑入口仍在 loading"},
            {"ready": True, "x": 1, "y": 2, "w": 3, "h": 4},
        ]

    def evaluate(self, _script):
        return self.states.pop(0)

    def sleep(self, _seconds):
        return None


class KuaishouUploadTimeoutTest(unittest.TestCase):
    def test_large_video_gets_more_than_fixed_three_minute_form_budget(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _UploadCDP()
        publisher.ui = _UploadUI()

        with patch.object(
            publisher_core.os.path,
            "getsize",
            return_value=751 * 1024 * 1024,
        ):
            publisher._upload_video("/tmp/large.mov")

        self.assertGreaterEqual(publisher.ui.timeout, 540)
        self.assertEqual(publisher._active_video_wait_timeout, publisher.ui.timeout)

    def test_cover_wait_reuses_the_large_video_budget(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _CoverCDP()
        publisher._active_video_wait_timeout = 1

        with (
            patch.object(publisher_core, "VIDEO_PROCESS_TIMEOUT", 0),
            patch.object(publisher_core, "VIDEO_PROCESS_POLL", 0),
        ):
            state = publisher._wait_for_cover_editor_entry()

        self.assertTrue(state["ready"])


if __name__ == "__main__":
    unittest.main()
