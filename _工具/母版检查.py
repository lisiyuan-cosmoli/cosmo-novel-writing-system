#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查母版结构、发布清单与项目数据残留。"""
from __future__ import print_function

import ast
import io
import json
import os
import re


def _read(root, rel, default=""):
    try:
        with io.open(os.path.join(root, rel), "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        return default


def _safe_relative(rel):
    if (not isinstance(rel, str) or not rel or os.path.isabs(rel) or
            any(ord(char) < 32 or ord(char) == 127 for char in rel)):
        return False
    norm = os.path.normpath(rel).replace(os.sep, "/")
    return norm == rel.replace(os.sep, "/") and norm != ".." and not norm.startswith("../")


def _deny_words(root):
    return [line.strip() for line in _read(root, "_工具/母版禁词.txt").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def _effective_text_files(root):
    excluded = {".git", ".hg", ".svn", ".novel", "_候选", "_读取包", "_快照",
                "_备份", "_to_delete", "__pycache__", ".pytest_cache"}
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in excluded]
        for name in files:
            if name == "母版禁词.txt" or not name.endswith((".md", ".txt", ".py", ".json", ".sh")):
                continue
            path = os.path.join(current, name)
            yield os.path.relpath(path, root).replace(os.sep, "/"), path


def 检查(root):
    root = os.path.abspath(root)
    errors, warnings, passed = [], [], []

    def check(name, condition, detail=""):
        (passed if condition else errors).append((name, detail or "无"))

    check("母版标记存在", os.path.isfile(os.path.join(root, "_工具", "我是母版.txt")))

    # 逐章检查文件跟着正式读取包进每一章，四个插件同时启用会一起占预算。
    # 手册没有上限（它不进包），检查文件必须有。
    超限 = []
    for name in sorted(os.listdir(os.path.join(root, "04_题材插件", "_包"))
                       if os.path.isdir(os.path.join(root, "04_题材插件", "_包")) else []):
        pattern = os.path.join(root, "04_题材插件", "_包", name,
                               "templates", "02_检查层", "插件")
        if not os.path.isdir(pattern):
            continue
        for f in sorted(os.listdir(pattern)):
            text = _read(root, os.path.relpath(os.path.join(pattern, f), root))
            if len(text) > 1200:
                超限.append("%s %d 字符" % (f, len(text)))
    check("插件逐章检查文件不超过 1200 字符（它们进每一份读取包）",
          not 超限, "、".join(超限))
    check("母版根目录没有 project.json", not os.path.exists(os.path.join(root, "project.json")))

    manifest_path = os.path.join(root, "system-manifest.json")
    manifest = None
    try:
        manifest = json.loads(_read(root, "system-manifest.json"))
    except (TypeError, ValueError) as exc:
        errors.append(("发布清单可解析", str(exc)))
    if manifest:
        check("发布清单格式正确", manifest.get("format") == "novel-system-release")
        check("发布清单结构版本为 2", manifest.get("schema_version") == 2)
        core_version = re.search(r'^SYSTEM_VERSION\s*=\s*"([^"]+)"',
                                 _read(root, "_工具/v2_core.py"), re.M)
        check("发布清单与公共内核版本一致",
              bool(core_version) and manifest.get("system_version") == core_version.group(1),
              "manifest %s / core %s" %
              (manifest.get("system_version"), core_version.group(1) if core_version else "取不到"))
        for key in ("template_required_files", "project_required_files", "sync_files"):
            rows = manifest.get(key)
            check("发布清单 %s 是无重复路径数组" % key,
                  isinstance(rows, list) and len(rows) == len(set(rows or []))
                  and all(_safe_relative(x) for x in (rows or [])))
        required = manifest.get("template_required_files", [])
        missing = [rel for rel in required if not os.path.isfile(os.path.join(root, rel))]
        check("母版必需文件齐全", not missing, "缺 " + "、".join(missing))
        sync = manifest.get("sync_files", [])
        missing_sync = [rel for rel in sync if not os.path.isfile(os.path.join(root, rel))]
        check("同步源文件齐全", not missing_sync, "缺 " + "、".join(missing_sync))
        owned = [rel for rel in sync if rel in {
            "项目配置.md", "00_设定层/01_固定设定.md", "00_设定层/02_风格样本.md",
            "00_设定层/03_分章大纲.md", "01_运行层/04_状态快照.md",
            "01_运行层/05_伏笔表.md", "01_运行层/06_事实记录.md",
            "01_运行层/06b_事实记录_已归档段.md", "06_归档/流程审计.md",
            "_工具/专名表.txt", "_工具/允许重复.txt"
        }]
        check("同步清单不覆盖项目数据", not owned, "误列 " + "、".join(owned))

    # .git 不在这张表里：它是**版本控制**，不是运行产物。母版开源之后本来就该
    # 在版本控制下。R01 担心的是"整份复制把母版的历史一起带进新项目"，那件事由
    # 新建项目.py 的排除目录挡住，并且有专门的行为测试证明它不会传播——
    # 靠"禁止母版有 .git"来挡，等于用一条错误的前提换一份虚假的安心。
    residue_dirs = [name for name in (".novel", "_候选", "_读取包", "_快照",
                                      "_备份", "_to_delete", "__pycache__")
                    if os.path.exists(os.path.join(root, name))]
    check("母版根目录无运行残留", not residue_dirs, "发现 " + "、".join(residue_dirs))
    check("母版没有作品复盘或运行问题记录", not any(os.path.exists(os.path.join(root, rel)) for rel in
          ('06_归档/运行问题.jsonl', '06_归档/结构复盘.md', '06_归档/开书研究.md', '06_归档/文风推荐.md')))
    check("候选说明残留已移除", not os.path.exists(os.path.join(root, "_候选_README.md")))

    snapshot = _read(root, "01_运行层/04_状态快照.md")
    check("空白快照使用 K0000", "更新至 K0000" in snapshot)
    facts = _read(root, "01_运行层/06_事实记录.md") + _read(root, "01_运行层/06b_事实记录_已归档段.md")
    check("空白事实记录没有章节数据", not re.search(r"^###\s*K\d{4}", facts, re.M))
    audit = _read(root, "06_归档/流程审计.md")
    check("空白流程审计没有示例章节", not re.search(r"^\|\s*K\d{4}\s*\|", audit, re.M))

    syntax_errors = []
    tool_dir = os.path.join(root, "_工具")
    if os.path.isdir(tool_dir):
        for name in sorted(os.listdir(tool_dir)):
            if not name.endswith(".py"):
                continue
            try:
                ast.parse(_read(root, "_工具/" + name), filename=name)
            except SyntaxError as exc:
                syntax_errors.append("%s:%s" % (name, exc.lineno))
    check("Python 工具语法正确", not syntax_errors, "、".join(syntax_errors))

    words = _deny_words(root)
    contaminated = []
    if words:
        for rel, path in _effective_text_files(root):
            try:
                text = io.open(path, "r", encoding="utf-8").read()
            except (OSError, UnicodeError):
                continue
            hits = [word for word in words if word in text]
            if hits:
                contaminated.append("%s 含 %s" % (rel, "、".join(hits[:4])))
    check("母版禁词没有进入有效文件", not contaminated, "；".join(contaminated[:8]))
    if not words:
        warnings.append(("母版禁词表当前为空", "这是干净母版的合法状态。迁移具体旧项目时可临时填入该项目专名做扫描"))

    print("=" * 72)
    print("母版检查")
    print("=" * 72)
    for name, detail in errors:
        print("✗ 错误  %s  %s" % (name, detail))
    for name, detail in warnings:
        print("△ 注意  %s  %s" % (name, detail))
    for name, _ in passed:
        print("✓ %s" % name)
    print("=" * 72)
    print("错误 %d ／ 注意 %d ／ 通过 %d" % (len(errors), len(warnings), len(passed)))
    return 1 if errors else 0
