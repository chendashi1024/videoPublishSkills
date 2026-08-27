# RedBookSkills



自动发布内容到小红书（Xiaohongshu/RED）的命令行工具，也支持仅启动测试浏览器（不发布）。
通过 Chrome DevTools Protocol (CDP) 实现自动化发布，支持多账号管理、无头模式运行、自动搜索素材与内容数据抓取等功能。

## 功能特性
- **自动化发布**：自动填写标题、正文、上传图片
- **话题标签自动写入**：识别正文最后一行 `#标签`；抖音/快手保留在正文底部，小红书自动选择话题，B站写入标签栏且不保留简介尾巴
- **B站分区与声明固定**：B站视频填稿默认选择「知识」分区，并固定创作声明「个人观点，仅供参考」
- **B站可投稿状态校验**：直发只以当前可见、启用且文本精确为「立即投稿」的主按钮为准，不受隐藏或残留处理节点干扰
- **B站未提交视频防重**：上传前检查本地未提交视频和批量编辑页，命中即停止，避免重复上传、草稿堆积或批量误发
- **抖音已填稿续发**：直发时优先复用 `/content/post/video` 编辑页，精确回读标题和正文后跳过重复上传与填稿，仅点击表单底部发布按钮一次
- **多账号支持**：支持管理多个小红书账号，各账号 Cookie 隔离
- **无头模式**：支持后台运行，无需显示浏览器窗口
- **远程 CDP 支持**：可通过 `--host` / `--port` 连接远程 Chrome 调试端口
- **图片下载**：支持从 URL 自动下载图片，自动添加 Referer 绕过防盗链
- **登录检测**：自动检测登录状态，未登录时自动切换到有窗口模式扫码
- **登录状态缓存**：`check_login/check_home_login` 默认本地缓存 12 小时，减少重复跳转校验
- **内容检索与详情读取**：支持搜索笔记并获取指定笔记详情（含评论数据）
- **笔记评论**：支持按 `feed_id + xsec_token` 对指定笔记发表一级评论
- **通知评论抓取**：支持在 `/notification` 页面抓取 `you/mentions` 接口返回
- **内容数据看板抓取**：支持抓取“笔记基础信息”表（曝光/观看/点赞等）并导出 CSV

## 安装

### 环境要求

- Python 3.10+
- Google Chrome 浏览器
- Windows 操作系统（目前仅测试 Windows）

### 安装依赖

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 首次登录

```bash
python scripts/cdp_publish.py login
```

在弹出的 Edge/Chrome 窗口中扫码登录小红书。

### 2. 启动/测试浏览器（不发布）

OPC 视频发布固定使用 `--account edge`，对应持久化 Microsoft Edge/CDP Profile
`/Users/chenchen/Documents/cc-code/XiaohongshuSkills/edge_profile`。需要临时覆盖该目录时设置
`VIDEO_PUBLISH_EDGE_USER_DATA_DIR`。未传 `--account` 时仍使用账号管理器中的默认账号。

```bash
# 启动测试浏览器（有窗口，推荐）
python scripts/chrome_launcher.py

# 无头启动测试浏览器
python scripts/chrome_launcher.py --headless

# 检查当前登录状态
python scripts/cdp_publish.py check-login

# 可选：优先复用已有标签页（减少有窗口模式下切到前台）
python scripts/cdp_publish.py check-login --reuse-existing-tab

# 连接远程 CDP（Chrome 在另一台机器）
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 check-login

# 重启测试浏览器
python scripts/chrome_launcher.py --restart

# 关闭测试浏览器
python scripts/chrome_launcher.py --kill
```

### 3. 发布内容

