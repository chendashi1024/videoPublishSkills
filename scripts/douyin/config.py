"""
抖音平台配置

包含所有抖音特定的 URL、选择器、时间常量
"""

import os

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================================
# 抖音 URLs
# ============================================================================

DOUYIN_CREATOR_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_HOME_URL = "https://www.douyin.com"
DOUYIN_CREATOR_LOGIN_CHECK_URL = "https://creator.douyin.com"

# ============================================================================
# 登录检测
# ============================================================================

DOUYIN_LOGIN_INDICATOR_KEYWORD = "登录"

# ============================================================================
# DOM 选择器（页面结构变更时需更新）
# 待通过 CDP 实际获取后填充
# ============================================================================

SELECTORS = {
    # 视频上传
    "video_upload_button": "button.semi-button-primary.container-drag-btn-k6XmB4",
    "video_upload_input": 'input[type="file"]',
    "video_upload_area": ".container-drag-upload-tL99XD",

    # 标题输入框（上传后动态出现）
    "title_input": 'input.semi-input[placeholder*="填写作品标题"]',

    # 描述/正文输入框（上传后动态出现）
    "content_input": 'div.editor-kit-container[contenteditable="true"]',

    # 话题标签（上传后动态出现，需实际测试）
    "topic_input": 'input[placeholder*="话题"], input[placeholder*="添加话题"]',

    # 发布按钮
    "publish_button": "button.douyin-creator-master-button-primary.header-button-KP2xn1",
    "publish_button_text": "发布",

    # 登录指示器
    "login_indicator": "#header-avatar",

    # 视频处理状态
    "video_processing_indicator": '.uploading-container-kBnKYA, .upload-progress-CMQQOJ',
}

# ============================================================================
# 时间配置（秒）
# ============================================================================

PAGE_LOAD_WAIT = 3  # 页面加载等待时间
UPLOAD_WAIT = 6  # 上传后等待编辑器出现的时间
VIDEO_PROCESS_TIMEOUT = 180  # 视频处理超时时间（抖音可能较长）
VIDEO_PROCESS_POLL = 3  # 视频处理状态轮询间隔
ACTION_INTERVAL = 1  # 操作间隔时间

# ============================================================================
# 其他配置
# ============================================================================

MAX_TIMING_JITTER_RATIO = 0.7  # 时间抖动最大比例
DEFAULT_LOGIN_CACHE_TTL_HOURS = 12.0  # 登录缓存有效期（小时）
LOGIN_CACHE_FILE = os.path.abspath(
    os.path.join(SCRIPT_DIR, "..", "..", "tmp", "douyin_login_cache.json")
)

# Cookie 域名
COOKIE_DOMAIN = ".douyin.com"
