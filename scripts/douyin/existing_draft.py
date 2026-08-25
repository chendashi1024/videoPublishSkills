"""抖音已填稿编辑页的安全续发。

这条路径只处理已经上传并填好的 `/content/post/video` 页：
先回读标题和正文，再精确点击表单底部的发布按钮一次。
它不上传媒体、不重填字段、不重复设置封面或话题。
"""

from __future__ import annotations

import json
import time

from core.cdp_client import CDPError


DOUYIN_EDITOR_URL_PREFIX = (
    "https://creator.douyin.com/creator-micro/content/post/video"
)
DOUYIN_SUBMITTED_URL_PREFIX = (
    "https://creator.douyin.com/creator-micro/content/manage?enter_from=publish"
)


class ExistingDraftPublishOutcomeUnknown(CDPError):
    """已点击一次，但未观测到可信的提交结果。"""


def _normalize_text(value: str) -> str:
    """忽略平台零宽字符与空白展示差异。"""
    return "".join(
        str(value or "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .split()
    )


def is_douyin_editor_url(url: str) -> bool:
    """仅接受抖音视频填稿编辑页。"""
    return str(url or "").startswith(DOUYIN_EDITOR_URL_PREFIX)


def read_existing_draft(cdp) -> dict:
    """只读当前页的标题、正文和发布按钮。"""
    snapshot = cdp.evaluate(r"""
        (() => {
            const clean = (value) => String(value || '').trim();
            const visible = (el) => {
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const inputs = Array.from(document.querySelectorAll('input'))
                .filter(visible)
                .map((el) => clean(el.value))
                .filter(Boolean);
            const editors = Array.from(
                document.querySelectorAll('[contenteditable="true"]')
            )
                .filter(visible)
                .map((el) => clean(el.innerText || el.textContent))
                .filter(Boolean)
                .sort((a, b) => b.length - a.length);
            const buttons = Array.from(document.querySelectorAll('button'))
                .filter((button) => {
                    const text = clean(button.innerText || button.textContent);
                    return text === '发布'
                        && visible(button)
                        && !button.disabled
                        && !String(button.className).includes('header-button');
                })
                .map((button) => {
                    const rect = button.getBoundingClientRect();
                    return {
                        text: clean(button.innerText || button.textContent),
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                    };
                });
            return {
                url: location.href,
                inputs,
                editorText: editors[0] || '',
                publishButtons: buttons,
            };
        })()
    """)
    return snapshot if isinstance(snapshot, dict) else {}


def verify_existing_draft(cdp, *, expected_title: str, expected_content: str) -> dict:
    """回读已填稿页；任一关键字段不匹配就停止。"""
    snapshot = read_existing_draft(cdp)
    url = str(snapshot.get("url") or "")
    if not is_douyin_editor_url(url):
        raise CDPError(f"当前不是抖音已填稿编辑页：{url}")

    expected_title_normalized = _normalize_text(expected_title)
    observed_titles = {
        _normalize_text(value) for value in snapshot.get("inputs", [])
    }
    if expected_title_normalized not in observed_titles:
        raise CDPError("已填稿页标题与本次发布标题不匹配，已停止")

    expected_content_normalized = _normalize_text(expected_content)
    observed_content_normalized = _normalize_text(snapshot.get("editorText", ""))
    if not expected_content_normalized or (
        expected_content_normalized not in observed_content_normalized
    ):
        raise CDPError("已填稿页正文与本次发布正文不匹配，已停止")

    buttons = snapshot.get("publishButtons", [])
    if len(buttons) != 1:
        raise CDPError(
            f"已填稿页可用的表单发布按钮数量异常：{len(buttons)}"
        )
    return snapshot


def click_existing_draft_once(
    cdp,
    *,
    expected_title: str,
    expected_content: str,
    timeout_seconds: float = 12.0,
) -> dict:
    """验证后只点击表单发布按钮一次，再观测提交结果。"""
    snapshot = verify_existing_draft(
        cdp,
        expected_title=expected_title,
        expected_content=expected_content,
    )
    button = snapshot["publishButtons"][0]
    x = button["x"] + button["width"] / 2
    y = button["y"] + button["height"] / 2
    cdp.send(
        "Input.dispatchMouseEvent",
        {"type": "mouseMoved", "x": x, "y": y},
    )
    for event_type in ("mousePressed", "mouseReleased"):
        cdp.send(
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )

    deadline = time.monotonic() + timeout_seconds
    last_observed = {"url": snapshot.get("url", ""), "successText": False}
    while time.monotonic() < deadline:
        time.sleep(0.4)
        observed = cdp.evaluate(r"""
            (() => {
                const text = document.body ? document.body.innerText : '';
                return {
                    url: location.href,
                    successText: text.includes('发布成功'),
                };
            })()
        """)
        if isinstance(observed, dict):
            last_observed = observed
        if str(last_observed.get("url") or "").startswith(
            DOUYIN_SUBMITTED_URL_PREFIX
        ) or bool(last_observed.get("successText")):
            return {
                "clicked": True,
                "submitted": True,
                "observed": last_observed,
            }

    raise ExistingDraftPublishOutcomeUnknown(
        "已点击表单发布按钮一次，但未观测到可信提交结果；禁止重试。"
    )


def format_submit_result(result: dict) -> str:
    """为日志生成稳定 JSON，不包含草稿正文。"""
    return json.dumps(result, ensure_ascii=False, sort_keys=True)