```bash
# 显式直接发布（会点击最终发布）
python scripts/publish_pipeline.py --headless --auto-publish \
    --title "文章标题" \
    --content "文章正文" \
    --image-urls "https://example.com/image.jpg"

# 有窗口交接模式（仅填充，不点发布）
python scripts/publish_pipeline.py \
    --preview \
    --title "文章标题" \
    --content "文章正文" \
    --image-urls "https://example.com/image.jpg"

# 默认交接：优先复用已有标签页（减少有窗口模式下切到前台）
python scripts/publish_pipeline.py --reuse-existing-tab \
    --title "文章标题" \
    --content "文章正文" \
    --image-urls "https://example.com/image.jpg"

# 连接远程 CDP 并直接发布（远程 Chrome 需已开启调试端口）
python scripts/publish_pipeline.py --host 10.0.0.12 --port 9222 --auto-publish \
    --title "文章标题" \
    --content "文章正文" \
    --image-urls "https://example.com/image.jpg"

# 从文件读取内容
python scripts/publish_pipeline.py --headless \
    --title-file title.txt \
    --content-file content.txt \
    --image-urls "https://example.com/image.jpg"

# 正文最后一行可放话题标签（最多 10 个）；抖音/快手保留在正文底部，小红书自动选择话题，B站写入标签栏
# 例如 content.txt 最后一行：
# #春招 #26届 #校招 #求职 #找工作

# 使用本地图片
python scripts/publish_pipeline.py --headless \
    --title "文章标题" \
    --content "文章正文" \
    --images "C:\path\to\image.jpg"

# WSL/远程 CDP + Windows/UNC 路径可跳过本地文件预校验
python scripts/publish_pipeline.py --headless \
    --title "文章标题" \
    --content "文章正文" \
    --images "\\wsl.localhost\Ubuntu\home\user\image.jpg" \
    --skip-file-check

```

### 4. 多账号管理

```bash
# 列出所有账号
python scripts/cdp_publish.py list-accounts

# 添加新账号
python scripts/cdp_publish.py add-account myaccount --alias "我的账号"

# 登录指定账号
python scripts/cdp_publish.py --account myaccount login

# 使用指定账号发布
python scripts/publish_pipeline.py --account myaccount --headless \
    --title "标题" --content "正文" --image-urls "URL"

# 设置默认账号
python scripts/cdp_publish.py set-default-account myaccount

# 切换账号（清除当前登录，重新扫码）
python scripts/cdp_publish.py switch-account
```

### 5. 搜索内容、查看笔记详情与评论通知抓取

```bash
# 搜索笔记（可选筛选）
python scripts/cdp_publish.py search-feeds --keyword "春招"
python scripts/cdp_publish.py search-feeds --keyword "春招" --sort-by 最新 --note-type 图文

# 获取笔记详情（feed_id 与 xsec_token 可从搜索结果中获取）
python scripts/cdp_publish.py get-feed-detail \
    --feed-id 67abc1234def567890123456 \
    --xsec-token YOUR_XSEC_TOKEN

# 给笔记发表评论（一级评论）
python scripts/cdp_publish.py post-comment-to-feed \
    --feed-id 67abc1234def567890123456 \
    --xsec-token YOUR_XSEC_TOKEN \
    --content "写得很实用，感谢分享！"

# 抓取“评论和@”通知接口（you/mentions）
python scripts/cdp_publish.py get-notification-mentions
```

说明：`search-feeds` 会先在搜索框输入关键词，抓取下拉推荐词（`recommended_keywords`），再回车拉取 feed 列表。

### 6. 获取内容数据表（content_data）

```bash
# 抓取“笔记基础信息”数据表
python scripts/cdp_publish.py content-data

# 下划线别名
python scripts/cdp_publish.py content_data

# 导出 CSV
python scripts/cdp_publish.py content-data --csv-file "/abs/path/content_data.csv"
```

## 命令参考

### 话题标签（publish_pipeline.py）

- 从正文中提取规则：若“最后一个非空行”全部由 `#标签` 组成，则提取为话题标签。
- 平台处理策略：抖音、快手把话题行保留在正文/简介底部；小红书从正文移除话题行，并逐个选择平台话题；B站从正文移除话题行，并写入「标签」栏。
- B站分区与声明策略：视频填稿后主动选择「知识」分区，固定创作声明「个人观点，仅供参考」，再写入标签栏。
- 小红书标签输入策略：逐个输入 `#标签`，等待 `3` 秒，再发送 `Enter` 进行确认。
- 建议数量：`1-10` 个标签；超过平台限制时请手动精简。
- 示例（正文最后一行）：`#春招 #26届 #校招 #春招规划 #面试`

