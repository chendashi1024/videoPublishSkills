"""
平台发布器基类

定义所有平台发布器的统一接口，确保各平台实现一致性
"""

from abc import ABC, abstractmethod
from typing import Any


class BasePublisher(ABC):
    """
    平台发布器基类

    所有平台的发布器都应继承此类并实现抽象方法
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9222,
        timing_jitter: float = 0.25,
        account_name: str | None = None,
    ):
        """
        初始化发布器

        Args:
            host: CDP 服务地址
            port: CDP 服务端口
            timing_jitter: 时间抖动比例（0-0.7）
            account_name: 账号名称
        """
        self.host = host
        self.port = port
        self.timing_jitter = timing_jitter
        self.account_name = account_name or "default"

    # ========================================================================
    # 连接管理（必须实现）
    # ========================================================================

    @abstractmethod
    def connect(self, reuse_existing_tab: bool = False):
        """
        连接到 Chrome

        Args:
            reuse_existing_tab: 是否优先复用已有标签页
        """
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    # ========================================================================
    # 登录管理（必须实现）
    # ========================================================================

    @abstractmethod
    def check_login(self) -> bool:
        """
        检查登录状态

        Returns:
            bool: 是否已登录
        """
        pass

    @abstractmethod
    def open_login_page(self):
        """打开登录页面供用户扫码登录"""
        pass

    @abstractmethod
    def clear_cookies(self):
        """清除 Cookie（用于切换账号）"""
        pass

    # ========================================================================
    # 发布功能（必须实现）
    # ========================================================================

    @abstractmethod
    def publish(
        self,
        title: str,
        content: str,
        image_paths: list[str] | None = None,
        auto_publish: bool = True,
    ) -> dict[str, Any]:
        """
        发布图文内容

        Args:
            title: 标题
            content: 正文
            image_paths: 图片路径列表
            auto_publish: 是否自动点击发布按钮

        Returns:
            dict: 发布结果 {"status": "success/error", "message": "..."}
        """
        pass

    @abstractmethod
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
            content: 描述/正文
            video_path: 视频文件路径
            cover_path: 封面图片路径（可选）
            auto_publish: 是否自动点击发布按钮

        Returns:
            dict: 发布结果 {"status": "success/error", "message": "..."}
        """
        pass

    # ========================================================================
    # 辅助方法（可选实现）
    # ========================================================================

    def fill_title(self, title: str):
        """填写标题（子类可选实现）"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 fill_title 方法")

    def fill_content(self, content: str):
        """填写正文（子类可选实现）"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 fill_content 方法")

    def upload_images(self, image_paths: list[str]):
        """上传图片（子类可选实现）"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 upload_images 方法")

    def upload_video(self, video_path: str):
        """上传视频（子类可选实现）"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 upload_video 方法")

    def click_publish_button(self):
        """点击发布按钮（子类可选实现）"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 click_publish_button 方法")

    # ========================================================================
    # 平台信息（子类应覆盖）
    # ========================================================================

    @property
    def platform_name(self) -> str:
        """平台名称（如：xiaohongshu, douyin, bilibili, kuaishou）"""
        return "unknown"

    @property
    def platform_display_name(self) -> str:
        """平台显示名称（如：小红书、抖音、B站、快手）"""
        return "未知平台"
