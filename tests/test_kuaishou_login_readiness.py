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
from core.cdp_client import CDPError


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


class _CapturePublishCDP:
    def __init__(self):
        self.script = ""
        self.scripts = []
        self.calls = 0

    def evaluate(self, script):
        self.calls += 1
        self.script = script
        self.scripts.append(script)
        if self.calls > 1:
            return {
                "published": True,
                "text": "内容发布成功",
                "url": "https://cp.kuaishou.com/article/publish/video?tabType=1",
            }
        return {"ok": True, "tag": "DIV"}

    def sleep(self, _seconds):
        return None


class _RecordingUI:
    def __init__(self):
        self.selectors = []

    def click_element(self, selector):
        self.selectors.append(selector)


class _NoTerminalPublishCDP(_CapturePublishCDP):
    def evaluate(self, script):
        self.calls += 1
        self.script = script
        if self.calls > 1:
            return {
                "published": False,
                "text": "",
                "url": "https://cp.kuaishou.com/article/publish/video?tabType=1",
            }
        return {"ok": True, "tag": "DIV"}


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

    def test_publish_click_uses_visible_primary_div_instead_of_invalid_css(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _CapturePublishCDP()
        publisher.ui = _RecordingUI()

        publisher._click_publish()

        scripts = "\n".join(publisher.cdp.scripts)
        self.assertIn("text === '发布'", scripts)
        self.assertIn("_button-primary_", scripts)
        self.assertNotIn(":has-text", scripts)
        self.assertEqual(publisher.ui.selectors, [])

    def test_publish_click_without_terminal_fact_is_error(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _NoTerminalPublishCDP()

        with patch.object(
            publisher_core,
            "PUBLISH_RESULT_ATTEMPTS",
            1,
            create=True,
        ):
            with self.assertRaisesRegex(CDPError, "终态"):
                publisher._click_publish()


if __name__ == "__main__":
    unittest.main()