### publish_pipeline.py

统一发布入口，一条命令完成全部流程。

视频发布固定进入以下平台后台地址：

- 抖音：`https://creator.douyin.com/creator-micro/content/upload`
- B站：`https://member.bilibili.com/platform/upload/video/frame`
- 小红书：`https://creator.xiaohongshu.com/publish/publish?source=official`
- 快手：`https://cp.kuaishou.com/article/publish/video?tabType=1`

```bash
python scripts/publish_pipeline.py [选项]

选项:
  --title TEXT           文章标题
  --title-file FILE      从文件读取标题
  --content TEXT         文章正文
  --content-file FILE    从文件读取正文
  --image-urls URL...    图片 URL 列表
  --images FILE...       本地图片文件列表
  --video FILE           本地视频文件
  --video-url URL        视频 URL
  --cover FILE           视频封面图片路径（平台不支持时会跳过并提示）
  --skip-file-check      跳过本地媒体文件存在性检查（WSL/远程 CDP/UNC 路径可用）
  --host HOST            CDP 主机地址（默认 127.0.0.1）
  --port PORT            CDP 端口（默认 9222）
  --headless             无头模式（无浏览器窗口）
  --reuse-existing-tab   优先复用已有标签页（默认关闭）
  --account NAME         指定账号（OPC 视频发布固定使用 edge）
  --auto-publish         显式直发：等待可发布后只点击一次
  --preview              交接模式兼容参数；不写时默认也是交接
```

说明：启用 `--reuse-existing-tab` 时只复用同平台页面。抖音 `--auto-publish` 如命中已填好的 `/content/post/video` 页，会先精确回读标题和正文；匹配后跳过媒体上传、表单填写、话题和封面，只续发一次，不匹配则停止。定时发布的精确时间仍必须由上层在点击前回读验证。
说明：当 `--host` 非 `127.0.0.1/localhost` 时为远程模式，会跳过本地 `chrome_launcher.py` 的自动启动/重启逻辑，请确保远程 CDP 地址可达。
说明：当控制端运行在 WSL、但媒体路径使用 Windows/UNC（如 `\\wsl.localhost\...`）时，可加 `--skip-file-check` 跳过 Linux 侧 `isfile` 预校验。
说明：`publish_pipeline.py` 默认 HANDOFF，只上传和填稿，不监控后续处理，不点击发布。只有用户明确要求直接发布时才加 `--auto-publish`；点击后结果不明时停止，不得重传或重复点击。
说明：抖音封面弹窗优先按“点击上传文件”的稳定语义定位真实图片输入框，兼容新版 `role=dialog` / `semi-upload-*` 结构，并保留旧版上传区回退。竖封面上传后可能弹出“设置横封面获取更多流量”引导；流程会按需处理：有横封面时点击“设置横封面”继续上传横封面，没有横封面时点击“暂不设置”；没弹窗则跳过。
说明：快手会按视频文件大小动态计算表单、转码和封面生成等待预算，大视频不再因固定 180 秒上限被过早判定失败。
说明：快手填稿等待期间如检测到页面已被用户人工发布或导航离开，返回 `FILL_STATUS: MANUAL_TAKEOVER_DETECTED`。该状态是不可重试的填稿终态，调度方只能转入发布事实核验，不得再次上传。

### cdp_publish.py

底层发布控制，支持分步操作。

