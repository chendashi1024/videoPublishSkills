"""
Unified publish pipeline for Xiaohongshu.

Single CLI entry point that orchestrates:
  chrome_launcher → login check → image/video download → form fill → publish (default)

Usage:
    # Publish immediately after filling (default behavior)
    python publish_pipeline.py --title "标题" --content "正文" --image-urls URL1 URL2
    python publish_pipeline.py --title-file t.txt --content-file body.txt --image-urls URL1

    # Fill form only for manual review (preview mode)
    python publish_pipeline.py --title "标题" --content "正文" --image-urls URL1 --preview

    # Headless mode (no GUI window) - faster for automated publishing
    python publish_pipeline.py --headless --title-file t.txt --content-file body.txt --image-urls URL1

    # Publish to a specific account
    python publish_pipeline.py --account myaccount --title "标题" --content "正文" --image-urls URL1

    # Explicit auto-publish flag (optional compatibility flag)
    python publish_pipeline.py --title "标题" --content "正文" --image-urls URL1 --auto-publish

    # Prefer reusing existing tab (reduce focus switching in headed mode)
    python publish_pipeline.py --reuse-existing-tab --title "标题" --content "正文" --image-urls URL1

    # Use local image files instead of URLs
    python publish_pipeline.py --title "标题" --content "正文" --images img1.jpg img2.jpg
    # Skip local file check (for WSL/remote CDP + Windows/UNC paths)
    python publish_pipeline.py --title "标题" --content "正文" --images "\\\\wsl.localhost\\Ubuntu\\home\\me\\a.jpg" --skip-file-check

    # Publish a video (local file)
    python publish_pipeline.py --title "标题" --content "正文" --video video.mp4 --cover cover.jpg --preview

    # Publish a video (from URL)
    python publish_pipeline.py --title "标题" --content "正文" --video-url "https://example.com/video.mp4"

Exit codes:
    0 = success (PUBLISHED, or READY_TO_PUBLISH in preview mode)
    1 = not logged in (NOT_LOGGED_IN) - headless auto-fallback will restart headed
    2 = error (see stderr)
"""

import argparse
import json
import os
import random
import re
import sys
import time

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add scripts dir to path so sibling modules can be imported
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from chrome_launcher import ensure_chrome, restart_chrome
from cdp_publish import XiaohongshuPublisher, CDPError
from image_downloader import ImageDownloader
from run_lock import SingleInstanceError, single_instance


MAX_TIMING_JITTER_RATIO = 0.7


def _normalize_timing_jitter(value: float) -> float:
    """Clamp timing jitter to a safe range."""
    return max(0.0, min(MAX_TIMING_JITTER_RATIO, value))


def _is_local_host(host: str) -> bool:
    """Return True when host points to the local machine."""
    return host.strip().lower() in {"127.0.0.1", "localhost", "::1"}


def _resolve_account_name(account_name: str | None) -> str:
    """Resolve explicit or default account name for login cache scoping."""
    if account_name and account_name.strip():
        return account_name.strip()
    try:
        from account_manager import get_default_account
        resolved = get_default_account()
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
    except Exception:
        pass
    return "default"


def _jitter_ms(base_ms: int, jitter_ratio: float, minimum_ms: int = 0) -> int:
    """Return a randomized delay in milliseconds around the base value."""
    base = max(minimum_ms, int(base_ms))
    if jitter_ratio <= 0:
        return base

    delta = int(round(base * jitter_ratio))
    low = max(minimum_ms, base - delta)
    high = max(low, base + delta)
    return random.randint(low, high)


def _jitter_seconds(
    base_seconds: float,
    jitter_ratio: float,
    minimum_seconds: float = 0.05,
) -> float:
    """Return a randomized delay in seconds around the base value."""
    base = max(minimum_seconds, float(base_seconds))
    if jitter_ratio <= 0:
        return base

    delta = base * jitter_ratio
    low = max(minimum_seconds, base - delta)
    high = max(low, base + delta)
    return random.uniform(low, high)


