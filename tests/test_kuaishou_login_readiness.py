"""快手上传页异步就绪时的登录检测回归测试。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.kuaishou import publisher_core
from scripts.kuaishou.publisher_core import KuaishouPublisherCore


class _DelayedUploadPageCDP:
    def __init__(self):
        self.ws = object()
        self.states = [
            {
                "hasVideoUploadInput": False,
                "hasEditorForm": False,
                "hasLoginCallToAction": False,
            },
            {
                "hasVideoUploadInput": True,
                "hasEditorForm": False,
                "hasLoginCallToAction": False,
            },
        ]

    def get_current_url(self):
        return "https://cp.kuaishou.com/article/publish/video?tabType=1"

    def evaluate(self, _script):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def sleep(self, _seconds):
        return None


class KuaishouLoginReadinessTest(unittest.TestCase):
    def test_waits_for_upload_page_before_reporting_logged_out(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _DelayedUploadPageCDP()

        with (
            patch.object(publisher_core, "PAGE_LOAD_WAIT", 0),
            patch.object(
                publisher_core,
                "LOGIN_PAGE_READY_TIMEOUT",
                1,
                create=True,
            ),
        ):
            self.assertTrue(publisher.check_login())


if __name__ == "__main__":
    unittest.main()
