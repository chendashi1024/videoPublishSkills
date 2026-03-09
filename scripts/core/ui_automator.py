"""
UI 自动化器：跨平台复用的 UI 交互基础操作

85% 可复用到所有平台（小红书/抖音/B站/快手）
"""

import json
from typing import Any

from .cdp_client import CDPClient, CDPError


class UIAutomator:
    """
    UI 自动化基础操作

    提供跨平台复用的 UI 交互能力：
    - 元素点击
    - 文本输入
    - 文件上传
    - 鼠标操作
    - 元素查找
    """

    def __init__(self, cdp: CDPClient):
        """
        初始化 UI 自动化器

        Args:
            cdp: CDP 客户端实例
        """
        self.cdp = cdp

    def click_element_by_text(
        self,
        selector: str,
        text: str,
        wait_after: float = 1.0,
    ):
        """
        点击包含指定文本的元素

        Args:
            selector: CSS 选择器
            text: 元素文本内容
            wait_after: 点击后等待秒数
        """
        print(f"[UIAutomator] 点击元素: {selector} (文本='{text}')")

        # 查找并点击元素
        clicked = self.cdp.evaluate(f"""
            (() => {{
                const elements = document.querySelectorAll({json.dumps(selector)});
                for (const el of elements) {{
                    if (el.textContent.includes({json.dumps(text)})) {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }})()
        """)

        if not clicked:
            raise CDPError(f"未找到元素: {selector} (文本='{text}')")

        self.cdp.sleep(wait_after, minimum_seconds=0.5)

    def click_element(self, selector: str, wait_after: float = 1.0):
        """
        点击元素

        Args:
            selector: CSS 选择器
            wait_after: 点击后等待秒数
        """
        print(f"[UIAutomator] 点击元素: {selector}")

        clicked = self.cdp.evaluate(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return false;
                el.click();
                return true;
            }})()
        """)

        if not clicked:
            raise CDPError(f"未找到元素: {selector}")

        self.cdp.sleep(wait_after, minimum_seconds=0.5)

    def fill_input(
        self,
        selector: str,
        value: str,
        clear_first: bool = True,
        wait_after: float = 0.5,
    ):
        """
        填写输入框

        Args:
            selector: CSS 选择器
            value: 输入值
            clear_first: 是否先清空
            wait_after: 填写后等待秒数
        """
        print(f"[UIAutomator] 填写输入框: {selector}")

        filled = self.cdp.evaluate(f"""
            (() => {{
                const input = document.querySelector({json.dumps(selector)});
                if (!input) return false;

                // 使用原生 setter 以支持 React/Vue 等框架
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype,
                    'value'
                ).set;

                if ({json.dumps(clear_first)}) {{
                    nativeInputValueSetter.call(input, '');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}

                nativeInputValueSetter.call(input, {json.dumps(value)});
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }})()
        """)

        if not filled:
            raise CDPError(f"未找到输���框: {selector}")

        self.cdp.sleep(wait_after)

    def fill_contenteditable(
        self,
        selector: str,
        value: str,
        clear_first: bool = True,
        wait_after: float = 0.5,
    ):
        """
        填写 contenteditable 元素（富文本编辑器）

        Args:
            selector: CSS 选择器
            value: 输入值
            clear_first: 是否先清空
            wait_after: 填写后等待秒数
        """
        print(f"[UIAutomator] 填写富文本编辑器: {selector}")

        filled = self.cdp.evaluate(f"""
            (() => {{
                const editor = document.querySelector({json.dumps(selector)});
                if (!editor) return false;

                // 聚焦编辑器
                editor.focus();

                // 选中所有内容
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(editor);
                selection.removeAllRanges();
                selection.addRange(range);

                // 使用 insertText 命令插入内容（会自动替换选中内容）
                document.execCommand('insertText', false, {json.dumps(value)});

                return true;
            }})()
        """)

        if not filled:
            raise CDPError(f"未找到富文本编辑器: {selector}")

        self.cdp.sleep(wait_after)

    def upload_files(
        self,
        selector: str,
        file_paths: list[str],
        wait_after: float = 3.0,
    ):
        """
        上传文件

        Args:
            selector: 文件输入框选择器
            file_paths: 文件路径列表（绝对路径）
            wait_after: 上传后等待秒数
        """
        print(f"[UIAutomator] 上传文件: {len(file_paths)} 个")

        # 获取文件输入框的节点 ID
        result = self.cdp.send("DOM.getDocument")
        root_node_id = result["root"]["nodeId"]

        # 查找文件输入框
        result = self.cdp.send("DOM.querySelector", {
            "nodeId": root_node_id,
            "selector": selector,
        })
        node_id = result.get("nodeId")

        if not node_id:
            raise CDPError(f"未找到文件输入框: {selector}")

        # 设置文件
        self.cdp.send("DOM.setFileInputFiles", {
            "files": file_paths,
            "nodeId": node_id,
        })

        self.cdp.sleep(wait_after, minimum_seconds=1.0)

    def wait_for_element(
        self,
        selector: str,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        等待元素出现

        Args:
            selector: CSS 选择器
            timeout: 超时秒数
            poll_interval: 轮询间隔秒数

        Returns:
            True: 元素已出现
            False: 超时
        """
        print(f"[UIAutomator] 等待元素: {selector}")

        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            exists = self.cdp.evaluate(f"""
                (() => {{
                    const el = document.querySelector({json.dumps(selector)});
                    return el !== null;
                }})()
            """)

            if exists:
                print(f"[UIAutomator] 元素已出现: {selector}")
                return True

            time.sleep(poll_interval)

        print(f"[UIAutomator] 等待元素超时: {selector}")
        return False

    def element_exists(self, selector: str) -> bool:
        """
        检查元素是否存在

        Args:
            selector: CSS 选择器

        Returns:
            True: 元素存在
            False: 元素不存在
        """
        exists = self.cdp.evaluate(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                return el !== null;
            }})()
        """)
        return bool(exists)

    def get_element_text(self, selector: str) -> str | None:
        """
        获取元素文本内容

        Args:
            selector: CSS 选择器

        Returns:
            元素文本内容，不存在返回 None
        """
        text = self.cdp.evaluate(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? el.textContent.trim() : null;
            }})()
        """)
        return text

    def move_mouse(self, x: float, y: float):
        """
        移动鼠标

        Args:
            x: X 坐标
            y: Y 坐标
        """
        self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y,
        })

    def click_mouse(self, x: float, y: float):
        """
        点击鼠标

        Args:
            x: X 坐标
            y: Y 坐标
        """
        self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })

    def click_element_by_cdp(self, description: str, js_get_rect: str):
        """
        通过 CDP 鼠标事件点击元素（用于复杂场景）

        Args:
            description: 元素描述（用于日志）
            js_get_rect: 获取元素位置的 JS 代码（返回 {x, y, width, height}）
        """
        print(f"[UIAutomator] CDP 点击: {description}")

        rect = self.cdp.evaluate(js_get_rect)
        if not rect or not isinstance(rect, dict):
            raise CDPError(f"无法获取元素位置: {description}")

        x = rect.get("x", 0) + rect.get("width", 0) / 2
        y = rect.get("y", 0) + rect.get("height", 0) / 2

        self.move_mouse(x, y)
        self.cdp.sleep(0.2)
        self.click_mouse(x, y)
        self.cdp.sleep(0.5)

    def scroll_to_element(self, selector: str):
        """
        滚动到元素位置

        Args:
            selector: CSS 选择器
        """
        print(f"[UIAutomator] 滚动到元素: {selector}")

        scrolled = self.cdp.evaluate(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return false;
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                return true;
            }})()
        """)

        if not scrolled:
            raise CDPError(f"未找到元素: {selector}")

        self.cdp.sleep(1.0)

    def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        """
        获取元素属性

        Args:
            selector: CSS 选择器
            attribute: 属性名

        Returns:
            属性值，不存在返回 None
        """
        value = self.cdp.evaluate(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? el.getAttribute({json.dumps(attribute)}) : null;
            }})()
        """)
        return value

    def find_element(self, selector: str, timeout: float = 0) -> dict | None:
        """
        查找元素并返回节点信息

        Args:
            selector: CSS 选择器
            timeout: 超时秒数（0 表示不等待）

        Returns:
            包含 nodeId 的字典，未找到返回 None
        """
        if timeout > 0:
            if not self.wait_for_element(selector, timeout=timeout):
                return None

        try:
            result = self.cdp.send("DOM.getDocument")
            root_node_id = result["root"]["nodeId"]

            result = self.cdp.send("DOM.querySelector", {
                "nodeId": root_node_id,
                "selector": selector,
            })
            node_id = result.get("nodeId")

            if node_id and node_id != 0:
                return {"nodeId": node_id}
            return None
        except Exception:
            return None
