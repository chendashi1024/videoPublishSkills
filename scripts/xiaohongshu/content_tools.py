"""
小红书内容工具模块

包含内容管理相关功能：
- 搜索笔记
- 获取笔记详情
- 发表评论
- 获取通知
- 获取内容数据
"""

import json
import os
import sys
import time
from typing import Any

# 添加父目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from core.cdp_client import CDPClient, CDPError
from core.ui_automator import UIAutomator
from .config import *


class ContentTools:
    """
    小红书内容工具

    提供内容管理功能：
    - 搜索笔记
    - 获取笔记详情
    - 发表评论
    - 获取通知
    - 获取内容数据
    """

    def __init__(self, cdp: CDPClient, ui: UIAutomator):
        """
        初始化内容工具

        Args:
            cdp: CDP 客户端实例
            ui: UI 自动化器实例
        """
        self.cdp = cdp
        self.ui = ui

    # ========================================================================
    # 搜索功能
    # ========================================================================

    def search_feeds(
        self,
        keyword: str,
        filters: Any = None,
    ) -> dict[str, Any]:
        """
        搜索笔记

        Args:
            keyword: 搜索关键词
            filters: 搜索筛选条件

        Returns:
            搜索结果字典
        """
        print(f"[ContentTools] 搜索笔记: {keyword}")

        # 导入 feed_explorer 模块
        try:
            from feed_explorer import FeedExplorer, make_search_url
        except ImportError:
            raise CDPError("未找到 feed_explorer 模块")

        # 构建搜索 URL
        search_url = make_search_url(keyword, filters)

        # 使用 FeedExplorer 执行搜索
        explorer = FeedExplorer(self.cdp, self.ui)
        result = explorer.search(search_url, keyword)

        return result

    def get_feed_detail(self, feed_id: str, xsec_token: str) -> dict[str, Any]:
        """
        获取笔记详情

        Args:
            feed_id: 笔记 ID
            xsec_token: 安全令牌

        Returns:
            笔记详情字典
        """
        print(f"[ContentTools] 获取笔记详情: {feed_id}")

        # 导入 feed_explorer 模块
        try:
            from feed_explorer import make_feed_detail_url
        except ImportError:
            raise CDPError("未找到 feed_explorer 模块")

        # 构建详情 URL
        detail_url = make_feed_detail_url(feed_id, xsec_token)

        # 导航到详情页
        self.cdp.navigate(detail_url)
        self.cdp.sleep(3, minimum_seconds=1.0)

        # 检查页面是否可访问
        self._check_feed_page_accessible()

        # 提取详情数据（简化版，完整实现需要从原文件迁移）
        result = {
            "feed_id": feed_id,
            "xsec_token": xsec_token,
            "url": detail_url,
            "accessible": True,
        }

        return result

    def _check_feed_page_accessible(self):
        """
        检查笔记页面是否可访问

        Raises:
            CDPError: 页面不可访问
        """
        # 检查是否有不可访问的关键词
        page_text = self.cdp.evaluate("document.body.textContent")

        for keyword in XHS_FEED_INACCESSIBLE_KEYWORDS:
            if keyword in page_text:
                raise CDPError(f"笔记不可访问: {keyword}")

    # ========================================================================
    # 评论功能
    # ========================================================================

    def post_comment_to_feed(
        self,
        feed_id: str,
        xsec_token: str,
        content: str,
    ) -> dict[str, Any]:
        """
        发表评论

        Args:
            feed_id: 笔记 ID
            xsec_token: 安全令牌
            content: 评论内容

        Returns:
            评论结果字典
        """
        print(f"[ContentTools] 发表评论: {feed_id}")

        # 导入 feed_explorer 模块
        try:
            from feed_explorer import make_feed_detail_url
        except ImportError:
            raise CDPError("未找到 feed_explorer 模块")

        # 导航到笔记详情页
        detail_url = make_feed_detail_url(feed_id, xsec_token)
        self.cdp.navigate(detail_url)
        self.cdp.sleep(3, minimum_seconds=1.0)

        # 检查页面是否可访问
        self._check_feed_page_accessible()

        # 填写评论内容
        self._fill_comment_content(content)

        # 点击发布按钮
        self._click_comment_submit()

        result = {
            "feed_id": feed_id,
            "content": content,
            "success": True,
        }

        return result

    def _fill_comment_content(self, content: str) -> int:
        """
        填写评论内容

        Args:
            content: 评论内容

        Returns:
            填写的字符数
        """
        print(f"[ContentTools] 填写评论内容 ({len(content)} 字符)")

        # 查找评论输入框（简化版，完整实现需要从原文件迁移）
        comment_selectors = [
            'textarea[placeholder*="评论"]',
            'textarea[placeholder*="comment"]',
            '[contenteditable="true"][placeholder*="评论"]',
        ]

        for selector in comment_selectors:
            if self.ui.element_exists(selector):
                self.ui.fill_input(selector, content, wait_after=1.0)
                return len(content)

        raise CDPError("未找到评论输入框")

    def _click_comment_submit(self):
        """点击评论发布按钮"""
        print("[ContentTools] 点击评论发布按钮")

        # 查找发布按钮
        submit_selectors = [
            'button:has-text("发布")',
            'button:has-text("评论")',
            '[class*="submit"]',
        ]

        for selector in submit_selectors:
            try:
                self.ui.click_element(selector, wait_after=2.0)
                return
            except CDPError:
                continue

        raise CDPError("未找到评论发布按钮")

    # ========================================================================
    # 通知功能
    # ========================================================================

    def get_notification_mentions(self, wait_seconds: float = 18.0) -> dict[str, Any]:
        """
        获取评论和@通知

        Args:
            wait_seconds: 等待时间（秒）

        Returns:
            通知数据字典
        """
        print("[ContentTools] 获取通知数据")

        # 导航到通知页面
        self.cdp.navigate(XHS_NOTIFICATION_URL)
        self.cdp.sleep(3, minimum_seconds=1.0)

        # 点击"评论和@"标签页
        self._click_notification_mentions_tab()

        # 等待数据加载
        self.cdp.sleep(wait_seconds, minimum_seconds=5.0)

        # 抓取通知数据（简化版，完整实现需要从原文件迁移）
        result = {
            "url": XHS_NOTIFICATION_URL,
            "mentions": [],
            "count": 0,
        }

        return result

    def _click_notification_mentions_tab(self):
        """点击通知页面的"评论和@"标签页"""
        print("[ContentTools] 点击'评论和@'标签页")

        # 查找标签页
        tab_texts = ["评论和@", "评论", "mentions"]

        for text in tab_texts:
            try:
                self.ui.click_element_by_text('[class*="tab"]', text, wait_after=2.0)
                return
            except CDPError:
                continue

        print("[ContentTools] 未找到'评论和@'标签页，继续...")

    # ========================================================================
    # 数据分析功能
    # ========================================================================

    def get_content_data(
        self,
        page_num: int = 1,
        page_size: int = 10,
        note_type: int = 0,
    ) -> dict[str, Any]:
        """
        获取内容数据

        Args:
            page_num: 页码
            page_size: 每页数量
            note_type: 笔记类型（0=全部）

        Returns:
            内容数据字典
        """
        print(f"[ContentTools] 获取内容数据 (页码={page_num}, 每页={page_size})")

        # 导航到数据分析页面
        self.cdp.navigate(XHS_CONTENT_DATA_URL)
        self.cdp.sleep(5, minimum_seconds=2.0)

        # 抓取数据（简化版，完整实现需要从原文件迁移）
        result = {
            "page_num": page_num,
            "page_size": page_size,
            "note_type": note_type,
            "notes": [],
            "total": 0,
        }

        return result


# ============================================================================
# 辅助函数（从原文件迁移）
# ============================================================================

def _build_search_filters_from_args(args) -> Any:
    """从 CLI 参数构建搜索筛选条件"""
    try:
        from feed_explorer import SearchFilters
        filters = SearchFilters(
            sort_by=getattr(args, "sort_by", None),
            note_type=getattr(args, "note_type", None),
            publish_time=getattr(args, "publish_time", None),
            search_scope=getattr(args, "search_scope", None),
            location=getattr(args, "location", None),
        )
        return filters if filters.selected_items() else None
    except ImportError:
        return None
