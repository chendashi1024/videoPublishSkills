"""发布专用 Edge 身份与 CDP 就绪检查；失败时禁止连接其它浏览器。"""
import os
import subprocess
from urllib.parse import urlparse

import psutil
import requests


class PublishBrowserError(RuntimeError):
    """发布浏览器不符合固定身份。"""


def _fail(reason):
    raise PublishBrowserError(f"PUBLISH_BROWSER_MISMATCH：{reason}；禁止切换日常浏览器或自动关闭占用者。")


def validate_publish_browser(host="127.0.0.1", port=9222):
    """核验监听进程、精确启动参数及真实 CDP 接口，不读取账号数据。"""
    from chrome_launcher import EDGE_PROFILE_DIR, EDGE_USER_DATA_DIR_ENV
    if host != "127.0.0.1" or port != 9222:
        _fail("发布必须使用 127.0.0.1:9222")
    override = os.environ.get(EDGE_USER_DATA_DIR_ENV)
    if override and os.path.realpath(override) != os.path.realpath(EDGE_PROFILE_DIR):
        _fail("不允许覆盖发布专用 Profile")
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-t", "-iTCP:9222", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        pids = set(result.stdout.split())
        if result.returncode != 0 or len(pids) != 1:
            _fail("无法唯一识别 9222 监听进程")
        process = psutil.Process(int(next(iter(pids))))
        args = process.cmdline()
        if os.path.basename(process.exe()).lower() not in {"microsoft edge", "msedge.exe", "microsoft-edge", "microsoft-edge-stable"}:
            _fail("监听者不是 Microsoft Edge")
        if "--remote-debugging-port=9222" not in args:
            _fail("监听者未以发布调试端口启动")
        profiles = [arg.split("=", 1)[1] for arg in args if arg.startswith("--user-data-dir=")]
        if len(profiles) != 1 or os.path.realpath(profiles[0]) != os.path.realpath(EDGE_PROFILE_DIR):
            _fail("监听者未使用发布专用 Profile")
        session = requests.Session()
        session.trust_env = False
        with session:
            version = session.get("http://127.0.0.1:9222/json/version", timeout=5)
            version.raise_for_status()
            browser_ws = urlparse(version.json().get("webSocketDebuggerUrl", ""))
            if browser_ws.scheme != "ws" or browser_ws.hostname not in {"127.0.0.1", "localhost"} or browser_ws.port != 9222 or not browser_ws.path.startswith("/devtools/browser/"):
                _fail("CDP browser WebSocket 无效")
            targets = session.get("http://127.0.0.1:9222/json", timeout=5)
            targets.raise_for_status()
            if not isinstance(targets.json(), list):
                _fail("CDP 页面列表无效")
        return {"status": "PUBLISH_BROWSER_VERIFIED", "pid": process.pid, "port": 9222}
    except PublishBrowserError:
        raise
    except Exception as error:
        _fail(f"专用 Edge 或 CDP 未就绪（{type(error).__name__}）")


def guard_cdp_endpoint(host, port, account=None):
    """9222 保留给发布；edge 账号不能通过改端口绕过校验。"""
    if port == 9222 or account == "edge":
        return validate_publish_browser(host, port)
