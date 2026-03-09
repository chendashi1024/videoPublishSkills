"""
B站平台配置

包含所有 B站特定的 URL、选择器、时间常量
"""

import os

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================================
# B站 URLs
# ============================================================================

BILIBILI_CREATOR_URL = "https://member.bilibili.com/platform/upload/video/frame"
BILIBILI_HOME_URL = "https://www.bilibili.com"
BILIBILI_CREATOR_LOGIN_CHECK_URL = "https://member.bilibili.com"

# ============================================================================
# 登录检测
# ============================================================================

BILIBILI_LOGIN_INDICATOR_KEYWORD = "登录"

# ============================================================================
# DOM 选择器（页面结构变更时需更新）
# 待通过 CDP 实际获取后填充
# ============================================================================

SELECTORS = {
    # 视频上传
    "video_upload_button": ".upload-btn",
    "video_upload_input": 'input[type="file"][accept*=".mp4"]',
    "video_upload_input_name": 'input[name="buploader"]',

    # 标题输入框（上传后动态出现）
    "title_input": 'input[placeholder*="标题"], .input-title input',

    # 简介输入框（上传后动态出现）
    "content_input": 'textarea[placeholder*="简介"], .input-desc textarea',

    # 标签输入（上传后动态出现）
    "tag_input": 'input[placeholder*="标签"], .tag-input input',

    # 分区选择（上传后动态出现）
    "category_selector": '.category-select, [class*="type-select"]',

    # 封面上传
    "cover_upload_button": '[class*="cover"] button, .cover-upload',
    "cover_upload_input": 'input[type="file"][accept*="image"]',

    # 发布按钮
    "publish_button": 'button[class*="submit"], button:has-text("立即投稿")',
    "publish_button_text": "立即投稿",

    # 登录指示器
    "login_indicator": '.nav-user-info, [class*="user"]',

    # 视频处理状态
    "video_processing_indicator": '[class*="progress"], [class*="uploading"], [class*="transcoding"]',
}

# ============================================================================
# 时间配置（秒）
# ============================================================================

PAGE_LOAD_WAIT = 3  # 页面加载等待时间
UPLOAD_WAIT = 8  # 上传后等待编辑器出现的时间
VIDEO_PROCESS_TIMEOUT = 300  # 视频处理超时时间（B站转码较慢）
VIDEO_PROCESS_POLL = 5  # 视频处理状态轮询间隔
ACTION_INTERVAL = 1  # 操作间隔时间

# ============================================================================
# 其他配置
# ============================================================================

MAX_TIMING_JITTER_RATIO = 0.7  # 时间抖动最大比例
DEFAULT_LOGIN_CACHE_TTL_HOURS = 12.0  # 登录缓存有效期（小时）
LOGIN_CACHE_FILE = os.path.abspath(
    os.path.join(SCRIPT_DIR, "..", "..", "tmp", "bilibili_login_cache.json")
)

# Cookie 域名
COOKIE_DOMAIN = ".bilibili.com"
