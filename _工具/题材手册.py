#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调阅题材手册。

为什么手册不进读取包
    每章都带着四份完整手册，是拿最贵的预算去装一份大部分章节用不到的资料。
    但"不进包"不能变成"没人读"——v1 的题材指导就是这么消失的：它在文档里，
    而逐章写作只会读取已装配的上下文。

    所以分两层：**每章必须执行的检查**蒸馏进 `02_检查层/插件/*.md`，
    作为 CONTROL 跟包走；**判断依据与完整指导**留在手册里，用这条命令按需调阅。
    检查文件末尾都指向对应手册，吃不准时一条命令就能拿到。

用法
    python3 novel.py guide              列出本项目可用的手册
    python3 novel.py guide suspense     打印某一份
"""
from __future__ import print_function

import argparse
import os
import sys

import v2_core as core


# 逐章检查文件进读取包，必须有上限：四个插件同时启用时它们会一起占预算。
# 手册没有上限——它不进包。
检查上限 = 1200


def 手册路径(project, plugin_id):
    名 = core.SUPPORTED_PLUGINS.get(plugin_id)
    if not 名:
        return None, None
    rel = os.path.join("04_题材插件", "%s.md" % 名).replace(os.sep, "/")
    return rel, os.path.join(project, rel)


def 检查文件(project, plugin_id):
    rel = "02_检查层/插件/%s.md" % plugin_id
    return rel, os.path.join(project, rel)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="guide", description="调阅题材手册")
    parser.add_argument("plugin", nargs="?")
    parser.add_argument("project", nargs="?", default=".")
    args = parser.parse_args(argv)
    # 只给一个位置参数且不是插件 ID 时，那是项目路径
    if args.plugin and args.plugin not in core.SUPPORTED_PLUGINS and args.project == ".":
        args.project, args.plugin = args.plugin, None

    project = core.resolve_project(args.project)
    data = core.load_project(project, required=False) or {}
    启用 = set(data.get("enabled_plugins", []))

    if not args.plugin:
        print("题材手册（不进读取包，按需调阅）")
        for pid, 名 in sorted(core.SUPPORTED_PLUGINS.items()):
            rel, path = 手册路径(project, pid)
            标 = "已启用" if pid in 启用 else "未启用"
            有 = "有" if os.path.isfile(path) else "缺失"
            print("  %-12s %-6s %-4s %s" % (pid, 标, 有, rel))
        print()
        print("每章要执行的检查在 02_检查层/插件/<插件>.md，跟着正式读取包走，不用手动调阅。")
        print("手册是判断依据与完整指导，写不下去或吃不准时才看：")
        print("  python3 novel.py guide suspense")
        return 0

    if args.plugin not in core.SUPPORTED_PLUGINS:
        print("✗ 未知插件 %s。可用：%s"
              % (args.plugin, "、".join(sorted(core.SUPPORTED_PLUGINS))))
        return 2
    rel, path = 手册路径(project, args.plugin)
    text = core.read_text(path)
    if text is None:
        print("✗ 读不到 %s。从新版母版 sync 补入。" % rel)
        return 1
    if args.plugin not in 启用:
        print("△ 插件 %s 当前未启用。手册可以读，但它描述的表和检查还不在这个项目里。"
              % args.plugin)
        print()
    print(text.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
