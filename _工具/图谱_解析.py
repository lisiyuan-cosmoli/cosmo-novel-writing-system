#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把核心账本解析成题材中立的图谱数据。"""
from __future__ import print_function

import io
import os
import re


KMAP = {}


def read(project, rel):
    try:
        with io.open(os.path.join(project, rel), "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        return ""


def cells(line):
    return [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]


def chapter_number(value):
    ids = [KMAP[kid] for kid in re.findall(r"K\d{4}", value or "") if kid in KMAP]
    if ids:
        return max(ids)
    cleaned = re.sub(r"\d{4}-\d{1,2}-\d{1,2}|20\d{2}", " ", value or "")
    upper = max(KMAP.values()) if KMAP else None
    numbers = [int(x) for x in re.findall(r"(?<!\d)(\d{1,4})(?!\d)", cleaned)
               if int(x) >= 1 and (upper is None or int(x) <= upper)]
    return max(numbers) if numbers else None


def _index(headers, *keywords):
    for index, value in enumerate(headers):
        if any(keyword in value for keyword in keywords):
            return index
    return None


def _cell(row, index):
    return row[index] if index is not None and index < len(row) else ""


def _tracked_rows(project, rel, prefix, kind):
    text = read(project, rel)
    headers = []
    out = []
    section_status = None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1)
            if "未兑现" in title or "活跃线索" in title:
                section_status = "活动"
            elif "已兑现" in title or "已结清" in title or "已揭晓" in title:
                section_status = "已兑现"
            elif "已废弃" in title or "废弃" in title:
                section_status = "已废弃"
            else:
                section_status = None
            headers = []
            continue
        if line.startswith("|") and (("编号" in line) or ("ID" in line)):
            headers = cells(line)
            continue
        if not re.match(r"^\|\s*%s\d+\s*\|" % prefix, line):
            continue
        row = cells(line)
        item_id = row[0]
        text_index = _index(headers, "内容", "伏笔", "线索")
        born_index = _index(headers, "埋设", "首次出现", "出现章")
        actual_index = _index(headers, "实际揭晓", "兑现（永久", "兑现章", "结清章")
        plan_index = _index(headers, "计划揭晓", "计划兑现", "揭晓（永久")
        status_index = _index(headers, "状态")
        meaning_index = _index(headers, "当前含义", "真实含义", "兑现会改变", "效果")
        born = chapter_number(_cell(row, born_index))
        actual = chapter_number(_cell(row, actual_index))
        planned = chapter_number(_cell(row, plan_index))
        status = _cell(row, status_index) or section_status or "活动"
        out.append({
            "id": item_id,
            "kind": kind,
            "text": _cell(row, text_index) or (row[1] if len(row) > 1 else ""),
            "born": born,
            "land": actual or planned,
            "planned": planned,
            "status": status,
            "meaning": _cell(row, meaning_index),
            "source": rel,
        })
    return out


def parse(project):
    project = os.path.abspath(project)
    data = {}
    KMAP.clear()
    chapters = []
    outline = read(project, "00_设定层/03_分章大纲.md")
    for line in outline.splitlines():
        if not re.match(r"^\|\s*K\d{4}\s*\|", line):
            continue
        row = cells(line)
        if len(row) < 7 or not row[1].isdigit():
            continue
        KMAP[row[0]] = int(row[1])
        chapters.append({
            "id": row[0],
            "no": int(row[1]),
            "pov": row[2],
            "what": re.sub(r"<br>", " ", row[3]),
            "start": re.sub(r"<br>", " ", row[4]),
            "leaves": re.sub(r"<br>", " ", row[5]),
            "status": row[6],
        })
    data["chapters"] = chapters

    seeds = _tracked_rows(project, "01_运行层/05_伏笔表.md", "F", "伏笔")
    clues = []
    for rel in ("01_运行层/05b_线索兑现表.md", "06_归档/线索归档.md"):
        clues.extend(_tracked_rows(project, rel, "C", "线索"))
    # 若运行表与归档暂时同时存在同一 ID，后读到的归档状态优先，避免图谱仍显示活动。
    clue_map = {}
    for item in clues:
        clue_map[item["id"]] = item
    clues = list(clue_map.values())
    data["seeds"] = seeds
    data["clues"] = clues
    data["tracked"] = seeds + clues
    data["active_tracked"] = [item for item in data["tracked"]
                              if not re.search(r"已兑现|已结清|已揭晓|已废弃|废弃|灭失|锁死",
                                               item["status"] or "")]

    snapshot = read(project, "01_运行层/04_状态快照.md")
    knowledge = {"cols": [], "rows": []}
    if "## C." in snapshot:
        section = re.split(r"\n## ", snapshot.split("## C.", 1)[1])[0]
        rows = [line for line in section.splitlines()
                if line.strip().startswith("|") and "---" not in line]
        if rows:
            knowledge["cols"] = cells(rows[0])
            knowledge["rows"] = [cells(line) for line in rows[1:]
                                 if len(cells(line)) == len(knowledge["cols"])]
    data["know"] = knowledge

    dates = {}
    for rel in ("01_运行层/06_事实记录.md",
                "01_运行层/06b_事实记录_已归档段.md"):
        blocks = re.split(r"\n(?=###\s*K\d{4})", read(project, rel))
        for block in blocks:
            match = re.match(r"###\s*(K\d{4})", block.strip())
            if not match:
                continue
            date = re.search(r"时间地点[：:][\s*_「【]*(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
                             block)
            if date:
                dates[match.group(1)] = "%s-%02d-%02d" % (
                    date.group(1), int(date.group(2)), int(date.group(3)))
    data["dates"] = dates

    data["done"] = max([item["no"] for item in chapters
                        if "已定稿" in item["status"]] or [0])
    data["total"] = max([item["no"] for item in chapters] or [0])
    gaps = []
    for item in data["active_tracked"]:
        if not item["born"]:
            gaps.append("%s 缺首次出现或埋设章" % item["id"])
        if not item["land"] and "废弃" not in item["status"]:
            gaps.append("%s 缺计划兑现或揭晓章" % item["id"])
    data["gaps"] = gaps
    data["chain"] = []
    for chapter in chapters:
        born = [item for item in data["tracked"] if item["born"] == chapter["no"]]
        if born:
            data["chain"].append({
                "id": chapter["id"],
                "no": chapter["no"],
                "pov": chapter["pov"],
                "act": chapter["what"],
                "items": born,
            })
    return data


解析 = parse


if __name__ == "__main__":
    import json
    import sys
    result = parse(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(json.dumps(result, ensure_ascii=False, indent=2))
