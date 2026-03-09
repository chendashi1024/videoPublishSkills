"""
小红书发布器核心模块

包含所有发布相关的核心功能：
- 图文发布
- 视频发布
- 标题/正文填写
- 话题标签处理
- 发布按钮点击
"""

import json
import os
import re
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


class XiaohongshuPublisherCore(BasePublisher):
    """
    小红书发布器核心

    提供完整的发布功能：
    - 图文发布（多图）
    - 视频发布
    - 标题/正文填写
    - 话题标签自动识别和填写
    - 发布按钮点击
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9222,
        timing_jitter: float = 0.25,
        account_name: str | None = None,
    ):
        """
        初始化小红书发布器

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

        self.account_name = account_name or "default"

    # ========================================================================
    # 连接管理
    # ========================================================================

    def connect(self, reuse_existing_tab: bool = False):
        """
        连接到 Chrome

        Args:
            reuse_existing_tab: 是否优先复用已有标签页
        """
        self.cdp.connect(
            target_url_prefix=XHS_CREATOR_URL,
            reuse_existing_tab=reuse_existing_tab,
            default_url=XHS_CREATOR_URL,
        )

    def disconnect(self):
        """断开连接"""
        self.cdp.disconnect()

    # ========================================================================
    # 登录管理
    # ========================================================================

    def check_login(self) -> bool:
        """
        检查创作者中心登录状态

        Returns:
            True: 已登录
            False: 未登录
        """
        return self.login.check_login_by_url_redirect(
            check_url=XHS_CREATOR_LOGIN_CHECK_URL,
            login_keyword="login",
            scope="creator",
        )

    def check_home_login(self) -> bool:
        """
        检查主页登录状态

        Returns:
            True: 已登录
            False: 未登录
        """
        return self.login.check_login_by_modal(
            check_url=XHS_HOME_URL,
            modal_keyword=XHS_HOME_LOGIN_MODAL_KEYWORD,
            scope="home",
        )

    def clear_cookies(self):
        """清除小红书 Cookie"""
        self.login.clear_cookies(COOKIE_DOMAIN)

    def open_login_page(self):
        """打开登录页面"""
        self.login.open_login_page(XHS_CREATOR_LOGIN_CHECK_URL)

    # ========================================================================
    # 标签页切换
    # ========================================================================

    def _click_tab(self, tab_selector: str, tab_text: str):
        """
        点击标签页

        Args:
            tab_selector: 标签页选择器
            tab_text: 标签页文本
        """
        print(f"[XHS Publisher] 点击标签页: {tab_text}")
        self.ui.click_element_by_text(tab_selector, tab_text, wait_after=TAB_CLICK_WAIT)

    def _click_image_text_tab(self):
        """点击"上传图文"标签页"""
        self._click_tab(SELECTORS["image_text_tab"], SELECTORS["image_text_tab_text"])

    def _click_video_tab(self):
        """点击"上传视频"标签页"""
        self._click_tab(SELECTORS["video_tab"], SELECTORS["video_tab_text"])

    # ========================================================================
    # 文件上传
    # ========================================================================

    def _upload_images(self, image_paths: list[str]):
        """
        上传图片

        Args:
            image_paths: 图片路径列表（绝对路径）
        """
        if not image_paths:
            print("[XHS Publisher] 无图片需要上传")
            return

        # 规范化路径（CDP 需要正斜杠）
        normalized = [p.replace("\\", "/") for p in image_paths]
        print(f"[XHS Publisher] 上传 {len(image_paths)} 张图片...")

        # 查找文件输入框
        for selector in (SELECTORS["upload_input"], SELECTORS["upload_input_alt"]):
            try:
                self.ui.upload_files(selector, normalized, wait_after=UPLOAD_WAIT)
                print("[XHS Publisher] 图片上传完成，等待编辑器加载...")
                return
            except CDPError:
                continue

        raise CDPError(
            "未找到文件上传输入框\n"
            "页面结构可能已变更，请检查选择器配置"
        )

    def _upload_video(self, video_path: str):
        """
        上传视频

        Args:
            video_path: 视频路径（绝对路径）
        """
        normalized = video_path.replace("\\", "/")
        print(f"[XHS Publisher] 上传视频: {normalized}")

        # 查找文件输入框
        for selector in (SELECTORS["upload_input"], SELECTORS["upload_input_alt"]):
            try:
                self.ui.upload_files(selector, [normalized], wait_after=2.0)
                print("[XHS Publisher] 视频文件已提交，等待处理...")
                return
            except CDPError:
                continue

        raise CDPError(
            "未找到视频上传输入框\n"
            "页面结构可能已变更，请检查选择器配置"
        )

    def _wait_video_processing(self):
        """
        等待视频处理完成

        小红书上传视频后需要转码处理，等待标题输入框出现表示处理完成
        """
        print("[XHS Publisher] 等待视频处理完成...")
        deadline = time.time() + VIDEO_PROCESS_TIMEOUT
        last_pct = ""

        while time.time() < deadline:
            # 检查标题输入框是否出现（表示处理完成）
            for selector in (SELECTORS["title_input"], SELECTORS["title_input_alt"]):
                if self.ui.element_exists(selector):
                    print("[XHS Publisher] 视频处理完成，编辑器已就绪")
                    time.sleep(1)
                    return

            # 尝试读取处理进度
            pct = self.cdp.evaluate("""
                (() => {
                    const elements = document.querySelectorAll(
                        '[class*="progress"], [class*="percent"], [class*="upload"]'
                    );
                    for (const el of elements) {
                        const text = el.textContent.trim();
                        if (text && /\\d+%/.test(text)) {
                            return text;
                        }
                    }
                    return '';
                })()
            """) or ""

            if pct and pct != last_pct:
                print(f"[XHS Publisher] 视频处理进度: {pct}")
                last_pct = pct

            time.sleep(VIDEO_PROCESS_POLL)

        raise CDPError(
            f"视频处理超时（{VIDEO_PROCESS_TIMEOUT}秒）\n"
            "视频可能过大或处理速度较慢"
        )

    # ========================================================================
    # 内容填写
    # ========================================================================

    def _fill_title(self, title: str):
        """
        填写标题

        Args:
            title: 标题文本
        """
        print(f"[XHS Publisher] 填写标题: {title[:40]}...")
        self.cdp.sleep(ACTION_INTERVAL, minimum_seconds=0.25)

        for selector in (SELECTORS["title_input"], SELECTORS["title_input_alt"]):
            if self.ui.element_exists(selector):
                # 使用原生 setter 触发 React/Vue 事件
                escaped_title = json.dumps(title)
                self.cdp.evaluate(f"""
                    (() => {{
                        const el = document.querySelector({json.dumps(selector)});
                        const nativeSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        el.focus();
                        nativeSetter.call(el, {escaped_title});
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }})();
                """)
                print("[XHS Publisher] 标题填写完成")
                return

        raise CDPError("未找到标题输入框")

    def _fill_content(self, content: str):
        """
        填写正文内容

        Args:
            content: 正文文本（支持多行）
        """
        print(f"[XHS Publisher] 填写正文 ({len(content)} 字符)...")
        self.cdp.sleep(ACTION_INTERVAL, minimum_seconds=0.25)

        for selector in (SELECTORS["content_editor"], SELECTORS["content_editor_alt"]):
            if self.ui.element_exists(selector):
                # 将文本转换为 HTML 段落
                escaped = json.dumps(content)
                self.cdp.evaluate(f"""
                    (() => {{
                        const el = document.querySelector({json.dumps(selector)});
                        el.focus();
                        const text = {escaped};
                        const paragraphs = text.split('\\n').filter(p => p.trim());
                        const html = [];
                        for (let i = 0; i < paragraphs.length; i++) {{
                            html.push('<p>' + paragraphs[i] + '</p>');
                            if (i < paragraphs.length - 1) {{
                                html.push('<p><br></p>');
                            }}
                        }}
                        el.innerHTML = html.join('');
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }})();
                """)
                print("[XHS Publisher] 正文填写完成")
                return

        raise CDPError("未找到正文编辑器")

    # ========================================================================
    # 发布按钮
    # ========================================================================

    def _click_publish(self) -> str | None:
        """
        点击发布按钮

        Returns:
            发布成功后的笔记链接（如果能获取到）
        """
        print("[XHS Publisher] 点击发布按钮...")
        self.cdp.sleep(ACTION_INTERVAL, minimum_seconds=0.25)

        btn_text = SELECTORS["publish_button_text"]

        # 查找发布按钮并获取位置
        js_get_rect = f"""
            (() => {{
                // 策略 1: 通过按钮文本查找
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {{
                    if (btn.textContent.trim() === '{btn_text}') {{
                        const r = btn.getBoundingClientRect();
                        return {{ x: r.x, y: r.y, width: r.width, height: r.height }};
                    }}
                }}

                // 策略 2: 通过 span 文本查找父按钮
                const spans = document.querySelectorAll(
                    '.d-button-content .d-text, .d-button-content span'
                );
                for (const span of spans) {{
                    if (span.textContent.trim() === '{btn_text}') {{
                        const btn = span.closest(
                            'button, [role="button"], .d-button, [class*="btn"], [class*="button"]'
                        );
                        if (btn) {{
                            const r = btn.getBoundingClientRect();
                            return {{ x: r.x, y: r.y, width: r.width, height: r.height }};
                        }}
                    }}
                }}
                return null;
            }})();
        """

        self.ui.click_element_by_cdp("发布按钮", js_get_rect)
        print("[XHS Publisher] 发布按钮已点击")

        # 等待发布完成并尝试获取笔记链接
        self.cdp.sleep(5, minimum_seconds=2.0)
        note_link = self.cdp.evaluate("""
            (() => {
                // 尝试从成功消息中查找笔记链接
                const links = document.querySelectorAll('a[href*="xiaohongshu.com/explore"]');
                if (links.length > 0) {
                    return links[0].href;
                }
                // 尝试从页面中提取笔记 ID
                const noteId = document.body.textContent.match(/\\b[0-9a-fA-F]{24}\\b/);
                if (noteId) {
                    return 'https://www.xiaohongshu.com/explore/' + noteId[0];
                }
                return null;
            })();
        """)

        return note_link

    # ========================================================================
    # 主发布流程
    # ========================================================================

    def publish(
        self,
        title: str,
        content: str,
        image_paths: list[str] | None = None,
    ):
        """
        发布图文内容

        Args:
            title: 标题
            content: 正文
            image_paths: 图片路径列表

        Raises:
            CDPError: 未连接或发布失败
        """
        if not self.cdp.ws:
            raise CDPError("未连接，请先调用 connect()")

        if not image_paths:
            raise CDPError("小红书发布图文至少需要一张图片")

        # 1. 导航到发布页面
        self.cdp.navigate(XHS_CREATOR_URL)
        self.cdp.sleep(2, minimum_seconds=1.0)

        # 2. 点击"上传图文"标签页
        self._click_image_text_tab()

        # 3. 上传图片（编辑器会在上传后出现）
        self._upload_images(image_paths)

        # 4. 填写标题
        self._fill_title(title)

        # 5. 填写正文
        self._fill_content(content)

        print(
            "\n[XHS Publisher] 内容已填写完成\n"
            "  请在浏览器中检查后再发布\n"
        )

    def publish_video(
        self,
        title: str,
        content: str,
        video_path: str,
    ):
        """
        发布视频内容

        Args:
            title: 标题
            content: 正文
            video_path: 视频路径

        Raises:
            CDPError: 未连接或发布失败
        """
        if not self.cdp.ws:
            raise CDPError("未连接，请先调用 connect()")

        if not video_path:
            raise CDPError("小红书发布视频需要提供视频文件")

        # 1. 导航到发布页面
        self.cdp.navigate(XHS_CREATOR_URL)
        time.sleep(2)

        # 2. 点击"上传视频"标签页
        self._click_video_tab()

        # 3. 上传视频并等待处理
        self._upload_video(video_path)
        self._wait_video_processing()

        # 4. 填写标题
        self._fill_title(title)

        # 5. 填写正文
        self._fill_content(content)

        print(
            "\n[XHS Publisher] 视频内容已填写完成\n"
            "  请在浏览器中检查后再发布\n"
        )

    def click_publish_button(self) -> str | None:
        """
        点击发布按钮（独立方法，用于手动控制发布时机）

        Returns:
            发布成功后的笔记链接
        """
        return self._click_publish()

    # ========================================================================
    # 平台信息（覆盖基类属性）
    # ========================================================================

    @property
    def platform_name(self) -> str:
        """平台名称"""
        return "xiaohongshu"

    @property
    def platform_display_name(self) -> str:
        """平台显示名称"""
        return "小红书"
