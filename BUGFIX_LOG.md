## 2026-06-26 快手：封面上传假成功

- 现象：快手填稿日志输出“竖版封面已通过新版封面入口应用”，但发布页主封面区域仍为空，只显示“封面设置”入口。
- 根因：发布器点击了整个封面模块的中心位置，实际落在“智能推荐封面”区域，封面编辑弹窗没有打开；随后兜底逻辑直接给页面隐藏图片 input 设置文件，文件被 input 接收但没有应用为主封面，且旧校验会把推荐封面图片误判为成功。
- 当前页修复：复用当前快手发布页，点击左侧主封面卡片进入封面弹窗，切换“上传封面”，上传本期 3:4 竖版封面，选择 3:4 并确认；重新生成 `发布验证/20260626-173104/kuaishou-report.json`，严格验证通过。
- 代码修复：快手发布器改为优先点击左侧 `default-cover` / `cover-full-editor` 主封面卡片；移除隐藏图片 input 兜底的成功路径；确认后只以主封面区域出现图片或背景图作为应用成功。OPC 发布页验证新增快手主封面检查，避免无封面时报告误判通过。
- 验证：`python3 -m py_compile scripts/kuaishou/publisher_core.py` 通过；`python3 -m py_compile /Users/chenchen/Documents/cge-opc/skill/video-publish/scripts/validate_publish_page.py` 通过；补丁后的 `KuaishouPublisherCore._upload_cover()` 在当前草稿页输出“竖版封面已应用（3:4）”；`validate_publish_page.py --platform kuaishou --strict` 通过。
- 提交：本次修复提交后记录在 Git 历史中，commit message 为“修复快手封面应用校验”。
- 后续规则：快手封面必须通过主封面卡片打开编辑器并确认应用；不得把隐藏 input 接收文件或推荐封面图当作主封面成功。