def _extract_topic_tags_from_last_line(content: str) -> tuple[str, list[str]]:
    """Extract topic tags from the last non-empty line.

    Expected format of the last line: "#标签1 #标签2 #标签3"
    Returns:
        (content_without_tag_line, tags)
    """
    lines = content.splitlines()

    # Ignore trailing blank lines when finding the last meaningful line.
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return content, []

    last_line = lines[-1].strip()
    parts = [p for p in last_line.split() if p]
    if not parts:
        return content, []

    # Every token must look like '#xxx' and cannot contain spaces.
    if not all(re.fullmatch(r"#[^\s#]+", part) for part in parts):
        return content, []

    body = "\n".join(lines[:-1]).strip()
    return body, parts


def _append_topic_tags_to_content(content: str, topic_tags: list[str]) -> str:
    """把话题标签恢复为正文最后一个非空行。"""
    if not topic_tags:
        return content

    tag_line = " ".join(topic_tags)
    body = content.strip()
    if not body:
        return tag_line

    return f"{body}\n\n{tag_line}"


def _send_cdp(publisher, method: str, params: dict | None = None):
    """兼容新旧发布器的 CDP send 入口。"""
    cdp = getattr(publisher, "cdp", None)
    if cdp is not None and hasattr(cdp, "send"):
        return cdp.send(method, params or {})
    if hasattr(publisher, "_send"):
        return publisher._send(method, params or {})
    raise RuntimeError("publisher does not expose a CDP send method")


