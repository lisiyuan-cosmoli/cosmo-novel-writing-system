#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目内容排除表。

影子验证、扫描、备份和发布检查都从这里读取。运行产物与历史版本不参与
当前状态判断，也不会再次进入备份。
"""
import os

目录 = (
    '_快照', '_备份', '_候选', '_to_delete', '_读取包', '.novel',
    '__pycache__', '.pytest_cache', '.git', '.hg', '.svn', '.idea', '.vscode',
)
子路径 = ('06_归档/_候选存根',)

def 跳过(rel):
    """rel 为相对项目根的路径。返回 True 表示这不是项目内容，任何检查都不该看它。"""
    rel = rel.replace(os.sep, '/')
    while rel.startswith('./'):
        rel = rel[2:]
    rel = rel.lstrip('/')
    parts = rel.split('/')
    if any(p in 目录 for p in parts): return True
    return any(rel.startswith(s + '/') or rel == s for s in 子路径)
