"""文本处理工具函数"""
import re


def normalize_speaker_name(name):
    """智能提取核心角色名，去除状态信息

    去除规则：
    1. 去除 BOM 字符
    2. 以第一个空格为截断点，取前面部分作为角色名
    3. 去除尾部的英文字母、数字和空格（处理紧贴的状态如"千夏hp"）

    Args:
        name: 原始角色名（可能包含状态信息）

    Returns:
        str: 归一化后的核心角色名

    Examples:
        >>> normalize_speaker_name("博雅 ap5 先攻90 铠甲耐久1354/1404")
        '博雅'
        >>> normalize_speaker_name("千夏hp 356/166 ap6 先攻")
        '千夏'
        >>> normalize_speaker_name("﻿艾琳娜•爱德华")
        '艾琳娜•爱德华'
    """
    if not name:
        return name

    # 去除 BOM 字符
    name = name.replace('\ufeff', '')
    original = name.strip()

    # 以第一个空格为截断点
    space_index = name.find(' ')
    if space_index != -1:
        name = name[:space_index]
    # 去除尾部的英文字母和数字（处理如"千夏hp"的情况）
    # 从后往前找，去除连续的英文字母和数字
    name = re.sub(r'[a-zA-Z0-9]+$', '', name)

    # 去除尾部空格
    name = name.rstrip()

    # 归一化后为空（典型：纯英文名 "Azure Cruiser" 被剥成空），回退使用原名
    if not name:
        return original

    return name


def count_char_weight(text):
    """计算文本的加权字数，汉字计4，其他字符计1"""
    weight = 0
    for char in text:
        if '\u4e00' <= char <= '\u9fff':  # 判断是否为汉字
            weight += 1
        else:
            weight += 1
    return weight


def get_display_width(s):
    """计算字符串在终端中的显示宽度（汉字占2宽度）"""
    width = 0
    for char in s:
        if '\u4e00' <= char <= '\u9fff':  # 判断是否为汉字
            width += 2
        else:
            width += 1
    return width


def pad_string(s, width, align='left'):
    """填充字符串到指定显示宽度"""
    s_str = str(s)
    display_width = get_display_width(s_str)

    # 如果字符串显示宽度超过列宽，截断并添加省略号
    if display_width > width:
        # 逐个字符累加直到接近限制宽度
        truncated = ""
        curr_width = 0
        for char in s_str:
            char_width = 2 if '\u4e00' <= char <= '\u9fff' else 1
            if curr_width + char_width + 3 <= width:  # 为省略号预留宽度
                truncated += char
                curr_width += char_width
            else:
                break
        s_str = truncated + "..."
        display_width = get_display_width(s_str)

    if align == 'left':
        return s_str + ' ' * (width - display_width)
    else:  # right align
        return ' ' * (width - display_width) + s_str
