---
name: RedBookSkills
description: |
  将图文/视频内容自动发布到小红书（XHS）。
  支持三类任务：发布图文、发布视频、仅启动测试浏览器（不发布）。
metadata:
  trigger: 发布内容到小红书
  source: Angiin/Post-to-xhs
---

# Post-to-xhs

你是多平台发布助手。默认只完成上传与填稿交接；只有用户明确要求“直接发布”时才点击最终发布。

## 输入判断

优先按以下顺序判断：
1. 用户明确要求"测试浏览器 / 启动浏览器 / 检查登录 / 只打开不发布"：进入测试浏览器流程。
2. 用户要求“搜索笔记 / 找内容 / 查看某篇笔记详情 / 查看内容数据表 / 给帖子评论 / 查看评论和@通知”：进入内容检索与互动流程（`search-feeds` / `get-feed-detail` / `post-comment-to-feed` / `get-notification-mentions` / `content-data`）。
3. 用户已提供 `标题 + 正文 + 视频(本地路径或URL)`：进入视频流程，按用户语义选择 HANDOFF 或 DIRECT_PUBLISH。
4. 用户已提供 `标题 + 正文 + 图片(本地路径或URL)`：进入图文流程，按用户语义选择 HANDOFF 或 DIRECT_PUBLISH。
5. 用户只提供网页 URL：先提取网页内容与图片/视频，再给出可发布草稿，等待用户确认。
6. 信息不全：先补齐缺失信息，不要直接发布。

## 必做约束

- 用户只说“上传、填好、准备发布、我自己发布”时一律使用 HANDOFF；缺省模式也是 HANDOFF。
- 只有用户明确说“直接发布、帮我发出去、你来点发布”时才使用 DIRECT_PUBLISH 并传 `--auto-publish`。
- DIRECT_PUBLISH 要先等待媒体可发布，然后只点击一次；点击后结果不明时停止，不得重传或重复点击。
- 抖音已存在 `/content/post/video` 填稿页时，`--reuse-existing-tab --auto-publish` 必须先回读并精确匹配本次标题和正文，然后跳过上传、填稿、话题与封面，只点击表单底部“发布”一次。不匹配时 fail closed，不得新建上传页。
- 如本次是定时发布，续发前还必须由上层回读精确定时值；未验证定时值不得点击。
- B站 DIRECT_PUBLISH 的可发布事实以当前可见、启用且文本精确为「立即投稿」的主按钮为准；不得用宽泛 class 节点是否存在推断上传状态。
- B站上传前必须检查当前浏览器是否已有本地未提交视频或处于批量编辑页；命中时在设置文件输入前失败关闭，不得继续上传、追加草稿或点击批量投稿。
- 图文发布时，没有图片不得发布（小红书发图文必须有图片）。
- 视频发布时，没有视频不得发布。图片和视频不可混合使用（二选一）。`--preview` 仅作为 HANDOFF 的兼容显式写法。
- 正文最后一个非空行可以放空格分隔的 `#标签`。抖音、快手保留在正文/简介底部；小红书会识别后逐个选择平台话题；B站会识别后写入「标签」栏，简介不保留 `#标签` 尾巴。上游应先根据内容和平台热度选好目标平台话题。
- 默认使用无头模式；若检测到未登录，切换有窗口模式登录。
- 标题长度不超过 38（中文/中文标点按 2，英文数字按 1）。
- 用户要求"仅测试浏览器"时，不得触发发布命令。
- 如果使用文件路径，必定使用绝对路径，禁止使用相对路径

## 测试浏览器流程（不发布）

1. 启动 post-to-xhs 专用 Chrome（默认有窗口模式，便于人工观察）。
2. 如用户要求静默运行，再使用无头模式。
3. 可选：执行登录状态检查并回传结果。
4. 结束后如用户要求，关闭测试浏览器实例。

## 图文发布流程

1. 准备输入（标题、正文、图片 URL 或本地图片）。
2. 如需文件输入，先写入 `title.txt`、`content.txt`；`content.txt` 最后一行可放目标平台话题标签。
3. 执行发布命令（默认无头）。
4. 回传执行结果（成功/失败 + 关键信息）。

## 视频发布流程

1. 准备输入（标题、正文、视频文件路径或 URL，可选封面路径）。
2. 如需文件输入，先写入 `title.txt`、`content.txt`。
3. HANDOFF：上传已启动且表单可填后完成标题、正文、话题和封面，不监控后续转码，不点击发布，保留页面后退出脚本。
4. DIRECT_PUBLISH：传 `--auto-publish`，等待可发布后点击一次，再交由上层执行平台终态核验。如抖音已有填好的编辑页，必须复用该页并跳过全部 FILL 动作。
5. 回传模式与执行结果；不得把“已点击”表述为“已验证发布”。

