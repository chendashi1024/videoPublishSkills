"""新旧小红书封面编辑器的 DOM 定位；不把页面删除视为保存成功。"""

COVER_DOM = r"""
const clean = el => String(el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
};
const rect = el => {
    if (!visible(el)) return null;
    const r = el.getBoundingClientRect();
    return {x:r.x, y:r.y, w:r.width, h:r.height};
};
const enabled = el => visible(el) && !el.disabled && el.getAttribute('aria-disabled') !== 'true'
    && !/(?:disabled|loading)/.test(String(el.className || ''));
const unique = items => items.length === 1 ? items[0] : null;
const coverEditor = () => {
    const roots = new Set();
    for (const input of document.querySelectorAll('input[aria-label="上传封面图片"]')) {
        for (let parent = input.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
            if (visible(parent) && [...parent.querySelectorAll('button')].some(b=>['完成','确定'].includes(clean(b)) || /d-button-loading/.test(b.className))) {
                roots.add(parent); break;
            }
        }
    }
    if (roots.size) return unique([...roots]);
    return unique([...document.querySelectorAll('.cover-modal, .d-modal')].filter(el =>
        visible(el) && el.querySelector('.crop-ratio-item, .ratio-select, input[type="file"][accept*="image"]')));
};
const modal = coverEditor();
const exact = (root, selector, text) => {
    const matches = [...root.querySelectorAll(selector)].filter(el=>visible(el) && clean(el)===text);
    return unique(matches.filter(el=>!matches.some(other=>other!==el && el.contains(other))));
};
const confirm = modal ? unique([...modal.querySelectorAll('button')].filter(b=>enabled(b) && ['完成','确定'].includes(clean(b)))) : null;
"""


def cover_script(body: str) -> str:
    return "(() => {" + COVER_DOM + body + "})()"
