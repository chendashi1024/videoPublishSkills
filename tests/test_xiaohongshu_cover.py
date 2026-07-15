"""小红书视频封面裁剪回归测试。"""

import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.publish_pipeline import (
    _find_xiaohongshu_cover_confirm_rect,
    _xiaohongshu_cover_zoom_ready,
)


class _RecordingPublisher:
    def __init__(self):
        self.expression = ""

    def _evaluate(self, expression):
        self.expression = expression
        return {"x": 1, "y": 2, "w": 3, "h": 4}


class XiaohongshuCoverZoomReadyTest(unittest.TestCase):
    def test_original_ratio_without_slider_accepts_complete_three_four_image(self):
        self.assertTrue(
            _xiaohongshu_cover_zoom_ready("", "原始", [(1086, 1448)])
        )

    def test_three_four_ratio_without_slider_accepts_complete_three_four_image(self):
        self.assertTrue(
            _xiaohongshu_cover_zoom_ready("", "3:4", [(1086, 1448)])
        )

    def test_other_ratio_without_slider_is_rejected(self):
        self.assertFalse(
            _xiaohongshu_cover_zoom_ready("", "16:9", [(1086, 1448)])
        )

    def test_original_ratio_without_slider_rejects_incomplete_image(self):
        self.assertFalse(
            _xiaohongshu_cover_zoom_ready("", "原始", [(1086, 1400)])
        )

    def test_existing_slider_still_requires_one_hundred_percent(self):
        self.assertTrue(
            _xiaohongshu_cover_zoom_ready("100%", "16:9", [(1086, 1400)])
        )
        self.assertFalse(
            _xiaohongshu_cover_zoom_ready("99%", "原始", [(1086, 1448)])
        )


class XiaohongshuCoverConfirmScopeTest(unittest.TestCase):
    def test_confirm_button_lookup_is_scoped_to_cover_modal(self):
        publisher = _RecordingPublisher()

        rect = _find_xiaohongshu_cover_confirm_rect(publisher)

        self.assertEqual(rect, {"x": 1, "y": 2, "w": 3, "h": 4})
        self.assertIn("document.querySelector('.cover-modal')", publisher.expression)
        self.assertIn("candidate.querySelector", publisher.expression)
        self.assertIn("modal.querySelectorAll('button')", publisher.expression)
        self.assertNotIn("document.querySelectorAll('.cover-modal button", publisher.expression)


if __name__ == "__main__":
    unittest.main()
