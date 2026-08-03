"""
Unified publish pipeline for Xiaohongshu.

Single CLI entry point that orchestrates:
  chrome_launcher → login check → image/video download → form fill → handoff (default)

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

    # Explicit direct-publish authorization
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
    0 = success (PUBLISHED, READY_TO_PUBLISH, or MANUAL_TAKEOVER_DETECTED)
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
from core.cdp_client import ManualTakeoverDetected
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


def _evaluate_js(publisher, expression: str):
    """兼容新旧发布器的 JavaScript 执行入口。"""
    if hasattr(publisher, "_evaluate"):
        return publisher._evaluate(expression)
    cdp = getattr(publisher, "cdp", None)
    if cdp is not None and hasattr(cdp, "evaluate"):
        return cdp.evaluate(expression)
    raise RuntimeError("publisher does not expose a CDP evaluate method")


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


def _cdp_insert_text(publisher, text: str):
    """通过 CDP 输入文本，触发平台编辑器的真实输入链路。"""
    _send_cdp(publisher, "Input.insertText", {"text": text})


def _cdp_press_key(publisher, key: str, count: int = 1):
    """发送键盘按键事件。"""
    key_code_map = {
        "Backspace": 8,
        "Escape": 27,
        "Enter": 13,
    }
    code = key_code_map.get(key, 0)
    for _ in range(max(1, count)):
        event = {
            "key": key,
            "code": key,
            "windowsVirtualKeyCode": code,
            "nativeVirtualKeyCode": code,
        }
        _send_cdp(publisher, "Input.dispatchKeyEvent", {"type": "keyDown", **event})
        _send_cdp(publisher, "Input.dispatchKeyEvent", {"type": "keyUp", **event})
        time.sleep(0.03)


def _cdp_hotkey(publisher, key: str, modifiers: int):
    """发送带修饰键的快捷键；macOS Command 对应 modifiers=4。"""
    event = {
        "key": key,
        "code": f"Key{key.upper()}",
        "windowsVirtualKeyCode": ord(key.upper()),
        "nativeVirtualKeyCode": ord(key.upper()),
        "modifiers": modifiers,
    }
    _send_cdp(publisher, "Input.dispatchKeyEvent", {"type": "keyDown", **event})
    _send_cdp(publisher, "Input.dispatchKeyEvent", {"type": "keyUp", **event})
    time.sleep(0.1)


def _wait_for_cdp_event(publisher, event_method: str, timeout_seconds: float = 5.0) -> dict | None:
    """等待一个 CDP 事件；用于 file chooser 这类不能只靠 request/response 的流程。"""
    cdp = getattr(publisher, "cdp", None)
    ws = getattr(cdp, "ws", None)
    if ws is None or not hasattr(ws, "recv"):
        return None

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        timeout = max(0.1, deadline - time.time())
        try:
            raw = ws.recv(timeout=timeout)
        except TypeError:
            raw = ws.recv()
        except Exception:
            return None

        try:
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("method") == event_method:
            return data.get("params", {})
    return None


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
        try:
            _send_cdp(publisher, "DOM.setFileInputFiles", {
                "files": [file_path],
                "nodeId": node_id,
            })
        except Exception as exc:
            print(f"[pipeline] Warning: skipped stale file input node {node_id}: {exc}")
            continue
        time.sleep(0.8)
        return True
    return False


def _upload_douyin_cover_from_modal(
    publisher,
    cover_path: str,
    timing_jitter: float = 0.25,
) -> bool:
    """在抖音封面弹窗里通过主上传区上传封面，并让当前裁剪区切到上传图。"""
    upload_rect = None
    deadline = time.time() + 180
    while time.time() < deadline:
        upload_rect = _evaluate_js(publisher, r"""
            (() => {
                const candidates = Array.from(document.querySelectorAll(
                    '.dy-creator-content-modal .upload-ZOJTUA, '
                    + '.dy-creator-content-modal-wrap .upload-ZOJTUA'
                ));
                for (const el of candidates) {
                    const text = (el.innerText || el.textContent || '').trim();
                    const r = el.getBoundingClientRect();
                    const disabled = String(el.className || '').includes('disabled')
                        || el.getAttribute('aria-disabled') === 'true'
                        || Boolean(el.querySelector('.semi-upload-disabled'));
                    if (
                        text.includes('上传封面')
                        && r.width > 0
                        && r.height > 0
                        && !disabled
                    ) {
                        return { x: r.x, y: r.y, w: r.width, h: r.height };
                    }
                }
                return null;
            })()
        """)
        if upload_rect:
            break
        time.sleep(1)
    if not upload_rect:
        return False

    _send_cdp(publisher, "Page.enable")
    _send_cdp(publisher, "DOM.enable")
    _send_cdp(publisher, "Page.setInterceptFileChooserDialog", {"enabled": True})
    try:
        _cdp_click_rect(publisher, upload_rect, timing_jitter)
        chooser = _wait_for_cdp_event(
            publisher,
            "Page.fileChooserOpened",
            timeout_seconds=5.0,
        )
        backend_node_id = (chooser or {}).get("backendNodeId")
        if not backend_node_id:
            return False

        _send_cdp(publisher, "DOM.setFileInputFiles", {
            "backendNodeId": backend_node_id,
            "files": [cover_path],
        })
    finally:
        _send_cdp(publisher, "Page.setInterceptFileChooserDialog", {"enabled": False})

    deadline = time.time() + 20
    while time.time() < deadline:
        uploaded = _evaluate_js(publisher, r"""
            (() => {
                const uploadedTile = document.querySelector(
                    '.dy-creator-content-modal .upload-ZOJTUA [style*="background-image"], '
                    + '.dy-creator-content-modal-wrap .upload-ZOJTUA [style*="background-image"]'
                );
                if (!uploadedTile) return false;
                const style = uploadedTile.getAttribute('style') || '';
                return style.includes('data:image') || style.includes('blob:') || style.includes('url(');
            })()
        """)
        if uploaded:
            # 抖音会在 file chooser 选择完成后把裁剪区切到上传图，稍等预览稳定。
            time.sleep(_jitter_seconds(1.8, timing_jitter, minimum_seconds=1.0))
            return True
        time.sleep(0.8)

    return False


XIAOHONGSHU_COMPLETE_COVER_RATIOS = ("3:4", "原始")


def _xiaohongshu_cover_zoom_ready(
    slider_value: str,
    active_ratio: str,
    image_dimensions: list[tuple[int, int]],
) -> bool:
    """判断小红书封面是否保持完整 3:4 原图。"""
    if slider_value:
        return slider_value == "100%"
    complete_vertical_image = any(
        width > 0
        and height > 0
        and height > width
        and abs((width / height) - 0.75) < 0.02
        for width, height in image_dimensions
    )
    return (
        active_ratio in XIAOHONGSHU_COMPLETE_COVER_RATIOS
        and complete_vertical_image
    )


def _xiaohongshu_cover_state_ready(state: dict) -> bool:
    """兼容新旧小红书发布页，确认已应用真实 3:4 封面。"""
    cover_style = str(state.get("coverStyle") or "")
    has_background = (
        "background-image" in cover_style
        and "url(" in cover_style
        and "background-image: none" not in cover_style
    )
    vertical = bool(
        state.get("previewVertical")
        or state.get("coverVertical")
        or "0.75 / 1" in cover_style
    )
    return has_background and vertical


def _find_xiaohongshu_cover_confirm_rect(publisher):
    """只在小红书封面弹窗内查找确定按钮。"""
    return _evaluate_js(publisher, r"""
        (() => {
            const modal = document.querySelector('.cover-modal')
                || Array.from(document.querySelectorAll('.d-modal')).find((candidate) =>
                    candidate.querySelector(
                        '.crop-ratio-item, .ratio-select, input[type="file"][accept*="image"]'
                    )
                );
            if (!modal) return null;
            const buttons = Array.from(modal.querySelectorAll('button'));
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


def _upload_xiaohongshu_video_cover(
    publisher,
    cover_path: str,
    timing_jitter: float = 0.25,
):
    """设置小红书视频 3:4 竖屏封面。"""
    print(f"[pipeline] Step 4.2: Uploading Xiaohongshu 3:4 cover: {cover_path}")

    cover_rect = _evaluate_js(publisher, r"""
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

    upload_tab_rect = _evaluate_js(publisher, r"""
        (() => {
            const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
            const visible = (el) => {
                if (!el) return false;
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const modal = document.querySelector('.cover-modal, .d-modal');
            const tab = Array.from(
                (modal || document).querySelectorAll('button, span, div')
            ).find((el) => visible(el) && clean(el.innerText || el.textContent) === '上传封面');
            if (!tab) return null;
            const r = tab.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        })()
    """)
    if upload_tab_rect:
        _cdp_click_rect(publisher, upload_tab_rect, timing_jitter)
        time.sleep(_jitter_seconds(0.6, timing_jitter, minimum_seconds=0.3))

    ratio_rect = _evaluate_js(publisher, r"""
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
        vertical_ratio_rect = _evaluate_js(publisher, r"""
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
        raise CDPError("小红书封面图片上传入口未找到，未能应用 3:4 竖版封面")

    modal_ready = False
    deadline = time.time() + 12
    while time.time() < deadline:
        modal_ready = bool(_evaluate_js(publisher, r"""
            (() => {
                const modal = document.querySelector('.cover-modal, .d-modal');
                if (!modal) return false;
                const ratioText = String(
                    modal.querySelector('.ratio-select, .ratio-text')?.innerText
                    || modal.querySelector('.ratio-select, .ratio-text')?.textContent
                    || ''
                ).trim();
                const activeRatio = String(
                    modal.querySelector('.crop-ratio-item-active')?.innerText
                    || modal.querySelector('.crop-ratio-item-active')?.textContent
                    || ''
                ).trim();
                const hasCropRatioList = Boolean(modal.querySelector('.crop-ratio-item'));
                const verticalImage = Array.from(modal.querySelectorAll('img')).some((img) =>
                    img.naturalWidth > 0
                    && img.naturalHeight > 0
                    && img.naturalHeight > img.naturalWidth
                );
                const verticalPreview = Array.from(modal.querySelectorAll('[style*="background-image"]')).some((el) => {
                    const r = el.getBoundingClientRect();
                    return r.height > r.width;
                });
                const ratioReady = ratioText.includes('3:4')
                    || activeRatio === '3:4'
                    || hasCropRatioList;
                return ratioReady && (verticalImage || verticalPreview);
            })()
        """))
        if modal_ready:
            break
        time.sleep(_jitter_seconds(0.5, timing_jitter, minimum_seconds=0.25))
    if not modal_ready:
        raise CDPError("小红书封面弹窗未检测到 3:4 竖版预览，停止避免误用横版封面")

    crop_ratio_rect = _evaluate_js(publisher, r"""
        (() => {
            const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
            const visible = (el) => {
                if (!el) return false;
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const modal = document.querySelector('.cover-modal, .d-modal');
            const item = Array.from(
                (modal || document).querySelectorAll('.crop-ratio-item')
            ).find((el) => visible(el) && clean(el.innerText || el.textContent) === '3:4');
            if (!item) return null;
            const r = item.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        })()
    """)
    if crop_ratio_rect:
        _cdp_click_rect(publisher, crop_ratio_rect, timing_jitter)
        time.sleep(_jitter_seconds(0.5, timing_jitter, minimum_seconds=0.25))

    complete_cover_ratios = json.dumps(
        XIAOHONGSHU_COMPLETE_COVER_RATIOS,
        ensure_ascii=False,
    )
    zoom_ready_script = r"""
        (() => {
            const modal = document.querySelector('.cover-modal, .d-modal');
            if (!modal) return false;
            const value = String(modal.querySelector('.slider-value')?.innerText || '').trim();
            if (value) return value === '100%';
            const activeRatio = String(
                modal.querySelector('.crop-ratio-item-active')?.innerText
                || modal.querySelector('.crop-ratio-item-active')?.textContent
                || ''
            ).trim();
            const completeVerticalImage = Array.from(modal.querySelectorAll('img')).some((img) =>
                img.naturalWidth > 0
                && img.naturalHeight > 0
                && img.naturalHeight > img.naturalWidth
                && Math.abs((img.naturalWidth / img.naturalHeight) - 0.75) < 0.02
            );
            return __COMPLETE_COVER_RATIOS__.includes(activeRatio) && completeVerticalImage;
        })()
    """.replace("__COMPLETE_COVER_RATIOS__", complete_cover_ratios)
    zoom_ready = bool(_evaluate_js(publisher, zoom_ready_script))
    if not zoom_ready:
        slider_rect = _evaluate_js(publisher, r"""
            (() => {
                const button = document.querySelector('.cover-modal .d-slider__button, .d-modal .d-slider__button');
                const runway = document.querySelector('.cover-modal .d-slider__runway, .d-modal .d-slider__runway');
                if (!button || !runway) return null;
                const b = button.getBoundingClientRect();
                const r = runway.getBoundingClientRect();
                return {
                    button: { x: b.x, y: b.y, w: b.width, h: b.height },
                    runway: { x: r.x, y: r.y, w: r.width, h: r.height },
                };
            })()
        """)
        if not slider_rect:
            raise CDPError("小红书封面图片大小滑块未找到，无法确认完整竖版封面")

        start_x = float(slider_rect["button"]["x"]) + float(slider_rect["button"]["w"]) / 2
        y = float(slider_rect["button"]["y"]) + float(slider_rect["button"]["h"]) / 2
        end_x = float(slider_rect["runway"]["x"])
        _send_cdp(publisher, "Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": start_x,
            "y": y,
        })
        _send_cdp(publisher, "Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": start_x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        for step in range(1, 13):
            x = start_x + (end_x - start_x) * step / 12
            _send_cdp(publisher, "Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x,
                "y": y,
                "button": "left",
                "buttons": 1,
            })
            time.sleep(_jitter_seconds(0.05, timing_jitter, minimum_seconds=0.02))
        _send_cdp(publisher, "Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": end_x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        time.sleep(_jitter_seconds(0.8, timing_jitter, minimum_seconds=0.4))

        zoom_ready = bool(_evaluate_js(publisher, r"""
            (() => {
                const modal = document.querySelector('.cover-modal, .d-modal');
                if (!modal) return false;
                const value = String(modal.querySelector('.slider-value')?.innerText || '').trim();
                return value === '100%';
            })()
        """))
    if not zoom_ready:
        raise CDPError("小红书封面图片大小未能归零到 100%，停止避免生成放大裁切封面")

    confirm_rect = _find_xiaohongshu_cover_confirm_rect(publisher)
    if not confirm_rect:
        raise CDPError("小红书封面确认按钮未找到，未能应用 3:4 竖版封面")

    ok = False
    for _ in range(3):
        _cdp_click_rect(publisher, confirm_rect, timing_jitter)
        time.sleep(_jitter_seconds(1.2, timing_jitter, minimum_seconds=0.8))
        cover_state = _evaluate_js(publisher, r"""
            (() => {
                const modalOpen = !!document.querySelector('.cover-modal, .d-modal');
                const cover = document.querySelector('.publish-page-content-cover .default');
                const preview = document.querySelector('.publish-page-preview img.cover');
                const coverStyle = cover ? (cover.getAttribute('style') || '') : '';
                const coverRect = cover ? cover.getBoundingClientRect() : null;
                const previewVertical = !!preview
                    && preview.naturalWidth > 0
                    && preview.naturalHeight > 0
                    && preview.naturalHeight > preview.naturalWidth;
                const coverVertical = !!coverRect && coverRect.height > coverRect.width;
                return {
                    modalOpen,
                    previewVertical,
                    coverVertical,
                    coverStyle,
                };
            })()
        """) or {}
        cover_state["coverApplied"] = _xiaohongshu_cover_state_ready(cover_state)
        if cover_state.get("coverApplied") and cover_state.get("modalOpen"):
            close_rect = _evaluate_js(publisher, r"""
                (() => {
                    const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                    const buttons = Array.from(document.querySelectorAll('.cover-modal button, .d-modal button'));
                    const btn = buttons.find((button) =>
                        ['取消', '关闭'].includes(clean(button.innerText || button.textContent))
                    );
                    if (!btn) return null;
                    const r = btn.getBoundingClientRect();
                    return { x: r.x, y: r.y, w: r.width, h: r.height };
                })()
            """)
            if close_rect:
                _cdp_click_rect(publisher, close_rect, timing_jitter)
                time.sleep(_jitter_seconds(0.8, timing_jitter, minimum_seconds=0.4))
            cover_state = _evaluate_js(publisher, r"""
                (() => {
                    const modalOpen = !!document.querySelector('.cover-modal, .d-modal');
                    if (modalOpen) {
                        for (const el of Array.from(document.querySelectorAll('.cover-modal, .d-modal, .d-modal-mask'))) {
                            el.remove();
                        }
                        document.body.style.overflow = 'auto';
                    }
                    return {
                        modalOpen: !!document.querySelector('.cover-modal, .d-modal'),
                        coverApplied: true,
                    };
                })()
            """) or cover_state
        ok = bool(cover_state.get("coverApplied")) and not bool(cover_state.get("modalOpen"))
        if ok:
            break
        confirm_rect = _find_xiaohongshu_cover_confirm_rect(publisher)
        if not confirm_rect:
            break

    if not ok:
        raise CDPError("小红书封面未应用为 3:4 竖版，停止避免误判发布页")
    print("[pipeline] Xiaohongshu 3:4 cover uploaded.")


def _click_first_visible_text(
    publisher,
    text: str,
    timing_jitter: float = 0.25,
) -> bool:
    """点击第一个可见的精确文本节点。"""
    rect = _evaluate_js(publisher, f"""
        (() => {{
            const wanted = {json.dumps(text)};
            const nodes = Array.from(document.querySelectorAll('button, div, span'));
            for (const el of nodes) {{
                const current = (el.innerText || el.textContent || '').trim();
                const r = el.getBoundingClientRect();
                if (current === wanted && r.width > 0 && r.height > 0) {{
                    return {{ x: r.x, y: r.y, w: r.width, h: r.height }};
                }}
            }}
            return null;
        }})()
    """)
    if not rect:
        return False
    _cdp_click_rect(publisher, rect, timing_jitter)
    return True


def _click_douyin_horizontal_cover_prompt(
    publisher,
    action_text: str,
    timing_jitter: float = 0.25,
) -> bool:
    """处理抖音竖封面后偶发的横封面引导弹窗。"""
    rect = _evaluate_js(publisher, f"""
        (() => {{
            const wanted = {json.dumps(action_text)};
            const dialogs = Array.from(document.querySelectorAll(
                '.dy-creator-content-modal, .dy-creator-content-modal-wrap, [role="dialog"], body'
            ));
            for (const dialog of dialogs) {{
                const dialogText = (dialog.innerText || dialog.textContent || '').trim();
                if (
                    !dialogText.includes('设置横封面获取更多流量')
                    && !(dialogText.includes('横封面') && dialogText.includes('更多流量'))
                ) {{
                    continue;
                }}
                const buttons = Array.from(dialog.querySelectorAll('button, div, span'));
                for (const el of buttons) {{
                    const text = (el.innerText || el.textContent || '').trim();
                    if (text !== wanted) continue;
                    const button = el.closest('button') || el;
                    const r = button.getBoundingClientRect();
                    const disabled = button.disabled
                        || button.getAttribute('aria-disabled') === 'true'
                        || String(button.className || '').includes('disabled');
                    if (r.width > 0 && r.height > 0 && !disabled) {{
                        return {{ x: r.x, y: r.y, w: r.width, h: r.height }};
                    }}
                }}
            }}
            return null;
        }})()
    """)
    if not rect:
        return False

    print(f"[pipeline] Douyin horizontal-cover prompt detected, clicking: {action_text}")
    _cdp_click_rect(publisher, rect, timing_jitter)
    time.sleep(_jitter_seconds(1.2, timing_jitter, minimum_seconds=0.6))
    return True


def _douyin_cover_modal_is_open_for(
    publisher,
    card_label: str,
) -> bool:
    """判断抖音封面编辑弹窗是否已经打开在目标封面页。"""
    return bool(_evaluate_js(publisher, f"""
        (() => {{
            const wanted = {json.dumps(card_label.replace('3:4', '').replace('4:3', ''))};
            const modal = document.querySelector(
                '.dy-creator-content-modal, .dy-creator-content-modal-wrap'
            );
            if (!modal) return false;
            const r = modal.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return false;
            const text = (modal.innerText || modal.textContent || '').trim();
            return text.includes(wanted);
        }})()
    """))


def _upload_douyin_cover_card(
    publisher,
    cover_path: str,
    card_label: str,
    timing_jitter: float = 0.25,
    horizontal_prompt_action: str | None = None,
    use_current_modal: bool = False,
) -> bool:
    """上传抖音指定封面卡片，card_label 为「竖封面3:4」或「横封面4:3」。"""
    print(f"[pipeline] Step 4.2: Uploading Douyin {card_label} cover: {cover_path}")

    modal_already_open = use_current_modal or _douyin_cover_modal_is_open_for(
        publisher,
        card_label,
    )
    if not modal_already_open:
        card_rect = _evaluate_js(publisher, f"""
            (() => {{
                const wanted = {json.dumps(card_label)};
                const cards = Array.from(document.querySelectorAll('.coverControl-CjlzqC'));
                for (const card of cards) {{
                    const text = (card.innerText || card.textContent || '').trim();
                    const r = card.getBoundingClientRect();
                    if (text.includes(wanted) && r.width > 0 && r.height > 0) {{
                        return {{ x: r.x, y: r.y, w: r.width, h: r.height }};
                    }}
                }}
                return null;
            }})()
        """)
        if not card_rect:
            print(f"[pipeline] Warning: Douyin {card_label} cover card not found.")
            return False

        _cdp_click_rect(publisher, card_rect, timing_jitter)
        time.sleep(_jitter_seconds(1.8, timing_jitter, minimum_seconds=1.0))

    uploaded = _upload_douyin_cover_from_modal(
        publisher,
        cover_path,
        timing_jitter=timing_jitter,
    )
    if not uploaded:
        print("[pipeline] Warning: Douyin cover upload area did not accept the image.")
        return False

    deadline = time.time() + 20
    complete_rect = None
    while time.time() < deadline:
        if horizontal_prompt_action and _click_douyin_horizontal_cover_prompt(
            publisher,
            horizontal_prompt_action,
            timing_jitter,
        ):
            if horizontal_prompt_action == "设置横封面":
                return True
            complete_rect = None

        complete_rect = _evaluate_js(publisher, r"""
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
        return False

    _cdp_click_rect(publisher, complete_rect, timing_jitter)
    time.sleep(_jitter_seconds(2.0, timing_jitter, minimum_seconds=1.0))

    ok = _evaluate_js(publisher, f"""
        (() => {{
            const wanted = {json.dumps(card_label)};
            const cards = Array.from(document.querySelectorAll('.coverControl-CjlzqC'));
            const target = cards.find((card) => (card.innerText || card.textContent || '').includes(wanted));
            if (!target) return false;
            return Array.from(target.querySelectorAll('[style*="background-image"]'))
                .some((el) => {{
                    const style = el.getAttribute('style') || '';
                    return style.includes('url(') && !style.includes('background-image: none');
                }});
        }})()
    """)
    print(
        f"[pipeline] Douyin {card_label} cover uploaded."
        if ok
        else f"[pipeline] Warning: Douyin {card_label} cover upload was not verified."
    )
    return bool(ok)


def _upload_douyin_covers(
    publisher,
    vertical_cover_path: str,
    horizontal_cover_path: str | None = None,
    timing_jitter: float = 0.25,
):
    """设置抖音竖封面和横封面；缺横封面时才跳过横封面提示。"""
    vertical_ok = _upload_douyin_cover_card(
        publisher,
        vertical_cover_path,
        "竖封面3:4",
        timing_jitter=timing_jitter,
        horizontal_prompt_action="设置横封面" if horizontal_cover_path else "暂不设置",
    )
    if not vertical_ok:
        raise CDPError("抖音竖封面未上传或未验证，停止进入可发布状态")

    if horizontal_cover_path:
        prompt_clicked = _click_douyin_horizontal_cover_prompt(
            publisher,
            "设置横封面",
            timing_jitter,
        )
        horizontal_ok = _upload_douyin_cover_card(
            publisher,
            horizontal_cover_path,
            "横封面4:3",
            timing_jitter=timing_jitter,
            use_current_modal=prompt_clicked,
        )
        if not horizontal_ok:
            raise CDPError("抖音横封面未上传或未验证，停止进入可发布状态")
    elif _click_douyin_horizontal_cover_prompt(
        publisher,
        "暂不设置",
        timing_jitter,
    ) or (vertical_ok and _click_first_visible_text(publisher, "暂不设置", timing_jitter)):
        time.sleep(_jitter_seconds(2.0, timing_jitter, minimum_seconds=1.0))


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
        return _evaluate_js(publisher, """
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
        return _evaluate_js(publisher, r"""
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
        return _evaluate_js(publisher, f"""
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


def _select_douyin_topics(
    publisher,
    tags: list[str],
    timing_jitter: float = 0.25,
):
    """在抖音正文末尾通过话题联想选择器生成有效高亮话题。"""
    normalized_tags = [tag.lstrip("#").strip() for tag in tags if tag.lstrip("#").strip()]
    if not normalized_tags:
        return

    print(f"[pipeline] Step 4.1: Selecting {len(normalized_tags)} Douyin topic tag(s)...")
    failed_tags = []

    def _move_caret_to_editor_end() -> bool:
        return bool(_evaluate_js(publisher, r"""
            (() => {
                const editor = document.querySelector('div.editor-kit-container[contenteditable="true"]');
                if (!editor) return false;
                editor.focus();
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(editor);
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);
                return true;
            })()
        """))

    def _mention_names() -> list[str]:
        return _evaluate_js(publisher, r"""
            (() => {
                const editor = document.querySelector('div.editor-kit-container[contenteditable="true"]');
                if (!editor) return [];
                return Array.from(editor.querySelectorAll('[data-mention="#"]')).map((el) =>
                    (el.innerText || el.textContent || '')
                        .replace(/\u00a0/g, '')
                        .replace(/^#/, '')
                        .trim()
                );
            })()
        """) or []

    def _find_candidate(tag: str) -> dict | None:
        return _evaluate_js(publisher, f"""
            (() => {{
                const wanted = {json.dumps(tag, ensure_ascii=False)};
                const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const isVisible = (el) => {{
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && r.width > 0
                        && r.height > 0
                        && r.bottom >= 0
                        && r.top <= window.innerHeight
                        && r.right >= 0
                        && r.left <= window.innerWidth;
                }};

                const nameNodes = Array.from(document.querySelectorAll(
                    '[class*="tag-hash-view-name"]'
                )).filter((el) => isVisible(el) && clean(el.innerText || el.textContent) === wanted);
                for (const nameNode of nameNodes) {{
                    const row = nameNode.closest('div[class*="tag-hash-"]')
                        || nameNode.closest('[class*="mention-suggest-item"]')
                        || nameNode;
                    if (!isVisible(row)) continue;
                    const r = row.getBoundingClientRect();
                    return {{
                        text: clean(row.innerText || row.textContent),
                        x: r.x,
                        y: r.y,
                        w: r.width,
                        h: r.height,
                    }};
                }}

                const items = Array.from(document.querySelectorAll(
                    'div[class*="tag-hash-"], '
                    + '.mention-suggest-item-container-TVOZMl, '
                    + '.mention-suggest-item-container, '
                    + '[class*="mention-suggest-item"]'
                ));
                const mapped = items.map((el) => {{
                    const r = el.getBoundingClientRect();
                    const text = clean(el.innerText || el.textContent);
                    return {{
                        text,
                        x: r.x,
                        y: r.y,
                        w: r.width,
                        h: r.height,
                    }};
                }}).filter((item) => item.w > 0 && item.h > 0);
                return mapped.find((item) => {{
                    const firstToken = item.text.split(/\\s+/)[0].replace(/^#/, '');
                    return firstToken === wanted;
                }}) || null;
            }})()
        """)

    def _remove_plain_tag_text(tag: str):
        """删除非 mention 的普通 #话题文本，避免失败/重试残留污染正文。"""
        _evaluate_js(publisher, f"""
            (() => {{
                const editor = document.querySelector('div.editor-kit-container[contenteditable="true"]');
                if (!editor) return false;
                const tag = {json.dumps(tag, ensure_ascii=False)};
                const needle = '#' + tag;
                const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
                const textNodes = [];
                while (walker.nextNode()) {{
                    textNodes.push(walker.currentNode);
                }}
                for (const node of textNodes) {{
                    if (node.parentElement && node.parentElement.closest('[data-mention="#"]')) {{
                        continue;
                    }}
                    let value = node.nodeValue || '';
                    value = value
                        .split('\\u00a0' + needle).join('')
                        .split(' ' + needle).join('')
                        .split(needle).join('');
                    node.nodeValue = value;
                }}
                editor.normalize();
                editor.dispatchEvent(new InputEvent('input', {{
                    bubbles: true,
                    inputType: 'deleteContentBackward',
                    data: null,
                }}));
                editor.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }})()
        """)

    def _restore_topic_state(before_names: set[str], attempted_tag: str) -> set[str]:
        """只清理本轮失败的话题文本或错误 mention，避免误删已成功话题。"""
        _cdp_press_key(publisher, "Escape")
        cleaned_names = _evaluate_js(publisher, f"""
            (() => {{
                const editor = document.querySelector('div.editor-kit-container[contenteditable="true"]');
                if (!editor) return [];

                const allowed = new Set({json.dumps(sorted(before_names), ensure_ascii=False)});
                const attempted = {json.dumps(attempted_tag, ensure_ascii=False)};
                const needle = '#' + attempted;

                const normalizeMention = (el) => (el.innerText || el.textContent || '')
                    .replace(/\\u00a0/g, '')
                    .replace(/^#/, '')
                    .trim();

                for (const mention of Array.from(editor.querySelectorAll('[data-mention="#"]'))) {{
                    const name = normalizeMention(mention);
                    if (!allowed.has(name)) {{
                        mention.remove();
                    }}
                }}

                const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
                const textNodes = [];
                while (walker.nextNode()) {{
                    textNodes.push(walker.currentNode);
                }}

                for (const node of textNodes) {{
                    if (node.parentElement && node.parentElement.closest('[data-mention="#"]')) {{
                        continue;
                    }}
                    let value = node.nodeValue || '';
                    if (!value.includes(needle)) {{
                        continue;
                    }}
                    value = value
                        .split('\\u00a0' + needle).join('')
                        .split(' ' + needle).join('')
                        .split(needle).join('');
                    node.nodeValue = value;
                }}

                editor.normalize();
                editor.dispatchEvent(new InputEvent('input', {{
                    bubbles: true,
                    inputType: 'deleteContentBackward',
                    data: null,
                }}));
                editor.dispatchEvent(new Event('change', {{ bubbles: true }}));

                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(editor);
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);

                return Array.from(editor.querySelectorAll('[data-mention="#"]')).map(normalizeMention);
            }})()
        """) or []
        time.sleep(_jitter_seconds(0.35, timing_jitter, minimum_seconds=0.2))
        return set(cleaned_names)

    if not _move_caret_to_editor_end():
        print("[pipeline] Warning: Douyin topic editor not found.")
        return

    for tag in normalized_tags:
        if tag in _mention_names():
            print(f"[pipeline] Douyin topic already selected: #{tag}")
            continue

        before_names = set(_mention_names())
        _move_caret_to_editor_end()
        _cdp_insert_text(publisher, f" #{tag}")

        candidate = None
        for attempt in range(12):
            time.sleep(_jitter_seconds(0.45, timing_jitter, minimum_seconds=0.25))
            candidate = _find_candidate(tag)
            if candidate:
                break
        if candidate:
            _cdp_click_rect(publisher, candidate, timing_jitter)
            time.sleep(_jitter_seconds(0.9, timing_jitter, minimum_seconds=0.5))
        else:
            _restore_topic_state(before_names, tag)

        _remove_plain_tag_text(tag)
        existing_after = set(_mention_names())
        expected_after = before_names | {tag}
        if existing_after == expected_after:
            print(f"[pipeline] Douyin topic selected: #{tag}")
        else:
            if existing_after != before_names:
                existing_after = _restore_topic_state(before_names, tag)
            failed_tags.append("#" + tag)
            print(
                f"[pipeline] Warning: Failed to select Douyin topic #{tag}. "
                f"Current topics: {', '.join('#' + t for t in sorted(existing_after)) or '(none)'}"
            )

    if failed_tags:
        print(
            "[pipeline] Warning: Some Douyin topic tags were not selected: "
            f"{', '.join(failed_tags)}"
        )


def _select_kuaishou_topics(
    publisher,
    tags: list[str],
):
    """在快手正文末尾插入平台同款 at-tag-item 话题节点。"""
    normalized_tags = [tag.lstrip("#").strip() for tag in tags if tag.lstrip("#").strip()]
    if not normalized_tags:
        return

    print(f"[pipeline] Step 4.1: Inserting {len(normalized_tags)} Kuaishou topic tag(s)...")
    result = _evaluate_js(publisher, f"""
        (() => {{
            const tags = {json.dumps(normalized_tags, ensure_ascii=False)};
            const editor = document.querySelector(
                '#work-description-edit, div[contenteditable="true"][class*="description"]'
            );
            if (!editor) {{
                return {{ ok: false, names: [], reason: 'editor not found' }};
            }}

            editor.focus();
            const selection = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(editor);
            range.collapse(false);
            selection.removeAllRanges();
            selection.addRange(range);

            const existing = new Set(
                Array.from(editor.querySelectorAll('.at-tag-item')).map((el) =>
                    (el.getAttribute('data-tag-name') || el.innerText || '')
                        .replace(/^#/, '')
                        .trim()
                )
            );

            const fragment = document.createDocumentFragment();
            for (const tag of tags) {{
                if (!tag || existing.has(tag)) continue;

                fragment.appendChild(document.createTextNode('\\u00a0'));

                const outer = document.createElement('span');
                outer.setAttribute('is-tag', 'true');
                outer.style.fontSize = '14px';
                outer.style.letterSpacing = '0px';

                const inner = document.createElement('span');
                inner.className = 'at-tag-item';
                inner.setAttribute('data-tag-name', tag);
                inner.textContent = '#' + tag;
                outer.appendChild(inner);
                fragment.appendChild(outer);

                const space = document.createElement('span');
                space.style.fontSize = '14px';
                space.style.letterSpacing = '0px';
                space.textContent = '\\u00a0';
                fragment.appendChild(space);
            }}

            range.insertNode(fragment);
            range.collapse(false);
            selection.removeAllRanges();
            selection.addRange(range);

            editor.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertHTML', data: null }}));
            editor.dispatchEvent(new Event('change', {{ bubbles: true }}));

            const names = Array.from(editor.querySelectorAll('.at-tag-item')).map((el) =>
                (el.getAttribute('data-tag-name') || el.innerText || '')
                    .replace(/^#/, '')
                    .trim()
            );
            return {{ ok: true, names }};
        }})()
    """) or {}

    names = set(result.get("names") or [])
    missing = [f"#{tag}" for tag in normalized_tags if tag not in names]
    for tag in normalized_tags:
        if tag in names:
            print(f"[pipeline] Kuaishou topic inserted: #{tag}")
    if missing:
        print(
            "[pipeline] Warning: Some Kuaishou topic tags were not inserted: "
            f"{', '.join(missing)}"
        )


def _select_bilibili_tags(
    publisher,
    tags: list[str],
    timing_jitter: float = 0.25,
):
    """把发布稿里的 B站话题行转成 B站标签栏关键词，不写入简介。"""
    normalized_tags = []
    seen = set()
    for tag in tags:
        normalized = tag.lstrip("#").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_tags.append(normalized)
    if not normalized_tags:
        return

    print(f"[pipeline] Step 4.1: Setting {len(normalized_tags)} Bilibili tag(s)...")
    _evaluate_js(publisher, """
        (() => {
            const el = document.querySelector('#tag-container');
            if (el) el.scrollIntoView({ block: 'center', inline: 'nearest' });
        })()
    """)
    time.sleep(_jitter_seconds(0.4, timing_jitter, minimum_seconds=0.2))

    for _ in range(10):
        close_rect = _evaluate_js(publisher, r"""
            (() => {
                const visible = (el) => {
                    if (!el) return false;
                    const style = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0
                        && rect.bottom >= 0
                        && rect.top <= innerHeight
                        && rect.right >= 0
                        && rect.left <= innerWidth;
                };
                const close = Array.from(
                    document.querySelectorAll('#tag-container .label-item-v2-container .close')
                ).find(visible);
                if (!close) return null;
                const rect = close.getBoundingClientRect();
                return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
            })()
        """)
        if not close_rect:
            break
        _cdp_click_rect(publisher, close_rect, timing_jitter)
        time.sleep(_jitter_seconds(0.25, timing_jitter, minimum_seconds=0.1))

    for tag in normalized_tags:
        target = _evaluate_js(publisher, f"""
            (() => {{
                const wanted = {json.dumps(tag, ensure_ascii=False)};
                const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {{
                    if (!el) return false;
                    const style = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0
                        && rect.bottom >= 0
                        && rect.top <= innerHeight
                        && rect.right >= 0
                        && rect.left <= innerWidth;
                }};
                const existing = Array.from(
                    document.querySelectorAll('#tag-container .label-item-v2-container')
                ).map((el) => clean(el.innerText || el.textContent));
                if (existing.includes(wanted)) return {{ already: true }};
                const hot = Array.from(
                    document.querySelectorAll('.tag-wrp .hot-tag-container, .tag-wrp .hot-tag-item')
                ).filter(visible).find((el) => clean(el.innerText || el.textContent) === wanted);
                if (hot) {{
                    const rect = hot.getBoundingClientRect();
                    return {{ rect: {{ x: rect.x, y: rect.y, w: rect.width, h: rect.height }} }};
                }}
                const input = document.querySelector('#tag-container input.input-val');
                if (!input) return null;
                input.scrollIntoView({{ block: 'center', inline: 'nearest' }});
                input.focus();
                const rect = input.getBoundingClientRect();
                return {{
                    inputRect: {{ x: rect.x, y: rect.y, w: rect.width, h: rect.height }},
                }};
            }})()
        """)
        if target and target.get("already"):
            continue
        if target and target.get("rect"):
            _cdp_click_rect(publisher, target["rect"], timing_jitter)
            time.sleep(_jitter_seconds(0.4, timing_jitter, minimum_seconds=0.2))
        elif target and target.get("inputRect"):
            _cdp_click_rect(publisher, target["inputRect"], timing_jitter)
            _cdp_insert_text(publisher, tag)
            time.sleep(_jitter_seconds(0.2, timing_jitter, minimum_seconds=0.1))
            _cdp_press_key(publisher, "Enter")
            time.sleep(_jitter_seconds(0.55, timing_jitter, minimum_seconds=0.25))

    result = _evaluate_js(publisher, r"""
        (() => {
            const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
            return Array.from(
                document.querySelectorAll('#tag-container .label-item-v2-container')
            ).map((el) => clean(el.innerText || el.textContent));
        })()
    """) or []
    names = set(result)
    missing = [tag for tag in normalized_tags if tag not in names]
    for tag in normalized_tags:
        if tag in names:
            print(f"[pipeline] Bilibili tag set: {tag}")
    if missing:
        raise CDPError(
            "B站标签未完整写入，停止进入可发布状态: "
            + ", ".join(missing)
        )


def resolve_publish_mode(*, auto_publish: bool, preview: bool) -> str:
    """解析发布模式：默认只填充交接，直发必须显式授权。"""
    if auto_publish and preview:
        raise ValueError("--auto-publish 与 --preview 不能同时使用")
    return "DIRECT_PUBLISH" if auto_publish else "HANDOFF"


def should_execute_direct_publish(mode: str) -> bool:
    """只有 DIRECT_PUBLISH 模式允许点击最终发布。"""
    return mode == "DIRECT_PUBLISH"


def execute_direct_publish(publisher, *, is_video_mode: bool):
    """直发前等待媒体可发布，然后只点击一次。"""
    if is_video_mode:
        wait_for_processing = getattr(publisher, "_wait_video_processing", None)
        if not callable(wait_for_processing):
            raise CDPError("当前平台缺少视频可发布检查，拒绝直接点击发布")
        wait_for_processing()
    return publisher._click_publish()


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
    publish_mode_group = parser.add_mutually_exclusive_group()
    publish_mode_group.add_argument(
        "--auto-publish",
        action="store_true",
        default=False,
        help="Direct-publish mode: wait until publishable, then click publish exactly once",
    )

    publish_mode_group.add_argument(
        "--preview",
        action="store_true",
        default=False,
        help="Compatibility flag for handoff mode; handoff is already the default",
    )

    parser.add_argument(
        "--cover",
        default=None,
        help="Local cover image path for video mode. The platform module may skip it if cover upload is unsupported.",
    )
    parser.add_argument(
        "--cover-horizontal",
        default=None,
        help="Local horizontal cover image path for platforms that support separate horizontal and vertical covers.",
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
        help="Account name to publish to (OPC publishing: edge)",
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
    publish_mode = resolve_publish_mode(
        auto_publish=args.auto_publish,
        preview=args.preview,
    )
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
        if not ensure_chrome(port=port, headless=headless, account=cache_account_name):
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
                    restart_chrome(port=port, headless=False, account=cache_account_name)
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
    horizontal_cover_path = args.cover_horizontal
    downloader = None

    if cover_path:
        _verify_local_files_exist(
            file_paths=[cover_path],
            media_label="Cover",
            skip_file_check=args.skip_file_check,
        )
        print(f"[pipeline] Step 3: Using local cover: {cover_path}")

    if horizontal_cover_path:
        _verify_local_files_exist(
            file_paths=[horizontal_cover_path],
            media_label="Horizontal cover",
            skip_file_check=args.skip_file_check,
        )
        print(f"[pipeline] Step 3: Using local horizontal cover: {horizontal_cover_path}")

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
    # 抖音、快手、小红书话题必须走平台话题能力；B站标签走标签栏，不追加到简介。
    platform_content = content

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

            publish_result = publisher.publish_video(**publish_video_kwargs)
            if isinstance(publish_result, dict) and publish_result.get("status") == "error":
                raise CDPError(publish_result.get("message") or "视频填稿失败")
        else:
            publish_result = publisher.publish(
                title=title, content=platform_content, image_paths=image_paths
            )
            if isinstance(publish_result, dict) and publish_result.get("status") == "error":
                raise CDPError(publish_result.get("message") or "图文填稿失败")

        if platform == "douyin" and topic_tags:
            _select_douyin_topics(publisher, topic_tags, timing_jitter=timing_jitter)
        elif platform == "kuaishou" and topic_tags:
            _select_kuaishou_topics(publisher, topic_tags)
        elif platform == "xiaohongshu" and topic_tags:
            _select_topics(publisher, topic_tags, timing_jitter=timing_jitter)
        elif platform == "bilibili" and topic_tags:
            _select_bilibili_tags(publisher, topic_tags, timing_jitter=timing_jitter)

        if is_video_mode and cover_path:
            if platform == "xiaohongshu":
                _upload_xiaohongshu_video_cover(
                    publisher,
                    cover_path,
                    timing_jitter=timing_jitter,
                )
            elif platform == "douyin":
                _upload_douyin_covers(
                    publisher,
                    cover_path,
                    horizontal_cover_path,
                    timing_jitter=timing_jitter,
                )

        print("FILL_STATUS: READY_TO_PUBLISH")
    except ManualTakeoverDetected as e:
        print("FILL_STATUS: MANUAL_TAKEOVER_DETECTED")
        print(f"[pipeline] {e}")
        publisher.disconnect()
        if downloader:
            downloader.cleanup()
        print("[pipeline] Done without retrying fill.")
        return
    except CDPError as e:
        print(f"Error during form fill: {e}", file=sys.stderr)
        if downloader:
            downloader.cleanup()
        sys.exit(2)

    # --- Step 5: Handoff by default; publish only with explicit authorization ---
    should_publish = should_execute_direct_publish(publish_mode)
    if not should_publish:
        print("PUBLISH_MODE: HANDOFF")
        print("[pipeline] Handoff ready. Leaving the page open without monitoring or clicking publish.")

    if should_publish:
        print("PUBLISH_MODE: DIRECT_PUBLISH")
        print("[pipeline] Step 5: Clicking publish button...")
        try:
            note_link = execute_direct_publish(
                publisher,
                is_video_mode=is_video_mode,
            )
            print("PUBLISH_STATUS: CLICKED_AWAITING_TERMINAL_CHECK")
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
