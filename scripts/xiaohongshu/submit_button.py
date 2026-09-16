"""通过 CDP 穿透封闭 shadow root，精确点击小红书主提交按钮一次。"""
from core.cdp_client import CDPError


def _walk(node):
    yield node
    for child in node.get("children", []) + node.get("shadowRoots", []):
        yield from _walk(child)


def _text(node):
    return " ".join("".join(
        item.get("nodeValue", "") for item in _walk(node)
        if item.get("nodeName") == "#text"
    ).split())


def _inspect(cdp, node_id, expected):
    obj = cdp.send("DOM.resolveNode", {"nodeId": node_id})["object"]["objectId"]
    try:
        result = cdp.send("Runtime.callFunctionOn", {
            "objectId": obj, "returnByValue": True,
            "arguments": [{"value": expected}],
            "functionDeclaration": r"""function(expected) {
                const r = this.getBoundingClientRect(), s = getComputedStyle(this);
                if (!r.width || !r.height || s.display==='none' || s.visibility==='hidden') return null;
                const root = this.getRootNode();
                const host = this.matches('xhs-publish-btn') ? this : root.host;
                const disabled = this.disabled || this.getAttribute('aria-disabled')==='true'
                    || /disabled|loading/.test(String(this.className || ''))
                    || (host && (host.getAttribute('submit-disabled')!=='false'
                        || host.getAttribute('submit-loading')!=='false'));
                const text = String(host?.getAttribute('submit-text') || this.textContent || '').trim();
                const checkbox = document.querySelector('.post-time-wrapper input[type="checkbox"]');
                const scheduled = checkbox ? checkbox.checked :
                    document.querySelector('.post-time-wrapper [role="switch"]')?.getAttribute('aria-checked')==='true';
                const mode = scheduled ? '定时发布' : '发布';
                if (host && this!==host && String(this.textContent || '').replace(/\s+/g,' ').trim()!==text) return null;
                if (disabled || text!==mode || (expected && text!==expected)) return null;
                return {x:r.x,y:r.y,w:r.width,h:r.height,text};
            }""",
        })
        if result.get("exceptionDetails"):
            raise CDPError("小红书提交按钮状态读取失败")
        return result.get("result", {}).get("value")
    finally:
        cdp.send("Runtime.releaseObject", {"objectId": obj})


def click_submit_once(cdp):
    tree = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})["root"]
    hosts = [node for node in _walk(tree) if node.get("nodeName", "").lower() == "xhs-publish-btn"]
    if hosts:
        if len(hosts) != 1:
            raise CDPError("小红书提交组件不唯一，停止发布")
        host = hosts[0]
        state = _inspect(cdp, host["nodeId"], None)
        if not state or state["text"] not in ("发布", "定时发布"):
            raise CDPError("小红书提交组件禁用、加载中或状态未知")
        expected = state["text"]
        scope = host
    else:
        scheduled = cdp.evaluate("""(() => {
            const checkbox=document.querySelector('.post-time-wrapper input[type=checkbox]');
            return checkbox ? checkbox.checked : document.querySelector('.post-time-wrapper [role=switch]')?.getAttribute('aria-checked')==='true';
        })()""")
        expected = "定时发布" if scheduled else "发布"
        scope = tree
    candidates = []
    for node in _walk(scope):
        attrs = dict(zip(node.get("attributes", [])[::2], node.get("attributes", [])[1::2]))
        if (node.get("nodeName") == "BUTTON" or attrs.get("role") == "button") and _text(node) == expected:
            if _inspect(cdp, node["nodeId"], expected):
                candidates.append(node)
    if len(candidates) != 1:
        raise CDPError(f"小红书可用的「{expected}」按钮不唯一或不存在，停止发布")
    node_id = candidates[0]["nodeId"]
    cdp.send("DOM.scrollIntoViewIfNeeded", {"nodeId": node_id})
    rect = _inspect(cdp, node_id, expected)
    if not rect:
        raise CDPError("小红书提交按钮状态已变化，停止发布")
    x, y = rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2
    # 唯一最终点击：不点同时包含“暂存离开”的宿主中心，不重试。
    for event in ("mouseMoved", "mousePressed", "mouseReleased"):
        cdp.send("Input.dispatchMouseEvent", {
            "type": event, "x": x, "y": y, "button": "left", "clickCount": 1,
        })
