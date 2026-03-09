"""
CDP-based Xiaohongshu publisher (重构版)

向后兼容的 CLI 入口，内部使用模块化架构

CLI usage:
    # Basic commands
    python cdp_publish.py [--host HOST] [--port PORT] check-login
    python cdp_publish.py [--host HOST] [--port PORT] fill --title "标题" --content "正文" --images img1.jpg
    python cdp_publish.py [--host HOST] [--port PORT] publish --title "标题" --content "正文" --images img1.jpg
    python cdp_publish.py [--host HOST] [--port PORT] click-publish
    python cdp_publish.py [--host HOST] [--port PORT] search-feeds --keyword "关键词"
    python cdp_publish.py [--host HOST] [--port PORT] get-feed-detail --feed-id FEED_ID --xsec-token TOKEN
    python cdp_publish.py [--host HOST] [--port PORT] post-comment-to-feed --feed-id FEED_ID --xsec-token TOKEN --content "评论"
    python cdp_publish.py [--host HOST] [--port PORT] get-notification-mentions
    python cdp_publish.py [--host HOST] [--port PORT] content-data

    # Account management
    python cdp_publish.py [--host HOST] [--port PORT] login [--account NAME]
    python cdp_publish.py [--host HOST] [--port PORT] list-accounts
    python cdp_publish.py [--host HOST] [--port PORT] add-account NAME [--alias ALIAS]
    python cdp_publish.py [--host HOST] [--port PORT] remove-account NAME

Library usage:
    from cdp_publish import XiaohongshuPublisher

    publisher = XiaohongshuPublisher()
    publisher.connect()
    publisher.check_login()
    publisher.publish(
        title="Article title",
        content="Article body text",
        image_paths=["/path/to/img1.jpg", "/path/to/img2.jpg"],
    )
"""

import json
import os
import sys

# 确保 UTF-8 输出
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 添加 scripts 目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from xiaohongshu.publisher_core import XiaohongshuPublisherCore
from xiaohongshu.content_tools import ContentTools, _build_search_filters_from_args
from xiaohongshu.config import *


# ============================================================================
# 向后兼容的统一入口类
# ============================================================================

class CDPError(Exception):
    """CDP 通信错误（向后兼容）"""


