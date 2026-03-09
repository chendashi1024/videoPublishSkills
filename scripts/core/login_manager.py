"""
登录管理器：跨平台复用的登录状态管理和缓存

90% 可复用到所有平台（小红书/抖音/B站/快手）
各平台只需实现自己的登录检测逻辑
"""

import json
import os
import time
from typing import Any

from .cdp_client import CDPClient, CDPError


# 默认登录缓存配置
DEFAULT_LOGIN_CACHE_TTL_HOURS = 12
LOGIN_CACHE_FILE = "tmp/login_status_cache.json"


class LoginManager:
    """
    登录状态管理器

    功能：
    - 登录状态检测（需子类实现具体平台逻辑）
    - 登录状态缓存（12小时 TTL）
    - Cookie 管理
    - 登录页面打开
    """

    def __init__(
        self,
        cdp: CDPClient,
        account_name: str = "default",
        cache_ttl_hours: float = DEFAULT_LOGIN_CACHE_TTL_HOURS,
        cache_file: str = LOGIN_CACHE_FILE,
    ):
        """
        初始化登录管理器

        Args:
            cdp: CDP 客户端实例
            account_name: 账号名称（用于缓存隔离）
            cache_ttl_hours: 缓存有效期（小时）
            cache_file: 缓存文件路径
        """
        self.cdp = cdp
        self.account_name = (account_name or "default").strip() or "default"
        self.cache_ttl_hours = cache_ttl_hours
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.cache_file = cache_file

    def _cache_key(self, scope: str) -> str:
        """
        构建缓存键

        Args:
            scope: 登录范围（如 "creator", "home"）

        Returns:
            唯一缓存键
        """
        return f"{self.cdp.host}:{self.cdp.port}:{self.account_name}:{scope}"

    def _load_cache(self) -> dict[str, Any]:
        """加载登录缓存"""
        if not os.path.exists(self.cache_file):
            return {"entries": {}}

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return {"entries": {}}

        if not isinstance(payload, dict):
            return {"entries": {}}
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            payload["entries"] = {}
        return payload

    def _save_cache(self, payload: dict[str, Any]):
        """保存登录缓存"""
        parent = os.path.dirname(self.cache_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_cached_status(self, scope: str) -> bool | None:
        """
        获取缓存的登录状态

        Args:
            scope: 登录范围

        Returns:
            True: 已登录（缓存有效）
            None: 缓存不存在或已过期
        """
        if self.cache_ttl_seconds <= 0:
            return None

        payload = self._load_cache()
        entries = payload.get("entries", {})
        entry = entries.get(self._cache_key(scope))
        if not isinstance(entry, dict):
            return None

        checked_at = entry.get("checked_at")
        logged_in = entry.get("logged_in")
        if not isinstance(checked_at, (int, float)) or not isinstance(logged_in, bool):
            return None

        age_seconds = time.time() - float(checked_at)
        if age_seconds < 0 or age_seconds > self.cache_ttl_seconds:
            return None

        # 只缓存"已登录"状态
        if not logged_in:
            return None

        age_minutes = int(age_seconds // 60)
        print(
            f"[LoginManager] 使用缓存的登录状态 "
            f"({scope}, 缓存时长={age_minutes}分钟, TTL={self.cache_ttl_hours:g}小时)"
        )
        return logged_in

    def set_cache(self, scope: str, logged_in: bool):
        """
        设置登录状态缓存

        Args:
            scope: 登录范围
            logged_in: 是否已登录
        """
        if not logged_in:
            self.clear_cache(scope=scope)
            return

        payload = self._load_cache()
        entries = payload.setdefault("entries", {})
        entries[self._cache_key(scope)] = {
            "logged_in": True,
            "checked_at": int(time.time()),
        }
        self._save_cache(payload)
        print(f"[LoginManager] 已缓存登录状态 ({scope})")

    def clear_cache(self, scope: str | None = None):
        """
        清除登录缓存

        Args:
            scope: 登录范围（None 表示清除当前账号的所有缓存）
        """
        payload = self._load_cache()
        entries = payload.get("entries", {})
        if not isinstance(entries, dict) or not entries:
            return

        if scope is None:
            # 清除当前账号的所有缓存
            prefix = f"{self.cdp.host}:{self.cdp.port}:{self.account_name}:"
            keys_to_remove = [k for k in entries if k.startswith(prefix)]
            for k in keys_to_remove:
                del entries[k]
            if keys_to_remove:
                print(f"[LoginManager] 已清除 {len(keys_to_remove)} 个登录缓存")
        else:
            # 清除指定范围的缓存
            key = self._cache_key(scope)
            if key in entries:
                del entries[key]
                print(f"[LoginManager] 已清除登录缓存 ({scope})")

        self._save_cache(payload)

    def clear_cookies(self, domain: str):
        """
        清除指定域名的 Cookie

        Args:
            domain: 域名（如 ".xiaohongshu.com"）
        """
        print(f"[LoginManager] 清除 Cookie: {domain}")
        try:
            self.cdp.send("Network.enable")
            cookies_result = self.cdp.send("Network.getAllCookies")
            cookies = cookies_result.get("cookies", [])

            for cookie in cookies:
                if domain in cookie.get("domain", ""):
                    self.cdp.send("Network.deleteCookies", {
                        "name": cookie["name"],
                        "domain": cookie.get("domain", ""),
                        "path": cookie.get("path", "/"),
                    })

            print(f"[LoginManager] 已清除 {len(cookies)} 个 Cookie")
            self.clear_cache()  # 清除登录缓存
        except Exception as e:
            print(f"[LoginManager] 清除 Cookie 失败: {e}")

    def check_login_by_url_redirect(
        self,
        check_url: str,
        login_keyword: str = "login",
        scope: str = "default",
    ) -> bool:
        """
        通过 URL 重定向检测登录状态（通用方法）

        适用于：小红书、抖音、快手等平台

        Args:
            check_url: 检测 URL（需要登录才能访问的页面）
            login_keyword: 登录页面 URL 关键词
            scope: 登录范围标识

        Returns:
            True: 已登录
            False: 未登录
        """
        # 检查缓存
        cached_status = self.get_cached_status(scope)
        if cached_status is not None:
            return cached_status

        # 导航到检测页面
        self.cdp.navigate(check_url)
        self.cdp.sleep(2, minimum_seconds=1.0)

        # 检查是否重定向到登录页
        current_url = self.cdp.get_current_url()
        print(f"[LoginManager] 当前 URL: {current_url}")

        if login_keyword in current_url.lower():
            self.set_cache(scope, logged_in=False)
            print(
                f"\n[LoginManager] 未登录\n"
                f"  请在 Chrome 窗口中扫码登录，然后重新运行脚本\n"
            )
            return False

        self.set_cache(scope, logged_in=True)
        print(f"[LoginManager] 已登录")
        return True

    def check_login_by_modal(
        self,
        check_url: str,
        modal_keyword: str,
        scope: str = "default",
    ) -> bool:
        """
        通过弹窗检测登录状态（通用方法）

        适用于：B站等平台

        Args:
            check_url: 检测 URL
            modal_keyword: 登录弹窗关键词
            scope: 登录范围标识

        Returns:
            True: 已登录
            False: 未登录
        """
        # 检查缓存
        cached_status = self.get_cached_status(scope)
        if cached_status is not None:
            return cached_status

        # 导航到检测页面
        self.cdp.navigate(check_url)
        self.cdp.sleep(2, minimum_seconds=1.0)

        # 检查是否有登录弹窗
        has_modal = self._check_modal_visible(modal_keyword)

        if has_modal:
            self.set_cache(scope, logged_in=False)
            print(
                f"\n[LoginManager] 未登录\n"
                f"  请在 Chrome 窗口中登录，然后重新运行脚本\n"
            )
            return False

        self.set_cache(scope, logged_in=True)
        print(f"[LoginManager] 已登录")
        return True

    def _check_modal_visible(self, keyword: str) -> bool:
        """检查登录弹窗是否可见"""
        keyword_literal = json.dumps(keyword)
        visible = self.cdp.evaluate(f"""
            (() => {{
                const keyword = {keyword_literal};
                const normalize = (text) => (text || "").replace(/\\s+/g, " ").trim();
                const containsKeyword = (text) => normalize(text).includes(keyword);

                const modalSelectors = [
                    "[class*='login']",
                    "[class*='modal']",
                    "[class*='popup']",
                    "[class*='dialog']",
                    "[class*='mask']",
                ];

                for (const selector of modalSelectors) {{
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {{
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') {{
                            continue;
                        }}
                        if (containsKeyword(el.textContent)) {{
                            return true;
                        }}
                    }}
                }}
                return false;
            }})()
        """)
        return bool(visible)

    def open_login_page(self, login_url: str):
        """
        打开登录页面

        Args:
            login_url: 登录页面 URL
        """
        print(f"[LoginManager] 打开登录页面: {login_url}")
        self.clear_cache()  # 清除缓存
        self.cdp.navigate(login_url)
        print("[LoginManager] 请在浏览器中完成登录")
