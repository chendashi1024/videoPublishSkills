"""快手人工接管后不得重试填稿的回归测试。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.kuaishou.publisher_core import KuaishouPublisherCore
from core import cdp_client


class _ManagePageCDP:
    ws = object()

    def get_current_url(self):
        return "https://cp.kuaishou.com/article/manage/video?status=2&from=publish"


class _PublishPageCDP(_ManagePageCDP):
    def get_current_url(self):
        return "https://cp.kuaishou.com/article/publish/video?tabType=1"


class KuaishouManualTakeoverTest(unittest.TestCase):
    def test_upload_wait_stops_when_user_leaves_editor_for_manage_page(self):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _ManagePageCDP()

        if not hasattr(publisher, "_wait_for_upload_form"):
            self.fail("快手上传等待尚不能检测人工接管")

        manual_takeover = getattr(cdp_client, "ManualTakeoverDetected", None)
        if manual_takeover is None:
            self.fail("缺少不可重试的人工接管状态")

        with self.assertRaises(manual_takeover):
            publisher._wait_for_upload_form()

    def test_publish_video_does_not_convert_manual_takeover_to_generic_error(self):
        manual_takeover = getattr(cdp_client, "ManualTakeoverDetected", None)
        if manual_takeover is None:
            self.fail("缺少不可重试的人工接管状态")

        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _PublishPageCDP()
        with patch.object(
            publisher,
            "_upload_video",
            side_effect=manual_takeover(
                "https://cp.kuaishou.com/article/manage/video?status=2&from=publish"
            ),
        ):
            with self.assertRaises(manual_takeover):
                publisher.publish_video(
                    title="标题",
                    content="正文",
                    video_path="/tmp/video.mov",
                    auto_publish=False,
                )


if __name__ == "__main__":
    unittest.main()
