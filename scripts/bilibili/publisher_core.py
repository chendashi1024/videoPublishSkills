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

            # 5. 固定选择 B站创作声明，这是投稿页必填项。
            self._select_declaration(BILIBILI_DEFAULT_DECLARATION)

            # 6. 固定选择 OPC 默认 B站分区，避免平台按标签自动推荐到“人工智能”。
            self._select_category(BILIBILI_DEFAULT_CATEGORY)

            # 7. 上传封面（如果提供）
            if cover_path:
                self._upload_cover(cover_path)

            # 8. 等待视频处理完成并发布（仅在需要发布时等待）
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
    def _select_declaration(self, declaration: str):
        """选择 B站创作声明。"""
        print(f"[Bilibili] 选择创作声明: {declaration}")

        result = self.cdp.evaluate(f"""
            (() => {{
                const targetDeclaration = {json.dumps(declaration, ensure_ascii=False)};
                const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const clickLikeUser = (el) => {{
                    const rect = el.getBoundingClientRect();
                    const options = {{
                        bubbles: true,
                        cancelable: true,
                        clientX: rect.x + rect.width / 2,
                        clientY: rect.y + rect.height / 2,
                        view: window,
                    }};
                    for (const type of ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {{
                        el.dispatchEvent(new MouseEvent(type, options));
                    }}
                }};
                const readSelected = () => clean(
                    document.querySelector('.creation-statement-container input')?.value || ''
                );
                const readSelectedOption = () => clean(
                    Array.from(document.querySelectorAll('.creation-statement-container .bcc-option.selected'))
                        .map((el) => el.innerText || el.textContent)
                        .find(Boolean) || ''
                );

                const current = readSelected() || readSelectedOption();
                if (current === targetDeclaration) {{
                    return {{ ok: true, selected: current, changed: false }};
                }}

                const field = document.querySelector(
                    '.creation-statement-container .bcc-select-input-wrap, '
                    + '.creation-statement-container input, '
                    + '.creation-statement-container .bcc-select'
                );
                if (!field) {{
                    return {{ ok: false, reason: 'declaration selector not found' }};
                }}
                field.scrollIntoView({{ block: 'center', inline: 'nearest' }});
                clickLikeUser(field);

                const item = Array.from(document.querySelectorAll('.creation-statement-container .bcc-option'))
                    .find((el) => clean(el.innerText || el.textContent) === targetDeclaration);
                if (!item) {{
                    return {{
                        ok: false,
                        reason: 'declaration item not found',
                        available: Array.from(document.querySelectorAll('.creation-statement-container .bcc-option'))
                            .map((el) => clean(el.innerText || el.textContent))
                            .filter(Boolean),
                    }};
                }}

                clickLikeUser(item);
                item.click();
                const span = item.querySelector('span');
                if (span) {{
                    clickLikeUser(span);
                    span.click();
                }}

                const input = document.querySelector('.creation-statement-container input');
                if (input) {{
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}

                const selected = readSelected() || readSelectedOption();
                return {{
                    ok: selected === targetDeclaration,
                    selected,
                    changed: true,
                }};
            }})()
        """) or {{}}

        if not result.get("ok"):
            raise CDPError(f"未能选择 B站创作声明 {declaration}: {result}")

        print(f"[Bilibili] 创作声明已设置为: {result.get('selected') or declaration}")
        self.cdp.sleep(ACTION_INTERVAL)

    def _select_category(self, category: str):
        """选择 B站分区。"""
        print(f"[Bilibili] 选择分区: {category}")

        result = self.cdp.evaluate(f"""
            (async () => {{
                const targetCategory = {json.dumps(category, ensure_ascii=False)};
                const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {{
                    if (!el) return false;
                    const style = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || '1') !== 0
                        && rect.width > 0
                        && rect.height > 0;
                }};
                const clickLikeUser = (el) => {{
                    const rect = el.getBoundingClientRect();
                    const options = {{
                        bubbles: true,
                        cancelable: true,
                        clientX: rect.x + rect.width / 2,
                        clientY: rect.y + rect.height / 2,
                        view: window,
                    }};
                    for (const type of ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {{
                        el.dispatchEvent(new MouseEvent(type, options));
                    }}
                }};
                const current = document.querySelector(
                    '.video-human-type .select-controller, .video-human-type .selector-container'
                );
                if (!current) {{
                    return {{ ok: false, reason: 'category selector not found' }};
                }}
                if (clean(current.innerText || current.textContent) === targetCategory) {{
                    return {{ ok: true, selected: targetCategory, changed: false }};
                }}

                current.scrollIntoView({{ block: 'center', inline: 'nearest' }});
                clickLikeUser(current);

                let list = null;
                for (let attempt = 0; attempt < 12; attempt += 1) {{
                    await new Promise((resolve) => setTimeout(resolve, 250));
                    list = Array.from(document.querySelectorAll('.drop-list-v2-container.human-type-list'))
                        .find(visible);
                    if (list) break;
                }}
                if (!list) {{
                    return {{ ok: false, reason: 'category dropdown not opened' }};
                }}

                const item = Array.from(list.querySelectorAll('.drop-list-v2-item'))
                    .find((el) => clean(el.innerText || el.textContent) === targetCategory);
                if (!item) {{
                    return {{
                        ok: false,
                        reason: 'category item not found',
                        available: clean(list.innerText || list.textContent),
                    }};
                }}
                item.scrollIntoView({{ block: 'center', inline: 'nearest' }});
                clickLikeUser(item);

                await new Promise((resolve) => setTimeout(resolve, 500));
                const selected = clean(
                    document.querySelector('.video-human-type .select-controller')?.innerText
                    || document.querySelector('.video-human-type .selector-container')?.innerText
                    || ''
                );
                return {{
                    ok: selected === targetCategory,
                    selected,
                    changed: true,
                }};
            }})()
        """) or {{}}

        if not result.get("ok"):
            raise CDPError(f"未能选择 B站分区 {category}: {result}")

        print(f"[Bilibili] 分区已设置为: {result.get('selected') or category}")
        self.cdp.sleep(ACTION_INTERVAL)


    def _upload_cover(self, cover_path: str):
        """上传封面"""
        print(f"[Bilibili] 上传封面: {cover_path}")

        opened = self.cdp.evaluate(r"""
            (() => {
                const candidates = Array.from(document.querySelectorAll(
                    'span.edit-text, .cover-img span, .cover-main span, .cover-item span'
                ));
                const target = candidates.find((el) =>
                    (el.textContent || '').trim().includes('封面设置')
                );
                if (!target) return false;
                target.scrollIntoView({ block: 'center' });
                const r = target.getBoundingClientRect();
                const options = {
                    bubbles: true,
                    cancelable: true,
                    clientX: r.x + r.width / 2,
                    clientY: r.y + r.height / 2,
                    view: window,
                };
                for (const type of ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                    target.dispatchEvent(new MouseEvent(type, options));
                }
                return true;
            })()
        """)

        if not opened:
            print("[Bilibili] 未找到封面设置入口，跳过")
            return

        self.cdp.sleep(1.2)

        document = self.cdp.send("DOM.getDocument", {
            "depth": -1,
            "pierce": True,
        })
        root_id = document.get("root", {}).get("nodeId")
        if not root_id:
            print("[Bilibili] 未能读取封面编辑器 DOM，跳过")
            return

        query = self.cdp.send("DOM.querySelector", {
            "nodeId": root_id,
            "selector": '.cover-editor input[type="file"][accept*="image"]',
        })
        node_id = query.get("nodeId")
        if not node_id:
            print("[Bilibili] 未找到封面编辑器图片上传输入框，跳过")
            return

        self.cdp.send("DOM.setFileInputFiles", {
            "files": [cover_path],
            "nodeId": node_id,
        })

        self.cdp.sleep(2.5)

        has_preview = self.cdp.evaluate(r"""
            (() => Array.from(document.querySelectorAll('.cover-editor img')).some((img) =>
                img.src.startsWith('blob:') && img.naturalWidth > 0 && img.naturalHeight > 0
            ))()
        """)
        if not has_preview:
            print("[Bilibili] 封面上传后未检测到预览图，请发布前人工检查")

        completed = self.cdp.evaluate(r"""
            (() => {
                const candidates = Array.from(document.querySelectorAll(
                    '.cover-editor .submit, .cover-editor button, .cover-editor div'
                ));
                const target = candidates.find((el) => {
                    const text = (el.innerText || el.textContent || '').trim();
                    const r = el.getBoundingClientRect();
                    return text === '完成' && r.width > 0 && r.height > 0;
                });
                if (!target) return false;
                const r = target.getBoundingClientRect();
                const options = {
                    bubbles: true,
                    cancelable: true,
                    clientX: r.x + r.width / 2,
                    clientY: r.y + r.height / 2,
                    view: window,
                };
                for (const type of ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                    target.dispatchEvent(new MouseEvent(type, options));
                }
                return true;
            })()
        """)
        if not completed:
            print("[Bilibili] 未找到封面编辑器完成按钮，请发布前人工确认")
            return

        self.cdp.sleep(2)
        print("[Bilibili] 封面上传完成")

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
