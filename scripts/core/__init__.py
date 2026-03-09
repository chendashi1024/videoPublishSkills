"""
核心模块：跨平台复用的基础组件

包含：
- CDPClient: Chrome DevTools Protocol 底层通信
- LoginManager: 登录状态管理和缓存
- UIAutomator: UI 自动化基础操作
"""

from .cdp_client import CDPClient, CDPError
from .login_manager import LoginManager
from .ui_automator import UIAutomator

__all__ = [
    "CDPClient",
    "CDPError",
    "LoginManager",
    "UIAutomator",
]
