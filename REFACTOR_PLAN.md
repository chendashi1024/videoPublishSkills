# 代码重构计划

## 目标
将 2690 行的 `cdp_publish.py` 拆分为模块化架构，支持多平台扩展

## 架构设计

### 核心层（100% 跨平台复用）
```
scripts/core/
├── cdp_client.py      ✅ 已完成 - CDP 底层通信
├── login_manager.py   ✅ 已完成 - 登录管理+缓存
└── ui_automator.py    ✅ 已完成 - UI 自动化基础
```

### 平台层（小红书）
```
scripts/xiaohongshu/
├── config.py          ✅ 已完成 - 配置常量
├── publisher.py       🔄 进行中 - 发布核心逻辑
├── content_manager.py ⏳ 待完成 - 搜索+详情
├── interaction.py     ⏳ 待完成 - 评论+互动
└── analytics.py       ⏳ 待完成 - 数据抓取
```

### 兼容层
```
scripts/cdp_publish.py ⏳ 待完成 - 向后兼容的 CLI 入口
```

## 代码迁移清单

### 阶段 1：核心层 ✅ 已完成

- [x] CDPClient (300行)
  - connect/disconnect
  - send/evaluate/navigate
  - get_targets/find_or_create_tab

- [x] LoginManager (350行)
  - 登录缓存管理
  - check_login_by_url_redirect
  - check_login_by_modal
  - clear_cookies

- [x] UIAutomator (300行)
  - click_element/click_element_by_text
  - fill_input/fill_contenteditable
  - upload_files
  - wait_for_element

### 阶段 2：小红书发布器 🔄 进行中

**publisher.py** (约 500 行)
- [ ] XiaohongshuPublisher 类
- [ ] _click_image_text_tab()
- [ ] _click_video_tab()
- [ ] _upload_images()
- [ ] _upload_video()
- [ ] _wait_video_processing()
- [ ] _fill_title()
- [ ] _fill_content()
- [ ] _parse_and_fill_topics()
- [ ] _click_publish()
- [ ] publish() - 图文发布
- [ ] publish_video() - 视频发布

### 阶段 3：内容管理 ⏳ 待完成

**content_manager.py** (约 500 行)
- [ ] ContentManager 类
- [ ] _prepare_search_input_keyword()
- [ ] _capture_search_recommendations_via_network()
- [ ] search_feeds()
- [ ] get_feed_detail()
- [ ] _check_feed_page_accessible()

### 阶段 4：互动管理 ⏳ 待完成

**interaction.py** (约 400 行)
- [ ] InteractionManager 类
- [ ] _fill_comment_content()
- [ ] post_comment_to_feed()
- [ ] _like_note()
- [ ] _collect_note()

### 阶段 5：数据分析 ⏳ 待完成

**analytics.py** (约 400 行)
- [ ] AnalyticsManager 类
- [ ] get_content_data()
- [ ] get_notification_mentions()
- [ ] _schedule_click_notification_mentions_tab()
- [ ] _fetch_notification_mentions_via_page()

### 阶段 6：CLI 兼容层 ⏳ 待完成

**cdp_publish.py** (约 300 行)
- [ ] 组合各模块功能
- [ ] 保持向后兼容的 API
- [ ] CLI 参数解析
- [ ] main() 函数

## 复用性评估

| 模块 | 小红书 | 抖音 | B站 | 快手 | 复用率 |
|------|--------|------|-----|------|--------|
| CDPClient | ✅ | ✅ | ✅ | ✅ | 100% |
| LoginManager | ✅ | ✅ | ✅ | ✅ | 90% |
| UIAutomator | ✅ | ✅ | ✅ | ✅ | 85% |
| Publisher | ✅ | 需适配 | 需适配 | 需适配 | 50% |
| ContentManager | ✅ | 需适配 | 需适配 | 需适配 | 30% |

## 下一步行动

1. ✅ 创建核心模块（已完成）
2. 🔄 创建小红书发布器（进行中）
3. ⏳ 迁移内容管理功能
4. ⏳ 迁移互动功能
5. ⏳ 迁移数据分析功能
6. ⏳ 重构 CLI 入口
7. ⏳ 测试向后兼容性
8. ⏳ 更新文档

## 测试计划

- [ ] 核心模块单元测试
- [ ] 小红书发布器集成测试
- [ ] 向后兼容性测试
- [ ] 多账号测试
- [ ] 远程 CDP 测试
