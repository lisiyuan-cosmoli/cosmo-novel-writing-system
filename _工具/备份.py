#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压缩备份与只读校验。

备份只收当前有效内容。运行产物、事务历史、候选区和旧备份不会再次进入
压缩包，避免旧产物被反复归档而扩大备份体积。
"""
from __future__ import print_function

import argparse
import io
import json
import os
import stat
import tarfile
import tempfile
import time
import uuid

import v2_core as core
import 事务


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def scan(project, state=None):
    """返回 (可备份的相对路径, 不安全对象说明)。

    符号链接一律拒绝，不静默解引用。v3.0 用 os.path.isfile 判断（跟随链接）
    却用 tarfile.add 保存（按 lstat 存成 symlink 成员），于是创建报告成功、
    随后自己的 verify 又拒绝这个成员——做出来的备份恢复不了，而用户看到的
    是一个 ✓。创建器与校验器必须用同一套链接策略。
    """
    ex = core.load_exclusions()
    files, unsafe = [], []
    def unreadable(exc):
        unsafe.append("%s（目录无法读取：%s）" % (exc.filename or project, exc))

    for root, dirs, names in os.walk(project, followlinks=False, onerror=unreadable):
        rel_root = os.path.relpath(root, project)
        if state is not None:
            try:
                state[rel_root] = _signature(os.lstat(root))
            except OSError as exc:
                unreadable(exc)
                continue
        kept = []
        for name in dirs:
            rel = os.path.normpath(os.path.join(rel_root, name)).replace(os.sep, "/")
            if rel.startswith("./"):
                rel = rel[2:]
            if ex.跳过(rel):
                continue
            if os.path.islink(os.path.join(root, name)):
                unsafe.append(rel + "（目录符号链接）")
                continue
            kept.append(name)
        dirs[:] = kept
        for name in names:
            rel = os.path.normpath(os.path.join(rel_root, name))
            if rel.startswith("./"):
                rel = rel[2:]
            rel = rel.replace(os.sep, "/")
            if rel in (".", "") or ex.跳过(rel) or name in (".DS_Store", "Thumbs.db", "desktop.ini"):
                continue
            full = os.path.join(root, name)
            if os.path.islink(full):
                target = ""
                try:
                    target = os.readlink(full)
                except OSError:
                    pass
                broken = not os.path.exists(full)
                unsafe.append("%s（%s符号链接 → %s）"
                              % (rel, "断裂" if broken else "", target or "读不到目标"))
                continue
            if not os.path.isfile(full):
                unsafe.append(rel + "（不是普通文件）")
                continue
            if state is not None:
                try:
                    state[rel] = _signature(os.lstat(full))
                except OSError as exc:
                    unsafe.append("%s（文件无法检查：%s）" % (rel, exc))
                    continue
            files.append(rel)
    return sorted(files), sorted(unsafe)


def collect(project):
    """仅返回可备份文件。遇到不安全对象直接抛错，不产出半份清单。"""
    files, unsafe = scan(project)
    if unsafe:
        raise RuntimeError(_不安全说明(unsafe))
    return files


def _不安全说明(unsafe):
    lines = ["项目里有备份无法安全保存的对象，已停止，未生成任何备份文件："]
    for item in unsafe[:20]:
        lines.append("    · " + item)
    if len(unsafe) > 20:
        lines.append("    · 另有 %d 项" % (len(unsafe) - 20))
    lines.append("  请恢复读取权限或修正不安全对象后重试；不能把未读到的内容当作不存在。")
    lines.append("  符号链接须换成真实文件或移到排除目录（如 _备份、_候选）。")
    return "\n".join(lines)


def create(project, note=""):
    project = core.resolve_project(project)
    # 与所有正式事务共用锁，但不调用 pending_guard：用户仍可明确备份
    # 中断现场。日志损坏也不阻止保全当前文件，manifest 会记录其状态。
    handle = 事务._acquire(project)
    try:
        return _create_locked(project, note)
    finally:
        事务._release(handle)


def _create_locked(project, note):
    pending = 事务.inspect(project)
    # 创建排除目录会改变项目根的目录时间，必须发生在基线扫描之前。
    backup_dir = core.safe_output_dir(project, "_备份")
    baseline = {}
    files, unsafe = scan(project, baseline)
    if unsafe:
        raise RuntimeError(_不安全说明(unsafe))
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    target = os.path.join(backup_dir, "%s.tar.gz" % stamp)
    fd, temp_path = tempfile.mkstemp(prefix=".backup-", suffix=".tar.gz", dir=backup_dir)
    os.close(fd)
    manifest = {
        "created_at": core.utc_now(),
        "format": "novel-backup-v2",
        "files": [],
        "note": note,
        "project": os.path.basename(project),
        "source_state": "interrupted" if pending is not None else "consistent",
    }
    if pending is not None:
        manifest["pending_transaction"] = pending
    try:
        with tarfile.open(temp_path, "w:gz") as archive:
            for rel in files:
                full = os.path.join(project, rel)
                if os.path.islink(full) or not os.path.isfile(full):
                    # 扫描之后被换成链接：宁可整笔失败，也不做一个恢复不了的包
                    raise RuntimeError("备份期间 %s 发生变化，已停止" % rel)
                if core.path_has_symlink(project, rel):
                    raise RuntimeError("备份期间 %s 路径变成了符号链接，已停止" % rel)
                fd = os.open(full, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd, "rb") as handle:
                    before = os.fstat(handle.fileno())
                    if not stat.S_ISREG(before.st_mode) or _signature(before) != baseline.get(rel):
                        raise RuntimeError("备份期间 %s 发生变化，已停止" % rel)
                    data = handle.read()
                    if _signature(os.fstat(handle.fileno())) != _signature(before):
                        raise RuntimeError("读取期间 %s 发生变化，已停止" % rel)
                # 归档头与内容来自同一个已检查的文件描述符；不再分别按
                # 路径取大小、摘要和正文，避免把不同版本混成一个成员。
                info = tarfile.TarInfo(rel)
                info.size = len(data)
                info.mode = stat.S_IMODE(before.st_mode)
                info.mtime = before.st_mtime
                info.uid, info.gid = before.st_uid, before.st_gid
                manifest["files"].append({
                    "path": rel,
                    "sha256": core.sha256_bytes(data),
                    "size": len(data),
                })
                archive.addfile(info, io.BytesIO(data))
            payload = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            info = tarfile.TarInfo("_备份清单.json")
            info.size = len(payload)
            info.mtime = int(time.time())
            archive.addfile(info, io.BytesIO(payload))
        # 先自校验再改名：**没通过校验的包不许出现在 _备份 目录里**
        verify(temp_path)
        final_state = {}
        final_files, unsafe = scan(project, final_state)
        if unsafe:
            raise RuntimeError(_不安全说明(unsafe))
        if files != final_files or baseline != final_state:
            raise RuntimeError("备份期间项目文件或目录发生变化，已停止；请关闭外部写入后重试")
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
    return target, manifest


def _safe_members(archive):
    seen = set()
    for member in archive.getmembers():
        rel = member.name
        # 正式备份只生成普通文件；目录、链接、设备和 FIFO 都不属于此格式。
        if (not core.safe_relative(rel) or rel == "." or "\\" in rel
                or not member.isfile()):
            raise RuntimeError("备份含不安全路径 %s" % member.name)
        if rel in seen:
            raise RuntimeError("备份含重复路径 %s" % rel)
        seen.add(rel)
        yield member


def _verified_archive(archive):
    members = list(_safe_members(archive))
    try:
        raw = archive.extractfile("_备份清单.json").read()
    except Exception as exc:
        raise RuntimeError("备份缺少清单 %s" % exc)
    manifest = json.loads(raw.decode("utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("format") != "novel-backup-v2"
            or not isinstance(manifest.get("files"), list)):
        raise RuntimeError("备份清单格式不合法")
    indexed = {}
    for item in manifest["files"]:
        rel = item.get("path") if isinstance(item, dict) else None
        if (not core.safe_relative(rel) or rel in (".", "_备份清单.json")
                or "\\" in rel or rel in indexed):
            raise RuntimeError("备份清单含非法或重复路径 %r" % rel)
        indexed[rel] = item
    actual = {m.name for m in members if m.name != "_备份清单.json"}
    if actual != set(indexed):
        raise RuntimeError("备份文件列表与清单不一致")
    for rel in actual:
        parent = os.path.dirname(rel)
        while parent:
            if parent in actual:
                raise RuntimeError("备份文件与父目录路径冲突：%s / %s" % (parent, rel))
            parent = os.path.dirname(parent)
    for rel, item in indexed.items():
        _verified_payload(archive, rel, item)
    return manifest, members, indexed


def _verified_payload(archive, rel, item):
    data = archive.extractfile(rel).read()
    if (type(item.get("size")) is not int or item["size"] < 0
            or core.sha256_bytes(data) != item.get("sha256") or len(data) != item["size"]):
        raise RuntimeError("备份校验失败 %s" % rel)
    return data


def verify(path):
    with tarfile.open(path, "r:gz") as archive:
        return _verified_archive(archive)[0]


def restore(path, target):
    target = os.path.abspath(target)
    if os.path.lexists(target):
        raise RuntimeError("恢复目标已经存在，拒绝覆盖 %s" % target)
    parent = os.path.dirname(target)
    if not os.path.isdir(parent):
        raise RuntimeError("恢复目标的父目录不存在 %s" % parent)
    temp_dir = None
    try:
        with tarfile.open(path, "r:gz") as archive:
            # 校验和恢复使用同一个打开的包；每个实际写入的字节再核验一次。
            manifest, members, indexed = _verified_archive(archive)
            temp_dir = tempfile.mkdtemp(prefix=".novel-restore-", dir=parent)
            for member in members:
                if member.name == "_备份清单.json":
                    continue
                data = _verified_payload(archive, member.name, indexed[member.name])
                destination = os.path.join(temp_dir, member.name)
                if os.path.lexists(destination):
                    # 大小写或 Unicode 规范化不同的归档名，可能是目标盘上的同一文件。
                    raise RuntimeError("恢复路径在目标文件系统中重名：%s" % member.name)
                core.atomic_write_bytes(destination, data, mode=member.mode & 0o777)
                os.utime(destination, (member.mtime, member.mtime))
            for rel, item in indexed.items():
                destination = os.path.join(temp_dir, rel)
                if (core.sha256_file(destination) != item["sha256"]
                        or os.path.getsize(destination) != item["size"]):
                    raise RuntimeError("恢复写后校验失败：%s" % rel)
        if os.path.lexists(target):
            raise RuntimeError("恢复目标在操作期间出现，拒绝覆盖 %s" % target)
        os.replace(temp_dir, target)
        temp_dir = None
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="创建、验证或恢复小说项目备份")
    sub = parser.add_subparsers(dest="command", required=True)
    p_create = sub.add_parser("create")
    p_create.add_argument("project", nargs="?", default=".")
    p_create.add_argument("--note", default="")
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("archive")
    p_restore = sub.add_parser("restore")
    p_restore.add_argument("archive")
    p_restore.add_argument("target")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            path, manifest = create(args.project, args.note)
            print("✓ 备份完成 %s" % path)
            print("  文件 %d 份" % len(manifest["files"]))
            if manifest.get("source_state") == "interrupted":
                print("  △ 本备份保存未完成事务的现场，不代表自洽版本；状态已写入备份清单。")
            print("  ※ 备份只收**当前有效内容**：不含 .novel 事务历史，也不含候选区、")
            print("    读取包和旧备份。恢复出来的项目没有提交历史，rollback 无从谈起。")
        elif args.command == "verify":
            manifest = verify(args.archive)
            print("✓ 备份校验通过，文件 %d 份" % len(manifest.get("files", [])))
            if manifest.get("source_state") == "interrupted":
                print("  △ 摘要校验通过不代表项目自洽；本备份来自未完成事务现场。")
        else:
            manifest = restore(args.archive, args.target)
            print("✓ 已恢复到新目录 %s" % os.path.abspath(args.target))
            if manifest.get("source_state") == "interrupted":
                print("  △ 还原的是未完成事务现场，须先核对文件一致性；不能直接当作可续写版本。")
                print("    备份不含原事务日志，不能在恢复目录通过 recover 或 rollback 修复原事务。")
            else:
                print("  ※ 这份恢复不含事务历史（备份本来就不收）。它是一份可以继续写的")
                print("    项目，但 history 与 rollback 从这里重新开始。")
        return 0
    except Exception as exc:
        print("✗ %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
