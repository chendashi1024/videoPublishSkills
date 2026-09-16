"""执行真实页面 JS 的离线 CDP 适配，不启动浏览器。"""
import json
import subprocess
from pathlib import Path


class DomCDP:
    def __init__(self, html, setup=""):
        self.process = subprocess.Popen(
            ["node", str(Path(__file__).parent / "dom/harness.cjs")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        self.events = []
        self.request(op="init", html=html, setup=setup)

    def request(self, **data):
        self.process.stdin.write(json.dumps(data) + "\n")
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        if not response:
            raise RuntimeError("离线 DOM 进程退出；请先安装 tests/dom/package.json 中的依赖")
        value = json.loads(response)
        if "error" in value:
            raise RuntimeError(value["error"])
        return value.get("value")

    def evaluate(self, expression):
        return self.request(op="eval", expression=expression)

    def send(self, method, params=None):
        self.events.append((method, params or {}))
        return self.request(op="cdp", method=method, params=params or {})

    def sleep(self, *_args, **_kwargs):
        self.request(op="tick")

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        self.process.stdout.close()
