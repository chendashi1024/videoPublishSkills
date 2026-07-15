"""快手封面编辑入口选择回归测试。"""

import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.kuaishou.publisher_core import KuaishouPublisherCore


class _StopAfterEntryClick(Exception):
    """首次点击封面入口后终止测试流程。"""


class _FakeCDP:
    """模拟 default-cover 在 DOM 中早于 cover-full-editor。"""

    def __init__(self, has_full_editor=True):
        self.has_full_editor = has_full_editor

    def evaluate(self, script):
        compact_script = "".join(script.split())
        if "querySelectorAll('[class*=\"default-cover\"],[class*=\"cover-full-editor\"]')" in compact_script:
            return {"kind": "default-cover"}
        prioritized_selector = (
            "querySelectorAll('[class*=\"cover-full-editor\"]')).find(visible)||"
            "Array.from(document.querySelectorAll('[class*=\"default-cover\"]'))"
            ".find(visible)"
        )
        if prioritized_selector in compact_script:
            kind = "cover-full-editor" if self.has_full_editor else "default-cover"
            return {"kind": kind}
        return None


class KuaishouCoverEntryTest(unittest.TestCase):
    def _capture_entry_click(self, has_full_editor):
        publisher = KuaishouPublisherCore.__new__(KuaishouPublisherCore)
        publisher.cdp = _FakeCDP(has_full_editor=has_full_editor)
        clicked = []

        def stop_after_click(rect):
            clicked.append(rect)
            raise _StopAfterEntryClick

        publisher._click_rect_center = stop_after_click

        with self.assertRaises(_StopAfterEntryClick):
            publisher._upload_cover("/tmp/cover.png")

        return clicked

    def test_upload_cover_prioritizes_full_editor_over_default_cover(self):
        self.assertEqual(
            self._capture_entry_click(has_full_editor=True),
            [{"kind": "cover-full-editor"}],
        )

    def test_upload_cover_falls_back_to_default_cover(self):
        self.assertEqual(
            self._capture_entry_click(has_full_editor=False),
            [{"kind": "default-cover"}],
        )


if __name__ == "__main__":
    unittest.main()
