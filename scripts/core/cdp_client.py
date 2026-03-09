"""
CDP 客户端：跨平台复用的 Chrome DevTools Protocol 底层通信

100% 可复用到所有平台（小红书/抖音/B站/快手）
"""

import json
import random
import time
from typing import Any

import requests
import websockets.sync.client as ws_client


class CDPError(Exception):
    """CDP 通信错误"""


class CDPClient:
    """
    Chrome DevTools Protocol 客户端

    提供底层 CDP 通信能力：
    - WebSocket 连接管理
    - CDP 命令发送
    - JavaScript 执行
    - 页面导航
    - 标签页管理
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9222,
        timing_jitter: float = 0.25,
    ):
        """
        初始化 CDP 客户端

        Args:
            host: CDP 服务地址
            port: CDP 服务端口
            timing_jitter: 时间抖动比例（0-0.7），用于模拟人类操作
        """
        self.host = host
        self.port = port
        self.ws = None
        self._msg_id = 0
        self.timing_jitter = max(0.0, min(0.7, timing_jitter))

    def is_local_host(self) -> bool:
        """判断是否为本地主机"""
        return self.host.strip().lower() in {"127.0.0.1", "localhost", "::1"}

    def sleep(self, base_seconds: float, minimum_seconds: float = 0.05):
        """
        带抖动的延迟（模拟人类操作）

        Args:
            base_seconds: 基础延迟秒数
            minimum_seconds: 最小延迟秒数
        """
        if self.timing_jitter <= 0:
            time.sleep(base_seconds)
            return

        delta = base_seconds * self.timing_jitter
        low = max(minimum_seconds, base_seconds - delta)
        high = max(low, base_seconds + delta)
        time.sleep(random.uniform(low, high))

    def get_targets(self) -> list[dict]:
        """
        获取浏览器标签页列表

        Returns:
            标签页信息列表

        Raises:
            CDPError: 连接失败
        """
        url = f"http://{self.host}:{self.port}/json"
        for attempt in range(2):
            try:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt == 0:
                    if self.is_local_host():
                        print(f"[CDPClient] CDP 连接失败 ({e})，尝试重启 Chrome...")
                        from chrome_launcher import ensure_chrome
                        ensure_chrome(port=self.port)
                    else:
                        print(f"[CDPClient] CDP 连接失败 ({e})，重试远程端点 {self.host}:{self.port}...")
                    self.sleep(2, minimum_seconds=1.0)
                else:
                    raise CDPError(f"无法连接到 Chrome {self.host}:{self.port}: {e}")

    def find_or_create_tab(
        self,
        target_url_prefix: str = "",
        reuse_existing_tab: bool = False,
        default_url: str = "about:blank",
    ) -> str:
        """
        查找或创建标签页

        Args:
            target_url_prefix: 目标 URL 前缀（用于查找已有标签页）
            reuse_existing_tab: 是否优先复用已有标签页
            default_url: 创建新标签页时的默认 URL

        Returns:
            WebSocket 调试 URL

        Raises:
            CDPError: 无可用标签页
        """
        targets = self.get_targets()
        pages = [
            t for t in targets
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl")
        ]

        # 优先查找匹配 URL 的标签页
        if target_url_prefix:
            for t in pages:
                if t.get("url", "").startswith(target_url_prefix):
                    print(f"[CDPClient] 复用已有标签页: {t.get('url')}")
                    return t["webSocketDebuggerUrl"]

        # 复用第一个标签页（减少窗口切换）
        if reuse_existing_tab and pages:
            url = pages[0].get("url", "")
            print(f"[CDPClient] 复用已有标签页: {url}")
            return pages[0]["webSocketDebuggerUrl"]

        # 创建新标签页
        resp = requests.put(
            f"http://{self.host}:{self.port}/json/new?{default_url}",
            timeout=5,
        )
        if resp.ok:
            ws_url = resp.json().get("webSocketDebuggerUrl", "")
            if ws_url:
                print(f"[CDPClient] 创建新标签页: {default_url}")
                return ws_url

        # 兜底：使用第一个可用标签页
        if pages:
            print(f"[CDPClient] 使用第一个可用标签页")
            return pages[0]["webSocketDebuggerUrl"]

        raise CDPError("无可用浏览器标签页")

    def connect(
        self,
        target_url_prefix: str = "",
        reuse_existing_tab: bool = False,
        default_url: str = "about:blank",
    ):
        """
        连接到 Chrome 标签页

        Args:
            target_url_prefix: 目标 URL 前缀
            reuse_existing_tab: 是否优先复用已有标签页
            default_url: 创建新标签页时的默认 URL
        """
        ws_url = self.find_or_create_tab(
            target_url_prefix=target_url_prefix,
            reuse_existing_tab=reuse_existing_tab,
            default_url=default_url,
        )

        print(f"[CDPClient] 连接到 {ws_url}")
        self.ws = ws_client.connect(ws_url)
        print("[CDPClient] 已连接到 Chrome 标签页")

    def disconnect(self):
        """关闭 WebSocket 连接"""
        if self.ws:
            self.ws.close()
            self.ws = None
            print("[CDPClient] 已断开连接")

    def send(self, method: str, params: dict | None = None) -> dict:
        """
        发送 CDP 命令

        Args:
            method: CDP 方法名（如 "Page.navigate"）
            params: 方法参数

        Returns:
            CDP 响应结果

        Raises:
            CDPError: 未连接或命令执行失败
        """
        if not self.ws:
            raise CDPError("未连接，请先调用 connect()")

        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params

        self.ws.send(json.dumps(msg))

        # 等待匹配的响应
        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._msg_id:
                if "error" in data:
                    raise CDPError(f"CDP 错误: {data['error']}")
                return data.get("result", {})
            # 跳过事件消息

    def evaluate(self, expression: str) -> Any:
        """
        在页面中执行 JavaScript

        Args:
            expression: JavaScript 表达式

        Returns:
            执行结果值

        Raises:
            CDPError: 执行失败
        """
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        remote_obj = result.get("result", {})
        if remote_obj.get("subtype") == "error":
            raise CDPError(f"JS 错误: {remote_obj.get('description', remote_obj)}")
        return remote_obj.get("value")

    def navigate(self, url: str, wait_seconds: float = 3.0):
        """
        导航到指定 URL

        Args:
            url: 目标 URL
            wait_seconds: 等待页面加载的秒数
        """
        print(f"[CDPClient] 导航到 {url}")
        self.send("Page.enable")
        self.send("Page.navigate", {"url": url})
        self.sleep(wait_seconds, minimum_seconds=1.0)

    def get_current_url(self) -> str:
        """获取当前页面 URL"""
        return self.evaluate("window.location.href")

    def reload(self, wait_seconds: float = 3.0):
        """刷新当前页面"""
        print("[CDPClient] 刷新页面")
        self.send("Page.reload")
        self.sleep(wait_seconds, minimum_seconds=1.0)

    def set_file_input(self, selector: str, file_paths: list[str]):
        """
        设置文件输入框的文件（用于上传）

        Args:
            selector: 文件输入框选择器
            file_paths: 文件路径列表（绝对路径）
        """
        # 获取文件输入框的 DOM 节点 ID
        node_id = self.evaluate(f"""
            (() => {{
                const input = document.querySelector({json.dumps(selector)});
                if (!input) return null;
                return input;
            }})()
        """)

        if not node_id:
            raise CDPError(f"未找到文件输入框: {selector}")

        # 使用 CDP 设置文件
        self.send("DOM.setFileInputFiles", {
            "files": file_paths,
            "nodeId": node_id,
        })
