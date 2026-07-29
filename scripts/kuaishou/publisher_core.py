"""
快手发布器核心模块

包含所有发布相关的核心功能：
- 视频发布
- 标题/描述填写
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


class KuaishouPublisherCore(BasePublisher):
    """
    快手发布器核心

    提供完整的发布功能：
    - 视频发布
    - 标题/描述填写
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
        初始化 快手发布器

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
            target_url_prefix=KUAISHOU_CREATOR_URL_PREFIX,
            reuse_existing_tab=reuse_existing_tab,
            default_url=KUAISHOU_CREATOR_URL,
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

        current_url = self.cdp.get_current_url()
        if not current_url.startswith(KUAISHOU_CREATOR_URL_PREFIX):
            self.cdp.navigate(KUAISHOU_CREATOR_URL)
            self.cdp.sleep(PAGE_LOAD_WAIT)

        current_url = self.cdp.get_current_url()
        print(f"[Kuaishou] 当前 URL: {current_url}")
        if "login" in current_url.lower() or "passport" in current_url.lower():
            print("[Kuaishou] 未登录：上传页跳转到登录页")
            return False

        page_state = self.cdp.evaluate("""
            (() => {
                const text = document.body ? document.body.innerText : '';
                return {
                    hasVideoUploadInput: !!document.querySelector(
                        'input[type="file"][accept*="video"]'
                    ),
                    hasEditorForm: !!document.querySelector(
                        '#work-description-edit, '
                        + 'div[contenteditable="true"][class*="description"], '
                        + 'textarea[placeholder*="作品描述"]'
                    ),
                    hasLoginCallToAction: text.includes('立即登录')
                        || text.includes('扫码登录')
                        || text.includes('验证码登录')
                        || text.includes('密码登录')
                };
            })()
        """) or {}

        logged_in = bool(
            not page_state.get("hasLoginCallToAction")
            and (
                page_state.get("hasVideoUploadInput")
                or page_state.get("hasEditorForm")
            )
        )
        print("[Kuaishou] 已登录" if logged_in else "[Kuaishou] 未登录")
        return logged_in

    def open_login_page(self):
        """打开登录页面"""
        if not self.cdp.ws:
            raise CDPError("未连接，请先调用 connect()")

        self.cdp.navigate(KUAISHOU_CREATOR_URL)
        self.cdp.sleep(PAGE_LOAD_WAIT)
        print("[Kuaishou] 请在浏览器中扫码登录")

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
        发布图文内容（快手主要是视频平台）

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
            "message": "快手主要支持视频发布，请使用 publish_video 方法",
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
            content: 描述（快手会忽略此参数，只使用标题）
            video_path: 视频文件路径
            cover_path: 封面图片路径（可选）
            auto_publish: 是否自动点击发布按钮

        Returns:
            dict: 发布结果
        """
        if not self.cdp.ws:
            raise CDPError("未连接，请先调用 connect()")

        if not video_path:
            raise CDPError("快手发布视频需要提供视频文件")

        try:
            # 1. 导航到发布页面；新建 tab 已经打开上传入口时不重复导航。
            current_url = self.cdp.get_current_url()
            if not current_url.startswith(KUAISHOU_CREATOR_URL_PREFIX):
                self.cdp.navigate(KUAISHOU_CREATOR_URL)
                self.cdp.sleep(PAGE_LOAD_WAIT)

            # 2. 上传视频
            self._upload_video(video_path)

            # 3. 填写作品描述（快手只有作品描述字段，合并标题、正文和话题）
            description_parts = [title.strip()]
            if content and content.strip() and content.strip() != title.strip():
                description_parts.append(content.strip())
            self._fill_content("\n\n".join(description_parts))

            # 4. 上传封面（如果提供）
            if cover_path:
                self._upload_cover(cover_path)

            # 5. 等待视频处理完成并发布（仅在需要发布时等待）
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

    def _click_rect_center(self, rect: dict[str, float]):
        """用 CDP 鼠标事件点击矩形中心。"""
        x = float(rect["x"]) + float(rect.get("w", rect.get("width", 0))) / 2
        y = float(rect["y"]) + float(rect.get("h", rect.get("height", 0))) / 2
        self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y,
        })
        time.sleep(0.08)
        for event_type in ("mousePressed", "mouseReleased"):
            self.cdp.send("Input.dispatchMouseEvent", {
                "type": event_type,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            })
            time.sleep(0.04)

    def _upload_video(self, video_path: str):
        """上传视频"""
        print(f"[Kuaishou] 上传视频: {video_path}")

        # 查找文件输入框
        file_input = self.ui.find_element(SELECTORS["video_upload_input"])
        if not file_input:
            # 尝试备用选择器
            fallback_selector = SELECTORS.get("video_upload_input_name")
            if fallback_selector:
                file_input = self.ui.find_element(fallback_selector)

        if not file_input:
            raise CDPError("未找到视频上传输入框")

        # 设置文件路径
        self.cdp.send("DOM.setFileInputFiles", {
            "files": [video_path],
            "nodeId": file_input["nodeId"],
        })
        self._dispatch_file_input_events(SELECTORS["video_upload_input"])

        self.cdp.sleep(UPLOAD_WAIT)
        print("[Kuaishou] 视频上传中...")

        form_ready = self.ui.wait_for_element(
            SELECTORS["content_input"],
            timeout=UPLOAD_FORM_TIMEOUT,
            poll_interval=2,
        )
        if not form_ready:
            raise CDPError("快手上传后未进入作品描述表单")

    def _wait_video_processing(self):
        """等待视频处理完成"""
        print("[Kuaishou] 等待视频处理...")

        start_time = time.time()
        while time.time() - start_time < VIDEO_PROCESS_TIMEOUT:
            # 检查是否还有处理指示器
            processing = self.ui.find_element(
                SELECTORS["video_processing_indicator"],
                timeout=2,
            )

            if not processing:
                print("[Kuaishou] 视频处理完成")
                return

            self.cdp.sleep(VIDEO_PROCESS_POLL)

        raise CDPError(f"视频处理超时（{VIDEO_PROCESS_TIMEOUT}秒）")

    def _fill_content(self, content: str):
        """填写作品描述"""
        print(f"[Kuaishou] 填写作品描述: {content[:50]}...")

        self.ui.fill_contenteditable(
            SELECTORS["content_input"],
            content,
            clear_first=True,
        )

        self.cdp.sleep(ACTION_INTERVAL)

    def _upload_cover(self, cover_path: str):
        """上传封面"""
        print(f"[Kuaishou] 上传封面: {cover_path}")

        entry_rect = self._wait_for_cover_editor_entry()

        upload_tab_rect = None
        for attempt in range(3):
            self._click_rect_center(entry_rect)
            deadline = time.time() + 6
            while time.time() < deadline:
                upload_tab_rect = self.cdp.evaluate(r"""
                    (() => {
                        const modal = document.querySelector('.ant-modal');
                        if (!modal) return null;
                        const target = Array.from(modal.querySelectorAll('div, span, button')).find((el) => {
                            const text = (el.innerText || el.textContent || '').trim();
                            const r = el.getBoundingClientRect();
                            return text === '上传封面' && r.width > 0 && r.height > 0;
                        });
                        if (!target) return null;
                        const r = target.getBoundingClientRect();
                        return { x: r.x, y: r.y, w: r.width, h: r.height };
                    })()
                """)
                if upload_tab_rect:
                    break
                self.cdp.sleep(0.5)
            if upload_tab_rect:
                break
            if attempt < 2:
                print("[Kuaishou] 封面编辑器未打开，重试点击封面设置")

        if not upload_tab_rect:
            raise CDPError("未找到快手封面编辑器的上传封面页签")

        self._click_rect_center(upload_tab_rect)
        self.cdp.sleep(0.8)

        upload_state = None
        deadline = time.time() + 6
        while time.time() < deadline:
            upload_state = self.cdp.evaluate(f"""
                (() => {{
                    const modal = document.querySelector('.ant-modal');
                    if (!modal) return {{ ok: false, reason: 'modal not found' }};
                    const input = modal.querySelector({json.dumps(SELECTORS["cover_modal_upload_input"])});
                    const text = String(modal.innerText || modal.textContent || '');
                    return {{
                        hasInput: !!input,
                        hasUploadedCover: text.includes('清空上传'),
                    }};
                }})()
            """) or {}
            if upload_state.get("hasInput") or upload_state.get("hasUploadedCover"):
                break
            self.cdp.sleep(0.5)

        if not upload_state or (
            not upload_state.get("hasInput") and not upload_state.get("hasUploadedCover")
        ):
            raise CDPError("快手封面编辑器上传区域未出现")

        if upload_state.get("hasInput"):
            document = self.cdp.send("DOM.getDocument", {
                "depth": -1,
                "pierce": True,
            })
            root_id = document.get("root", {}).get("nodeId")
            if not root_id:
                raise CDPError("未能读取快手封面编辑器 DOM")

            query = self.cdp.send("DOM.querySelector", {
                "nodeId": root_id,
                "selector": SELECTORS["cover_modal_upload_input"],
            })
            node_id = query.get("nodeId")
            if not node_id:
                raise CDPError("未找到快手封面编辑器图片上传输入框")

            self.cdp.send("DOM.setFileInputFiles", {
                "files": [cover_path],
                "nodeId": node_id,
            })
            self._dispatch_file_input_events(SELECTORS["cover_modal_upload_input"])

        has_upload_preview = False
        for _ in range(20):
            self.cdp.sleep(0.5)
            has_upload_preview = self.cdp.evaluate(r"""
                (() => {
                    const modal = document.querySelector('.ant-modal');
                    if (!modal) return false;
                    const canvases = Array.from(modal.querySelectorAll('canvas'));
                    return canvases.some((canvas) => canvas.width > 0 && canvas.height > 0);
                })()
            """)
            if has_upload_preview:
                break
        if not has_upload_preview:
            raise CDPError("快手封面上传后未检测到裁剪预览")

        ratio_rect = self.cdp.evaluate(r"""
            (() => {
                const modal = document.querySelector('.ant-modal');
                if (!modal) return null;
                const target = Array.from(modal.querySelectorAll('[class*="ratio-item"], div')).find((el) => {
                    const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
                    const r = el.getBoundingClientRect();
                    return text.startsWith('3:4') && r.width > 0 && r.height > 0;
                });
                if (!target) return null;
                const r = target.getBoundingClientRect();
                return { x: r.x, y: r.y, w: r.width, h: r.height };
            })()
        """)
        if ratio_rect:
            self._click_rect_center(ratio_rect)
        else:
            print("[Kuaishou] 未找到 3:4 裁剪比例，保留平台默认裁剪")

        self.cdp.sleep(0.8)

        confirm_rect = None
        deadline = time.time() + 8
        while time.time() < deadline:
            confirm_rect = self.cdp.evaluate(r"""
                (() => {
                    const modal = document.querySelector('.ant-modal');
                    if (!modal) return null;
                    const target = Array.from(modal.querySelectorAll('button, div, span')).find((el) => {
                        const text = (el.innerText || el.textContent || '').trim();
                        const r = el.getBoundingClientRect();
                        return text === '确认' && r.width > 0 && r.height > 0;
                    });
                    const button = target && target.closest('button') ? target.closest('button') : target;
                    if (!button) return null;
                    if (button.disabled || button.className.includes('disabled') || button.getAttribute('aria-disabled') === 'true') {
                        return null;
                    }
                    const r = button.getBoundingClientRect();
                    return { x: r.x, y: r.y, w: r.width, h: r.height };
                })()
            """)
            if confirm_rect:
                break
            self.cdp.sleep(0.5)

        if not confirm_rect:
            raise CDPError("未能点击快手封面编辑器确认按钮")

        self._click_rect_center(confirm_rect)

        applied = False
        for _ in range(12):
            self.cdp.sleep(0.6)
            applied = self.cdp.evaluate(r"""
                (() => {
                    if (document.querySelector('.ant-modal-wrap')) return false;
                    const root = document.querySelector('[class*="default-cover"]');
                    if (!root) return false;
                    const img = root.querySelector('img');
                    return !!img
                        && img.naturalWidth > 0
                        && img.naturalHeight > 0
                        && img.naturalHeight > img.naturalWidth;
                })()
            """)
            if applied:
                break

        if not applied:
            raise CDPError("快手封面上传后未确认应用为 3:4 竖版封面")

        print("[Kuaishou] 竖版封面已应用（3:4）")

    def _wait_for_cover_editor_entry(self) -> dict[str, Any]:
        """等待视频和推荐封面处理完成后出现真实封面编辑入口。"""
        deadline = time.time() + VIDEO_PROCESS_TIMEOUT
        last_reason = "cover-full-editor 尚未出现"

        while time.time() < deadline:
            state = self.cdp.evaluate(r"""
                (() => {
                    const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                    const visible = (el) => {
                        if (!el) return false;
                        const style = getComputedStyle(el);
                        const r = el.getBoundingClientRect();
                        return style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && r.width > 0
                            && r.height > 0;
                    };
                    const target = Array.from(document.querySelectorAll(
                        '[class*="cover-full-editor"]'
                    )).find(visible);
                    const defaultCover = Array.from(document.querySelectorAll(
                        '[class*="default-cover"]'
                    )).find(visible);
                    const pageBusy = Array.from(document.querySelectorAll(
                        '[class*="uploading"], [class*="processing"]'
                    )).some(visible);
                    const coverBusy = Array.from(document.querySelectorAll(
                        '[class*="cover"] [class*="loading"], [class*="loading"][class*="cover"]'
                    )).some(visible);

                    if (!target) {
                        return {
                            ready: false,
                            reason: pageBusy || coverBusy
                                ? '视频或推荐封面仍在上传/处理中'
                                : 'cover-full-editor 尚未出现',
                            hasDefaultCover: !!defaultCover,
                        };
                    }

                    const targetBusy = !!target.closest(
                        '[class*="loading"], [class*="uploading"], [class*="processing"]'
                    ) || !!target.querySelector(
                        '[class*="loading"], [class*="uploading"], [class*="processing"]'
                    );
                    if (pageBusy || coverBusy || targetBusy) {
                        return {
                            ready: false,
                            reason: '封面编辑入口仍在 loading',
                            hasDefaultCover: !!defaultCover,
                        };
                    }

                    target.scrollIntoView({ block: 'center' });
                    const r = target.getBoundingClientRect();
                    return {
                        ready: true,
                        kind: 'cover-full-editor',
                        x: r.x,
                        y: r.y,
                        w: r.width,
                        h: r.height,
                        text: clean(target.innerText || target.textContent),
                    };
                })()
            """) or {}
            if state.get("ready"):
                return state
            last_reason = state.get("reason") or last_reason
            self.cdp.sleep(VIDEO_PROCESS_POLL)

        raise CDPError(
            "等待快手视频上传/处理完成超时："
            f"{last_reason}；未出现可用 cover-full-editor"
        )

    def _dispatch_file_input_events(self, selector: str):
        """快手上传组件需要真实 input/change 事件才会进入前端上传流程。"""
        result = self.cdp.evaluate(f"""
            (() => {{
                const input = document.querySelector({json.dumps(selector)});
                if (!input) return {{ ok: false, reason: 'input not found' }};
                input.dispatchEvent(new Event('input', {{ bubbles: true, composed: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true, composed: true }}));
                return {{ ok: true }};
            }})()
        """) or {{}}
        if not result.get("ok"):
            print(f"[Kuaishou] Warning: 上传控件事件补发失败: {result.get('reason')}")

    def _upload_cover_direct_input(self, cover_path: str) -> bool:
        """兼容快手新版封面模块：无弹窗时直接使用页面图片 input。"""
        document = self.cdp.send("DOM.getDocument", {
            "depth": -1,
            "pierce": True,
        })
        root_id = document.get("root", {}).get("nodeId")
        if not root_id:
            return False

        query = self.cdp.send("DOM.querySelector", {
            "nodeId": root_id,
            "selector": SELECTORS["cover_upload_input"],
        })
        node_id = query.get("nodeId")
        if not node_id:
            return False

        self.cdp.send("DOM.setFileInputFiles", {
            "files": [cover_path],
            "nodeId": node_id,
        })
        self._dispatch_file_input_events(SELECTORS["cover_upload_input"])

        for _ in range(20):
            self.cdp.sleep(0.5)
            applied = self.cdp.evaluate(r"""
                (() => {
                    const visible = (el) => {
                        if (!el) return false;
                        const style = getComputedStyle(el);
                        const r = el.getBoundingClientRect();
                        return style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && r.width > 0
                            && r.height > 0;
                    };
                    const coverRoot = document.querySelector(
                        '[class*="default-cover"], [class*="cover-full-editor"], [class*="high-cover-editor"]'
                    );
                    const root = coverRoot || document.body;
                    const imgs = Array.from(root.querySelectorAll('img')).filter(visible);
                    return imgs.some((img) =>
                        img.naturalWidth > 0
                        && img.naturalHeight > 0
                        && img.naturalHeight >= img.naturalWidth
                    );
                })()
            """)
            if applied:
                return True

        return False

    def _click_publish(self):
        """点击发布按钮"""
        print("[Kuaishou] 点击发布按钮...")

        self.ui.click_element(SELECTORS["publish_button"])
        self.cdp.sleep(2)

        print("[Kuaishou] 发布完成")

    # ========================================================================
    # 平台信息
    # ========================================================================

    @property
    def platform_name(self) -> str:
        """平台名称"""
        return "kuaishou"

    @property
    def platform_display_name(self) -> str:
        """平台显示名称"""
        return "快手"
