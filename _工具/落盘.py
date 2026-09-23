#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选提交与正式写入闸门。

候选只能改章节提交白名单内的内容文件。试算通过后会给出完整审批摘要；
正式提交必须带回同一个摘要，任何候选内容或正式基线变化都会使审批失效。
"""
from __future__ import print_function

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import v2_core as core
import 事务
import 引擎


def 出(value=""):
    print(value, flush=True)


_EX = core.load_exclusions()


def 建影子(project):
    temp_root = tempfile.mkdtemp(prefix="novel-shadow-")
    shadow = os.path.join(temp_root, os.path.basename(os.path.abspath(project)))

    def 忽略(path, names):
        ignored = []
        for name in names:
            rel = os.path.relpath(os.path.join(path, name), project).replace(os.sep, "/")
            if name == ".DS_Store" or _EX.跳过(rel):
                ignored.append(name)
        return ignored

    shutil.copytree(project, shadow, ignore=忽略, symlinks=True)
    return temp_root, shadow


def 收候选(candidate_root):
    """把候选内容一次读入内存，同时拒绝所有符号链接。"""
    entries, errors = [], []
    if os.path.islink(candidate_root):
        return [], ["候选根目录是符号链接"]
    def unreadable(exc):
        errors.append("候选目录无法读取：%s" % exc)
    for root, dirs, files in os.walk(candidate_root, followlinks=False, onerror=unreadable):
        kept = []
        for name in dirs:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, candidate_root).replace(os.sep, "/")
            if name == ".DS_Store":
                continue
            if os.path.islink(full):
                errors.append(rel + "（候选目录是符号链接）")
                continue
            kept.append(name)
        dirs[:] = kept
        for name in files:
            if name == ".DS_Store":
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, candidate_root).replace(os.sep, "/")
            if os.path.islink(full):
                errors.append(rel + "（候选文件是符号链接）")
                continue
            data = core.read_bytes(full)
            if data is None:
                errors.append(rel + "（候选文件无法读取）")
                continue
            entries.append({"path": rel, "data": data})
    return sorted(entries, key=lambda item: item["path"]), sorted(errors)


def 保留提交候选(project, kid, txid, approved_entries):
    """原子移出已提交候选，保留编辑器尚未关闭的文件句柄。

    比对后 rmtree 仍会删除比对之后才保存的文字；目录 rename 后不删除，
    原路径的新文件和指向旧 inode 的已打开句柄才能同时得到保留。
    """
    rel = "_候选/" + kid
    if (not core.safe_relative(rel) or "/" in kid
            or not core.safe_relative(txid) or "/" in txid
            or core.path_has_symlink(project, rel)):
        raise 事务.TransactionError("候选路径不安全，保留候选现场")
    source = os.path.join(project, rel)
    if not os.path.isdir(source):
        raise 事务.TransactionError("候选目录已变化，保留现场供核对")
    container = "%s-%s" % (kid, txid)
    target_rel = "06_归档/_候选存根/%s/候选" % container
    if not core.safe_relative(target_rel):
        raise 事务.TransactionError("候选存根路径不合法")
    core.safe_output_dir(project, "06_归档/_候选存根")
    # 打开逐级目录描述符后再 rename，父目录被换成软链也不能把移动操作
    # 引向外部。mkdir 独占本次容器；不覆盖任何已有存根。
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    handles = []
    try:
        root_fd = os.open(project, flags)
        handles.append(root_fd)
        def directory(parts):
            fd = root_fd
            for part in parts:
                fd = os.open(part, flags, dir_fd=fd)
                handles.append(fd)
            return fd
        source_fd = directory(["_候选"])
        retention_fd = directory(["06_归档", "_候选存根"])
        if not stat.S_ISDIR(os.stat(kid, dir_fd=source_fd, follow_symlinks=False).st_mode):
            raise 事务.TransactionError("候选已变成链接或非目录，保留现场")
        os.mkdir(container, dir_fd=retention_fd)
        destination_fd = os.open(container, flags, dir_fd=retention_fd)
        handles.append(destination_fd)
        os.rename(kid, "候选", src_dir_fd=source_fd, dst_dir_fd=destination_fd)
    finally:
        for fd in reversed(handles):
            os.close(fd)
    if core.path_has_symlink(project, target_rel):
        return target_rel, True
    retained, errors = 收候选(os.path.join(project, target_rel))
    changed = bool(errors) or retained != approved_entries
    return target_rel, changed


def _plugin_mutable_files(project, project_data):
    registry_path = os.path.join(project, "04_题材插件", "plugin-registry.json")
    registry = core.load_json(registry_path)
    if not isinstance(registry, dict) or not isinstance(registry.get("plugins"), list):
        raise core.ProjectError("插件注册表无法读取，不能安全计算章节白名单")
    by_id = {item.get("id"): item for item in registry["plugins"] if isinstance(item, dict)}
    allowed = set()
    for plugin_id in project_data.get("enabled_plugins", []):
        entry = by_id.get(plugin_id)
        if not entry or not entry.get("manifest"):
            raise core.ProjectError("已启用插件 %s 没有合法清单" % plugin_id)
        manifest_rel = os.path.join("04_题材插件", entry["manifest"]).replace(os.sep, "/")
        if not core.safe_relative(manifest_rel):
            raise core.ProjectError("插件 %s 的清单路径不安全" % plugin_id)
        manifest = core.load_json(os.path.join(project, manifest_rel))
        if not isinstance(manifest, dict) or manifest.get("id") != plugin_id:
            raise core.ProjectError("插件 %s 清单损坏" % plugin_id)
        declared_targets = {item.get("target") for item in manifest.get("files", [])
                            if isinstance(item, dict)}
        mutable = manifest.get("chapter_mutable_files")
        if not isinstance(mutable, list):
            raise core.ProjectError("插件 %s 未声明 chapter_mutable_files，请先同步" % plugin_id)
        for rel in mutable:
            if not core.safe_relative(rel) or rel not in declared_targets:
                raise core.ProjectError("插件 %s 的章节可写路径不合法 %s" % (plugin_id, rel))
            allowed.add(rel)
    return allowed


def 允许路径(project, kid, project_data, kids=None):
    """kids 给出时取批内各章白名单的并集（4.0 批次提交）。"""
    policy = core.load_chapter_policy(project)
    exact = set(policy["core_mutable_files"])
    exact.update(_plugin_mutable_files(project, project_data))
    patterns = []
    for one in (kids or [kid]):
        exact.update(template.format(kid=one) for template in policy["kid_files"])
        patterns.extend(re.compile(pattern.replace("{kid}", re.escape(one)))
                        for pattern in policy["kid_patterns"])
    return exact, patterns


def 核候选路径(project, entries, exact, patterns):
    errors = []
    for item in entries:
        rel = item["path"]
        if not core.safe_relative(rel):
            errors.append(rel + "（路径逃逸或非规范路径）")
            continue
        if rel not in exact and not any(pattern.fullmatch(rel) for pattern in patterns):
            errors.append(rel + "（不在本章可写白名单）")
            continue
        parent_rel = os.path.dirname(rel)
        if parent_rel and not os.path.isdir(os.path.join(project, parent_rel)):
            errors.append(rel + "（正式项目里没有目标目录）")
            continue
        linked = core.path_has_symlink(project, rel)
        if linked:
            errors.append(rel + "（正式目标路径经过符号链接 %s）" % linked)
    return errors


def 候选摘要(project, kid, entries, kids=None):
    rows = []
    for item in entries:
        target = os.path.join(project, item["path"])
        before = core.read_bytes(target)
        rows.append({
            "before_sha256": core.sha256_bytes(before) if before is not None else None,
            "candidate_sha256": core.sha256_bytes(item["data"]),
            "path": item["path"],
            "size": len(item["data"]),
            "state": "add" if before is None else "modify",
        })
    payload = {"chapter_id": kid, "files": rows, "format": "novel-candidate-v1"}
    if kids and len(kids) > 1:
        payload["chapter_ids"] = list(kids)
    return rows, core.canonical_digest(payload)


def 验证器摘要(project, project_data):
    rels = [
        "chapter-policy.json", "_工具/落盘.py", "_工具/提交包.py",
        "_工具/体检.py", "_工具/章节卡.py", "_工具/排除表.py",
        "_工具/模块表.py", "_工具/生成图谱.py", "_工具/图谱_解析.py",
        "_工具/v2_core.py", "_工具/事务.py", "_工具/novel.py", "novel.py",
        "_工具/封段.py", "_工具/状态.py", "_工具/引擎.py", "_工具/文风档.py",
    ]
    registry = core.load_json(os.path.join(project, "04_题材插件", "plugin-registry.json"), {}) or {}
    by_id = {item.get("id"): item for item in registry.get("plugins", []) if isinstance(item, dict)}
    for plugin_id in project_data.get("enabled_plugins", []):
        entry = by_id.get(plugin_id) or {}
        if entry.get("manifest"):
            rels.append(os.path.join("04_题材插件", entry["manifest"]).replace(os.sep, "/"))
    rows = [{"path": rel, "sha256": core.sha256_file(os.path.join(project, rel))}
            for rel in sorted(set(rels))]
    return core.canonical_digest({"files": rows, "format": "novel-validator-v1"})


def _建议命令(project, kid, digest):
    """给出可以直接复制运行的正式提交命令。"""
    project = os.path.abspath(project)
    if os.path.abspath(os.getcwd()) == project:
        return "python3 novel.py commit %s --apply --approve %s" % (kid, digest)
    return 'python3 novel.py commit %s "%s" --apply --approve %s' % (kid, project, digest)


def _parse_args(argv):
    if len(argv) < 2:
        return None, None, False, None, "参数不足"
    project, kid = argv[0].rstrip("/"), argv[1]
    apply = False
    approval = None
    rest = list(argv[2:])
    index = 0
    while index < len(rest):
        arg = rest[index]
        if arg == "--落盘":
            apply = True
        elif arg in ("--批准", "--approve"):
            index += 1
            if index >= len(rest):
                return None, None, False, None, "%s 后缺 SHA-256" % arg
            approval = rest[index].lower()
        else:
            return None, None, False, None, "未知参数 %s" % arg
        index += 1
    return project, kid, apply, approval, None


def main(argv=None):
    project, kid, apply, approval, arg_error = _parse_args(
        list(sys.argv[1:] if argv is None else argv))
    if arg_error:
        出("用法：python3 _工具/落盘.py <项目文件夹> <永久ID或批次> [--落盘 --批准 <SHA-256>]")
        出("✗ %s" % arg_error)
        return 2
    if not re.fullmatch(r"K\d{4}(-K\d{4})?", kid):
        出("✗ 永久 ID 形如 K0001，批次形如 K0019-K0021。收到：%s" % kid)
        return 2
    if approval is not None and not re.fullmatch(r"[0-9a-f]{64}", approval):
        出("✗ 批准摘要必须是完整的 64 位 SHA-256")
        return 2

    try:
        # v3.0 在这里隐式恢复。恢复是一次写入，即使是"试算"也会改正式文件，
        # 与"试算不碰正式文件"的承诺直接冲突。改成拒绝并让用户显式决定。
        _pending = 事务.inspect(project)
        if _pending is not None:
            出("✗ 项目存在未完成的事务 %s（%s）。" % (_pending["id"] or "日志损坏", _pending["phase"]))
            出("  %s。" % _pending["detail"])
            出("  确认现状后运行 python3 novel.py recover，再回来试算。")
            出("  本次没有改动任何正式文件。")
            return 2
        project_data = core.load_project(project)
        kids, batch_error = 引擎.解析批次(project, kid)
        if batch_error:
            raise core.ProjectError(batch_error)
        exact, patterns = 允许路径(project, kid, project_data, kids)
    except Exception as exc:
        出("✗ 项目无法进入落盘流程：%s" % exc)
        return 2

    candidate_root = os.path.join(project, "_候选", kid)
    出("=" * 60)
    出("落盘闸门 · %s · %s" % (kid, "正式落盘" if apply else "试算（不碰正式文件）"))
    if len(kids) > 1:
        出("批次：%s（一个摘要、一笔事务；闸门逐章执行）" % "、".join(kids))
    出("=" * 60)
    if (not os.path.isdir(candidate_root)
            or core.path_has_symlink(project, "_候选/" + kid)):
        出("✗ 候选区不存在或不是普通目录：%s" % candidate_root)
        return 1
    entries, collect_errors = 收候选(candidate_root)
    if collect_errors:
        出("✗ 候选区含不安全对象：")
        for error in collect_errors:
            出("    · " + error)
        return 1
    if not entries:
        出("✗ 候选区为空。输入缺失不等于没有问题。")
        return 1
    path_errors = 核候选路径(project, entries, exact, patterns)
    if path_errors:
        出("✗ 候选文件路径不合法：")
        for error in path_errors:
            出("    · " + error)
        出("  章节提交只能修改章节正文、章卡、梗概和声明过的运行账本；系统与固定设定必须走独立维护。")
        return 1

    manifest_rows, digest = 候选摘要(project, kid, entries, kids)
    changed = [row for row in manifest_rows
               if row["before_sha256"] != row["candidate_sha256"]]
    if not changed:
        出("✗ 候选与正式文件逐字节相同，这一章没有实际改动。")
        return 1
    出("候选文件 %d 份（完整摘要）：" % len(manifest_rows))
    for row in manifest_rows:
        出("    [%s] %s" % ("新增" if row["state"] == "add" else "替换", row["path"]))
        出("      BEFORE   %s" % (row["before_sha256"] or "(不存在)"))
        出("      CANDIDATE %s  %d bytes" % (row["candidate_sha256"], row["size"]))

    出()
    出("— 在影子项目运行受信任闸门 —")
    temp_root, shadow = 建影子(project)
    graph_bytes = None
    try:
        for item in entries:
            target = os.path.join(shadow, item["path"])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            core.atomic_write_bytes(target, item["data"])
        graph_run = subprocess.run(
            [sys.executable, os.path.join(project, "_工具", "生成图谱.py"), shadow],
            capture_output=True, text=True)
        graph_bytes = core.read_bytes(os.path.join(shadow, "图谱.html"))
        if graph_run.returncode != 0 or graph_bytes is None:
            出(graph_run.stdout.rstrip())
            if graph_run.stderr.strip():
                出("[图谱 stderr] " + graph_run.stderr.strip()[:800])
            出("✗ 影子图谱生成失败，正式文件没有改动。")
            return 1
        env = dict(os.environ)
        env["LUOPAN_SHADOW"] = "1"
        env["NOVEL_TRUSTED_TOOL_DIR"] = os.path.join(project, "_工具")
        失败 = []
        for one in kids:
            gate = subprocess.run(
                [sys.executable, os.path.join(project, "_工具", "提交包.py"), shadow, one]
                + (["--批末", kids[-1]] if len(kids) > 1 else []),
                capture_output=True, text=True, env=env)
            if gate.stdout.strip():
                出(gate.stdout.rstrip())
            if gate.stderr.strip():
                出("[闸门 stderr] " + gate.stderr.strip()[:800])
            if gate.returncode != 0:
                失败.append(one)
        if 失败:
            出()
            出("✗ 影子未通过（%s），正式文件没有改动。" % "、".join(失败))
            return 1
        出()
        出("✓ 影子通过。")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    validator_digest = 验证器摘要(project, project_data)
    出("CANDIDATE_SHA256=%s" % digest)
    出("VALIDATOR_SHA256=%s" % validator_digest)
    if not apply:
        出()
        出("※ 这是试算。完整阅读上面的候选清单后，使用：")
        # v2 在这里印的是字面的 <项目> 占位符，复制粘贴跑不通。
        出("  %s" % _建议命令(project, kid, digest))
        return 0
    if approval is None:
        出()
        出("✗ 正式落盘缺少 --approve <CANDIDATE_SHA256>，没有获得内容绑定的批准。")
        return 1
    if approval != digest:
        出()
        出("✗ 批准摘要与当前候选不一致。候选或正式基线已经变化，请重新试算和阅读。")
        出("  当前摘要：%s" % digest)
        return 1

    出()
    出("— 可恢复事务写入 —")
    review_output = {"text": ""}
    锁内 = {"rows": None}

    def 锁内复核():
        """**在事务锁内**重新读候选、重算摘要、比对批准值。

        v3.4 在锁外做这一步，然后才调 apply_changes 取锁。另一个进程可以
        插在中间提交同一批文件，旧批准仍然成功并覆盖它。检查和写入必须
        在同一把锁内完成，否则这道摘要闸门只是看起来严。
        """
        if core.path_has_symlink(project, "_候选/" + kid):
            raise 事务.TransactionError("候选路径经过符号链接，拒绝落盘")
        fresh_entries, fresh_errors = 收候选(candidate_root)
        fresh_path_errors = 核候选路径(project, fresh_entries, exact, patterns)
        fresh_rows, fresh_digest = 候选摘要(project, kid, fresh_entries, kids)
        if fresh_errors or fresh_path_errors or fresh_digest != digest:
            细节 = "；".join(fresh_errors + fresh_path_errors) or ("当前摘要 %s" % fresh_digest)
            raise 事务.TransactionError(
                "审批后候选或正式基线发生变化，拒绝落盘。请重新试算。  " + 细节)
        if 验证器摘要(project, project_data) != validator_digest:
            raise 事务.TransactionError("验证器在试算后发生变化，拒绝落盘。请重新试算。")
        锁内["rows"] = fresh_rows
        changes = {item["path"]: item["data"] for item in fresh_entries}
        changes["图谱.html"] = graph_bytes
        return {
            "changes": changes,
            "label": ("batch commit %s" if len(kids) > 1 else "chapter commit %s") % kid,
            "metadata": dict({
                "candidate_files": fresh_rows,
                "candidate_sha256": digest,
                "chapter_id": kid,
                "validator_sha256": validator_digest,
            }, **({"chapter_ids": list(kids)} if len(kids) > 1 else {})),
        }

    def 正式复核():
        env = dict(os.environ)
        env["NOVEL_TRUSTED_TOOL_DIR"] = os.path.join(project, "_工具")
        texts, ok = [], True
        for one in kids:
            run = subprocess.run(
                [sys.executable, os.path.join(project, "_工具", "提交包.py"), project, one]
                + (["--批末", kids[-1]] if len(kids) > 1 else []),
                capture_output=True, text=True, env=env)
            texts.append(run.stdout + (("\n[stderr] " + run.stderr) if run.stderr.strip() else ""))
            ok = ok and run.returncode == 0
        review_output["text"] = "\n".join(texts)
        return ok, "正式提交闸门未通过"

    try:
        tx = 事务.apply_changes(
            project, plan=锁内复核, validator=正式复核,
            fault_after=(os.environ.get("NOVEL_FAIL_AFTER")
                         if 事务._faults_enabled() else None),
            hard_crash_after=(os.environ.get("NOVEL_HARD_CRASH_AFTER")
                              if 事务._faults_enabled() else None))
    except BaseException as exc:
        if review_output["text"].strip():
            出(review_output["text"].rstrip())
        出()
        出("✗ 落盘未完成：%s" % exc)
        出("  如有待恢复事务，请按工具报告核对现场并显式恢复。")
        return 1
    if review_output["text"].strip():
        出(review_output["text"].rstrip())
    try:
        retained_path, changed_after_approval = 保留提交候选(project, kid, tx["id"], entries)
        出("  候选存根：%s（保留文件，不自动删除；不进入常规备份）" % retained_path)
        if changed_after_approval:
            出("△ 提交期间候选有新保存内容，尚未提交；请到上述存根核对后继续处理。")
    except Exception as exc:
        出("△ 正式提交已经完成，但候选未能移入存根，保留现场：%s" % exc)
    出()
    出("✓ 已落盘，正式复核通过。")
    if 锁内["rows"]:
        出("  锁内复核 %d 份候选文件，摘要与批准值逐字节一致。" % len(锁内["rows"]))
    出("  事务记录：.novel/commits/%s" % tx["id"])
    出("  候选摘要：%s" % digest)
    出("  ※ 通过只说明结构与账目自洽，不代替用户阅读正文。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
