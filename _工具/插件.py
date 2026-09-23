#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声明式题材插件管理。"""
from __future__ import print_function

import argparse
import json
import os
import re

import v2_core as core
import 事务


def _root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _registry(root=None):
    path = os.path.join(root or _root(), "04_题材插件", "plugin-registry.json")
    value = core.load_json(path)
    if not value or not isinstance(value.get("plugins"), list):
        raise RuntimeError("插件注册表无法读取 %s" % path)
    return value


def _entry(plugin_id, root=None):
    for entry in _registry(root)["plugins"]:
        if entry.get("id") == plugin_id:
            return entry
    raise RuntimeError("未知插件 %s" % plugin_id)


def _manifest(plugin_id, root=None):
    entry = _entry(plugin_id, root)
    if entry.get("status") != "supported" or not entry.get("manifest"):
        raise RuntimeError("插件 %s 仍是实验性资料，当前版本不能安装" % plugin_id)
    if not core.safe_relative(entry["manifest"]):
        raise RuntimeError("插件清单路径无效")
    path = os.path.join(root or _root(), "04_题材插件", entry["manifest"])
    value = core.load_json(path)
    if not value or value.get("id") != plugin_id:
        raise RuntimeError("插件清单损坏 %s" % path)
    return value, os.path.dirname(path)


def list_plugins(project=None):
    enabled = set()
    if project and os.path.isfile(core.project_manifest_path(project)):
        enabled = set(core.load_project(project).get("enabled_plugins", []))
    for entry in _registry()["plugins"]:
        flag = "已启用" if entry["id"] in enabled else entry.get("status", "unknown")
        print("%-12s %-8s %s" % (entry["id"], flag, entry.get("name", "")))


def _manifest_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _meaningful_text(data):
    """忽略换行格式与行尾空白，其他任何偏离模板的内容都视为项目数据。"""
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.strip().split("\n"))


def set_none(project):
    project = core.resolve_project(project)
    def plan():
        current = core.load_project(project)
        if current.get("enabled_plugins"):
            raise RuntimeError("已有启用插件，请先逐个卸载")
        updated = dict(current)
        updated["plugin_decision"] = "none"
        updated["updated_at"] = core.utc_now()
        return {"changes": {"project.json": _manifest_bytes(updated)},
                "label": "plugin decision none"}
    事务.apply_changes(project, plan=plan)
    print("✓ 已明确不启用题材插件")


def install(project, plugin_id):
    project = core.resolve_project(project)
    class AlreadyInstalled(Exception):
        pass

    def plan():
        current = core.load_project(project)
        manifest, package_root = _manifest(plugin_id)
        if core.SCHEMA_VERSION not in manifest.get("schema_versions", []):
            raise RuntimeError("插件不支持当前项目结构版本")
        if plugin_id in current.get("enabled_plugins", []):
            ok, details = verify(project, plugin_id)
            if ok:
                raise AlreadyInstalled()
            raise RuntimeError("插件登记为已安装，但文件不完整  " + "；".join(details))
        changes = {}
        for item in manifest.get("files", []):
            source = os.path.join(package_root, item["source"])
            target = item["target"]
            data = core.read_bytes(source)
            if data is None:
                raise RuntimeError("插件包缺文件 %s" % item["source"])
            existing = core.read_bytes(os.path.join(project, target))
            if existing is not None and existing.strip() and existing != data:
                raise RuntimeError("目标已有不同内容，拒绝覆盖 %s" % target)
            changes[target] = data
        updated = dict(current)
        updated["enabled_plugins"] = sorted(set(updated.get("enabled_plugins", [])) | {plugin_id})
        updated["plugin_decision"] = "selected"
        # 安装基线与配置在同一把锁内读取并生成，不能覆盖先完成的插件操作。
        托管 = {item["target"]: core.sha256_bytes(changes[item["target"]])
                for item in manifest.get("files", [])
                if item.get("owner") == "system" and item["target"] in changes}
        表 = dict(updated.get("plugin_files") or {})
        表[plugin_id] = 托管
        updated["plugin_files"] = 表
        updated["plugin_version"] = dict(updated.get("plugin_version") or {},
                                         **{plugin_id: manifest.get("version", "unknown")})
        updated["updated_at"] = core.utc_now()
        changes["project.json"] = _manifest_bytes(updated)
        return {"changes": changes, "label": "install plugin %s" % plugin_id,
                "metadata": {"plugin": plugin_id}}

    def validate():
        ok, details = verify(project, plugin_id, expect_registered=True)
        return ok, "；".join(details)

    try:
        事务.apply_changes(project, plan=plan, validator=validate)
    except AlreadyInstalled:
        print("✓ 插件已经安装且校验通过 %s" % plugin_id)
        return
    print("✓ 插件安装完成 %s" % plugin_id)


