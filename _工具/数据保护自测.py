#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6.0 数据保护回归：候选保存、备份一致性、插件并发与连续回退。

所有写入限于临时沙盒。测试复用真实事务与现行建书/章节夹具，不访问作品。
"""
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
import warnings
from unittest.mock import patch

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "_工具") not in sys.path:
    sys.path.insert(0, str(ROOT / "_工具"))

import v2_core as core
import 事务 as tx
import 备份 as backup
import 落盘 as commit
import 插件 as plugin
import 发布自测 as fixtures
import 新书自测 as book


class DataProtectionTests(unittest.TestCase):
    def setUp(self):
        # 复用的旧夹具直接 open(...).read/write；只收敛这两份夹具的
        # 既有警告，数据保护实现的新警告仍正常显示。
        warnings.filterwarnings("ignore", category=ResourceWarning, module=r"(?:发布自测|新书自测)$")
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"新书自测$")
        self.sandbox = tempfile.TemporaryDirectory(prefix="novel-data-protection-")
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name)

    def small_project(self, name="project"):
        project = self.root / name
        project.mkdir()
        (project / "a.txt").write_bytes(b"old-a")
        (project / "b.txt").write_bytes(b"old-b")
        return project

    def new_book(self, name="book"):
        return fixtures.init_project(str(self.root), name)

    def command(self, project, code, env=None):
        source = "import sys;sys.path.insert(0,sys.argv[1]);import 事务 as tx\n" + code
        return subprocess.run([sys.executable, "-c", source, str(ROOT / "_工具"), str(project)],
                              capture_output=True, text=True, env=env, timeout=20)

    @contextlib.contextmanager
    def after_first_member(self, action):
        original = tarfile.TarFile.addfile
        fired = []
        def wrapped(archive, info, fileobj=None):
            result = original(archive, info, fileobj)
            if info.name == "a.txt" and not fired:
                fired.append(True)
                action()
            return result
        with patch.object(tarfile.TarFile, "addfile", wrapped):
            yield fired

    def test_candidate_new_save_survives_real_commit(self):
        project = self.new_book()
        book.填全(project)
        book.开书(project)
        book.章卡(project)
        candidate = Path(fixtures.prepare_chapter_candidate(project))
        body = candidate / "05_正文/K0001.md"
        approved = body.read_bytes()
        preview = io.StringIO()
        with contextlib.redirect_stdout(preview):
            self.assertEqual(commit.main([project, "K0001"]), 0)
        digest = re.search(r"^CANDIDATE_SHA256=([0-9a-f]{64})$", preview.getvalue(), re.M)
        self.assertIsNotNone(digest, preview.getvalue()[-2000:])
        original = subprocess.run
        saved = []
        new_bytes = approved + "\n提交期间保存的新文字，尚未批准。\n".encode()
        def during_postcheck(args, *a, **kw):
            result = original(args, *a, **kw)
            if (len(args) > 2 and str(args[1]).endswith("/提交包.py")
                    and args[2] == project and not saved):
                body.write_bytes(new_bytes)
                saved.append(True)
            return result
        output = io.StringIO()
        with patch.object(subprocess, "run", during_postcheck), contextlib.redirect_stdout(output):
            result = commit.main([project, "K0001", "--落盘", "--approve", digest.group(1)])
        self.assertEqual(result, 0, output.getvalue()[-2000:])
        self.assertTrue(saved)
        self.assertFalse(candidate.exists())
        self.assertEqual((Path(project) / "05_正文/K0001.md").read_bytes(), approved)
        retained = list((Path(project) / "06_归档/_候选存根").glob("*/候选/05_正文/K0001.md"))
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].read_bytes(), new_bytes)
        self.assertIn("尚未提交", output.getvalue())
        self.assertIn("不进入常规备份", output.getvalue())

    def test_candidate_open_handle_and_recreated_source_survive(self):
        project = self.small_project()
        candidate = project / "_候选/K0001"
        candidate.mkdir(parents=True)
        body = candidate / "body.md"
        body.write_bytes(b"approved")
        entries, errors = commit.收候选(str(candidate))
        self.assertEqual(errors, [])
        with body.open("ab") as editor:
            rel, changed = commit.保留提交候选(str(project), "K0001", "transaction-one", entries)
            self.assertFalse(changed)
            candidate.mkdir()
            (candidate / "next.md").write_bytes(b"next candidate")
            editor.write(b" saved after comparison")
            editor.flush()
        self.assertEqual((project / rel / "body.md").read_bytes(), b"approved saved after comparison")
        self.assertEqual((candidate / "next.md").read_bytes(), b"next candidate")
        self.assertTrue(core.load_exclusions().跳过(rel))

    def test_candidate_storage_never_overwrites_or_follows_links(self):
        project = self.small_project()
        candidate = project / "_候选/K0001"
        candidate.mkdir(parents=True)
        (candidate / "body.md").write_bytes(b"new")
        reserved = project / "06_归档/_候选存根/K0001-duplicate"
        reserved.mkdir(parents=True)
        (reserved / "sentinel").write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            commit.保留提交候选(str(project), "K0001", "duplicate", [])
        self.assertEqual((candidate / "body.md").read_bytes(), b"new")
        self.assertEqual((reserved / "sentinel").read_bytes(), b"keep")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "sentinel").write_bytes(b"outside")
        linked = project / "_候选/K0002"
        linked.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(tx.TransactionError):
            commit.保留提交候选(str(project), "K0002", "link", [])
        self.assertTrue(linked.is_symlink())
        self.assertEqual((outside / "sentinel").read_bytes(), b"outside")

    def test_backup_unreadable_directory_is_an_error(self):
        project = self.small_project()
        blocked = project / "05_正文"
        blocked.mkdir()
        (blocked / "K0001.md").write_text("不能漏掉的正文", encoding="utf-8")
        original = os.scandir
        def unreadable(path):
            if os.path.abspath(path) == str(blocked):
                raise PermissionError(errno.EACCES, "test directory denied", str(blocked))
            return original(path)
        with patch.object(os, "scandir", unreadable):
            files, unsafe = backup.scan(str(project))
            self.assertTrue(unsafe)
            with self.assertRaisesRegex(RuntimeError, "目录无法读取"):
                backup.create(str(project))
        self.assertEqual(list((project / "_备份").glob("*.tar.gz")), [])
        self.assertEqual((blocked / "K0001.md").read_text(encoding="utf-8"), "不能漏掉的正文")

    def test_backup_blocks_concurrent_transaction_and_releases_lock(self):
        project = self.small_project()
        attempts = []
        def concurrent_write():
            attempts.append(self.command(project, "tx.apply_changes(sys.argv[2], {'a.txt':b'new-a','b.txt':b'new-b'})"))
        with self.after_first_member(concurrent_write):
            archive, manifest = backup.create(str(project))
        self.assertEqual(len(attempts), 1)
        self.assertNotEqual(attempts[0].returncode, 0)
        self.assertIn("另一个事务正在运行", attempts[0].stderr)
        self.assertEqual(manifest["source_state"], "consistent")
        with tarfile.open(archive) as packed:
            self.assertEqual(packed.extractfile("a.txt").read(), b"old-a")
            self.assertEqual(packed.extractfile("b.txt").read(), b"old-b")
        result = self.command(project, "tx.apply_changes(sys.argv[2], {'a.txt':b'new-a','b.txt':b'new-b'})")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_backup_pending_snapshot_preserves_journal_and_marks_manifest(self):
        project = self.small_project()
        env = dict(os.environ, NOVEL_SELFTEST_FAULTS="1")
        result = self.command(project, "tx.apply_changes(sys.argv[2], {'a.txt':b'new-a','b.txt':b'new-b'}, hard_crash_after=1)", env)
        self.assertEqual(result.returncode, 97)
        journal = project / ".novel/transaction.json"
        before = journal.read_bytes()
        archive, manifest = backup.create(str(project))
        self.assertEqual(manifest["source_state"], "interrupted")
        self.assertEqual(manifest["pending_transaction"]["state"], "pending")
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual((project / "a.txt").read_bytes(), b"new-a")
        self.assertEqual((project / "b.txt").read_bytes(), b"old-b")
        self.assertEqual(backup.verify(archive)["source_state"], "interrupted")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(backup.main(["restore", archive, str(self.root / "pending-restored")]), 0)
        self.assertIn("未完成事务现场", output.getvalue())
        self.assertNotIn("可以继续写", output.getvalue())

    def test_backup_corrupt_journal_can_still_preserve_current_files(self):
        project = self.small_project()
        (project / ".novel").mkdir()
        journal = project / ".novel/transaction.json"
        journal.write_bytes(b"not json")
        archive, manifest = backup.create(str(project))
        self.assertEqual(manifest["pending_transaction"]["state"], "corrupt")
        self.assertEqual(journal.read_bytes(), b"not json")
        self.assertEqual(len(backup.verify(archive)["files"]), 2)

    def test_backup_external_file_and_directory_changes_rejected(self):
        for change in ("edit", "add_file", "delete_file", "add_dir", "delete_dir", "replace_parent"):
            with self.subTest(change=change):
                project = self.small_project(change)
                (project / "empty").mkdir()
                def modify():
                    if change == "edit": (project / "a.txt").write_bytes(b"edited after capture")
                    elif change == "add_file": (project / "c.txt").write_bytes(b"added")
                    elif change == "delete_file": (project / "a.txt").unlink()
                    elif change == "add_dir": (project / "new-empty").mkdir()
                    elif change == "delete_dir": (project / "empty").rmdir()
                    else:
                        (project / "empty").rmdir()
                        (project / "empty").mkdir()
                with self.after_first_member(modify):
                    with self.assertRaisesRegex(RuntimeError, "发生变化"):
                        backup.create(str(project))
                self.assertEqual(list((project / "_备份").iterdir()), [])
                # Every failure also releases the shared lock.
                tx.apply_changes(str(project), {"probe.txt": b"lock released"})

    def test_backup_restore_bytes_and_permissions(self):
        project = self.small_project()
        (project / "a.txt").chmod(0o754)
        archive, manifest = backup.create(str(project))
        restored = self.root / "restored"
        backup.restore(archive, str(restored))
        for rel in ("a.txt", "b.txt"):
            self.assertEqual((restored / rel).read_bytes(), (project / rel).read_bytes())
        self.assertEqual((restored / "a.txt").stat().st_mode & 0o777, 0o754)

    @contextlib.contextmanager
    def before_plugin_lock(self, action):
        original = tx.apply_changes
        fired = []
        def wrapped(*a, **kw):
            if not fired:
                fired.append(True)
                action()
            return original(*a, **kw)
        with patch.object(tx, "apply_changes", wrapped):
            yield fired

    def test_plugin_operations_preserve_intervening_install(self):
        for operation in ("install", "none", "uninstall"):
            with self.subTest(operation=operation), contextlib.redirect_stdout(io.StringIO()):
                project = self.new_book(operation)
                if operation == "uninstall": plugin.install(project, "suspense")
                with self.before_plugin_lock(lambda: plugin.install(project, "romance")):
                    if operation == "install": plugin.install(project, "suspense")
                    elif operation == "none":
                        with self.assertRaisesRegex(RuntimeError, "已有启用插件"):
                            plugin.set_none(project)
                    else: plugin.uninstall(project, "suspense")
                current = core.load_project(project)
                expected = ["romance", "suspense"] if operation == "install" else ["romance"]
                self.assertEqual(current["enabled_plugins"], expected)
                self.assertTrue(plugin.verify(project, "romance")[0])

    def test_plugin_repeat_install_noop_does_not_hold_lock(self):
        project = self.new_book()
        with contextlib.redirect_stdout(io.StringIO()):
            plugin.install(project, "romance")
            previous = tx.head(project)
            plugin.install(project, "romance")
            self.assertEqual(tx.head(project), previous)
            plugin.install(project, "suspense")
        self.assertEqual(core.load_project(project)["enabled_plugins"], ["romance", "suspense"])

    def test_plugin_install_checks_new_target_content_inside_lock(self):
        project = self.new_book()
        manifest, _ = plugin._manifest("romance")
        rel = manifest["files"][0]["target"]
        def earlier_edit():
            tx.apply_changes(project, {rel: b"new authored data"})
        with self.before_plugin_lock(earlier_edit):
            with self.assertRaisesRegex(RuntimeError, "拒绝覆盖"):
                plugin.install(project, "romance")
        self.assertEqual((Path(project) / rel).read_bytes(), b"new authored data")
        self.assertNotIn("romance", core.load_project(project)["enabled_plugins"])

    def test_plugin_uninstall_checks_new_user_data_inside_lock(self):
        project = self.new_book()
        with contextlib.redirect_stdout(io.StringIO()):
            plugin.install(project, "romance")
        manifest, _ = plugin._manifest("romance")
        rel = next(item["target"] for item in manifest["files"] if item["owner"] == "user")
        original = (Path(project) / rel).read_bytes()
        new_bytes = original + "\n作者新保存的设定。\n".encode()
        with self.before_plugin_lock(lambda: tx.apply_changes(project, {rel: new_bytes})):
            with self.assertRaisesRegex(RuntimeError, "--force"):
                plugin.uninstall(project, "romance")
        self.assertEqual((Path(project) / rel).read_bytes(), new_bytes)
        self.assertIn("romance", core.load_project(project)["enabled_plugins"])

    def test_repeated_rollback_content_and_all_history_labels(self):
        project = self.small_project()
        first = tx.apply_changes(str(project), {"a.txt": b"new"})
        ids = [first["id"]]
        for count in range(1, 9):
            ids.append(tx.rollback_last(str(project))["id"])
            expected = {name for index, name in enumerate(ids[:-1]) if (count - index) % 2}
            self.assertEqual(tx.undone_ids(str(project)), expected, "rollback %d" % count)
            self.assertEqual((project / "a.txt").read_bytes(), b"old-a" if count % 2 else b"new")
        previous_undone = tx.undone_ids(str(project))
        separate = tx.apply_changes(str(project), {"b.txt": b"separate"})
        tx.rollback_last(str(project))
        self.assertEqual(tx.undone_ids(str(project)), previous_undone | {separate["id"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
