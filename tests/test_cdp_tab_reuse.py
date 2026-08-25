"""CDP 标签页复用必须限制在同平台。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core import cdp_client
from core.cdp_client import CDPClient
from douyin.publisher_core import DouyinPublisherCore


class _NewTabResponse:
    ok = True

    @staticmethod
    def json():
        return {"webSocketDebuggerUrl": "ws://new-xiaohongshu"}


class _TabFixtureClient(CDPClient):
    def get_targets(self):
        return [
            {
                "type": "page",
                "url": "https://member.bilibili.com/platform/upload/video/frame",
                "webSocketDebuggerUrl": "ws://bilibili",
            },
            {
                "type": "page",
                "url": "https://creator.douyin.com/creator-micro/content/post/video",
                "webSocketDebuggerUrl": "ws://douyin",
            },
        ]


class _DouyinTabFixtureClient(_TabFixtureClient):
    def connect(
        self,
        target_url_prefix="",
        reuse_existing_tab=False,
        default_url="about:blank",
    ):
        self.selected = self.find_or_create_tab(
            target_url_prefix=target_url_prefix,
            reuse_existing_tab=reuse_existing_tab,
            default_url=default_url,
        )


class CDPTabReuseTest(unittest.TestCase):
    def test_douyin_reuses_filled_editor_after_upload_redirect(self):
        publisher = DouyinPublisherCore.__new__(DouyinPublisherCore)
        publisher.cdp = _DouyinTabFixtureClient()

        with patch.object(
            cdp_client.requests,
            "put",
            return_value=_NewTabResponse(),
        ) as create_tab:
            publisher.connect(reuse_existing_tab=True)

        self.assertEqual(publisher.cdp.selected, "ws://douyin")
        create_tab.assert_not_called()

    def test_reuse_does_not_overwrite_another_platform_tab(self):
        client = _TabFixtureClient()

        with patch.object(
            cdp_client.requests,
            "put",
            return_value=_NewTabResponse(),
        ) as create_tab:
            selected = client.find_or_create_tab(
                target_url_prefix="https://creator.xiaohongshu.com/",
                reuse_existing_tab=True,
                default_url="https://creator.xiaohongshu.com/publish/publish",
            )

        self.assertEqual(selected, "ws://new-xiaohongshu")
        create_tab.assert_called_once()


if __name__ == "__main__":
    unittest.main()
