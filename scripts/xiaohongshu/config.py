"""
小红书平台配置

包含所有小红书特定的 URL、选择器、时间常量
"""

import os

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================================
# 小红书 URLs
# ============================================================================

XHS_CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"
XHS_HOME_URL = "https://www.xiaohongshu.com"
XHS_NOTIFICATION_URL = "https://www.xiaohongshu.com/notification"
XHS_CREATOR_LOGIN_CHECK_URL = "https://creator.xiaohongshu.com"
XHS_CONTENT_DATA_URL = "https://creator.xiaohongshu.com/statistics/data-analysis"

# ============================================================================
# API 路径
# ============================================================================

XHS_CONTENT_DATA_API_PATH = "/api/galaxy/creator/datacenter/note/analyze/list"
XHS_NOTIFICATION_MENTIONS_API_PATH = "/api/sns/web/v1/you/mentions"
XHS_SEARCH_RECOMMEND_API_PATH = "/api/sns/web/v1/search/recommend"

# ============================================================================
# 登录检测
# ============================================================================

XHS_HOME_LOGIN_MODAL_KEYWORD = "登录后推荐更懂你的笔记"

# ============================================================================
# 笔记不可访问关键词
# ============================================================================

XHS_FEED_INACCESSIBLE_KEYWORDS = (
    "当前笔记暂时无法浏览",
    "该内容因违规已被删除",
    "该笔记已被删除",
    "内容不存在",
    "笔记不存在",
    "已失效",
    "私密笔记",
    "仅作者可见",
    "因用户设置，你无法查看",
    "因违规无法查看",
)

# ============================================================================
# DOM 选择器（页面结构变更时需更新）
# 最后验证时间：2026-02
# ============================================================================

SELECTORS = {
    # "上传图文" 标签页
    "image_text_tab": "div.creator-tab",
    "image_text_tab_text": "上传图文",

    # "上传视频" 标签页
    "video_tab": "div.creator-tab",
    "video_tab_text": "上传视频",

    # 文件上传输入框
    "upload_input": "input.upload-input",
    "upload_input_alt": 'input[type="file"]',

    # 标题输入框
    "title_input": 'input[placeholder*="填写标题"]',
    "title_input_alt": "input.d-text",

    # 正文编辑器（TipTap/ProseMirror）
    "content_editor": "div.tiptap.ProseMirror",
    "content_editor_alt": 'div.ProseMirror[contenteditable="true"]',

    # 发布按钮
    "publish_button_text": "发布",

    # 登录指示器
    "login_indicator": '.user-info, .creator-header, [class*="user"]',

    # 视频处理状态
    "video_processing_indicator": '[class*="processing"], [class*="uploading"]',

    # 封面更换按钮
    "cover_change_button": '[class*="cover"] button, [class*="封面"] button',

    # 话题标签输入框
    "topic_input": 'input[placeholder*="添加话题"]',
}

# ============================================================================
# 时间配置（秒）
# ============================================================================

PAGE_LOAD_WAIT = 3  # 页面加载等待时间
TAB_CLICK_WAIT = 2  # 点击标签页后等待时间
UPLOAD_WAIT = 6  # 上传后等待编辑器出现的时间
VIDEO_PROCESS_TIMEOUT = 120  # 视频处理超时时间
VIDEO_PROCESS_POLL = 3  # 视频处理状态轮询间隔
ACTION_INTERVAL = 1  # 操作间隔时间

# ============================================================================
# 其他配置
# ============================================================================

MAX_TIMING_JITTER_RATIO = 0.7  # 时间抖动最大比例
DEFAULT_LOGIN_CACHE_TTL_HOURS = 12.0  # 登录缓存有效期（小时）
LOGIN_CACHE_FILE = os.path.abspath(
    os.path.join(SCRIPT_DIR, "..", "..", "tmp", "login_status_cache.json")
)

# Cookie 域名
COOKIE_DOMAIN = ".xiaohongshu.com"
