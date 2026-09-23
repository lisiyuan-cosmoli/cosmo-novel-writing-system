#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把旧项目迁到 v2。默认只显示计划，--apply 才写入。"""
from __future__ import print_function

import argparse
import json
import os
import re

import v2_core as core
import 事务


def _bytes_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _source_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _system_manifest():
    value = core.load_json(os.path.join(_source_root(), "system-manifest.json"))
    if not value or value.get("schema_version") != core.SCHEMA_VERSION:
        raise RuntimeError("system-manifest.json 缺失或版本不符")
    return value


def _latest_finalized(project):
    text = core.read_text(os.path.join(project, "00_设定层", "03_分章大纲.md"), "") or ""
    found = []
    for line in text.splitlines():
        match = re.match(r"^\|\s*(K\d{4})\s*\|.*\|\s*([^|]*)\|\s*$", line)
        if match and "已定稿" in match.group(2):
            found.append(match.group(1))
    return found[-1] if found else None


def _with_snapshot_header(project):
    path = os.path.join(project, "01_运行层", "04_状态快照.md")
    text = core.read_text(path)
    if text is None or re.search(r"^>\s*状态[：:].*更新至\s+K\d{4}", text, re.M):
        return None
    latest = _latest_finalized(project)
    if not latest:
        return None
    lines = text.splitlines()
    position = 1 if lines else 0
    lines[position:position] = ["", "> 状态：**更新至 %s**" % latest]
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _plugin_compatibility_changes(project, project_data, source):
    """为旧式插件账本补上 v2 隔离文件和结构标记，不覆盖已有项目数据。"""
    changes, reasons = {}, {}
    registry = core.load_json(os.path.join(source, "04_题材插件", "plugin-registry.json"), {}) or {}
    entries = {item.get("id"): item for item in registry.get("plugins", [])}
    for plugin_id in project_data.get("enabled_plugins", []):
        entry = entries.get(plugin_id)
        if not entry or not entry.get("manifest"):
            raise RuntimeError("找不到已启用插件的 v2 包 %s" % plugin_id)
        manifest_path = os.path.join(source, "04_题材插件", entry["manifest"])
        plugin_manifest = core.load_json(manifest_path)
        if not plugin_manifest:
            raise RuntimeError("插件清单无法读取 %s" % manifest_path)
        package_root = os.path.dirname(manifest_path)
        for item in plugin_manifest.get("files", []):
            rel = item["target"]
            template = core.read_text(os.path.join(package_root, item["source"]))
            if template is None:
                raise RuntimeError("插件模板缺失 %s" % item["source"])
            current = core.read_text(os.path.join(project, rel))
            if current is None:
                changes[rel] = template.encode("utf-8")
                reasons[rel] = "补齐已启用插件的 v2 隔离文件"
                continue
            markers = plugin_manifest.get("required_markers", {}).get(rel, [])
            missing = [marker for marker in markers if marker not in current]
            if not missing:
                continue
            supplement = template
            lines = supplement.splitlines()
            if lines and lines[0].startswith("# "):
                supplement = "\n".join(lines[1:]).lstrip()
            merged = (current.rstrip() +
                      "\n\n<!-- v2 迁移补充。上方旧数据保留，后续新记录使用下方结构。 -->\n\n" +
                      supplement.rstrip() + "\n")
            changes[rel] = merged.encode("utf-8")
            reasons[rel] = "保留旧插件数据并补入 v2 结构  " + "、".join(missing)
    return changes, reasons


