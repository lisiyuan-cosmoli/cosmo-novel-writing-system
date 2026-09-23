#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only efficiency invariants on a current-template synthetic project.

Temporary test data stays outside the template. No timing threshold is asserted:
these checks protect freshness, view separation, errors and bounded file reads.
"""
import collections
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import v2_core as core
import 结构复盘 as review
import 文风 as style
import 体检 as doctor
import 状态 as status

ROOT = Path(__file__).resolve().parent.parent


def captured(fn, *args, **kwargs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = fn(*args, **kwargs)
    return result, output.getvalue()


def fingerprint(project):
    return {str(p.relative_to(project)): (p.stat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in project.rglob('*') if p.is_file()}


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='novel-runtime-')
        cls.work = Path(cls.tmp.name)
        cls.seed = cls.work/'seed'
        cls.count = 16
        result = subprocess.run([sys.executable, '-B', str(ROOT/'novel.py'), 'init', str(cls.seed)],
                                capture_output=True, text=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        # Current initialization helper supplies valid synthetic foundation/card data.
        import 新书自测 as helper
        helper.填全(str(cls.seed))
        helper.开书(str(cls.seed))
        helper.章卡(str(cls.seed))
        shutil.rmtree(helper.本轮沙盘)
        outline = cls.seed/review.OUTLINE
        text = re.sub(r'^\| K\d{4} \|.*\n?', '', outline.read_text(), flags=re.M)
        rows = ['| K%04d | %d | 陈守田 | 合成事件 | 原状态 | 新状态 | 已定稿 |' % (i, i)
                for i in range(1, cls.count + 1)]
        outline.write_text(text.replace('## 大纲变更记录', '\n'.join(rows)+'\n\n## 大纲变更记录'))
        card = (cls.seed/'06_归档/章节卡_K0001.md').read_text()
        facts, audit = '# 合成事实\n', (cls.seed/'06_归档/流程审计.md').read_text()
        for i in range(1, cls.count + 1):
            kid = 'K%04d' % i
            body = ('甲乙丙丁戊己庚辛壬癸。'*200)[:2000]
            (cls.seed/('05_正文/'+kid+'.md')).write_text(
                '<!-- 永久ID:%s | 展示章号:%d | 视角:陈守田 | 字数:2000 | 状态:已定稿 -->\n%s\n'
                % (kid, i, body))
            (cls.seed/('06_归档/章节卡_'+kid+'.md')).write_text(
                card.replace('K0001', kid).replace('| 展示章号 | 1 |', '| 展示章号 | %d |' % i))
            (cls.seed/('06_归档/梗概_'+kid+'_合成.md')).write_text('合成梗概\n')
            facts += '\n### '+kid+'\n\n- 合成事实。\n'
            audit += '\n| '+kid+' | 完成 |\n'
        (cls.seed/'01_运行层/06_事实记录.md').write_text(facts)
        (cls.seed/'06_归档/流程审计.md').write_text(audit)
        p = cls.seed/'01_运行层/04_状态快照.md'
        p.write_text(p.read_text().replace('K0000', 'K0016'))
        now = review.snapshot(str(cls.seed))
        block = {'ids': now['finalized'][:12], 'body': {k: now['body'][k] for k in now['finalized'][:12]}}
        record = review.with_basis((cls.seed/review.TEMPLATE).read_text(), now)
        record = review.with_fields(record, {'复盘状态': '待复盘', '复盘间隔（新增定稿章）': '3',
                                            '作者访谈状态': '待访谈'})
        record = review.with_cycle(record, {'format': 'novel-review-cycle-v1', 'scope': 'small',
                                          'previous': {'small': block, 'large': block},
                                          'reviewed': {'ids': now['finalized'], 'body': now['body']}})
        (cls.seed/review.RECORD).write_text(record)
        errors, _, _ = captured(doctor.inspect, str(cls.seed))[0]
        if errors:
            raise RuntimeError('Synthetic doctor failed: '+repr(errors))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.project = self.work/self._testMethodName
        shutil.copytree(self.seed, self.project)
        self.p = str(self.project)

    def count_reads(self, fn, *args, **kwargs):
        counts = collections.Counter()
        original = review.read_file
        def read(root, rel, optional=False):
            if rel.startswith('05_正文/'):
                counts[rel] += 1
            return original(root, rel, optional=optional)
        with mock.patch.object(review, 'read_file', read):
            output = captured(fn, *args, **kwargs)
        return counts, output

    def recognize(self, ids=('K0001', 'K0002')):
        path = self.project/'00_设定层/02_风格样本.md'
        path.write_text(re.sub(r'^\| 认可为文风样本的章节 \|.*$',
                              '| 认可为文风样本的章节 | '+'、'.join(ids)+' |', path.read_text(), flags=re.M))
        baseline, notes = style.建基线(self.p)
        self.assertIsNotNone(baseline)
        for rel, data in style.写入基线(self.p, baseline, notes).items():
            (self.project/rel).write_bytes(data)
        return baseline

    def test_summary_and_prompt_read_each_formal_body_once(self):
        for fn in (review.summary, review.prompt):
            reads, _ = self.count_reads(fn, self.p)
            self.assertEqual(len(reads), self.count)
            self.assertEqual(set(reads.values()), {1})

    def test_pagination_reuses_snapshot_bytes_and_hash(self):
        reads, (_, output) = self.count_reads(review.reading, self.p, 'large', 0, 4)
        self.assertEqual(sum(reads.values()), self.count)
        self.assertEqual(output.count('--- DATA '), 4)
        self.assertIn(hashlib.sha256((self.project/'05_正文/K0004.md').read_bytes()).hexdigest(), output)

    def test_same_invocation_keeps_observed_bytes_next_call_refreshes(self):
        path = self.project/'05_正文/K0004.md'
        old = path.read_bytes()
        context = review.ReadContext(self.p)
        first = review.snapshot(self.p, context=context)
        path.write_bytes(old.replace('甲'.encode(), '新'.encode()))
        _, out = captured(review.reading, self.p, 'large', 0, 4, context)
        self.assertIn(first['body']['K0004'], out)
        self.assertIn(old.decode().split('\n', 1)[1].strip(), out)
        fresh = review.snapshot(self.p)
        self.assertNotEqual(first['body']['K0004'], fresh['body']['K0004'])
        self.assertIn('large', review.cycle_status(self.p)['stale'])

    def test_candidate_and_formal_snapshots_stay_distinct(self):
        rel = '05_正文/K0001.md'
        path = self.project/'_候选/REVISE'/rel
        path.parent.mkdir(parents=True)
        path.write_text('合成候选，不是正式正文。')
        context = review.ReadContext(self.p)
        formal = review.snapshot(self.p, context=context)
        candidate = review.snapshot(self.p, '_候选/REVISE', context)
        self.assertNotEqual(formal['body']['K0001'], candidate['body']['K0001'])
        self.assertEqual(candidate['body']['K0001'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(formal['body']['K0002'], candidate['body']['K0002'])
        self.assertIs(formal, review.snapshot(self.p, context=context))

    def test_cached_missing_candidate_does_not_bleed_into_next_command(self):
        context = review.ReadContext(self.p)
        before = review.snapshot(self.p, '_候选/REVISE', context)
        path = self.project/'_候选/REVISE/05_正文/K0001.md'
        path.parent.mkdir(parents=True)
        path.write_text('下一次命令可见的新候选。')
        self.assertEqual(before, review.snapshot(self.p, '_候选/REVISE', context))
        self.assertNotEqual(before['body']['K0001'], review.snapshot(self.p, '_候选/REVISE')['body']['K0001'])

    def test_context_cannot_be_used_for_another_project(self):
        with self.assertRaises(core.ProjectError):
            review.snapshot(str(self.seed), context=review.ReadContext(self.p))

    def test_missing_and_symlinked_prose_still_fail(self):
        path = self.project/'05_正文/K0001.md'
        path.unlink()
        with self.assertRaises(core.ProjectError):
            review.snapshot(self.p)
        path.symlink_to(self.seed/'05_正文/K0001.md')
        with self.assertRaises(core.ProjectError):
            review.snapshot(self.p)

    def test_unreadable_utf8_page_still_fails(self):
        (self.project/'05_正文/K0004.md').write_bytes(b'\xff')
        with self.assertRaises(core.ProjectError):
            captured(review.reading, self.p, 'large', 0, 4)

    def test_new_page_checks_changed_unprinted_prose(self):
        old = review.reading_window(self.p, 'large')[1]
        path = self.project/'05_正文/K0001.md'
        path.write_text(path.read_text()+'\n新增合成句子。')
        new = review.reading_window(self.p, 'large')[1]
        self.assertEqual(old[0], 'K0004')
        self.assertEqual(new[0], 'K0001')
        self.assertEqual(len(new), self.count)

    def test_style_reminder_reads_only_recognized_and_never_measures(self):
        baseline = self.recognize()
        reads = []
        original = style.core.read_text
        def read(path, default=None):
            if '/05_正文/' in str(path):
                reads.append(Path(path).name)
            return original(path, default)
        with mock.patch.object(style.core, 'read_text', read), \
             mock.patch.object(style, '度量', side_effect=AssertionError('reminder must not measure')):
            self.assertEqual(style.基线提醒(self.p), ('已建立', ''))
        self.assertEqual(reads, ['K0001.md', 'K0002.md'])
        expected = core.canonical_digest({'正样本': style.取正样本(self.p),
                                         '认可名单': style.认可章节(self.p),
                                         '认可正文': [(k, style.取正文(t)) for k, t in style.已定稿正文(self.p)]})
        self.assertEqual(baseline['_来源摘要'], expected)

    def test_no_recognized_prose_means_no_body_reads_in_reminder(self):
        original = style.core.read_text
        def read(path, default=None):
            self.assertNotIn('/05_正文/', str(path))
            return original(path, default)
        with mock.patch.object(style.core, 'read_text', read):
            self.assertEqual(style.基线提醒(self.p)[0], '语料不足')

    def test_style_new_invocation_detects_recognized_changes_only(self):
        self.recognize()
        path = self.project/'05_正文/K0016.md'
        path.write_text(path.read_text()+'未认可的合成变动。')
        self.assertEqual(style.基线提醒(self.p), ('已建立', ''))
        path = self.project/'05_正文/K0001.md'
        path.write_text(path.read_text()+'认可正文的合成变动。')
        self.assertEqual(style.基线提醒(self.p)[0], '需更新')

    def test_doctor_keeps_legacy_synopsis_and_rejects_empty_or_missing(self):
        path = self.project/'06_归档/梗概_K0001_合成.md'
        renamed = path.with_name('梗概_K0001旧名.md')
        path.rename(renamed)
        self.assertEqual(captured(doctor.inspect, self.p)[0][0], [])
        renamed.write_text('  \n')
        errors = captured(doctor.inspect, self.p)[0][0]
        self.assertTrue(any('梗概' in name and 'K0001' in detail for name, detail in errors))
        renamed.unlink()
        self.assertTrue(any('梗概' in name for name, _ in captured(doctor.inspect, self.p)[0][0]))

    def test_doctor_synopsis_keeps_unicode_digit_ids_accepted_by_outline(self):
        kid = 'K０００１'
        for rel in (review.OUTLINE, '01_运行层/06_事实记录.md', '06_归档/流程审计.md'):
            path = self.project/rel
            path.write_text(path.read_text().replace('K0001', kid))
        for rel in ('05_正文/K0001.md', '06_归档/章节卡_K0001.md', '06_归档/梗概_K0001_合成.md'):
            path = self.project/rel
            path.write_text(path.read_text().replace('K0001', kid))
            path.rename(path.with_name(path.name.replace('K0001', kid)))
        _, rows, malformed = doctor._outline(self.p)
        self.assertFalse(malformed)
        self.assertIn(kid, [row['id'] for row in rows])
        errors = captured(doctor.inspect, self.p)[0][0]
        self.assertFalse(any('梗概' in name for name, _ in errors), errors)

    def test_doctor_still_detects_duplicate_id_and_display(self):
        path = self.project/review.OUTLINE
        path.write_text(path.read_text()+'\n| K0001 | 1 | 陈守田 | 合成 | 原状态 | 新状态 | 已定稿 |\n')
        names = [name for name, _ in captured(doctor.inspect, self.p)[0][0]]
        self.assertIn('永久 ID 唯一', names)
        self.assertIn('展示章号唯一', names)

    def test_status_reports_fact_stock_without_sealing_advice(self):
        path = self.project/'01_运行层/06_事实记录.md'
        path.write_text(path.read_text()+'\n'+'长期合成记录。'*10000)
        _, output = captured(status.main, [self.p])
        self.assertIn('事实资料存量', output)
        self.assertIn('不是读取包实际占用', output)
        self.assertNotIn('考虑封段', output)
        self.assertNotIn('事实记录已占', output)
        self.assertFalse((self.project/'_读取包').exists())

    def test_read_only_commands_leave_project_unchanged(self):
        before = fingerprint(self.project)
        captured(status.main, [self.p])
        captured(doctor.inspect, self.p)
        captured(review.prompt, self.p)
        captured(review.reading, self.p, 'large', 0, 4)
        self.assertEqual(before, fingerprint(self.project))


if __name__ == '__main__':
    unittest.main(verbosity=2)