快手大视频的上传表单、转码和封面入口共享按文件大小计算的动态等待预算；不得在平台仍在处理时因固定 180 秒上限过早退出。
快手等待期间如用户人工发布或导航离开编辑页，必须返回 `MANUAL_TAKEOVER_DETECTED` 并以不可重试状态结束 FILL；后续只做终态核验，不得自动重传。

## 内容检索与互动流程（搜索/详情/评论/内容数据）

1. 先检查小红书主页登录状态（`XHS_HOME_URL`，非创作者中心）。
2. 执行 `search-feeds` 获取笔记列表（默认会先抓取搜索下拉推荐词，结果字段为 `recommended_keywords`）。
3. 若用户需要详情，从搜索结果中取 `id` + `xsecToken` 再执行 `get-feed-detail`。
4. 若用户需要发表评论，执行 `post-comment-to-feed`（一级评论；必填 `feed_id` / `xsec_token` / `content`）。
5. 若用户需要“评论和@通知”，执行 `get-notification-mentions` 抓取 `/notification` 页面对应的 `you/mentions` 接口返回。
6. 若用户需要“笔记基础信息表”，执行 `content-data` 获取曝光/观看/点赞等指标。
7. 回传结构化结果（数量、核心字段、链接）。

## 常用命令

### 参数顺序提醒（`cdp_publish.py` / `publish_pipeline.py`）

请严格按下面顺序写命令，避免 `unrecognized arguments`：

- 全局参数放在子命令前：`--host --port --headless --account --timing-jitter --reuse-existing-tab`
- 子命令参数放在子命令后：如 `search-feeds` 的 `--keyword --sort-by --note-type`

示例（正确）：

```bash
python scripts/cdp_publish.py --reuse-existing-tab search-feeds --keyword "春招" --sort-by 最新 --note-type 图文
```

### 0) 启动 / 测试浏览器（不发布）

默认 CDP 地址为 `127.0.0.1:9222`，可通过 `--host` / `--port` 指定（例如 `10.0.0.12:9222`）。

OPC 视频发布固定使用 `--account edge`，对应持久化 Microsoft Edge/CDP Profile
`/Users/chenchen/Documents/cc-code/XiaohongshuSkills/edge_profile`。需要临时覆盖该目录时设置
`VIDEO_PUBLISH_EDGE_USER_DATA_DIR`。未传 `--account` 时仍使用账号管理器中的默认账号。

视频发布固定进入以下平台后台地址：

- 抖音：`https://creator.douyin.com/creator-micro/content/upload`
- B站：`https://member.bilibili.com/platform/upload/video/frame`
- 小红书：`https://creator.xiaohongshu.com/publish/publish?source=official`
- 快手：`https://cp.kuaishou.com/article/publish/video?tabType=1`

B站视频填稿默认固定选择「知识」分区，并固定创作声明「个人观点，仅供参考」。标签仍从正文最后一行 `#标签` 提取后写入 B站标签栏，简介不保留话题尾巴。

```bash
# 启动测试浏览器（有窗口，推荐）
python scripts/chrome_launcher.py

# 可选-指定端口启动（默认端口为 9222）
python scripts/chrome_launcher.py --port 9223

# 可选-无头启动测试浏览器
python scripts/chrome_launcher.py --headless

# 可选-指定端口 + 无头
python scripts/chrome_launcher.py --headless --port 9223

# 检查当前登录状态
python scripts/cdp_publish.py check-login

# 可选：优先复用已有标签页（减少有窗口模式下切到前台）
python scripts/cdp_publish.py --reuse-existing-tab check-login

# 指定端口检查登录
python scripts/cdp_publish.py --port 9222 check-login

# 指定端口 + 优先复用已有标签页
python scripts/cdp_publish.py --port 9222 --reuse-existing-tab check-login

# 连接远程 CDP 检查登录（远程 Chrome 需已开启调试端口）
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 check-login

# 重启测试浏览器
python scripts/chrome_launcher.py --restart

# 指定端口重启
python scripts/chrome_launcher.py --restart --port 9223

# 关闭测试浏览器
python scripts/chrome_launcher.py --kill

# 指定端口关闭
python scripts/chrome_launcher.py --kill --port 9223
```

### 1) 首次登录

```bash
python scripts/cdp_publish.py login

# 指定端口登录
python scripts/cdp_publish.py --port 9223 login

# 远程 CDP 登录（不会自动重启远程 Chrome）
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 login
```

### 2) 无头发布 or 有头发布（推荐有窗口发布） 图片 url

```bash
python scripts/publish_pipeline.py --headless \
  --title-file title.txt \
  --content-file content.txt \
  --image-urls "URL1" "URL2"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --preview \
  --content-file content.txt \
  --image-urls "URL1" "URL2"

# 可选：优先复用已有标签页（减少有窗口模式下切到前台）
python scripts/publish_pipeline.py  --reuse-existing-tab --title-file title.txt \
  --content-file content.txt \
  --image-urls "URL1" "URL2"

# 远程 CDP 发布（远程 Chrome 需预先启动并可访问）
python scripts/publish_pipeline.py --host 10.0.0.12 --title-file title.txt \
  --content-file content.txt \
  --image-urls "URL1" "URL2"
```

