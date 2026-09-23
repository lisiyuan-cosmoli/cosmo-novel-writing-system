#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""崩溃可恢复的多文件事务。

每个目标文件都通过同目录临时文件和 os.replace 更新。事务日志先于正式
写入落盘。普通异常当场回滚。

互斥由操作系统的 flock 持有，不由"谁能删掉锁文件"决定。v3.0 用
O_EXCL 建零字节锁、随后才写 PID，另一个进程能在这个窗口把空锁当成陈旧锁
删掉并再次取得锁——实测两个进程会同时认为自己独占。锁文件现在常驻，
内容只作诊断。锁文件必须常驻；删除再重建会换掉 inode，绕过原来的锁。

进程被强制终止后**不再隐式恢复**。恢复会改写正式文件，那是一次写入，
必须由用户显式运行 recover 触发。其余命令只报告状态。
"""
from __future__ import print_function

import datetime
import errno
import fcntl
import io
import json
import os
import stat
import time
import uuid

import v2_core as core


class TransactionError(RuntimeError):
    pass


def _faults_enabled():
    """故障注入只在自测显式打开时生效。

    v2 直接读 NOVEL_FAIL_AFTER / NOVEL_HARD_CRASH_AFTER / NOVEL_TX_CRASH_PHASE，
    用户环境里碰巧存在同名变量就会在提交中途硬杀进程。现在必须同时设置
    NOVEL_SELFTEST_FAULTS=1 才认。
    """
    return os.environ.get("NOVEL_SELFTEST_FAULTS") == "1"


def _meta_root(project):
    return os.path.join(os.path.abspath(project), ".novel")


def _journal_path(project):
    return os.path.join(_meta_root(project), "transaction.json")


def _lock_path(project):
    return os.path.join(_meta_root(project), "transaction.lock")


def _safe_path(project, rel, directory=False, required=False):
    """只读检查项目内完整路径；不能让元数据或恢复路径绕过提交边界。"""
    if not core.safe_relative(rel) or rel == ".":
        raise TransactionError("非法事务路径 %r" % rel)
    link = core.path_has_symlink(project, rel)
    if link:
        raise TransactionError("事务路径经过符号链接，拒绝读写：%s" % link)
    current = os.path.abspath(project)
    parts = rel.split("/")
    for index, part in enumerate(parts):
        current = os.path.join(current, part)
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            if required:
                raise TransactionError("事务所需路径不存在：%s" % current)
            continue
        except OSError as exc:
            raise TransactionError("事务路径无法检查：%s  %s" % (current, exc))
        is_dir = index < len(parts) - 1 or directory
        if not (stat.S_ISDIR(mode) if is_dir else stat.S_ISREG(mode)):
            raise TransactionError("事务路径类型不合法：%s" % current)
    return current


def _check_metadata(project):
    for rel in (".novel", ".novel/transactions", ".novel/commits"):
        _safe_path(project, rel, directory=True)
    for rel in (".novel/transaction.json", ".novel/transaction.lock", ".novel/HEAD"):
        _safe_path(project, rel)


def _write_json(project, rel, value):
    core.atomic_write_json(_safe_path(project, rel), value)


def _write_bytes(project, rel, data):
    target = _safe_path(project, rel)
    if data is None:
        _remove(target)
    else:
        core.atomic_write_bytes(target, data)


def _read_bytes(project, rel, required=False):
    path = _safe_path(project, rel, required=required)
    if not os.path.exists(path):
        return None
    data = core.read_bytes(path)
    if data is None:
        raise TransactionError("事务文件无法读取：%s" % path)
    return data


def _validate_manifest(value):
    if not isinstance(value, dict):
        raise TransactionError("事务清单不是对象")
    txid = value.get("id")
    if not isinstance(txid, str) or not core.safe_relative(txid) or "/" in txid or txid == ".":
        raise TransactionError("事务编号不合法")
    parent = value.get("parent")
    if parent is not None and (not isinstance(parent, str) or not core.safe_relative(parent)
                               or "/" in parent or parent == "."):
        raise TransactionError("事务父提交编号不合法")
    files = value.get("files")
    if (not isinstance(files, list) or not files
            or any(not isinstance(rel, str) or not core.safe_relative(rel)
                   or rel == "." or rel.split("/")[0] == ".novel" for rel in files)
            or len(set(files)) != len(files)):
        raise TransactionError("事务文件清单不完整或含非法路径")
    missing = value.get("missing_before", [])
    if (not isinstance(missing, list) or any(not isinstance(rel, str) for rel in missing)
            or len(set(missing)) != len(missing) or not set(missing).issubset(files)):
        raise TransactionError("事务 missing_before 清单不合法")
    for key in ("before_sha256", "after_sha256"):
        if key not in value:
            continue  # 旧日志没有 before 哈希；仍要求快照完整、可读。
        hashes = value[key]
        if (not isinstance(hashes, dict) or set(hashes) != set(files)
                or any(v is not None and (not isinstance(v, str) or len(v) != 64
                       or any(c not in "0123456789abcdef" for c in v)) for v in hashes.values())):
            raise TransactionError("事务 %s 摘要清单不完整" % key)
        if key == "before_sha256" and {rel for rel, h in hashes.items() if h is None} != set(missing):
            raise TransactionError("事务 before 摘要与缺失文件清单不一致")
    return value


def _record_root(project, journal):
    """按当前项目和 ID 定位，绝不跟随旧日志里的绝对路径。"""
    _validate_manifest(journal)
    roots = []
    for parent in ("transactions", "commits"):
        rel = ".novel/%s/%s" % (parent, journal["id"])
        path = _safe_path(project, rel, directory=True)
        if os.path.isdir(path):
            roots.append(rel)
    if len(roots) != 1:
        raise TransactionError("事务快照目录缺失或不唯一，保留日志等待处理：%s" % journal["id"])
    return roots[0]


def _before_changes(project, journal, root):
    """先读取并验证全部快照和目标，再允许第一笔恢复写入。"""
    _validate_manifest(journal)
    _safe_path(project, root + "/before", directory=True, required=True)
    _safe_path(project, root + "/manifest.json")
    missing = set(journal.get("missing_before", []))
    changes = {}
    for rel in journal["files"]:
        _safe_path(project, rel)
        path = root + "/before/" + rel
        data = _read_bytes(project, path, required=rel not in missing)
        if rel in missing and data is not None:
            raise TransactionError("原本不存在的文件却有 before 快照：%s" % rel)
        if "before_sha256" in journal:
            actual = core.sha256_bytes(data) if data is not None else None
            if actual != journal["before_sha256"][rel]:
                raise TransactionError("事务 before 快照摘要不符，保留日志：%s" % rel)
        changes[rel] = data
    return changes


def _verify_contents(project, changes):
    for rel, expected in changes.items():
        if _read_bytes(project, rel, required=expected is not None) != expected:
            raise TransactionError("事务写后内容核验失败，保留日志：%s" % rel)


def _read_lock(project):
    """返回锁内容。零字节或损坏一律当作**陈旧锁**，不让它把项目锁死。"""
    return core.load_json_lenient(_lock_path(project), {}) or {}


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _write_journal(project, journal):
    _write_json(project, ".novel/transaction.json", journal)


def _read_journal(project):
    """事务日志承载恢复信息，损坏时不能静默当作"没有事务"。"""
    _check_metadata(project)
    path = _journal_path(project)
    if not os.path.isfile(path):
        return None
    try:
        value = core.load_json(path)
    except core.ProjectError as exc:
        raise TransactionError(
            "事务日志损坏，无法自动恢复：%s\n"
            "  正式文件可能停在中途状态。请先 python3 novel.py backup 保住现状，\n"
            "  再对照 .novel/transactions/ 下最新一笔的 before/ 手工还原，\n"
            "  确认无误后删除该日志文件。原始错误：%s" % (path, exc))
    return _validate_manifest(value)


def _remove(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _acquire(project):
    """取得项目的排他写锁。返回必须一直持有到事务结束的文件描述符。

    互斥由 flock 保证，与锁文件内容无关：零字节锁、损坏锁、别人手工建的
    锁都不会让两个进程同时进来。锁文件**不删除**——flock 绑定的是 inode，
    先 unlink 再让别人重建会直接绕过互斥。
    """
    _check_metadata(project)
    core.safe_output_dir(project, ".novel/transactions")
    core.safe_output_dir(project, ".novel/commits")
    lock = _safe_path(project, ".novel/transaction.lock")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            raise TransactionError("事务锁必须是独立普通文件：%s" % lock)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        holder = _read_lock(project)
        os.close(fd)
        if exc.errno not in (errno.EACCES, errno.EAGAIN):
            raise TransactionError(
                "无法在这个位置加文件锁：%s\n"
                "  云同步盘与网络文件系统可能不支持 flock。把项目放到本地磁盘再试。\n"
                "  原始错误：%s" % (lock, exc))
        raise TransactionError(
            "另一个事务正在运行，PID %s，开始于 %s。等它结束再试。"
            % (holder.get("pid", "未知"), holder.get("started_at", "未知")))
    try:
        payload = json.dumps({"pid": os.getpid(), "started_at": core.utc_now()},
                             ensure_ascii=False).encode("utf-8")
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, payload)
        os.fsync(fd)
    except OSError:
        pass                      # 诊断内容写不进去不影响互斥
    return fd


def _release(handle):
    if handle is None:
        return
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(handle)
    except OSError:
        pass


def _restore(project, journal):
    root = _record_root(project, journal)
    changes = _before_changes(project, journal, root)
    for rel in reversed(journal["files"]):
        _write_bytes(project, rel, changes[rel])
    _verify_contents(project, changes)
    return root


def _finish_commit(project, journal, root):
    """已移动到 commits 的中断事务须与已验证内容一致，才登记 HEAD。"""
    current_head = _parent_head(project)
    if current_head not in (journal.get("parent"), journal["id"]):
        raise TransactionError(
            "HEAD 与中断事务的父提交不一致，拒绝覆盖并保留日志：当前 %s，父提交 %s，事务 %s"
            % (current_head, journal.get("parent"), journal["id"]))
    _before_changes(project, journal, root)
    hashes = journal.get("after_sha256")
    if not hashes:
        raise TransactionError("已验证事务缺少 after 摘要，保留日志等待处理")
    _safe_path(project, root + "/after", directory=True, required=True)
    changes = {}
    for rel in journal["files"]:
        data = _read_bytes(project, root + "/after/" + rel, required=hashes[rel] is not None)
        actual = core.sha256_bytes(data) if data is not None else None
        if actual != hashes[rel]:
            raise TransactionError("事务 after 快照摘要不符，保留日志：%s" % rel)
        changes[rel] = data
    _verify_contents(project, changes)
    journal["phase"] = "committed"
    journal["committed_at"] = journal.get("committed_at") or core.utc_now()
    # 绝对字段仅保留旧格式兼容性；本模块定位与读写都使用受检的项目内路径。
    journal["transaction_root"] = os.path.join(project, root)
    journal["commit_dir"] = os.path.join(project, root)
    _write_json(project, root + "/manifest.json", journal)
    _write_bytes(project, ".novel/HEAD", (journal["id"] + "\n").encode("utf-8"))
    _remove(_safe_path(project, ".novel/transaction.json"))


def inspect(project):
    """**只读**探查未完成事务。任何情况下都不写文件。

    返回 None 或 {'state', 'id', 'phase', 'detail'}：
      pending  写到一半，需要 recover 回到事务前
      ready    已经通过验证，recover 会把它补完
      corrupt  日志损坏，只能人工处理
    """
    project = os.path.abspath(project)
    try:
        journal = _read_journal(project)
        root = _record_root(project, journal) if journal is not None else None
    except TransactionError as exc:
        return {"state": "corrupt", "id": None, "phase": None, "detail": str(exc)}
    if journal is None:
        return None
    ready = (journal.get("phase") in ("commit_ready", "committed")
             and root.startswith(".novel/commits/"))
    return {
        "state": "ready" if ready else "pending",
        "id": journal.get("id"),
        "phase": journal.get("phase"),
        "files": journal.get("files", []),
        "detail": ("中断前已经通过验证，恢复会把它补完"
                   if ready else "写到一半，恢复会退回事务开始前"),
    }


def _pending_guard(project):
    """写命令的统一入口检查。有未完成事务就停，不代替用户决定恢复。"""
    state = inspect(project)
    if state is None:
        return
    if state["state"] == "corrupt":
        raise TransactionError(state["detail"])
    raise TransactionError(
        "发现未完成的事务 %s（%s）。\n"
        "  它涉及 %d 份文件。%s。\n"
        "  确认现状后显式运行：python3 novel.py recover\n"
        "  在那之前本命令不会改动任何正式文件。"
        % (state["id"], state["phase"], len(state.get("files") or []), state["detail"]))


def recover(project, quiet=False):
    """**唯一**会因中断而改写正式文件的入口。必须由用户显式触发。"""
    project = os.path.abspath(project)
    handle = _acquire(project)
    try:
        journal = _read_journal(project)
        if journal is None:
            return False
        root = _record_root(project, journal)
        if (journal.get("phase") in ("commit_ready", "committed")
                and root.startswith(".novel/commits/")):
            _finish_commit(project, journal, root)
            if not quiet:
                print("✓ 已完成中断前已经通过验证的事务 %s" % journal.get("id"))
            return True
        root = _restore(project, journal)
        journal["phase"] = "recovered"
        journal["recovered_at"] = core.utc_now()
        journal["transaction_root"] = os.path.join(project, root)
        _write_json(project, root + "/manifest.json", journal)
        _remove(_safe_path(project, ".novel/transaction.json"))
        if not quiet:
            print("✓ 已恢复中断事务 %s，正式文件回到事务开始前" % journal.get("id"))
        return True
    finally:
        _release(handle)


def _parent_head(project):
    data = _read_bytes(project, ".novel/HEAD")
    if data is None:
        return None
    try:
        value = data.decode("utf-8").strip()
    except UnicodeError:
        raise TransactionError("事务 HEAD 无法解析")
    if value and (not core.safe_relative(value) or "/" in value or value == "."):
        raise TransactionError("事务 HEAD 编号不合法")
    return value or None


def head(project):
    """当前 HEAD 事务号。供 history、status 标注"哪一笔才是现在生效的"。"""
    return _parent_head(os.path.abspath(project))


def ordered_commits(project):
    """按提交时间升序返回 [(事务号, 清单)]。

    不直接按目录名排序：v2 的事务号只到秒，同一秒内的多笔会被随机后缀打乱。
    这里以清单里的 created_at 为主键，事务号做次键，兼容旧项目。
    """
    root = _safe_path(project, ".novel/commits", directory=True)
    if not os.path.isdir(root):
        return []
    rows = []
    for name in os.listdir(root):
        rel = ".novel/commits/%s/manifest.json" % name
        value = core.load_json_lenient(_safe_path(project, rel))
        if value:
            rows.append((value.get("created_at") or "", name, value))
    rows.sort(key=lambda row: (row[0], row[1]))
    return [(name, value) for _, name, value in rows]


def undone_ids(project):
    """已经被撤销、当前不生效的事务号集合。

    rollback 本身也是一笔提交，所以 history 里会同时存在"被撤销的那笔"和
    "撤销它的那笔"。不标出来，用户会把已经撤销的章节当成还在项目里。
    撤销一笔 rollback 等于重做，被它撤销的那笔要重新算作生效。
    """
    rolled_back_by = {}        # 事务号 -> 它撤销了哪一笔
    undone = set()
    for name, value in ordered_commits(project):
        target = (value.get("metadata") or {}).get("rollback_of")
        if not isinstance(target, str) or not target:
            continue
        rolled_back_by[name] = target
        # 撤销 rollback 会逐层反转它先前的效果。只处理两层会在第三次
        # rollback 时漏掉原提交。seen 同时防止损坏元数据形成循环。
        seen = set()
        while target and target not in seen:
            seen.add(target)
            if target in undone:
                undone.remove(target)
            else:
                undone.add(target)
            target = rolled_back_by.get(target)
    return undone


def _normalize(changes):
    normalized = {}
    for rel, data in (changes or {}).items():
        rel = rel.replace(os.sep, "/")
        if not core.safe_relative(rel) or rel == "." or rel.split("/")[0] == ".novel":
            raise TransactionError("非法相对路径 %r" % rel)
        if data is not None and not isinstance(data, bytes):
            raise TransactionError("变更内容必须是 bytes 或 None  %s" % rel)
        normalized[rel] = data
    return normalized


def apply_changes(project, changes=None, label=None, validator=None, fault_after=None,
                  hard_crash_after=None, metadata=None, plan=None):
    """应用 {相对路径: bytes 或 None}。None 表示删除。

    plan 是**在锁内**执行的计划函数，返回 {"changes","label","metadata"}。
    需要"读当前状态 → 校验 → 决定写什么"的调用方必须用 plan：v3.4 让上层
    先在锁外重算候选摘要、再调本函数取锁，两者之间另一个进程可以提交新内容，
    旧批准仍会成功并覆盖它。检查和写入必须在同一把锁内完成。

    validator 在文件全部替换后运行，应返回 True、(True, message) 或
    (False, message)。验证失败会恢复原文件。
    """
    project = os.path.abspath(project)
    if not os.path.isdir(project):
        raise TransactionError("项目目录不存在 %s" % project)
    if plan is None and not changes:
        raise TransactionError("事务没有任何变更")

    # 取锁之后的**每一行**都要被 finally 覆盖。v3.4 在这里到主 try 之间留了
    # makedirs、逐文件快照和写日志三步，任何一步抛异常锁都留在进程里，
    # 而 flock 绑的是打开文件描述符——同一个进程重开也拿不到，只能退出。
    handle = _acquire(project)
    已交接 = False
    try:
        _pending_guard(project)
        if plan is not None:
            结果 = plan()
            if not isinstance(结果, dict):
                raise TransactionError("plan 必须返回字典")
            changes = 结果.get("changes")
            label = 结果.get("label", label)
            metadata = 结果.get("metadata", metadata)
            if not changes:
                raise TransactionError("事务没有任何变更")
        normalized = _normalize(changes)
        journal = _准备(project, normalized, label, metadata)
        已交接 = True
    finally:
        if not 已交接:
            _release(handle)
    return _执行(project, handle, journal, normalized, validator,
                fault_after, hard_crash_after)


def _准备(project, normalized, label, metadata):
    """在锁内建事务目录、抓 before 快照、写日志。返回日志。"""
    # 同一秒内可能落多笔（如插件批量安装、自测）。v2 只到秒，随机后缀会让
    # 按名字排序的 history 与 undone_ids 拿到错误顺序，所以补上微秒。
    now = datetime.datetime.now()
    txid = now.strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:6]
    tx_root = ".novel/transactions/" + txid
    files = sorted(normalized)
    # 整份目标清单先检查；任何坏路径都不能留下半套正式写入。
    for rel in files:
        _safe_path(project, rel)
    _safe_path(project, tx_root, directory=True)
    os.mkdir(os.path.join(project, tx_root))
    core.safe_output_dir(project, tx_root + "/before")
    core.safe_output_dir(project, tx_root + "/after")
    missing = []
    hashes = {}
    for rel in files:
        data = _read_bytes(project, rel)
        if data is None:
            missing.append(rel)
        else:
            _write_bytes(project, tx_root + "/before/" + rel, data)
        hashes[rel] = core.sha256_bytes(data) if data is not None else None
        if normalized[rel] is not None:
            _write_bytes(project, tx_root + "/after/" + rel, normalized[rel])

    journal = {
        "applied": [],
        "created_at": core.utc_now(),
        "files": files,
        "id": txid,
        "label": label,
        "metadata": metadata or {},
        "missing_before": missing,
        "before_sha256": hashes,
        "parent": _parent_head(project),
        "phase": "prepared",
        "pid": os.getpid(),
        "transaction_root": os.path.join(project, tx_root),
    }
    _write_journal(project, journal)
    return journal


def _执行(project, handle, journal, normalized, validator,
         fault_after, hard_crash_after):
    files = journal["files"]
    txid = journal["id"]
    tx_root = ".novel/transactions/" + txid
    moved_to_commits = False
    try:
        journal["phase"] = "applying"
        _write_journal(project, journal)
        for index, rel in enumerate(files, 1):
            data = normalized[rel]
            _write_bytes(project, rel, data)
            journal["applied"].append(rel)
            _write_journal(project, journal)
            if _faults_enabled():
                if hard_crash_after is not None and index == int(hard_crash_after):
                    os._exit(97)
                if fault_after is not None and index == int(fault_after):
                    raise TransactionError("测试注入故障，已写入 %d 个文件" % index)

        journal["phase"] = "validating"
        _write_journal(project, journal)
        if validator:
            result = validator()
            if isinstance(result, tuple):
                passed, detail = result
            else:
                passed, detail = bool(result), ""
            if not passed:
                raise TransactionError("写后验证失败  %s" % detail)
        _verify_contents(project, normalized)

        journal["phase"] = "commit_ready"
        journal["committed_at"] = core.utc_now()
        for rel in files:
            data = normalized[rel]
            journal.setdefault("after_sha256", {})[rel] = core.sha256_bytes(data) if data is not None else None
        commit_dir = ".novel/commits/" + txid
        journal["commit_dir"] = os.path.join(project, commit_dir)
        _write_journal(project, journal)
        _write_json(project, tx_root + "/manifest.json", journal)
        if _faults_enabled() and os.environ.get("NOVEL_TX_CRASH_PHASE") == "before_commit_move":
            os._exit(98)
        source = _safe_path(project, tx_root, directory=True, required=True)
        target = _safe_path(project, commit_dir, directory=True)
        if os.path.exists(target):
            raise TransactionError("提交目录已存在，拒绝覆盖：%s" % target)
        os.replace(source, target)
        moved_to_commits = True
        if _faults_enabled() and os.environ.get("NOVEL_TX_CRASH_PHASE") == "after_commit_move":
            os._exit(99)
        _finish_commit(project, journal, commit_dir)
        _release(handle)
        return journal
    except BaseException:
        try:
            # 已验证的目录一旦进入 commits，后续登记故障留给显式 recover 补完，
            # 不把正式文件退回却留下一个已经前移的 HEAD。
            if not moved_to_commits:
                record_root = _restore(project, journal)
                journal["phase"] = "rolled_back"
                journal["rolled_back_at"] = core.utc_now()
                journal["transaction_root"] = os.path.join(project, record_root)
                _write_json(project, record_root + "/manifest.json", journal)
                _remove(_safe_path(project, ".novel/transaction.json"))
        finally:
            _release(handle)
        raise


def rollback_last(project, expect_head=None):
    """回退最近一笔提交。

    HEAD、目标清单和快照全部**在锁内**读取。v3.4 先读 HEAD 再进加锁写入，
    并发提交可以插在两者之间，然后被这次回退按旧目标覆盖掉。

    expect_head 不为空时，锁内看到的 HEAD 必须与它一致，否则整笔停止——
    给"先看 history 再决定回退哪一笔"的调用方用。
    """
    project = os.path.abspath(project)
    记 = {}

    def 计划():
        head = _parent_head(project)
        if not head:
            raise TransactionError("没有可回退的提交")
        if expect_head and head != expect_head:
            raise TransactionError(
                "HEAD 已经变了：你看到的是 %s，现在是 %s。\n"
                "  期间有新的提交落盘。请重新运行 python3 novel.py history 确认后再回退。"
                % (expect_head, head))
        commit = ".novel/commits/" + head
        manifest = core.load_json(_safe_path(project, commit + "/manifest.json", required=True))
        if not manifest:
            raise TransactionError("HEAD 指向的提交缺少清单 %s" % head)
        _validate_manifest(manifest)
        if manifest["id"] != head:
            raise TransactionError("HEAD 与提交清单编号不一致")
        changes = _before_changes(project, manifest, commit)
        记["id"] = head
        记["label"] = manifest.get("label", "")
        return {"changes": changes, "label": "rollback %s" % head,
                "metadata": {"rollback_of": head, "rollback_of_label": 记["label"]}}

    tx = apply_changes(project, plan=计划)
    tx["_undone"] = {"id": 记.get("id"), "label": 记.get("label", "")}
    return tx


def history(project, limit=20):
    """最近的提交，最新在前。"""
    rows = [value for _, value in ordered_commits(project)]
    rows.reverse()
    return rows[:limit]
