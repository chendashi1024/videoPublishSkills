"""
快手内容工具

提供快手平台特定的内容处理功能
"""


def extract_topics(content: str) -> tuple[str, list[str]]:
    """
    从正文中提取话题标签

    Args:
        content: 正文内容

    Returns:
        tuple: (去除话题后的正文, 话题列表)
    """
    # 快手话题格式：#话题
    import re

    # 提取所有 #话题
    topics = re.findall(r'#([^\s#]+)', content)

    # 移除话题标签，保留正文
    clean_content = re.sub(r'#[^\s#]+', '', content).strip()

    return clean_content, topics


def validate_title(title: str) -> tuple[bool, str]:
    """
    验证标题是否符合快手要求

    Args:
        title: 标题

    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not title or not title.strip():
        return False, "标题不能为空"

    # 快手标题长度限制（待确认）
    if len(title) > 50:
        return False, f"标题过长（{len(title)} 字符），建议不超过 50 字符"

    return True, ""


def validate_content(content: str) -> tuple[bool, str]:
    """
    验证正文是否符合快手要求

    Args:
        content: 正文

    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not content or not content.strip():
        return False, "正文不能为空"

    # 快手正文长度限制（待确认）
    if len(content) > 2000:
        return False, f"正文过长（{len(content)} 字符），建议不超过 2000 字符"

    return True, ""
