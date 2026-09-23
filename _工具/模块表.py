#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目启用的题材模块。

v2 以 project.json 为唯一判据。没有项目清单的旧项目才回退到项目配置，
方便迁移前做只读诊断。
"""
import io, json, os, re

# 运行表 → 模块名。加新插件时只改这一张表。
表到模块 = {
    '05b': '悬疑',
    '05c': '言情',
    '05d': '科幻奇幻',
    '05e': '网文',
}
插件定义 = {
    'suspense': {
        '模块': '悬疑',
        '运行表': ['01_运行层/05b_线索兑现表.md'],
        '设定': ['00_设定层/插件/suspense.md'],
        '检查': ['02_检查层/插件/suspense.md'],
    },
    'romance': {
        '模块': '言情',
        '运行表': ['01_运行层/05c_情感节拍表.md'],
        '设定': ['00_设定层/插件/romance.md'],
        '检查': ['02_检查层/插件/romance.md'],
    },
    'speculative': {
        '模块': '科幻奇幻',
        '运行表': ['01_运行层/05d_规则使用记录.md'],
        '设定': ['00_设定层/插件/speculative.md'],
        '检查': ['02_检查层/插件/speculative.md'],
    },
    'serial': {
        '模块': '网文',
        '运行表': ['01_运行层/05e_钩子与爽点表.md'],
        '设定': ['00_设定层/插件/serial.md'],
        '检查': ['02_检查层/插件/serial.md'],
    },
}
# 模块 → 它专属的归档账本（迁出后仍被工具读取的那些）
模块归档 = {
    '悬疑': [('06_归档/线索归档.md', '已揭晓线索（图谱解析器与闸门都要读它）')],
}

def _读(P, rel):
    try:
        return io.open(os.path.join(P, rel), encoding='utf-8').read()
    except Exception:
        return ''

def 启用(P):
    """返回 (已启用模块集合, 已启用运行表相对路径集合)。

    ⚠️ 读不到项目配置时返回空集，**调用方必须把"读不到"当成错误报出来**，
    不能当成"没启用所以跳过"——那正是本系统被违反最多的那条。
    """
    清单 = _读(P, 'project.json')
    if 清单:
        try:
            data = json.loads(清单)
            ids = set(data.get('enabled_plugins', []))
            模块 = {插件定义[x]['模块'] for x in ids if x in 插件定义}
            表 = {path for x in ids if x in 插件定义 for path in 插件定义[x]['运行表']}
            return 模块, 表
        except (TypeError, ValueError):
            return set(), set()
    配置 = _读(P, '项目配置.md')
    模块, 表 = set(), set()
    for ln in 配置.split('\n'):
        if not re.match(r'\s*-\s*\[x\]', ln, re.I):
            continue
        m = re.search(r'`?(01_运行层/(05[a-z])_[^`\s]+\.md)`?', ln)
        if not m:
            continue
        表.add(m.group(1))
        名 = 表到模块.get(m.group(2))
        if 名:
            模块.add(名)
    return 模块, 表

def 启用详情(P):
    """返回启用插件需要注入的设定、运行表和检查文件。"""
    清单 = _读(P, 'project.json')
    ids = []
    if 清单:
        try:
            ids = json.loads(清单).get('enabled_plugins', [])
        except (TypeError, ValueError):
            ids = []
    if not ids:
        模块, _ = 启用(P)
        ids = [pid for pid, detail in 插件定义.items() if detail['模块'] in 模块]
    out = []
    for pid in ids:
        detail = 插件定义.get(pid)
        if not detail:
            continue
        out.append((pid, detail))
    return out

def 配置可读(P):
    清单 = _读(P, 'project.json')
    if 清单:
        try:
            data = json.loads(清单)
            return data.get('format') == 'novel-project' and isinstance(data.get('enabled_plugins'), list)
        except (TypeError, ValueError):
            return False
    return bool(_读(P, '项目配置.md').strip())

def 需要的归档(P):
    """已启用模块各自要求存在的归档账本 [(相对路径, 为什么)]。未启用的模块一份都不要求。"""
    模块, _ = 启用(P)
    out = []
    for m in sorted(模块):
        out.extend(模块归档.get(m, []))
    return out
