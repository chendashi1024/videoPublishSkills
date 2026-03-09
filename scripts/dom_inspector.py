"""
DOM 结构获取工具

使用 CDP 连接到指定平台的创作者中心，获取页面 DOM 结构
用于分析页面元素选择器
"""

import argparse
import json
import sys
import os

# 添加 scripts 目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from core.cdp_client import CDPClient, CDPError


def get_dom_structure(url: str, host: str = "127.0.0.1", port: int = 9222):
    """
    获取指定 URL 的 DOM 结构

    Args:
        url: 目标 URL
        host: CDP 主机
        port: CDP 端口
    """
    print(f"[DOM Inspector] 连接到 {host}:{port}")
    cdp = CDPClient(host, port)

    try:
        # 连接到 Chrome
        cdp.connect(default_url=url)
        print(f"[DOM Inspector] 已连���，正在访问 {url}")

        # 导航到目标页面
        cdp.navigate(url)
        cdp.sleep(5)  # 等待页面加载

        print("[DOM Inspector] 正在获取 DOM 结构...")

        # 获取完整 DOM
        result = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})

        # 保存到文件
        output_file = f"dom_structure_{url.split('//')[1].split('/')[0].replace('.', '_')}.json"
        output_path = os.path.join(SCRIPT_DIR, "..", "tmp", output_file)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"[DOM Inspector] DOM 结构已保存到: {output_path}")

        # 跳过 HTML 保存（页面太大会导致 WebSocket 消息超限）
        # 查找常见元素
        print("\n[DOM Inspector] 查找常见元素...")

        # 查找上传按钮
        upload_buttons = cdp.evaluate("""
            Array.from(document.querySelectorAll('button, input[type="file"], [class*="upload"]'))
                .map(el => ({
                    tag: el.tagName,
                    type: el.type,
                    className: el.className,
                    id: el.id,
                    text: el.textContent?.trim().substring(0, 50)
                }))
        """)
        print(f"\n上传相关元素 ({len(upload_buttons)} 个):")
        for btn in upload_buttons[:10]:
            print(f"  - {btn}")

        # 查找输入框
        inputs = cdp.evaluate("""
            Array.from(document.querySelectorAll('input[type="text"], textarea, [contenteditable="true"]'))
                .map(el => ({
                    tag: el.tagName,
                    type: el.type,
                    className: el.className,
                    id: el.id,
                    placeholder: el.placeholder
                }))
        """)
        print(f"\n输入框元素 ({len(inputs)} 个):")
        for inp in inputs[:10]:
            print(f"  - {inp}")

        # 查找按钮
        buttons = cdp.evaluate("""
            Array.from(document.querySelectorAll('button'))
                .map(el => ({
                    className: el.className,
                    id: el.id,
                    text: el.textContent?.trim().substring(0, 30)
                }))
        """)
        print(f"\n按钮元素 ({len(buttons)} 个):")
        for btn in buttons[:15]:
            print(f"  - {btn}")

    except CDPError as e:
        print(f"[DOM Inspector] 错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[DOM Inspector] 未知错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cdp.disconnect()

    return 0


def main():
    parser = argparse.ArgumentParser(description="获取平台创作者中心 DOM 结构")
    parser.add_argument(
        "--platform",
        choices=["douyin", "bilibili", "kuaishou"],
        required=True,
        help="平台名称",
    )
    parser.add_argument("--host", default="127.0.0.1", help="CDP 主机地址")
    parser.add_argument("--port", type=int, default=9222, help="CDP 端口")

    args = parser.parse_args()

    # 平台 URL 映射
    platform_urls = {
        "douyin": "https://creator.douyin.com/creator-micro/content/upload",
        "bilibili": "https://member.bilibili.com/platform/upload/video/frame",
        "kuaishou": "https://cp.kuaishou.com/article/publish/video",
    }

    url = platform_urls[args.platform]
    print(f"[DOM Inspector] 目标平台: {args.platform}")
    print(f"[DOM Inspector] 目标 URL: {url}")
    print(f"[DOM Inspector] 请确保 Chrome 已启动并登录对应平台\n")

    return get_dom_structure(url, args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
