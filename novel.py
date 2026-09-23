#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COSMO 小说创作系统 v6 入口。运行 python3 novel.py --help 查看命令。"""
import importlib.util
import os
import sys


def main():
    tool_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_工具")
    if tool_dir not in sys.path:
        sys.path.insert(0, tool_dir)
    path = os.path.join(tool_dir, "novel.py")
    spec = importlib.util.spec_from_file_location("novel_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