def _cdp_click_rect(
    publisher,
    rect: dict,
    timing_jitter: float = 0.25,
):
    """用真实 CDP 鼠标事件点击矩形中心。"""
    x = float(rect["x"]) + float(rect.get("w", rect.get("width", 0))) / 2
    y = float(rect["y"]) + float(rect.get("h", rect.get("height", 0))) / 2
    _send_cdp(publisher, "Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": x,
        "y": y,
    })
    time.sleep(_jitter_seconds(0.08, timing_jitter, minimum_seconds=0.03))
    for event_type in ("mousePressed", "mouseReleased"):
        _send_cdp(publisher, "Input.dispatchMouseEvent", {
            "type": event_type,
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        time.sleep(0.04)


def _upload_file_to_selectors(
    publisher,
    selectors: list[str],
    file_path: str,
) -> bool:
    """把文件设置到第一个匹配的 file input。"""
    doc = _send_cdp(publisher, "DOM.getDocument")
    root_node_id = doc["root"]["nodeId"]

    for selector in selectors:
        result = _send_cdp(publisher, "DOM.querySelectorAll", {
            "nodeId": root_node_id,
            "selector": selector,
        })
        node_ids = result.get("nodeIds") or []
        for node_id in node_ids:
            _send_cdp(publisher, "DOM.setFileInputFiles", {
                "files": [file_path],
                "nodeId": node_id,
            })
            return True
    return False


def _upload_file_to_all_matching_inputs(
    publisher,
    selector: str,
    file_path: str,
):
    """部分上传组件有多个隐藏 input，逐个设置更稳。"""
    doc = _send_cdp(publisher, "DOM.getDocument")
    root_node_id = doc["root"]["nodeId"]
    result = _send_cdp(publisher, "DOM.querySelectorAll", {
        "nodeId": root_node_id,
        "selector": selector,
    })
    node_ids = result.get("nodeIds") or []
    for node_id in node_ids:
        _send_cdp(publisher, "DOM.setFileInputFiles", {
            "files": [file_path],
            "nodeId": node_id,
        })
        time.sleep(0.8)
    return bool(node_ids)


def _upload_xiaohongshu_video_cover(
    publisher,
    cover_path: str,
    timing_jitter: float = 0.25,
):
    """设置小红书视频 3:4 竖屏封面。"""
    print(f"[pipeline] Step 4.2: Uploading Xiaohongshu 3:4 cover: {cover_path}")

    cover_rect = publisher._evaluate(r"""
        (() => {
            const selectors = [
                '.cover-plugin-preview .cover .default',
                '.cover-plugin-preview .default.row',
                '.publish-page-content-cover .default',
                '.cover-plugin-preview [style*="background-image"]'
            ];
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (!el) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    return { x: r.x, y: r.y, w: r.width, h: r.height };
                }
            }
            return null;
        })()
    """)
    if not cover_rect:
        print("[pipeline] Warning: Xiaohongshu cover preview not found.")
        return

    _cdp_click_rect(publisher, cover_rect, timing_jitter)
    time.sleep(_jitter_seconds(1.3, timing_jitter, minimum_seconds=0.8))

    ratio_rect = publisher._evaluate(r"""
        (() => {
            const el = document.querySelector('.cover-modal .ratio-select, .d-modal .ratio-select');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0
                ? { x: r.x, y: r.y, w: r.width, h: r.height }
                : null;
        })()
    """)
    if ratio_rect:
        _cdp_click_rect(publisher, ratio_rect, timing_jitter)
        time.sleep(_jitter_seconds(0.4, timing_jitter, minimum_seconds=0.2))
        vertical_ratio_rect = publisher._evaluate(r"""
            (() => {
                const el = document.querySelector('.ratio-select-menu .ratio-item.ratio-3-4');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0
                    ? { x: r.x, y: r.y, w: r.width, h: r.height }
                    : null;
            })()
        """)
        if vertical_ratio_rect:
            _cdp_click_rect(publisher, vertical_ratio_rect, timing_jitter)
            time.sleep(_jitter_seconds(0.5, timing_jitter, minimum_seconds=0.25))

    uploaded = _upload_file_to_selectors(
        publisher,
        [
            '.cover-modal input[type="file"][accept*="image"]',
            '.d-modal input[type="file"][accept*="image"]',
        ],
        cover_path,
    )
    if not uploaded:
        print("[pipeline] Warning: Xiaohongshu cover image input not found.")
        return

    time.sleep(_jitter_seconds(2.5, timing_jitter, minimum_seconds=1.5))
    confirm_rect = publisher._evaluate(r"""
        (() => {
            const buttons = Array.from(document.querySelectorAll('.cover-modal button, .d-modal button'));
            for (const btn of buttons) {
                const text = (btn.innerText || btn.textContent || '').trim();
                if (text === '确定') {
                    const r = btn.getBoundingClientRect();
                    return { x: r.x, y: r.y, w: r.width, h: r.height };
                }
            }
            return null;
        })()
    """)
    if confirm_rect:
        _cdp_click_rect(publisher, confirm_rect, timing_jitter)
        time.sleep(_jitter_seconds(2.0, timing_jitter, minimum_seconds=1.0))

    ok = publisher._evaluate(r"""
        (() => {
            const cover = document.querySelector('.publish-page-content-cover .default');
            if (!cover) return false;
            const r = cover.getBoundingClientRect();
            const style = cover.getAttribute('style') || '';
            return r.width > 0 && r.height > 0 && (r.height > r.width || style.includes('0.75 / 1'));
        })()
    """)
    print("[pipeline] Xiaohongshu cover uploaded." if ok else "[pipeline] Warning: Xiaohongshu cover upload was not verified.")


def _upload_douyin_vertical_cover(
    publisher,
    cover_path: str,
    timing_jitter: float = 0.25,
):
    """设置抖音竖封面，必要时跳过横封面追加提示。"""
    print(f"[pipeline] Step 4.2: Uploading Douyin vertical cover: {cover_path}")

    vertical_card_rect = publisher._evaluate(r"""
        (() => {
            const cards = Array.from(document.querySelectorAll('.coverControl-CjlzqC'));
            for (const card of cards) {
                const text = (card.innerText || card.textContent || '').trim();
                const r = card.getBoundingClientRect();
                if (text.includes('竖封面3:4') && r.width > 0 && r.height > 0) {
                    return { x: r.x, y: r.y, w: r.width, h: r.height };
                }
            }
            return null;
        })()
    """)
    if not vertical_card_rect:
        print("[pipeline] Warning: Douyin vertical cover card not found.")
        return

    _cdp_click_rect(publisher, vertical_card_rect, timing_jitter)
    time.sleep(_jitter_seconds(1.8, timing_jitter, minimum_seconds=1.0))

    uploaded = _upload_file_to_all_matching_inputs(
        publisher,
        '.dy-creator-content-modal input[type="file"][accept*="image"], '
        '.dy-creator-content-modal-wrap input[type="file"][accept*="image"]',
        cover_path,
    )
    if not uploaded:
        print("[pipeline] Warning: Douyin cover image input not found.")
        return

    deadline = time.time() + 20
    complete_rect = None
    while time.time() < deadline:
        complete_rect = publisher._evaluate(r"""
            (() => {
                const buttons = Array.from(document.querySelectorAll(
                    '.dy-creator-content-modal button, .dy-creator-content-modal-wrap button'
                ));
                for (const btn of buttons) {
                    const text = (btn.innerText || btn.textContent || '').trim();
                    const disabled = btn.disabled
                        || btn.className.includes('disabled')
                        || btn.getAttribute('aria-disabled') === 'true';
                    if (text === '完成' && !disabled) {
                        const r = btn.getBoundingClientRect();
                        return { x: r.x, y: r.y, w: r.width, h: r.height };
                    }
                }
                return null;
            })()
        """)
        if complete_rect:
            break
        time.sleep(0.8)

    if not complete_rect:
        print("[pipeline] Warning: Douyin cover complete button did not become enabled.")
        return

    _cdp_click_rect(publisher, complete_rect, timing_jitter)
    time.sleep(_jitter_seconds(2.0, timing_jitter, minimum_seconds=1.0))

    skip_rect = publisher._evaluate(r"""
        (() => {
            const nodes = Array.from(document.querySelectorAll('button, div, span'));
            for (const el of nodes) {
                const text = (el.innerText || el.textContent || '').trim();
                const r = el.getBoundingClientRect();
                if (text === '暂不设置' && r.width > 0 && r.height > 0) {
                    return { x: r.x, y: r.y, w: r.width, h: r.height };
                }
            }
            return null;
        })()
    """)
    if skip_rect:
        _cdp_click_rect(publisher, skip_rect, timing_jitter)
        time.sleep(_jitter_seconds(2.0, timing_jitter, minimum_seconds=1.0))

    ok = publisher._evaluate(r"""
        (() => {
            const cards = Array.from(document.querySelectorAll('.coverControl-CjlzqC'));
            const vertical = cards.find((card) => (card.innerText || card.textContent || '').includes('竖封面3:4'));
            if (!vertical) return false;
            return Array.from(vertical.querySelectorAll('[style*="background-image"]'))
                .some((el) => {
                    const style = el.getAttribute('style') || '';
                    return style.includes('url(') && !style.includes('background-image: none');
                });
        })()
    """)
    print("[pipeline] Douyin vertical cover uploaded." if ok else "[pipeline] Warning: Douyin vertical cover upload was not verified.")


def _verify_local_files_exist(
    file_paths: list[str],
    media_label: str,
    skip_file_check: bool,
):
    """Verify local files exist unless explicitly skipped."""
    if skip_file_check:
        print(
            f"[pipeline] Step 3: Skipping local {media_label} file check "
            "(--skip-file-check)."
        )
        return

    for file_path in file_paths:
        if not os.path.isfile(file_path):
            print(f"Error: {media_label} file not found: {file_path}", file=sys.stderr)
            sys.exit(2)


def _select_topics(
    publisher: XiaohongshuPublisher,
    tags: list[str],
    timing_jitter: float = 0.25,
):
    """在小红书正文末尾逐个选择平台话题，生成蓝色 tiptap-topic 节点。"""
    if not tags:
        return

    print(f"[pipeline] Step 4.1: Selecting {len(tags)} topic tag(s)...")
    failed_tags = []

    def _cdp_send(method: str, params: dict | None = None):
        cdp = getattr(publisher, "cdp", None)
        if cdp is not None and hasattr(cdp, "send"):
            return cdp.send(method, params or {})
        if hasattr(publisher, "_send"):
            return publisher._send(method, params or {})
        raise RuntimeError("publisher does not expose a CDP send method")

    def _insert_text(text: str):
        _cdp_send("Input.insertText", {"text": text})

    def _press_enter():
        event = {
            "key": "Enter",
            "code": "Enter",
            "windowsVirtualKeyCode": 13,
            "nativeVirtualKeyCode": 13,
        }
        _cdp_send("Input.dispatchKeyEvent", {"type": "keyDown", **event})
        _cdp_send("Input.dispatchKeyEvent", {"type": "keyUp", **event})

    def _click_center(rect: dict):
        x = float(rect["x"]) + float(rect["w"]) / 2
        y = float(rect["y"]) + float(rect["h"]) / 2
        _cdp_send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y,
        })
        time.sleep(_jitter_seconds(0.08, timing_jitter, minimum_seconds=0.03))
        for event_type in ("mousePressed", "mouseReleased"):
            _cdp_send("Input.dispatchMouseEvent", {
                "type": event_type,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            })
            time.sleep(0.04)

    def _move_caret_to_editor_end():
        return publisher._evaluate("""
            (() => {
                const editor = document.querySelector(
                    'div.tiptap.ProseMirror, div.ProseMirror[contenteditable="true"]'
                );
                if (!editor) {
                    return false;
                }
                editor.focus();
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(editor);
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);
                return true;
            })()
        """)

    def _topic_names() -> list[str]:
        return publisher._evaluate(r"""
            (() => {
                const editor = document.querySelector(
                    'div.tiptap.ProseMirror, div.ProseMirror[contenteditable="true"]'
                );
                if (!editor) {
                    return [];
                }
                return Array.from(editor.querySelectorAll('a.tiptap-topic')).map((a) => {
                    try {
                        const data = JSON.parse(a.getAttribute('data-topic') || '{}');
                        if (data.name) return data.name;
                    } catch (e) {}
                    return (a.innerText || '')
                        .replace(/^#/, '')
                        .replace(/\[话题\]#?$/, '')
                        .trim();
                });
            })()
        """) or []

    def _find_topic_candidate(tag: str) -> dict | None:
        return publisher._evaluate(f"""
            (() => {{
                const wanted = {json.dumps("#" + tag)};
                const items = Array.from(document.querySelectorAll(
                    '.tippy-box .item, [role="tooltip"] .item'
                ));
                const mapped = items.map((el, idx) => {{
                    const text = (el.innerText || el.textContent || '').trim();
                    const first = text.split('\\n')[0].trim();
                    const r = el.getBoundingClientRect();
                    return {{
                        idx,
                        text,
                        first,
                        x: r.x,
                        y: r.y,
                        w: r.width,
                        h: r.height,
                        selected: el.classList.contains('is-selected'),
                    }};
                }}).filter((item) => item.w > 0 && item.h > 0);
                return (
                    mapped.find((item) => item.first === wanted)
                    || mapped.find((item) => item.selected)
                    || mapped[0]
                    || null
                );
            }})()
        """)

    if not _move_caret_to_editor_end():
        print("[pipeline] Warning: Xiaohongshu topic editor not found.")
        return

    _press_enter()
    time.sleep(_jitter_seconds(0.25, timing_jitter, minimum_seconds=0.12))

    for index, tag in enumerate(tags):
        normalized_tag = tag.lstrip("#").strip()
        if not normalized_tag:
            continue

        _move_caret_to_editor_end()
        _insert_text("#" + normalized_tag)
        time.sleep(_jitter_seconds(1.8, timing_jitter, minimum_seconds=1.1))

        candidate = _find_topic_candidate(normalized_tag)
        if candidate:
            _click_center(candidate)
        else:
            _press_enter()
        time.sleep(_jitter_seconds(0.9, timing_jitter, minimum_seconds=0.45))

        existing_after = set(_topic_names())
        if normalized_tag in existing_after:
            print(f"[pipeline] Topic selected: {tag}")
        else:
            failed_tags.append(tag)
            print(
                f"[pipeline] Warning: Failed to select topic {tag}. "
                f"Current topics: {', '.join(sorted(existing_after)) or '(none)'}"
            )

        _move_caret_to_editor_end()
        _insert_text(" ")
        if index < len(tags) - 1:
            time.sleep(_jitter_seconds(0.35, timing_jitter, minimum_seconds=0.15))

    if failed_tags:
        print(
            "[pipeline] Warning: Some topic tags were not selected: "
            f"{', '.join(failed_tags)}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Multi-platform publish pipeline - unified entry point"
    )

    # Platform selection
    parser.add_argument(
        "--platform",
        choices=["xiaohongshu", "douyin", "bilibili", "kuaishou"],
        default="xiaohongshu",
        help="Target platform (default: xiaohongshu)",
    )

    # Title
    title_group = parser.add_mutually_exclusive_group(required=True)
    title_group.add_argument("--title", help="Article title text")
    title_group.add_argument("--title-file", help="Read title from UTF-8 file")

    # Content
    content_group = parser.add_mutually_exclusive_group(required=True)
    content_group.add_argument("--content", help="Article body text")
    content_group.add_argument("--content-file", help="Read content from UTF-8 file")

    # Media: images OR video (mutually exclusive)
    media_group = parser.add_mutually_exclusive_group(required=True)
    media_group.add_argument(
        "--image-urls", nargs="+", help="Image URLs to download"
    )
    media_group.add_argument(
        "--images", nargs="+", help="Local image file paths"
    )
    media_group.add_argument(
        "--video", help="Local video file path"
    )
    media_group.add_argument(
        "--video-url", help="Video URL to download"
    )

    # Publish mode
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        default=False,
        help=(
            "Compatibility flag. Publish is now the default behavior unless "
            "--preview is enabled."
        ),
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        default=False,
        help="Preview mode: fill content only and never click publish button",
    )

    parser.add_argument(
        "--cover",
        default=None,
        help="Local cover image path for video mode. The platform module may skip it if cover upload is unsupported.",
    )

    # Headless mode
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run Chrome in headless mode (no GUI). Auto-falls back to headed if login is needed.",
    )

    parser.add_argument(
        "--timing-jitter",
        type=float,
        default=0.25,
        help=(
            "Timing jitter ratio for operation delays (default: 0.25). "
            "Set 0 to disable random jitter."
        ),
    )

    parser.add_argument(
        "--reuse-existing-tab",
        action="store_true",
        default=False,
        help=(
            "Prefer reusing an existing Chrome tab before creating a new one. "
            "Useful in headed mode to reduce foreground focus switching."
        ),
    )

    # Optional temp dir for downloaded images
    parser.add_argument(
        "--temp-dir",
        default=None,
        help="Directory for downloaded images (default: auto-created temp dir)",
    )
    parser.add_argument(
        "--skip-file-check",
        action="store_true",
        default=False,
        help=(
            "Skip local media file existence check. Useful when running in WSL "
            "or using remote CDP with Windows/UNC paths."
        ),
    )

    # Account selection
    parser.add_argument(
        "--account",
        default=None,
        help="Account name to publish to (default: default account)",
    )

    # CDP port
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="CDP host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9222,
        help="CDP remote debugging port (default: 9222)",
    )

    args = parser.parse_args()
    platform = args.platform
    host = args.host
    port = args.port
    headless = args.headless
    account = args.account
    cache_account_name = _resolve_account_name(account)
    reuse_existing_tab = args.reuse_existing_tab
    timing_jitter = _normalize_timing_jitter(args.timing_jitter)
    local_mode = _is_local_host(host)

    if timing_jitter != args.timing_jitter:
        print(
            "[pipeline] Warning: --timing-jitter out of range. "
            f"Clamped to {timing_jitter:.2f}."
        )

    # --- Resolve title ---
    if args.title_file:
        with open(args.title_file, encoding="utf-8") as f:
            title = f.read().strip()
    else:
        title = args.title

    if not title:
        print("Error: title is empty.", file=sys.stderr)
        sys.exit(2)

    # --- Resolve content ---
    if args.content_file:
        with open(args.content_file, encoding="utf-8") as f:
            content = f.read().strip()
    else:
        content = args.content

    if not content:
        print("Error: content is empty.", file=sys.stderr)
        sys.exit(2)

    content, topic_tags = _extract_topic_tags_from_last_line(content)
    content_with_topic_tags = _append_topic_tags_to_content(content, topic_tags)
    if topic_tags:
        print(
            "[pipeline] Detected topic tags from last line: "
            f"{' '.join(topic_tags)}"
        )

    # --- Step 1: Ensure Chrome is running ---
    mode_label = "headless" if headless else "headed"
    account_label = cache_account_name
    print(
        f"[pipeline] Step 1: Ensuring Chrome is running "
        f"({mode_label}, account: {account_label}, host: {host}, port: {port})..."
    )
    print(f"[pipeline] Timing jitter ratio: {timing_jitter:.2f}")
    if reuse_existing_tab:
        print("[pipeline] Tab selection mode: prefer reusing existing tab.")
    if local_mode:
        if not ensure_chrome(port=port, headless=headless, account=account):
            print("Error: Failed to start Chrome.", file=sys.stderr)
            sys.exit(2)
    else:
        print(
            f"[pipeline] Remote CDP mode enabled: {host}:{port}. "
            "Skipping local Chrome launch/restart."
        )

    # --- Step 2: Connect and check login ---
    print(f"[pipeline] Step 2: Checking login status (platform: {platform})...")

    # 根据平台动态加载 Publisher
    if platform == "xiaohongshu":
        from xiaohongshu.publisher_core import XiaohongshuPublisherCore
        publisher = XiaohongshuPublisherCore(
            host=host,
            port=port,
            timing_jitter=timing_jitter,
            account_name=cache_account_name,
        )
    elif platform == "douyin":
        from douyin.publisher_core import DouyinPublisherCore
        publisher = DouyinPublisherCore(
            host=host,
            port=port,
            timing_jitter=timing_jitter,
            account_name=cache_account_name,
        )
    elif platform == "bilibili":
        from bilibili.publisher_core import BilibiliPublisherCore
        publisher = BilibiliPublisherCore(
            host=host,
            port=port,
            timing_jitter=timing_jitter,
            account_name=cache_account_name,
        )
    elif platform == "kuaishou":
        from kuaishou.publisher_core import KuaishouPublisherCore
        publisher = KuaishouPublisherCore(
            host=host,
            port=port,
            timing_jitter=timing_jitter,
            account_name=cache_account_name,
        )
    else:
        print(f"Error: Unsupported platform: {platform}", file=sys.stderr)
        sys.exit(2)
    try:
        publisher.connect(reuse_existing_tab=reuse_existing_tab)
        logged_in = publisher.check_login()
        if not logged_in:
            publisher.disconnect()
            if headless:
                if local_mode:
                    # Auto-fallback: restart Chrome in headed mode for QR login
                    print("[pipeline] Headless mode: not logged in. Switching to headed mode for login...")
                    restart_chrome(port=port, headless=False, account=account)
                    publisher.connect(reuse_existing_tab=reuse_existing_tab)
                    publisher.open_login_page()
                else:
                    print(
                        "[pipeline] Headless + remote mode: cannot auto-restart remote Chrome. "
                        "Attempting to open login page on existing remote browser..."
                    )
                    publisher.connect(reuse_existing_tab=reuse_existing_tab)
                    publisher.open_login_page()
            print("NOT_LOGGED_IN")
            sys.exit(1)
    except CDPError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # --- Determine publish mode: video or image ---
    is_video_mode = bool(args.video or args.video_url)

    # --- Step 3: Prepare media ---
    image_paths = []
    video_path = None
    cover_path = args.cover
    downloader = None

    if cover_path:
        _verify_local_files_exist(
            file_paths=[cover_path],
            media_label="Cover",
            skip_file_check=args.skip_file_check,
        )
        print(f"[pipeline] Step 3: Using local cover: {cover_path}")

    if is_video_mode:
        if args.video_url:
            print("[pipeline] Step 3: Downloading video...")
            downloader = ImageDownloader(temp_dir=args.temp_dir)
            video_path = downloader.download_video(args.video_url)
            if not video_path:
                print("Error: Video download failed.", file=sys.stderr)
                sys.exit(2)
        else:
            video_path = args.video
            _verify_local_files_exist(
                file_paths=[video_path],
                media_label="Video",
                skip_file_check=args.skip_file_check,
            )
            print(f"[pipeline] Step 3: Using local video: {video_path}")
    elif args.image_urls:
        print(f"[pipeline] Step 3: Downloading {len(args.image_urls)} image(s)...")
        downloader = ImageDownloader(temp_dir=args.temp_dir)
        image_paths = downloader.download_all(args.image_urls)
        if not image_paths:
            print("Error: All image downloads failed.", file=sys.stderr)
            sys.exit(2)
    else:
        image_paths = args.images
        _verify_local_files_exist(
            file_paths=image_paths,
            media_label="Image",
            skip_file_check=args.skip_file_check,
        )
        print(f"[pipeline] Step 3: Using {len(image_paths)} local image(s).")

    # --- Step 4: Fill form ---
    print("[pipeline] Step 4: Filling form...")
    # 小红书话题必须走平台联想选择器，普通 #文本 不会生成有效话题节点。
    platform_content = content
    if platform in {"douyin", "kuaishou", "bilibili"}:
        platform_content = content_with_topic_tags

    try:
        if is_video_mode:
            publish_video_kwargs = {
                "title": title,
                "content": platform_content,
                "video_path": video_path,
            }
            if platform in {"bilibili", "kuaishou"}:
                publish_video_kwargs["cover_path"] = cover_path
                publish_video_kwargs["auto_publish"] = False
            elif platform == "douyin":
                # 抖音封面需要走新版封面弹窗，填稿后单独处理。
                publish_video_kwargs["auto_publish"] = False

            publisher.publish_video(**publish_video_kwargs)
        else:
            publisher.publish(
                title=title, content=platform_content, image_paths=image_paths
            )

        if is_video_mode and cover_path:
            if platform == "xiaohongshu":
                _upload_xiaohongshu_video_cover(
                    publisher,
                    cover_path,
                    timing_jitter=timing_jitter,
                )
            elif platform == "douyin":
                _upload_douyin_vertical_cover(
                    publisher,
                    cover_path,
                    timing_jitter=timing_jitter,
                )

        if platform == "xiaohongshu" and topic_tags:
            _select_topics(publisher, topic_tags, timing_jitter=timing_jitter)

        print("FILL_STATUS: READY_TO_PUBLISH")
    except CDPError as e:
        print(f"Error during form fill: {e}", file=sys.stderr)
        if downloader:
            downloader.cleanup()
        sys.exit(2)

    # --- Step 5: Publish (optional) ---
    should_publish = not args.preview
    if args.auto_publish:
        print("[pipeline] --auto-publish is now default and can be omitted.")
    if args.preview:
        print("[pipeline] Preview mode is on, skipping publish click.")

    if should_publish:
        print("[pipeline] Step 5: Clicking publish button...")
        try:
            note_link = publisher._click_publish()
            print("PUBLISH_STATUS: PUBLISHED")
            if note_link:
                print(f"[pipeline] Note published at: {note_link}")
        except CDPError as e:
            print(f"Error clicking publish: {e}", file=sys.stderr)
            if downloader:
                downloader.cleanup()
            sys.exit(2)

    # --- Cleanup ---
    publisher.disconnect()
    if downloader:
        downloader.cleanup()

    print("[pipeline] Done.")


if __name__ == "__main__":
    try:
        with single_instance("post_to_xhs_publish"):
            main()
    except SingleInstanceError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(3)
