#!/usr/bin/env python3
"""Download-folder startup regressions. All writes stay in temporary copies."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '_工具'))
import 新建项目 as startup
import v2_core as core
import 事务 as tx


class StartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cosmo-start-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.book = self.base / 'download'
        shutil.copytree(ROOT, self.book, ignore=shutil.ignore_patterns('.git', '__pycache__'))

    def command(self, *args, env=None):
        return subprocess.run([sys.executable, '-B', str(self.book / 'novel.py')] + list(args),
                              cwd=self.book, text=True, capture_output=True, env=env)

    def snapshot(self, include_runtime=False):
        return {p.relative_to(self.book).as_posix(): p.read_bytes()
                for p in self.book.rglob('*') if p.is_file() and
                (include_runtime or '.novel' not in p.relative_to(self.book).parts)}

    def start(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return startup.原地开始(str(self.book), **kwargs)

    def test_start_preserves_material_and_can_prepare_foundation(self):
        (self.book / 'my-notes.md').write_text('Original story notes.\n')
        before = self.snapshot()
        out = self.command('start')
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        after = self.snapshot()
        retired = {'_工具/我是母版.txt', '_工具/母版禁词.txt', '_工具/母版检查.py'}
        self.assertEqual(set(before) - set(after), retired)
        self.assertEqual(set(after) - set(before), {'project.json'})
        for name in set(before) & set(after):
            self.assertEqual(before[name], after[name], name)
        identity = core.load_project(str(self.book))
        self.assertEqual(identity['initialization']['status'], 'draft')
        self.assertEqual(identity['plugin_decision'], 'undecided')
        self.assertTrue(identity['system_file_hashes'])
        self.assertEqual(self.command('plugin', 'none').returncode, 0)
        doctor = self.command('doctor')
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertEqual(self.command('foundation', '--prepare').returncode, 0)
        self.assertTrue((self.book / '_候选/INIT').is_dir())

    def test_repeated_start_is_read_only_even_with_candidates(self):
        self.start()
        (self.book / '_候选').mkdir()
        (self.book / '_候选/note.md').write_text('Keep my draft.')
        before = self.snapshot(True)
        out = self.command('start')
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(before, self.snapshot(True))

    def test_corrupt_identity_is_not_reset(self):
        (self.book / 'project.json').write_text('{broken')
        before = self.snapshot(True)
        self.assertNotEqual(self.command('start').returncode, 0)
        self.assertEqual(before, self.snapshot(True))

    def test_existing_body_without_identity_is_not_registered(self):
        (self.book / '05_正文/K0001.md').write_text('Existing chapter.')
        before = self.snapshot()
        self.assertNotEqual(self.command('start').returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_missing_file_and_symlink_are_rejected(self):
        path = self.book / '00_设定层/01_固定设定.md'
        saved = path.read_bytes()
        path.unlink()
        self.assertNotEqual(self.command('start').returncode, 0)
        outside = self.base / 'outside.md'
        outside.write_bytes(saved)
        path.symlink_to(outside)
        self.assertNotEqual(self.command('start').returncode, 0)
        self.assertEqual(outside.read_bytes(), saved)
        self.assertFalse((self.book / 'project.json').exists())

    def test_partial_failure_restores_download_and_can_retry(self):
        before = self.snapshot()
        with patch.dict(os.environ, {'NOVEL_SELFTEST_FAULTS': '1'}):
            with self.assertRaises(tx.TransactionError):
                self.start(fault_after=2)
        self.assertEqual(before, self.snapshot())
        self.assertIsNone(tx.inspect(str(self.book)))
        self.assertTrue(self.start())

    def test_interrupted_start_requires_explicit_recovery(self):
        before = self.snapshot()
        env = dict(os.environ, NOVEL_SELFTEST_FAULTS='1',
                   NOVEL_TX_CRASH_PHASE='before_commit_move')
        result = self.command('start', env=env)
        self.assertEqual(result.returncode, 98)
        self.assertIsNotNone(tx.inspect(str(self.book)))
        interrupted = self.snapshot(True)
        self.command('start')
        self.assertEqual(interrupted, self.snapshot(True))
        result = self.command('recover')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(self.start())

    def test_old_init_project_start_remains_read_only(self):
        old = self.base / 'old-book'
        result = self.command('init', str(old))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.book = old
        before = self.snapshot(True)
        result = self.command('start')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot(True))

    def test_concurrent_start_keeps_one_identity_and_one_commit(self):
        args = [sys.executable, '-B', str(self.book / 'novel.py'), 'start']
        procs = [subprocess.Popen(args, cwd=self.book, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outputs = [p.communicate(timeout=30) for p in procs]
        self.assertTrue(any(p.returncode == 0 for p in procs), outputs)
        core.load_project(str(self.book))
        self.assertEqual(len(tx.ordered_commits(str(self.book))), 1)
        self.assertIsNone(tx.inspect(str(self.book)))


if __name__ == '__main__':
    unittest.main()
