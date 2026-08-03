"""
快手平台配置

包含所有快手特定的 URL、选择器、时间常量
"""

import os

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================================
# 快手 URLs
# ============================================================================

KUAISHOU_CREATOR_URL = "https://cp.kuaishou.com/article/publish/video?tabType=1"
KUAISHOU_CREATOR_URL_PREFIX = "https://cp.kuaishou.com/article/publish/video"
KUAISHOU_HOME_URL = "https://www.kuaishou.com"
KUAISHOU_CREATOR_LOGIN_CHECK_URL = "https://cp.kuaishou.com"

# ============================================================================
# 登录检测
# ============================================================================

KUAISHOU_LOGIN_INDICATOR_KEYWORD = "登录"

# ============================================================================
# DOM 选择器（页面结构变更时需更新）
# 待通过 CDP 实际获取后填充
# ============================================================================

SELECTORS = {
    # 视频上传
    "video_upload_button": "button._upload-btn_1j3uy_87",
    "video_upload_input": 'input[type="file"][accept*="video"]',
    "video_upload_area": "section._upload-container_1j3uy_12",

    # 标题输入框（上传后动态出现）
    "title_input": 'input[placeholder*="标题"], input[placeholder*="作品标题"]',

    # 描述/正文输入框（上传后动态出现）
    "content_input": '#work-description-edit, div[contenteditable="true"][class*="description"], textarea[placeholder*="描述"], textarea[placeholder*="作品描述"]',

    # 话题标签（上传后动态出现）
    "topic_input": 'input[placeholder*="话题"], input[placeholder*="添加话题"]',

    # 封面上传
    "cover_upload_input": 'input[type="file"][accept*="image"]',
    "cover_editor_entry": '[class*="cover-full-editor"], [class*="default-cover"]',
    "cover_modal": ".ant-modal",
    "cover_modal_upload_input": '.ant-modal [class*="cropper-upload-upload"] input[type="file"][accept*="image"], .ant-modal input[type="file"][accept*="image"]',
    "cover_default_image": '[class*="default-cover"] img',

    # 发布按钮
    "publish_button": 'button:has-text("发布"), button[class*="publish"]',
    "publish_button_text": "发布",

    # 登录指示器
    "login_indicator": '[class*="user"], [class*="avatar"]',

    # 视频处理状态
    "video_processing_indicator": '[class*="progress"], [class*="uploading"], [class*="processing"]',
}

# ============================================================================
# 时间配置（秒）
# ============================================================================

PAGE_LOAD_WAIT = 3  # 页面加载等待时间
LOGIN_PAGE_READY_TIMEOUT = 12  # 上传页首屏异步渲染等待时间
UPLOAD_WAIT = 6  # 上传后等待编辑器出现的时间
UPLOAD_FORM_TIMEOUT = 180  # 上传后等待发布表单出现的时间
VIDEO_PROCESS_TIMEOUT = 180  # 视频处理超时时间
VIDEO_PROCESS_POLL = 3  # 视频处理状态轮询间隔
MIN_UPLOAD_RATE_BYTES_PER_SECOND = 2 * 1024 * 1024  # 大视频等待预算的保守速率
UPLOAD_PROCESS_GRACE = 180  # 上传后留给平台转码和封面生成的时间
MAX_VIDEO_WAIT_TIMEOUT = 900  # 单次上传和处理的最大等待时间
PUBLISH_RESULT_ATTEMPTS = 30  # 点击发布后的终态轮询次数
ACTION_INTERVAL = 1  # 操作间隔时间

# ============================================================================
# ��他配置
# ============================================================================

MAX_TIMING_JITTER_RATIO = 0.7  # 时间抖动最大比例
DEFAULT_LOGIN_CACHE_TTL_HOURS = 12.0  # 登录缓存有效期（小时）
LOGIN_CACHE_FILE = os.path.abspath(
    os.path.join(SCRIPT_DIR, "..", "..", "tmp", "kuaishou_login_cache.json")
)

# Cookie 域名
COOKIE_DOMAIN = ".kuaishou.com"
