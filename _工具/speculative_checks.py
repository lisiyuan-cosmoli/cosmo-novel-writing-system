# -*- coding: utf-8 -*-
"""Opt-in structural checks for speculative-rules-v1.

No prose inference, approval inference, chronological inference, or writes.
The six-column 3.7 cards and usage tables remain valid.
"""
import re

RULES = "00_设定层/插件/speculative.md"
USAGE = "01_运行层/05d_规则使用记录.md"
CHANGE_TYPES = {"既有用法", "新组合", "新习得", "新披露", "规则变更", "待核对"}


def _visible_lines(text):
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"),
                  text or "", flags=re.S)
    fence = None
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^ {0,3}([\x60~]{3,})(.*)$", line)
        if fence:
            if match and set(match[1]) == {fence[0]} and len(match[1]) >= fence[1] and not match[2].strip():
                fence = None
            continue
        if match and len(set(match[1])) == 1:
            fence = (match[1][0], len(match[1]))
            continue
        out.append((number, line))
    return out


def _cells(line):
    # GFM escaped pipes are content, not column separators.
    parts, current, escaped = [], [], False
    for char in line.strip():
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    parts.append("".join(current).strip())
    if line.strip().startswith("|"):
        parts = parts[1:]
    if line.strip().endswith("|") and parts and parts[-1] == "":
        parts = parts[:-1]
    return [p.strip().strip(chr(96)).strip("*").strip() for p in parts]


def _table(text, heading, required, errors, path):
    visible = _visible_lines(text)
    starts = [i for i, (_, line) in enumerate(visible)
              if re.fullmatch(r"##\s+" + re.escape(heading) + r"\s*#*\s*", line.strip())]
    if len(starts) != 1:
        errors.append("%s 必须有一处有效的 ## %s（代码示例和注释不算）" % (path, heading))
        return []
    start = starts[0] + 1
    end = next((i for i in range(start, len(visible))
                if re.match(r"^#{1,2}\s", visible[i][1].strip())), len(visible))
    tables = [(n, _cells(line)) for n, line in visible[start:end] if line.strip().startswith("|")]
    if not tables:
        errors.append("%s 的 %s 缺表格" % (path, heading))
        return []
    headers = tables[0][1]
    if len(headers) != len(set(headers)) or not set(required).issubset(headers):
        errors.append("%s 的 %s 表头须包含 %s，且列名不能重复" % (path, heading, "、".join(required)))
        return []
    rows = []
    for number, values in tables[1:]:
        if values == headers or (values and all(re.fullmatch(r":?-{3,}:?", v) for v in values)):
            continue
        if not any(values):
            continue
        if len(values) != len(headers):
            errors.append("%s 第 %d 行列数为 %d，应为 %d；内容中的竖线须转义" %
                          (path, number, len(values), len(headers)))
            continue
        rows.append((number, dict(zip(headers, values))))
    return rows


def _unique(rows, key, content, errors, path):
    seen = set()
    for number, row in rows:
        value = row.get(key, "")
        if not value or not row.get(content, ""):
            errors.append("%s 第 %d 行的 %s 与 %s 不能为空" % (path, number, key, content))
        if value in seen:
            errors.append("%s 第 %d 行重复 %s %s" % (path, number, key, value))
        if value:
            seen.add(value)
    return seen


def validate(rule_text, usage_text, outline_text=None):
    """Return structural errors; an empty result is NOT semantic approval."""
    errors = []
    if rule_text is None or usage_text is None:
        return []  # The installer already reports missing files.
    rules = _table(rule_text, "规则卡", ("规则 ID", "内容", "使用代价", "边界", "谁知道", "首次展示章"),
                   errors, RULES)
    rule_ids = _unique(rules, "规则 ID", "内容", errors, RULES)
    limits = _table(rule_text, "明确不成立", ("限制 ID", "不能做到的事"), errors, RULES)
    _unique(limits, "限制 ID", "不能做到的事", errors, RULES)
    uses = _table(usage_text, "规则使用", ("永久 ID", "规则 ID", "使用者", "实际代价", "是否符合旧用法", "是否改变边界"),
                  errors, USAGE)
    chapter_ids = None if outline_text is None else {
        values[0] for _, line in _visible_lines(outline_text) if line.strip().startswith("|")
        for values in [_cells(line)] if values and re.fullmatch(r"K[0-9]{4}", values[0])
    }
    for number, row in uses:
        kid, rid = row["永久 ID"], row["规则 ID"]
        if not re.fullmatch(r"K[0-9]{4}", kid):
            errors.append("%s 第 %d 行永久 ID 格式无效 %s" % (USAGE, number, kid))
        elif chapter_ids is not None and kid not in chapter_ids:
            errors.append("%s 第 %d 行引用大纲中不存在的章节 %s" % (USAGE, number, kid))
        if rid not in rule_ids:
            errors.append("%s 第 %d 行引用不存在的规则 %s" % (USAGE, number, rid))
        kind = row.get("变化类型", "")
        if kind and kind not in CHANGE_TYPES:
            errors.append("%s 第 %d 行变化类型无效 %s" % (USAGE, number, kind))
    return errors
