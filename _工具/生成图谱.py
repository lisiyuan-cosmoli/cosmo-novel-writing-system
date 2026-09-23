#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成题材中立的项目状态图谱。"""
from __future__ import print_function

import html
import importlib.util
import json
import os
import sys


TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

import v2_core as core


def _parser():
    path = os.path.join(TOOL_DIR, "图谱_解析.py")
    spec = importlib.util.spec_from_file_location("novel_graph_parser", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def e(value):
    return html.escape(str(value or ""))


def _title(project):
    manifest = core.load_json(os.path.join(project, "project.json"), {}) or {}
    return manifest.get("title") or os.path.basename(os.path.abspath(project))


def _plugins(project):
    manifest = core.load_json(os.path.join(project, "project.json"), {}) or {}
    return manifest.get("enabled_plugins", [])


def _chapter_rows(data):
    rows = []
    for item in data["chapters"]:
        rows.append(
            "<tr><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td>"
            "<td>%s</td><td><span class='tag'>%s</span></td></tr>" %
            (e(item["no"]), e(item["id"]), e(item["pov"]), e(item["what"]),
             e(item["leaves"]), e(item["status"])))
    return "".join(rows) or "<tr><td colspan='6' class='empty'>尚无章节</td></tr>"


def _tracked_rows(data):
    rows = []
    for item in sorted(data["tracked"],
                       key=lambda value: (value["born"] or 10 ** 6,
                                          value["land"] or 10 ** 6, value["id"])):
        rows.append(
            "<tr><td><code>%s</code></td><td>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td><td><span class='tag'>%s</span></td></tr>" %
            (e(item["id"]), e(item["kind"]), e(item["text"]),
             e(item["born"] or "—"), e(item["land"] or "—"), e(item["status"])))
    return "".join(rows) or "<tr><td colspan='6' class='empty'>当前没有追踪项</td></tr>"


def _knowledge(data):
    knowledge = data["know"]
    if not knowledge["cols"]:
        return "<p class='empty'>知情范围表尚未初始化</p>"
    head = "".join("<th>%s</th>" % e(value) for value in knowledge["cols"])
    rows = []
    for row in knowledge["rows"]:
        if not any(str(value).strip() for value in row):
            continue
        rows.append("<tr>%s</tr>" % "".join("<td>%s</td>" % e(value) for value in row))
    body = "".join(rows) or "<tr><td colspan='%d' class='empty'>暂无数据</td></tr>" % len(knowledge["cols"])
    return "<div class='scroll'><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>" % (head, body)


def _dates(data):
    if not data["dates"]:
        return "<p class='empty'>项目没有使用可解析的精确公历日期。自然语言时间仍可正常使用。</p>"
    rows = []
    for kid, date in sorted(data["dates"].items(), key=lambda item: item[1]):
        rows.append("<tr><td>%s</td><td><code>%s</code></td></tr>" % (e(date), e(kid)))
    return "<table><thead><tr><th>日期</th><th>永久 ID</th></tr></thead><tbody>%s</tbody></table>" % "".join(rows)


def render(project, data):
    plugins = _plugins(project)
    gaps = "".join("<li>%s</li>" % e(item) for item in data["gaps"])
    gap_block = (
        "<section class='warning'><h2>账本缺口</h2><ul>%s</ul></section>" % gaps
        if gaps else "")
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s　项目图谱</title>
<style>
:root{--bg:#f5f3ee;--paper:#fffdfa;--ink:#24231f;--muted:#716d63;--line:#ddd7cc;--accent:#2d5f5d;--warn:#9a3e2d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC",sans-serif}
main{max-width:1180px;margin:0 auto;padding:42px 24px 80px}header{display:flex;gap:24px;align-items:flex-end;justify-content:space-between;margin-bottom:28px}
h1{font:700 34px/1.2 Georgia,"Songti SC",serif;margin:0}h2{font-size:18px;margin:0 0 14px}p{margin:6px 0}.muted,.empty{color:var(--muted)}
.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}.metric,section{background:var(--paper);border:1px solid var(--line);border-radius:12px}
.metric{padding:16px}.metric b{display:block;font-size:28px;color:var(--accent)}section{padding:22px;margin:14px 0}.warning{border-color:#d9a99f;color:var(--warn)}
.scroll{overflow:auto}table{width:100%%;border-collapse:collapse}th,td{padding:10px 11px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);white-space:nowrap}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.tag{display:inline-block;padding:1px 8px;border-radius:99px;background:#e6efed;color:var(--accent);white-space:nowrap}
ul{margin:0;padding-left:20px}@media(max-width:760px){header{display:block}.summary{grid-template-columns:repeat(2,1fr)}main{padding:24px 14px}}
</style>
</head>
<body><main>
<header><div><p class="muted">COSMO 小说创作系统 v3</p><h1>%s</h1></div><p class="muted">已启用插件　%s</p></header>
<div class="summary">
<div class="metric"><span>规划章数</span><b>%d</b></div>
<div class="metric"><span>已定稿</span><b>%d</b></div>
<div class="metric"><span>活动追踪项</span><b>%d</b></div>
<div class="metric"><span>账本缺口</span><b>%d</b></div>
</div>
%s
<section><h2>章节状态</h2><div class="scroll"><table><thead><tr><th>章号</th><th>永久 ID</th><th>视角</th><th>主要行动</th><th>章末变化</th><th>状态</th></tr></thead><tbody>%s</tbody></table></div></section>
<section><h2>承诺与追踪项</h2><div class="scroll"><table><thead><tr><th>ID</th><th>类型</th><th>内容</th><th>出现</th><th>计划落点</th><th>状态</th></tr></thead><tbody>%s</tbody></table></div></section>
<section><h2>知情范围</h2>%s</section>
<section><h2>精确日期</h2>%s</section>
<p class="muted">本页由账本生成。修改账本后重新运行生成工具。</p>
</main></body></html>""" % (
        e(_title(project)), e(_title(project)), e("、".join(plugins) or "无"),
        data["total"], data["done"], len(data["active_tracked"]), len(data["gaps"]),
        gap_block, _chapter_rows(data), _tracked_rows(data), _knowledge(data), _dates(data))


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    project = os.path.abspath(argv[0] if argv else ".")
    if not os.path.isdir(project):
        print("✗ 项目目录不存在 %s" % project)
        return 2
    try:
        data = _parser().parse(project)
        target = os.path.join(project, "图谱.html")
        core.atomic_write_text(target, render(project, data))
        print("✓ 已生成 %s（%d KB）" % (target, os.path.getsize(target) // 1024))
        return 0
    except Exception as exc:
        print("✗ 图谱生成失败  %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