```bash
# 检查登录状态
python scripts/cdp_publish.py check-login
python scripts/cdp_publish.py check-login --reuse-existing-tab
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 check-login

# 填写表单（不发布）
python scripts/cdp_publish.py fill --title "标题" --content "正文" --images img.jpg
python scripts/cdp_publish.py fill --title "标题" --content "正文" --images img.jpg --reuse-existing-tab
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 fill --title "标题" --content "正文" --images img.jpg

# 点击发布按钮
python scripts/cdp_publish.py click-publish

# 搜索笔记（支持下划线别名：search_feeds）
python scripts/cdp_publish.py search-feeds --keyword "春招"
python scripts/cdp_publish.py search-feeds --keyword "春招" --sort-by 最新 --note-type 图文

# 获取笔记详情（支持下划线别名：get_feed_detail）
python scripts/cdp_publish.py get-feed-detail --feed-id FEED_ID --xsec-token XSEC_TOKEN

# 发表评论（支持下划线别名：post_comment_to_feed）
python scripts/cdp_publish.py post-comment-to-feed --feed-id FEED_ID --xsec-token XSEC_TOKEN --content "评论内容"

# 抓取通知评论接口（支持下划线别名：get_notification_mentions）
python scripts/cdp_publish.py get-notification-mentions

# 获取内容数据表（支持下划线别名：content_data）
python scripts/cdp_publish.py content-data
python scripts/cdp_publish.py content-data --csv-file "/abs/path/content_data.csv"

# 账号管理
python scripts/cdp_publish.py login
python scripts/cdp_publish.py list-accounts
python scripts/cdp_publish.py add-account NAME [--alias ALIAS]
python scripts/cdp_publish.py remove-account NAME [--delete-profile]
python scripts/cdp_publish.py set-default-account NAME
python scripts/cdp_publish.py switch-account
```

说明：`search-feeds`、`get-feed-detail`、`post-comment-to-feed` 与 `get-notification-mentions` 会校验 `xiaohongshu.com` 主页登录态（非创作者中心登录态）。
说明：登录态检查默认启用本地缓存（12 小时，仅缓存“已登录”结果），到期后自动重新走网页校验。
说明：`search-feeds` 输出新增 `recommended_keywords_count` 与 `recommended_keywords` 字段，表示输入关键词后回车前的下拉推荐词。
说明：`content-data` 会校验创作者中心登录态，并抓取 `statistics/data-analysis` 页面中的笔记基础信息表。

### chrome_launcher.py

Chrome 浏览器管理。

```bash
# 启动 Chrome
python scripts/chrome_launcher.py
python scripts/chrome_launcher.py --headless

# 重启 Chrome
python scripts/chrome_launcher.py --restart

# 关闭 Chrome
python scripts/chrome_launcher.py --kill
```

## 支持各种 Skill 工具

本项目可作为 Claude Code、OpenCode 等支持 Skill 的工具使用，只需将项目复制到 `.claude/skills/post-to-xhs/` 目录，并添加 `SKILL.md` 文件即可。

详见 [docs/claude-code-integration.md](docs/claude-code-integration.md)

## 注意事项

1. **仅供学习研究**：请遵守小红书平台规则，不要用于违规内容发布
2. **登录安全**：Cookie 存储在本地 Chrome Profile 中，请勿泄露
3. **选择器更新**：如果小红书页面结构变化导致发布失败，需要更新 `cdp_publish.py` 中的选择器
4. feed 的图片类型
- WB_PRV：预览图（preview），通常更轻、更快，适合列表卡片。
  - WB_DFT：默认图（default），通常用于详情展示，质量/尺寸更完整。

## RoadMap
- [x] 支持更多账号管理功能
- [x] 支持发布功能
- [x] 增加后台笔记获取功能
- [x] 支持自动评论
- [x] 支持素材检索功能
- [x] 增加更多错误处理机制


## 许可证

MIT License

## 联系方式

微信号：`whitedewstory`

<img src="public/whitedew.jpg" alt="微信二维码" width="240" />

### 知识星球，分享最新的使用技巧
<img src="20260302-141029.jpg" alt="知识星球二维码" width="240" />

## Stars
[![Stargazers over time](https://starchart.cc/white0dew/XiaohongshuSkills.svg?variant=adaptive)](https://starchart.cc/white0dew/XiaohongshuSkills)

## 致谢
灵感来自：[Post-to-xhs](https://github.com/Angiin/Post-to-xhs)