def build_plan(project):
    project = core.resolve_project(project)
    if core.is_template(project):
        raise RuntimeError("目标带母版标记，迁移器只处理小说项目")
    manifest_path = core.project_manifest_path(project)
    existing = core.load_json(manifest_path)
    if existing is None:
        project_data = core.new_project_manifest(project, migrated_from="legacy-markdown")
    else:
        errors = core.validate_project(existing)
        if errors:
            old_schema = existing.get("schema_version") if isinstance(existing, dict) else "unknown"
            if old_schema not in (1,):
                raise RuntimeError("无法迁移未知项目结构  " + "；".join(errors))
            project_data = core.new_project_manifest(project, migrated_from="schema-%s" % old_schema)
            project_data["project_id"] = existing.get("project_id", project_data["project_id"])
            project_data["created_at"] = existing.get("created_at", project_data["created_at"])
        else:
            project_data = dict(existing)
            project_data["system_version"] = core.SYSTEM_VERSION
            project_data["updated_at"] = core.utc_now()

    changes = {"project.json": _bytes_json(project_data)}
    reasons = {"project.json": "建立或更新项目结构版本"}
    system = _system_manifest()
    source = _source_root()
    for rel in system.get("sync_files", []):
        data = core.read_bytes(os.path.join(source, rel))
        if data is None:
            raise RuntimeError("升级包缺共享文件 %s" % rel)
        old = core.read_bytes(os.path.join(project, rel))
        if old != data:
            changes[rel] = data
            reasons[rel] = "更新 v2 共享文件"

    # 种子文件与合并文件不在 sync_files 里，但都在 project_required_files 里。
    # 只搬 sync_files 的话，迁移完成后会缺这几份，而 apply() 自己的写后验证
    # 又要求它们必须存在 —— 迁移器做不到自己的验收标准，v1 项目一迁就失败。
    # （实测：一本 v1.0 的 41 章项目迁移时报「缺必需文件」并整笔回滚。）
    #
    # 两类都**只在缺失时补入**，绝不覆盖：
    #   种子文件是用户数据（创作意图、开书决策、项目词表）；
    #   合并文件里装着这本书自己算出来的文风基线区块。
    # 已经有的一个字节都不动，这一条和 sync 的语义保持一致。
    补入 = []
    for rel in list(system.get("seed_files", [])) + \
            [item.get("path") for item in system.get("merge_files", []) if item.get("path")]:
        if rel in changes or not rel:
            continue
        if core.read_bytes(os.path.join(project, rel)) is not None:
            continue                       # 项目里已经有了，保持原样
        data = core.read_bytes(os.path.join(source, rel))
        if data is None:
            raise RuntimeError("升级包缺必需文件 %s" % rel)
        changes[rel] = data
        reasons[rel] = "补入缺失的必需文件（项目里没有，不覆盖已有）"
        补入.append(rel)

    plugin_changes, plugin_reasons = _plugin_compatibility_changes(
        project, project_data, source)
    changes.update(plugin_changes)
    reasons.update(plugin_reasons)

    for rel in ("_候选_README.md", "_工具/我是母版.txt",
                "_工具/母版禁词.txt", "_工具/母版检查.py",
                "01_运行层/07_场景卡_模板.md"):
        if os.path.exists(os.path.join(project, rel)):
            changes[rel] = None
            reasons[rel] = ("旧场景卡模板由章节卡模板替代"
                            if rel.endswith("07_场景卡_模板.md")
                            else "移除误入项目的母版或候选说明残留")

    for rel in (
        "01_运行层/06b_事实记录_已归档段.md",
        "02_检查层/13_已推翻判断表.md",
        "06_归档/流程审计.md",
        "_工具/专名表.txt",
        "_工具/允许重复.txt",
    ):
        target = os.path.join(project, rel)
        if not os.path.exists(target):
            data = core.read_bytes(os.path.join(source, rel))
            if data is None:
                raise RuntimeError("升级包缺初始化模板 %s" % rel)
            changes[rel] = data
            reasons[rel] = "补齐 v2 必需文件"

    header = _with_snapshot_header(project)
    if header is not None:
        rel = "01_运行层/04_状态快照.md"
        changes[rel] = header
        reasons[rel] = "补入检查器要求的快照版本抬头"

    archive = os.path.join(project, "06_归档")
    if os.path.isdir(archive):
        for name in sorted(os.listdir(archive)):
            match = re.fullmatch(r"场景卡_(K\d{4})\.md", name)
            if not match:
                continue
            old_rel = "06_归档/%s" % name
            new_rel = "06_归档/章节卡_%s.md" % match.group(1)
            old_data = core.read_bytes(os.path.join(project, old_rel))
            existing_new = core.read_bytes(os.path.join(project, new_rel))
            if existing_new is not None and existing_new != old_data:
                raise RuntimeError("章卡改名发生冲突 %s 与 %s" % (old_rel, new_rel))
            changes[new_rel] = old_data
            changes[old_rel] = None
            reasons[new_rel] = "统一章卡名称"
            reasons[old_rel] = "旧名称由新名称替代"
    return changes, reasons, project_data


def apply(project, changes):
    def validate():
        try:
            data = core.load_project(project)
            missing = [rel for rel in _system_manifest().get("project_required_files", [])
                       if not os.path.exists(os.path.join(project, rel))]
            if missing:
                return False, "缺必需文件 " + "、".join(missing)
            return data.get("schema_version") == core.SCHEMA_VERSION, "项目清单版本不符"
        except Exception as exc:
            return False, str(exc)
    return 事务.apply_changes(project, changes, "migrate to v2", validator=validate,
                            metadata={"schema_version": core.SCHEMA_VERSION})


def main(argv=None):
    parser = argparse.ArgumentParser(description="迁移旧小说项目到 v2")
    parser.add_argument("project")
    parser.add_argument("--apply", action="store_true", help="执行迁移，默认只显示计划")
    args = parser.parse_args(argv)
    try:
        changes, reasons, data = build_plan(args.project)
        print("迁移目标 %s" % os.path.abspath(args.project))
        print("推断归档基线 %s" % data["archive_required_from"])
        print("推断插件决定 %s  %s" % (data["plugin_decision"], ",".join(data["enabled_plugins"]) or "无"))
        print("变更 %d 项" % len(changes))
        for rel in sorted(changes):
            action = "删除旧名" if changes[rel] is None else ("新增" if not os.path.exists(os.path.join(args.project, rel)) else "更新")
            print("  %-8s %-42s %s" % (action, rel, reasons.get(rel, "")))
        if not args.apply:
            print("只读试算完成。确认后加 --apply")
            return 0
        tx = apply(os.path.abspath(args.project), changes)
        print("✓ 迁移完成，事务 %s" % tx["id"])
        return 0
    except Exception as exc:
        print("✗ 迁移失败，正式文件未保留半次变更  %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
