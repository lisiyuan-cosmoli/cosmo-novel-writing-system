#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6.0 工作流回归：真实开书/提交基线，隔离验证读取与文风候选边界。"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import 发布自测 as release
import 新书自测 as book
import 读取包自测 as pack
import 定声 as voice
import 文风 as style
import 事务


def run(project, *args):
    # project 位于命令必需位置参数之后、所有选项之前。Python 3.9 的
    # argparse 不接受把这个 nargs='?' 位置参数拖到 --apply/--approve 后面。
    arguments = list(map(str, args))
    first_option = next((i for i, value in enumerate(arguments)
                         if value.startswith('-')), len(arguments))
    arguments.insert(first_option, str(project))
    result = subprocess.run([sys.executable, '-B', str(project / 'novel.py'),
                             *arguments], capture_output=True, text=True,
                            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    return result.returncode, result.stdout + result.stderr


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='novel-v6-workflow-')
        cls.root = Path(cls.tmp.name)
        cls.base = Path(release.init_project(str(cls.root), 'baseline'))
        # 这套已存在的发布夹具描述升级对抗；显式选择它，不假定新书默认模式。
        engine = cls.base / '00_设定层/04_读者引擎.md'
        engine.write_text(engine.read_text().replace('| 创作模式 | 通用 |', '| 创作模式 | 升级对抗 |'))
        book.填全(str(cls.base))
        book.填意图与决策(str(cls.base))
        cls.draft = cls.root / 'draft-baseline'
        shutil.copytree(cls.base, cls.draft)
        book.开书(str(cls.base))
        book.章卡(str(cls.base))
        release.prepare_chapter_candidate(str(cls.base))
        code, text = run(cls.base, 'commit', 'K0001')
        if code:
            raise AssertionError(text)
        digest = re.search(r'^CANDIDATE_SHA256=([0-9a-f]{64})$', text, re.M).group(1)
        code, text = run(cls.base, 'commit', 'K0001', '--apply', '--approve', digest)
        if code:
            raise AssertionError(text)
        code, text = run(cls.base, 'doctor')
        if code or not re.search(r'错误 0 ／ 注意 \d+ ／ 通过 \d+', text):
            raise AssertionError(text)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        shutil.rmtree(book.本轮沙盘, ignore_errors=True)
        shutil.rmtree(pack.本轮沙盘, ignore_errors=True)

    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix='case-', dir=self.root))
        self.project = self.area / 'project'
        shutil.copytree(self.base, self.project)

    def tearDown(self):
        shutil.rmtree(self.area)

    def fresh_draft(self):
        shutil.rmtree(self.project)
        shutil.copytree(self.draft, self.project)

    def sample(self, length=1000):
        path = self.area / '作者提供的样本.txt'
        path.write_text('风' * length)
        return path

    def cli(self, *args, good=True):
        code, text = run(self.project, *args)
        if good:
            self.assertEqual(code, 0, text)
        else:
            self.assertNotEqual(code, 0, text)
        return text

    def next_card(self):
        card = pack.章卡文本('K0002', 2, '无')
        card = card.replace('| 取样章 | K0001 K0002 |', '| 取样章 | K0001 |')
        (self.project / '06_归档/章节卡_K0002.md').write_text(card)

    def outline(self, future_ids):
        path = self.project / '00_设定层/03_分章大纲.md'
        first = re.search(r'^\| K0001 \|[^\n]*', path.read_text(), re.M).group(0)
        text = '# 分章大纲\n\n## 全书节拍\n\n## 章节表\n'
        text += '| 永久 ID | 展示章号 | 视角 | 事件 | 开始 | 结束 | 状态 |\n|---|---|---|---|---|---|---|\n' + first + '\n'
        for no, kid in enumerate(future_ids, 2):
            text += '| %s | %d | 陈守田 | 查信 | 门外 | 门内 | 未写 |\n' % (kid, no)
        path.write_text(text)

    def test_missing_or_unreadable_prior_body_never_outputs_package(self):
        self.next_card()
        self.cli('doctor')
        before = self.cli('package', 'K0002', '--write')
        self.assertIn('READ_PACKAGE=', before)
        body = self.project / '05_正文/K0001.md'
        saved = body.read_bytes()
        old_packages = set((self.project / '_读取包').iterdir())
        for bad in (None, b'\xff'):
            with self.subTest(bad=bad):
                body.unlink()
                if bad is not None:
                    body.write_bytes(bad)
                text = self.cli('package', 'K0002', '--write', good=False)
                self.assertIn('05_正文/K0001.md', text)
                self.assertNotIn('READ_PACKAGE=', text)
                self.assertEqual(old_packages, set((self.project / '_读取包').iterdir()))
                body.write_bytes(saved)

    def test_status_and_doctor_report_batch_candidate(self):
        candidate = self.project / '_候选/K0002-K0004/05_正文/K0002.md'
        candidate.parent.mkdir(parents=True)
        candidate.write_text('# 已保存的批次候选\n')
        for command in ('doctor', 'status'):
            with self.subTest(command=command):
                text = self.cli(command)
                self.assertIn('K0002-K0004', text)
                self.assertNotIn('✓ 没有悬着的候选提交', text)

    def test_exploration_does_not_become_pending_chapter(self):
        (self.project / '_候选/探索').mkdir(parents=True)
        text = self.cli('doctor')
        self.assertIn('✓ 没有悬着的候选提交', text)

    def test_brief_accepts_reordered_and_sparse_ids(self):
        self.outline(['K0900', 'K0002'])
        self.cli('brief', 'K0900-K0002', '--write')
        self.cli('brief', 'K0002-K0900', good=False)

    def test_brief_counts_chapters_by_display_order(self):
        self.outline(['K0900', 'K0700', 'K0500', 'K0300', 'K0002'])
        self.cli('brief', 'K0900-K0002')
        self.outline(['K0002', 'K0900', 'K0700', 'K0500', 'K0300', 'K0003'])
        text = self.cli('brief', 'K0002-K0003', good=False)
        self.assertIn('最多 5 章', text)

    def test_voice_draft_stages_init_and_approved_foundation_uses_it(self):
        self.fresh_draft()
        formal = self.project / voice.样本rel
        original = formal.read_bytes()
        baseline = style.取正样本(str(self.project))
        text = self.cli('voice', '--apply', self.sample())
        self.assertIn('VOICE_CANDIDATE=_候选/INIT/' + voice.样本rel, text)
        self.assertEqual(formal.read_bytes(), original)
        self.assertEqual(style.取正样本(str(self.project)), baseline)
        self.assertNotEqual(voice.取正样本(str(self.project)), voice.取正样本(str(self.project), 候选=True))
        self.assertIn('_候选/INIT/' + voice.样本rel, self.cli('voice', '--check', '--foundation'))
        text = self.cli('foundation')
        digest = re.search(r'^FOUNDATION_CANDIDATE_SHA256=([0-9a-f]{64})$', text, re.M).group(1)
        self.cli('foundation', '--apply', '--approve', digest)
        self.assertEqual(voice.取正样本(str(self.project)), '风' * 1000)

    def test_voice_updates_existing_init_preserving_analysis_and_other_choices(self):
        self.fresh_draft()
        self.cli('foundation', '--prepare')
        candidate = self.project / '_候选/INIT'
        path = candidate / voice.样本rel
        text = path.read_text() + '\n候选专用分析说明。\n'
        path.write_text(text)
        intent = candidate / voice.意图rel
        intent.write_text(intent.read_text().replace('乡镇', '本轮候选乡镇'))
        original_intent = intent.read_bytes()
        self.cli('voice', '--apply', self.sample())
        self.assertIn('候选专用分析说明。', path.read_text())
        self.assertEqual(intent.read_bytes(), original_intent)
        prompt = self.cli('voice', '--prompt')
        self.assertIn('_候选/INIT/' + voice.意图rel, prompt)
        self.assertIn('_候选/INIT/' + voice.样本rel, prompt)

    def test_voice_confirmed_stages_revise_keeps_formal_and_head(self):
        formal = (self.project / voice.样本rel).read_bytes()
        head = (self.project / '.novel/HEAD').read_bytes()
        baseline = style.取正样本(str(self.project))
        text = self.cli('voice', '--apply', self.sample(600))
        self.assertIn('VOICE_CANDIDATE=_候选/REVISE/' + voice.样本rel, text)
        self.assertEqual((self.project / voice.样本rel).read_bytes(), formal)
        self.assertEqual((self.project / '.novel/HEAD').read_bytes(), head)
        self.assertEqual(style.取正样本(str(self.project)), baseline)
        self.assertIn('_候选/REVISE/' + voice.样本rel, self.cli('voice', '--check'))
        self.assertEqual(voice.取正样本(str(self.project), 候选=True), '风' * 600)

    def test_voice_resumes_existing_init_for_legacy_and_confirmed_books(self):
        for state in ('legacy', 'confirmed'):
            with self.subTest(state=state):
                shutil.rmtree(self.project)
                shutil.copytree(self.base, self.project)
                path = self.project / 'project.json'
                manifest = json.loads(path.read_text())
                if state == 'legacy':
                    manifest['initialization'] = {'status': 'legacy'}
                path.write_text(json.dumps(manifest, ensure_ascii=False))
                formal = (self.project / voice.样本rel).read_bytes()
                self.cli('foundation', '--prepare')
                self.assertIn('_候选/INIT/' + voice.样本rel,
                              self.cli('voice', '--apply', self.sample()))
                self.assertFalse((self.project / '_候选/REVISE').exists())
                self.assertEqual((self.project / voice.样本rel).read_bytes(), formal)
                self.assertIn('_候选/INIT/' + voice.样本rel, self.cli('voice', '--check'))
                self.assertIn('_候选/INIT/' + voice.样本rel, self.cli('voice', '--prompt'))
                self.assertIn('FOUNDATION_CANDIDATE_SHA256=', self.cli('foundation'))

    def test_voice_explicit_foundation_creates_init_for_confirmed_book(self):
        formal = (self.project / voice.样本rel).read_bytes()
        self.assertIn('_候选/INIT/' + voice.样本rel,
                      self.cli('voice', '--apply', self.sample(), '--foundation'))
        self.assertFalse((self.project / '_候选/REVISE').exists())
        self.assertEqual((self.project / voice.样本rel).read_bytes(), formal)
        self.assertIn('_候选/INIT/' + voice.样本rel,
                      self.cli('voice', '--check', '--foundation'))
        self.assertIn('_候选/INIT/' + voice.样本rel,
                      self.cli('voice', '--prompt', '--foundation'))

    def test_voice_ambiguous_candidates_require_explicit_foundation_view(self):
        self.cli('foundation', '--prepare')
        self.cli('revise', '--prepare', '--file', voice.样本rel)
        revise = self.project / '_候选/REVISE' / voice.样本rel
        original_revise = revise.read_bytes()
        formal = (self.project / voice.样本rel).read_bytes()
        for args in [('--check',), ('--prompt',), ('--apply', self.sample())]:
            with self.subTest(args=args):
                text = self.cli('voice', *args, good=False)
                self.assertIn('INIT 与 REVISE 候选同时存在', text)
        self.assertEqual((self.project / voice.样本rel).read_bytes(), formal)
        self.assertEqual(revise.read_bytes(), original_revise)
        # 正式基线 API 不受候选并存影响。
        self.assertTrue(voice.取正样本(str(self.project)))
        self.cli('voice', '--apply', self.sample(), '--foundation')
        self.assertEqual(revise.read_bytes(), original_revise)
        self.assertIn('_候选/INIT/' + voice.样本rel,
                      self.cli('voice', '--check', '--foundation'))
        self.assertIn('_候选/INIT/' + voice.样本rel,
                      self.cli('voice', '--prompt', '--foundation'))
        # 显式开书视图仍按800字核验，不能借已确认状态接受600字。
        self.cli('voice', '--apply', self.sample(600), '--foundation', good=False)

    def test_voice_insufficient_samples_leave_no_candidate(self):
        self.cli('voice', '--apply', self.sample(499), good=False)
        self.assertFalse((self.project / '_候选/REVISE').exists())
        self.fresh_draft()
        text = self.cli('voice', '--apply', self.sample(600), good=False)
        self.assertIn('不足 800 字', text)
        self.assertFalse((self.project / '_候选/INIT').exists())

    def test_voice_refuses_symlink_candidate_without_touching_external_file(self):
        self.fresh_draft()
        outside = self.area / 'outside'
        outside.mkdir()
        marker = outside / '保留.txt'
        marker.write_text('不能改动')
        (self.project / '_候选').symlink_to(outside, target_is_directory=True)
        self.cli('voice', '--apply', self.sample(), good=False)
        self.assertEqual(list(outside.iterdir()), [marker])
        self.assertEqual(marker.read_text(), '不能改动')

    def test_voice_refuses_symlink_sample_target(self):
        self.fresh_draft()
        self.cli('foundation', '--prepare')
        external = self.area / 'outside-sample.md'
        external.write_text('不得改变外部文件')
        path = self.project / '_候选/INIT' / voice.样本rel
        path.unlink()
        path.symlink_to(external)
        self.cli('voice', '--apply', self.sample(), good=False)
        self.assertEqual(external.read_text(), '不得改变外部文件')
        self.assertTrue(path.is_symlink())

    def test_voice_honors_project_lock(self):
        self.fresh_draft()
        handle = 事务._acquire(str(self.project))
        try:
            text = self.cli('voice', '--apply', self.sample(), good=False)
            self.assertIn('另一个事务正在运行', text)
            self.assertFalse((self.project / '_候选/INIT').exists())
        finally:
            事务._release(handle)


if __name__ == '__main__':
    unittest.main()
