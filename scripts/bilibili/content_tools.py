"""
B站内容工具

提供 B站平台特定的内容处理功能
"""


def extract_tags(content: str) -> tuple[str, list[str]]:
    """
    从正文中提取标签

    Args:
        content: 正文内容

    Returns:
        tuple: (去除标签后的正文, 标签列表)
    """
    # B站标签格式：通常在正文末尾，用逗号或空格分隔
    # 这里简单处理，实际可能需要更复杂的逻辑
    import re

    # 提取最后一行的标签（如果以 # 开头）
    lines = content.strip().split('\n')
    tags = []
    clean_lines = lines.copy()

    if lines and lines[-1].strip().startswith('#'):
        tag_line = lines[-1].strip()
        # 提取所有 #标签
        tags = re.findall(r'#([^\s#]+)', tag_line)
        clean_lines = lines[:-1]

    clean_content = '\n'.join(clean_lines).strip()
    return clean_content, tags


def validate_title(title: str) -> tuple[bool, str]:
    """
    验证标题���否符合 B站要求

    Args:
        title: 标题

    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not title or not title.strip():
        return False, "标题不能为空"

    # B站标题长度限制：80 字符
    if len(title) > 80:
        return False, f"标题过长（{len(title)} 字符），不能超过 80 字符"

    return True, ""


def validate_content(content: str) -> tuple[bool, str]:
    """
    验证简介是否符合 B站要求

    Args:
        content: 简介

    Returns:
        tuple: (是否有效, 错误信息)
    """
    # B站简介长度限制：2000 字符
    if len(content) > 2000:
        return False, f"简介过长（{len(content)} 字符），不能超过 2000 字符"

    return True, ""
