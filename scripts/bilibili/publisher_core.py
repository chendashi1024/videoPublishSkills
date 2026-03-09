"""
B站发布器核心模块

包含所有发布相关的核心功能：
- 视频发布
- 标题/简介填写
- 标签处理
- 分区选择
- 封面上传
- 发布按钮点击
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

from core.base_publisher import BasePublisher
from core.cdp_client import CDPClient, CDPError
from core.login_manager import LoginManager
from core.ui_automator import UIAutomator
from .config import *


class BilibiliPublisherCore(BasePublisher):
    """
    B站发布器核心

    提供完整的发布功能：
    - 视频发布
    - 标题/简介填写
    - 标签处理
    - 分区选择
    - 封面上传
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9222,
        timing_jitter: float = 0.25,
        account_name: str | None = None,
    ):
        """
        初始化 B站发布器

        Args:
            host: CDP 服务地址
            port: CDP 服务端口
            timing_jitter: 时间抖动比例
            account_name: 账号名称
        """
        # 调用基类初始化
        super().__init__(host, port, timing_jitter, account_name)

        # 初始化核心组件
        self.cdp = CDPClient(host, port, timing_jitter)
        self.login = LoginManager(
            self.cdp,
            account_name=account_name or "default",
            cache_ttl_hours=DEFAULT_LOGIN_CACHE_TTL_HOURS,
            cache_file=LOGIN_CACHE_FILE,
        )
        self.ui = UIAutomator(self.cdp)

    # ========================================================================
    # 连接管理
    # ========================================================================

    def connect(self, reuse_existing_tab: bool = False):
        """连接到 Chrome"""
        self.cdp.connect(
            target_url_prefix=BILIBILI_CREATOR_URL,
            reuse_existing_tab=reuse_existing_tab,
            default_url=BILIBILI_CREATOR_URL,
        )

    def disconnect(self):
        """断开连接"""
        self.cdp.disconnect()

    # ========================================================================
    # 登录管理
    # ========================================================================

    def check_login(self) -> bool:
        """检查登录状态"""
        if not self.cdp.ws:
            raise CDPError("未连接，请先调用 connect()")

        self.cdp.navigate(BILIBILI_CREATOR_LOGIN_CHECK_URL)
        self.cdp.sleep(PAGE_LOAD_WAIT)

        # 检查是否有登录指示器
        has_login = self.ui.wait_for_element(
            SELECTORS["login_indicator"],
            timeout=5,
        )

        return has_login

    def open_login_page(self):
        """打开登录页面"""
        if not self.cdp.ws:
            raise CDPError("未连接，请先调用 connect()")

        self.cdp.navigate(BILIBILI_CREATOR_URL)
        self.cdp.sleep(PAGE_LOAD_WAIT)
        print("[Bilibili] 请在浏览器中扫码登录")

    def clear_cookies(self):
        """清除 Cookie"""
        self.login.clear_cookies(COOKIE_DOMAIN)

    # ========================================================================
    # 发布功能
    # ========================================================================

    def publish(
        self,
        title: str,
        content: str,
        image_paths: list[str] | None = None,
        auto_publish: bool = True,
    ) -> dict[str, Any]:
        """
        发布图文内容（B站主要是视频平台）

        Args:
            title: 标题
            content: 正文
            image_paths: 图片路径列表
            auto_publish: 是否自动点击发布按钮

        Returns:
            dict: 发布结果
        """
        return {
            "status": "error",
            "message": "B站主要支持视频发布，请使用 publish_video 方法",
        }

    def publish_video(
        self,
        title: str,
        content: str,
        video_path: str,
        cover_path: str | None = None,
        auto_publish: bool = True,
    ) -> dict[str, Any]:
        """
        发布视频内容

        Args:
            title: 标题
            content: 简介
            video_path: 视频文件路径
            cover_path: 封面图片路径（可选）
            auto_publish: 是否自动点击发布按钮

        Returns:
            dict: 发布结果
        """
        if not self.cdp.ws:
            raise CDPError("未连接，请先调用 connect()")

        if not video_path:
            raise CDPError("B站发布视频需要提供视频文件")

        try:
            # 1. 导航到发布页面
            self.cdp.navigate(BILIBILI_CREATOR_URL)
            self.cdp.sleep(PAGE_LOAD_WAIT)

            # 2. 上传视频
            self._upload_video(video_path)

            # 3. 填写标题（视频上传后立即可填写，无需等待处理完成）
            self._fill_title(title)

            # 4. 填写简介
            self._fill_content(content)

            # 5. 上传封面（如果提供）
            if cover_path:
                self._upload_cover(cover_path)

            # 6. 等待视频处理完成并发布（仅在需要发布时等待）
            if auto_publish:
                self._wait_video_processing()
                self._click_publish()
                return {"status": "success", "message": "视频发布成功"}
            else:
                return {"status": "success", "message": "视频内容已填写完成，等待手动发布"}

        except Exception as e:
            return {"status": "error", "message": f"发布失败: {str(e)}"}

    # ========================================================================
    # 内部辅助方法
    # ========================================================================

    def _upload_video(self, video_path: str):
        """上传视频"""
        print(f"[Bilibili] 上传视频: {video_path}")

        # 查找文件输入框
        file_input = self.ui.find_element(SELECTORS["video_upload_input"])
        if not file_input:
            # 尝试备用选择器
            file_input = self.ui.find_element(SELECTORS["video_upload_input_name"])

        if not file_input:
            raise CDPError("未找到视频上传输入框")

        # 设置文件路径
        self.cdp.send("DOM.setFileInputFiles", {
            "files": [video_path],
            "nodeId": file_input["nodeId"],
        })

        self.cdp.sleep(UPLOAD_WAIT)
        print("[Bilibili] 视频上传中...")

    def _wait_video_processing(self):
        """等待视频处理完成"""
        print("[Bilibili] 等待视频处理...")

        start_time = time.time()
        while time.time() - start_time < VIDEO_PROCESS_TIMEOUT:
            # 检查是否还有处理指示器
            processing = self.ui.find_element(
                SELECTORS["video_processing_indicator"],
                timeout=2,
            )

            if not processing:
                print("[Bilibili] 视频处理完成")
                return

            self.cdp.sleep(VIDEO_PROCESS_POLL)

        raise CDPError(f"视频处理超时（{VIDEO_PROCESS_TIMEOUT}秒）")

    def _fill_title(self, title: str):
        """填写标题"""
        print(f"[Bilibili] 填写标题: {title}")

        self.ui.fill_input(
            SELECTORS["title_input"],
            title,
            clear_first=True,
        )

        self.cdp.sleep(ACTION_INTERVAL)

    def _fill_content(self, content: str):
        """填写简介"""
        print(f"[Bilibili] 填写简介: {content[:50]}...")

        # 智能判断编辑器类型
        is_contenteditable = self.cdp.evaluate(f"""
            (() => {{
                const el = document.querySelector({json.dumps(SELECTORS["content_input"])});
                return el && el.getAttribute('contenteditable') === 'true';
            }})()
        """)

        if is_contenteditable:
            self.ui.fill_contenteditable(
                SELECTORS["content_input"],
                content,
                clear_first=True,
            )
        else:
            self.ui.fill_input(
                SELECTORS["content_input"],
                content,
                clear_first=True,
            )

        self.cdp.sleep(ACTION_INTERVAL)

    def _upload_cover(self, cover_path: str):
        """上传封面"""
        print(f"[Bilibili] 上传封面: {cover_path}")

        # 查找封面上传输入框
        cover_input = self.ui.find_element(SELECTORS["cover_upload_input"])
        if not cover_input:
            print("[Bilibili] 未找到封面上传输入框，跳过")
            return

        # 设置文件路径
        self.cdp.send("DOM.setFileInputFiles", {
            "files": [cover_path],
            "nodeId": cover_input["nodeId"],
        })

        self.cdp.sleep(2)

    def _click_publish(self):
        """点击发布按钮"""
        print("[Bilibili] 点击发布按钮...")

        self.ui.click_element(SELECTORS["publish_button"])
        self.cdp.sleep(2)

        print("[Bilibili] 发布完成")

    # ========================================================================
    # 平台信息
    # ========================================================================

    @property
    def platform_name(self) -> str:
        """平台名称"""
        return "bilibili"

    @property
    def platform_display_name(self) -> str:
        """平台显示名称"""
        return "B站"
