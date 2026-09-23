#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Current-template regressions for sparse revision writes and preserved modes."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

import v2_core as core
import 事务
import 结构复盘 as review
from 优化自测 import load

ROOT = Path(__file__).resolve().parent.parent


class RevisionEfficiencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='novel-revision-efficiency-')
        cls.parent = Path(cls.temp.name)
        cls.seed = cls.parent / 'seed'
        cls.fixture = load('新书自测')
        cls.release = load('发布自测')
        cls.call(cls.seed, 'init', str(cls.seed), launcher=ROOT)
        cls.fixture.开书(str(cls.seed))
        cls.fixture.章卡(str(cls.seed))
        cls.release.prepare_chapter_candidate(str(cls.seed))
        output = cls.call(cls.seed, 'commit', 'K0001')
        digest = re.search(r'^CANDIDATE_SHA256=([0-9a-f]{64})$', output, re.M).group(1)
        cls.call(cls.seed, 'commit', 'K0001', '--apply', '--approve', digest)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.fixture.本轮沙盘, ignore_errors=True)
        cls.temp.cleanup()

    @staticmethod
    def call(project, *args, launcher=None, good=True):
        root = launcher or project
        result = subprocess.run([sys.executable, '-B', str(root / 'novel.py'), *args],
                                cwd=root, capture_output=True, text=True)
        output = result.stdout + result.stderr
        if good and result.returncode:
            raise AssertionError(output)
        if not good and not result.returncode:
            raise AssertionError('Unexpected success: ' + output)
        return output

    def setUp(self):
        self.project = self.parent / self._testMethodName
        shutil.copytree(self.seed, self.project)

    def prepare_record(self):
        self.call(self.project, 'outline', '--prepare')
        output = self.call(self.project, 'revise')
        digest = re.search(r'^REVISION_SHA256=([0-9a-f]{64})$', output, re.M).group(1)
        return output, digest

    def fingerprint(self, rel):
        path = self.project / rel
        info = path.stat()
        return path.read_bytes(), stat.S_IMODE(info.st_mode), info.st_mtime_ns

    def test_record_only_writes_record_and_rollback_leaves_dependencies(self):
        protected = list(review.PLAN) + ['图谱.html']
        before = {rel: self.fingerprint(rel) for rel in protected}
        output, digest = self.prepare_record()
        self.assertIn('未改变，保留为批准依据，不重复写入', output)
        self.assertFalse((self.project / '_候选/REVISE_关联核对.json').exists())
        self.call(self.project, 'revise', '--apply', '--approve', digest)
        head = (self.project / '.novel/HEAD').read_text().strip()
        manifest = json.loads((self.project / '.novel/commits' / head / 'manifest.json').read_text())
        self.assertEqual(manifest['files'], [review.RECORD])
        self.assertEqual(len(manifest['metadata']['candidate_files']), 4)
        self.assertEqual(before, {rel: self.fingerprint(rel) for rel in protected})
        self.call(self.project, 'doctor')
        self.call(self.project, 'rollback')
        self.assertFalse((self.project / review.RECORD).exists())
        self.assertEqual(before, {rel: self.fingerprint(rel) for rel in protected})
        self.call(self.project, 'rollback')
        self.assertTrue((self.project / review.RECORD).exists())
        self.assertEqual(before, {rel: self.fingerprint(rel) for rel in protected})

    def test_unchanged_candidate_still_bound_to_approval(self):
        _, digest = self.prepare_record()
        target = self.project / '_候选/REVISE' / review.PLAN[0]
        target.write_text(target.read_text() + '\n合成的后续改动。\n')
        output = self.call(self.project, 'revise', '--apply', '--approve', digest, good=False)
        self.assertIn('批准摘要已失效', output)
        self.assertFalse((self.project / review.RECORD).exists())

    def test_same_graph_bytes_refresh_when_ledger_changes(self):
        import 体检
        tracked = 体检.graph_tracked_paths(str(self.project))
        stamp = time.time() - 20
        for rel in tracked + ['图谱.html']:
            path = self.project / rel
            if path.exists():
                os.utime(path, (stamp, stamp))
        graph_before = (self.project / '图谱.html').read_bytes()
        rel = '01_运行层/06_事实记录.md'
        self.call(self.project, 'revise', '--prepare', '--file', rel)
        candidate = self.project / '_候选/REVISE' / rel
        candidate.write_text(candidate.read_text() + '\n<!-- 合成账本备注，不影响图谱渲染 -->\n')
        self.call(self.project, 'revise', '--review')
        path = self.project / '_候选/REVISE_关联核对.json'
        data = json.loads(path.read_text())
        for item in data['items']:
            item.update(status='已核对', note='合成测试：仅备注，不代表真实审读。')
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        output = self.call(self.project, 'revise')
        digest = re.search(r'^REVISION_SHA256=([0-9a-f]{64})$', output, re.M).group(1)
        self.call(self.project, 'revise', '--apply', '--approve', digest)
        self.assertEqual((self.project / '图谱.html').read_bytes(), graph_before)
        self.assertGreater((self.project / '图谱.html').stat().st_mtime, stamp)
        head = (self.project / '.novel/HEAD').read_text().strip()
        tx = json.loads((self.project / '.novel/commits' / head / 'manifest.json').read_text())
        self.assertIn('图谱.html', tx['files'])
        self.assertIn('图谱不比账本旧', self.call(self.project, 'doctor'))

    def test_atomic_replace_preserves_mode_and_explicit_override(self):
        path = self.project / 'mode-probe'
        for mode in (0o644, 0o755):
            path.write_bytes(b'before')
            path.chmod(mode)
            core.atomic_write_bytes(str(path), b'after')
            self.assertEqual(path.read_bytes(), b'after')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
        core.atomic_write_bytes(str(path), b'private', mode=0o600)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        path.unlink()
        core.atomic_write_bytes(str(path), b'new')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_transaction_update_and_failed_validation_keep_permissions(self):
        rel = 'mode-probe'
        path = self.project / rel
        path.write_bytes(b'before')
        path.chmod(0o755)
        事务.apply_changes(str(self.project), {rel: b'after'}, label='synthetic mode test')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        事务.rollback_last(str(self.project))
        self.assertEqual(path.read_bytes(), b'before')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        with self.assertRaises(事务.TransactionError):
            事务.apply_changes(str(self.project), {rel: b'rejected'},
                              label='synthetic failure', validator=lambda: False)
        self.assertEqual(path.read_bytes(), b'before')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        self.assertIsNone(事务.inspect(str(self.project)))

    def test_formal_sync_preserves_updated_executable_mode(self):
        rel = '_工具/快照.sh'
        path = self.project / rel
        old = b'#!/bin/sh\n# synthetic installed version\n'
        path.write_bytes(old)
        path.chmod(0o755)
        manifest_path = self.project / 'project.json'
        manifest = json.loads(manifest_path.read_text())
        manifest.setdefault('system_file_hashes', {})[rel] = core.sha256_bytes(old)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        body_before = self.fingerprint('05_正文/K0001.md')
        self.call(ROOT, 'sync', str(self.project), '--check')
        self.call(ROOT, 'sync', str(self.project))
        self.assertEqual(path.read_bytes(), (ROOT / rel).read_bytes())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        self.assertEqual(body_before, self.fingerprint('05_正文/K0001.md'))
        self.call(self.project, 'doctor')


if __name__ == '__main__':
    unittest.main(verbosity=2)