def verify(project, plugin_id, expect_registered=True, reader=None):
    # Validation uses this project's package, including explicit local extensions.
    manifest, _ = _manifest(plugin_id, root=project)
    read = reader or (lambda rel: core.read_text(os.path.join(project, rel)))
    details = []
    try:
        project_data = core.load_project(project)
    except Exception as exc:
        return False, [str(exc)]
    if expect_registered and plugin_id not in project_data.get("enabled_plugins", []):
        details.append("project.json 没有登记插件")
    装版 = (project_data.get("plugin_version") or {}).get(plugin_id)
    母版 = manifest.get("version")
    if expect_registered and 装版 and 母版 and 装版 != 母版:
        details.append("已安装版本 %s 与本项目插件包 %s 不一致，请核对插件迁移" % (装版, 母版))
    for item in manifest.get("files", []):
        target = item["target"]
        text = read(target)
        if text is None:
            details.append("缺文件 %s" % target)
            continue
        for marker in manifest.get("required_markers", {}).get(target, []):
            if marker not in text:
                details.append("%s 缺标记 %s" % (target, marker))
    if manifest.get("content_checks") == "speculative-rules-v1":
        from speculative_checks import validate, RULES, USAGE
        details.extend(validate(read(RULES), read(USAGE), read("00_设定层/03_分章大纲.md")))
    return not details, details


def uninstall(project, plugin_id, force=False):
    project = core.resolve_project(project)
    result = {}
    def plan():
        current = core.load_project(project)
        if plugin_id not in current.get("enabled_plugins", []):
            raise RuntimeError("插件尚未启用 %s" % plugin_id)
        manifest, package_root = _manifest(plugin_id)
        changes = {}
        retirement = os.path.join("06_归档", "插件", plugin_id,
                                  core.utc_now().replace(":", ""))
        for item in manifest.get("files", []):
            target = item["target"]
            data = core.read_bytes(os.path.join(project, target))
            if data is None:
                continue
            template = core.read_bytes(os.path.join(package_root, item["source"]))
            if template is None:
                raise RuntimeError("插件模板缺失，不能判断卸载数据 %s" % item["source"])
            has_data = _meaningful_text(data) != _meaningful_text(template)
            if has_data and not force:
                raise RuntimeError("插件文件已经偏离原始模板，使用 --force 才会归档后卸载 %s" % target)
            changes[os.path.join(retirement, target).replace(os.sep, "/")] = data
            changes[target] = None
        updated = dict(current)
        updated["enabled_plugins"] = [x for x in updated.get("enabled_plugins", []) if x != plugin_id]
        updated["plugin_decision"] = "selected" if updated["enabled_plugins"] else "none"
        for key in ("plugin_files", "plugin_version"):
            if isinstance(updated.get(key), dict) and plugin_id in updated[key]:
                表 = dict(updated[key]); 表.pop(plugin_id); updated[key] = 表
        updated["updated_at"] = core.utc_now()
        changes["project.json"] = _manifest_bytes(updated)
        result.update(retirement=retirement, decision=updated["plugin_decision"])
        return {"changes": changes, "label": "uninstall plugin %s" % plugin_id,
                "metadata": {"plugin": plugin_id}}
    事务.apply_changes(project, plan=plan)
    print("✓ 插件已卸载 %s" % plugin_id)
    print("  原文件保存在 %s" % result["retirement"])
    if result["decision"] == "none":
        print("  项目已回到**明确不启用插件**的状态。核心流程完整可用；")
        print("  如果这不是你想要的，运行 python3 novel.py plugin install <插件>。")


def main(argv=None):
    parser = argparse.ArgumentParser(description="题材插件管理")
    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("project", nargs="?", default=".")
    p_none = sub.add_parser("none")
    p_none.add_argument("project", nargs="?", default=".")
    for name in ("install", "verify", "uninstall"):
        p = sub.add_parser(name)
        p.add_argument("plugin")
        p.add_argument("project", nargs="?", default=".")
        if name == "uninstall":
            p.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            list_plugins(args.project)
        elif args.command == "none":
            set_none(args.project)
        elif args.command == "install":
            install(args.project, args.plugin)
        elif args.command == "verify":
            ok, details = verify(args.project, args.plugin)
            if not ok:
                raise RuntimeError("；".join(details))
            print("✓ 插件校验通过 %s" % args.plugin)
        else:
            uninstall(args.project, args.plugin, args.force)
        return 0
    except Exception as exc:
        print("✗ %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