class XiaohongshuPublisher:
    """
    小红书发布器（向后兼容的统一入口）

    内部使用模块化架构：
    - core: XiaohongshuPublisherCore (发布核心)
    - tools: ContentTools (内容工具)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9222,
        timing_jitter: float = 0.25,
        account_name: str | None = None,
    ):
        """
        初始化发布器

        Args:
            host: CDP 服务地址
            port: CDP 服务端口
            timing_jitter: 时间抖动比例
            account_name: 账号名称
        """
        # 初始化核心模块
        self.core = XiaohongshuPublisherCore(host, port, timing_jitter, account_name)
        self.tools = ContentTools(self.core.cdp, self.core.ui)

        # 向后兼容的属性
        self.host = host
        self.port = port
        self.ws = None  # 由 core.cdp.ws 管理
        self.account_name = account_name or "default"

    # ========================================================================
    # 连接管理（代理到 core）
    # ========================================================================

    def connect(self, target_url_prefix: str = "", reuse_existing_tab: bool = False):
        """连接到 Chrome"""
        self.core.connect(reuse_existing_tab=reuse_existing_tab)
        self.ws = self.core.cdp.ws  # 同步 ws 属性

    def disconnect(self):
        """断开连接"""
        self.core.disconnect()
        self.ws = None

    # ========================================================================
    # 登录管理（代理到 core.login）
    # ========================================================================

    def check_login(self) -> bool:
        """检查创作者中心登录状态"""
        return self.core.check_login()

    def check_home_login(self) -> bool:
        """检查主页登录状态"""
        return self.core.check_home_login()

    def clear_cookies(self, domain: str = COOKIE_DOMAIN):
        """清除 Cookie"""
        self.core.clear_cookies()

    def open_login_page(self):
        """打开登录页面"""
        self.core.open_login_page()

    # ========================================================================
    # 发布功能（代理到 core）
    # ========================================================================

    def publish(
        self,
        title: str,
        content: str,
        image_paths: list[str] | None = None,
    ):
        """发布图文内容"""
        self.core.publish(title, content, image_paths)

    def publish_video(
        self,
        title: str,
        content: str,
        video_path: str,
    ):
        """发布视频内容"""
        self.core.publish_video(title, content, video_path)

    def click_publish(self) -> str | None:
        """点击发布按钮"""
        return self.core.click_publish_button()

    # ========================================================================
    # 内容工具（代理到 tools）
    # ========================================================================

    def search_feeds(self, keyword: str, filters=None) -> dict:
        """搜索笔记"""
        return self.tools.search_feeds(keyword, filters)

    def get_feed_detail(self, feed_id: str, xsec_token: str) -> dict:
        """获取笔记详情"""
        return self.tools.get_feed_detail(feed_id, xsec_token)

    def post_comment_to_feed(self, feed_id: str, xsec_token: str, content: str) -> dict:
        """发表评论"""
        return self.tools.post_comment_to_feed(feed_id, xsec_token, content)

    def get_notification_mentions(self, wait_seconds: float = 18.0) -> dict:
        """获取通知"""
        return self.tools.get_notification_mentions(wait_seconds)

    def get_content_data(
        self,
        page_num: int = 1,
        page_size: int = 10,
        note_type: int = 0,
    ) -> dict:
        """获取内容数据"""
        return self.tools.get_content_data(page_num, page_size, note_type)

    # ========================================================================
    # 内部方法（向后兼容，代理到 core）
    # ========================================================================

    def _navigate(self, url: str):
        """导航到 URL"""
        self.core.cdp.navigate(url)

    def _evaluate(self, expression: str):
        """执行 JavaScript"""
        return self.core.cdp.evaluate(expression)

    def _send(self, method: str, params: dict | None = None) -> dict:
        """发送 CDP 命令"""
        return self.core.cdp.send(method, params)

    def _sleep(self, base_seconds: float, minimum_seconds: float = 0.05):
        """延迟"""
        self.core.cdp.sleep(base_seconds, minimum_seconds)


# ============================================================================
# CLI 入口（从原文件保留，简化版）
# ============================================================================

def main():
    """CLI 主入口"""
    import argparse

    # 由于原 main() 函数有 400+ 行，这里先创建一个简化版
    # 完整版本需要从原文件的 main() 函数迁移

    parser = argparse.ArgumentParser(description="小红书 CDP 发布器")
    parser.add_argument("--host", default="127.0.0.1", help="CDP 服务地址")
    parser.add_argument("--port", type=int, default=9222, help="CDP 服务端口")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--account", help="账号名称")
    parser.add_argument("--timing-jitter", type=float, default=0.25, help="时间抖动比例")
    parser.add_argument("--reuse-existing-tab", action="store_true", help="复用已有标签页")

    sub = parser.add_subparsers(dest="command", required=True)

    # check-login
    sub.add_parser("check-login", help="检查登录状态")

    # login
    sub.add_parser("login", help="打开登录页面")

    # fill
    fill_parser = sub.add_parser("fill", help="填写内容（不发布）")
    fill_parser.add_argument("--title", help="标题")
    fill_parser.add_argument("--title-file", help="标题文件")
    fill_parser.add_argument("--content", help="正文")
    fill_parser.add_argument("--content-file", help="正文文件")
    fill_parser.add_argument("--images", nargs="+", help="图片路径")
    fill_parser.add_argument("--video", help="视频路径")

    # publish
    publish_parser = sub.add_parser("publish", help="发布内容")
    publish_parser.add_argument("--title", help="标题")
    publish_parser.add_argument("--title-file", help="标题文件")
    publish_parser.add_argument("--content", help="正文")
    publish_parser.add_argument("--content-file", help="正文文件")
    publish_parser.add_argument("--images", nargs="+", help="图片路径")
    publish_parser.add_argument("--video", help="视频路径")

    # click-publish
    sub.add_parser("click-publish", help="点击发布按钮")

    # search-feeds
    search_parser = sub.add_parser("search-feeds", help="搜索笔记")
    search_parser.add_argument("--keyword", required=True, help="搜索关键词")
    search_parser.add_argument("--sort-by", help="排序方式")
    search_parser.add_argument("--note-type", help="笔记类型")

    # 其他命令...（完整版本需要从原文件迁移）

    args = parser.parse_args()

    # 创建发布器实例
    publisher = XiaohongshuPublisher(
        host=args.host,
        port=args.port,
        timing_jitter=args.timing_jitter,
        account_name=args.account,
    )

    try:
        # 连接
        publisher.connect(reuse_existing_tab=args.reuse_existing_tab)

        # 执行命令
        if args.command == "check-login":
            logged_in = publisher.check_login()
            sys.exit(0 if logged_in else 1)

        elif args.command == "login":
            publisher.open_login_page()
            print("请在浏览器中完成登录")

        elif args.command in ("fill", "publish"):
            # 读取标题和正文
            title = args.title
            if args.title_file:
                with open(args.title_file, "r", encoding="utf-8") as f:
                    title = f.read().strip()

            content = args.content
            if args.content_file:
                with open(args.content_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()

            # 发布
            if args.video:
                publisher.publish_video(title, content, args.video)
            else:
                publisher.publish(title, content, args.images)

            # 如果是 publish 命令，点击发布按钮
            if args.command == "publish":
                note_link = publisher.click_publish()
                if note_link:
                    print(f"发布成功: {note_link}")

        elif args.command == "click-publish":
            note_link = publisher.click_publish()
            if note_link:
                print(f"发布成功: {note_link}")

        elif args.command == "search-feeds":
            filters = _build_search_filters_from_args(args)
            result = publisher.search_feeds(args.keyword, filters)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        else:
            print(f"未实现的命令: {args.command}")
            print("完整命令列表请参考原 cdp_publish.py.backup")
            sys.exit(1)

    except CDPError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    finally:
        publisher.disconnect()


if __name__ == "__main__":
    main()