远程模式说明：当 `--host` 不是 `127.0.0.1/localhost` 时，脚本会跳过本地 `chrome_launcher.py` 的自动启动/重启逻辑。
发布模式说明：`publish_pipeline.py` 默认 HANDOFF，不点击发布；只有明确直发授权时加 `--auto-publish`。


### 3) 无头发布 or 有头发布  使用本地图片发布

```bash
python scripts/publish_pipeline.py --headless \
  --title-file title.txt \
  --content-file content.txt \
  --images "./images/pic1.jpg" "./images/pic2.jpg"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --content-file content.txt \
  --images "./images/pic1.jpg" "./images/pic2.jpg"

# WSL/远程 CDP + Windows/UNC 路径：跳过本地文件预校验
python scripts/publish_pipeline.py --headless \
  --title-file title.txt \
  --content-file content.txt \
  --images "\\\\wsl.localhost\\Ubuntu\\home\\user\\pic1.jpg" \
  --skip-file-check
```

说明：当控制端在 WSL 运行，且传入 Windows/UNC 路径（如 `\\wsl.localhost\...`）时，可加 `--skip-file-check`，避免 Linux 侧 `os.path.isfile()` 误判不存在。

### 3.5) 视频发布（本地视频文件）

```bash
python scripts/publish_pipeline.py --headless \

  --title-file title.txt \
  --content-file content.txt \
  --video "C:/videos/my_video.mp4" \
  --cover "C:/videos/cover.jpg"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --preview \
  --content-file content.txt \
  --video "C:/videos/my_video.mp4" \
  --cover "C:/videos/cover.jpg"
```

抖音封面弹窗必须优先按“点击上传文件”的稳定语义定位真实图片输入框，兼容新版 `role=dialog` / `semi-upload-*` 结构，并保留旧版上传区回退。竖封面上传后可能弹出“设置横封面获取更多流量”引导。流程必须按需处理：有横封面时点击“设置横封面”继续上传横封面，没有横封面时点击“暂不设置”；没弹窗则跳过，不能把它当成每次必有状态。

### 3.6) 视频发布（视频 URL）

```bash
python scripts/publish_pipeline.py --headless \

  --title-file title.txt \
  --content-file content.txt \
  --video-url "https://example.com/video.mp4"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --content-file content.txt \
  --video-url "https://example.com/video.mp4"
```

### 4) 多账号发布 /切换

```bash
python scripts/cdp_publish.py list-accounts
python scripts/cdp_publish.py add-account work --alias "工作号"
python scripts/cdp_publish.py --port 9223 --account work login
python scripts/publish_pipeline.py --port 9223 --account work --headless --title-file title.txt --content-file content.txt --image-urls "URL1"
```

### 5) 搜索内容 / 获取笔记详情

```bash
# 搜索笔记
python scripts/cdp_publish.py search-feeds --keyword "春招"

# 可选：带筛选搜索
python scripts/cdp_publish.py --reuse-existing-tab search-feeds --keyword "春招" --sort-by 最新 --note-type 图文

# 获取笔记详情（feed_id 与 xsec_token 来自搜索结果）
python scripts/cdp_publish.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN
```

说明：`search-feeds` 输出中包含 `recommended_keywords_count` 与 `recommended_keywords`，表示回车前搜索框下拉推荐词。
说明：`check-login` 与主页登录检查默认启用本地缓存（12h，仅缓存“已登录”），到期后自动重新网页校验。

### 6) 给笔记发表评论（一级评论）

```bash
# 直接传评论文本
python scripts/cdp_publish.py post-comment-to-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content "写得很实用，感谢分享"

# 使用文件传评论（适合多行文本）
python scripts/cdp_publish.py post-comment-to-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content-file "/abs/path/comment.txt"
```

### 7) 获取内容数据表（content_data）

```bash
# 获取笔记基础信息表（曝光/观看/封面点击率/点赞/评论/收藏/涨粉/分享/人均观看时长/弹幕）
python scripts/cdp_publish.py content-data

# 下划线别名
python scripts/cdp_publish.py content_data

# 可选：导出 CSV
python scripts/cdp_publish.py --reuse-existing-tab content-data --csv-file "/abs/path/content_data.csv"
```

### 8) 获取评论和@通知（notification mentions）

```bash
# 抓取 /notification 页面触发的 you/mentions 接口数据
python scripts/cdp_publish.py get-notification-mentions

# 下划线别名
python scripts/cdp_publish.py get_notification_mentions
```

## 失败处理

- 登录失败：提示用户重新扫码登录并重试。
- 图片下载失败：提示更换图片 URL 或改用本地图片。
- 页面选择器失效：提示检查 `scripts/cdp_publish.py` 中选择器并更新。
