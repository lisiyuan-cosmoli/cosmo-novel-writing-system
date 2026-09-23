#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创作意图与全局修订的端到端回归，所有写入仅发生在本轮临时目录。"""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location('optimization_' + name, ROOT / '_工具' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='novel-optimization-')
        cls.base = Path(cls.temp.name)
        cls.fixture = load('新书自测')
        cls.release = load('发布自测')
        cls.book = cls.base / 'seed'
        rc = subprocess.run([sys.executable, str(ROOT / 'novel.py'), 'init', str(cls.book)], capture_output=True, text=True)
        if rc.returncode:
            raise RuntimeError(rc.stdout + rc.stderr)
        cls.fixture.开书(str(cls.book))
        cls.fixture.章卡(str(cls.book))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.fixture.本轮沙盘, ignore_errors=True)
        cls.temp.cleanup()

    def setUp(self):
        self.project = self.base / self._testMethodName
        shutil.copytree(self.book, self.project)

    def run_cli(self, *args, env=None):
        result = subprocess.run([sys.executable, str(self.project / 'novel.py'), *args], cwd=self.project,
                                capture_output=True, text=True, env=env)
        return result.returncode, result.stdout + result.stderr

    def ok(self, *args):
        code, output = self.run_cli(*args)
        self.assertEqual(code, 0, output)
        return output

    def digest(self):
        self.complete_review()
        output = self.ok('revise')
        match = re.search(r'^REVISION_SHA256=([0-9a-f]{64})$', output, re.M)
        self.assertIsNotNone(match, output)
        return match.group(1)

    def complete_review(self, note='测试夹具已逐文件核对，记录按本用例预期修改或保留。'):
        self.ok('revise', '--review')
        path = self.project / '_候选/REVISE_关联核对.json'
        if path.exists():
            review = json.loads(path.read_text())
            for item in review['items']:
                item.update(status='已核对', note=note)
            path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')

    def committed(self):
        self.release.prepare_chapter_candidate(str(self.project))
        output = self.ok('commit', 'K0001')
        digest = re.search(r'^CANDIDATE_SHA256=([0-9a-f]{64})$', output, re.M).group(1)
        self.ok('commit', 'K0001', '--apply', '--approve', digest)

    def prepare(self, *files):
        args = ['revise', '--prepare']
        for file in files:
            args.extend(['--file', file])
        self.ok(*args)
        return self.project / '_候选/REVISE'

    def change(self):
        self.committed()
        root = self.prepare('00_设定层/01_固定设定.md', '05_正文/K0001.md')
        fixed = root / '00_设定层/01_固定设定.md'
        fixed.write_text(fixed.read_text() + '\n本轮修订保留院门上的旧钉孔。\n')
        body = root / '05_正文/K0001.md'
        body.write_text(body.read_text().replace('没有署名', '没有落款'))
        return root

    def test_intent_reaches_brief_and_package_as_data(self):
        self.fixture.改表(str(self.project / '00_设定层/00_创作意图.md'), '明确不想写成的样子', '不得用绝症迫使父女和解，回归专用禁区\\|保留边界')
        for command in ('brief', 'package'):
            output = self.ok(command, 'K0001', '--write')
            path = re.search(r'^READ_PACKAGE=(.+)$', output, re.M).group(1)
            text = (self.project / path).read_text()
            self.assertIn('回归专用禁区', text)
            self.assertIn('回归专用禁区\\|保留边界', text)
            self.assertRegex(text, r'<!-- ===== DATA ｜ 00_设定层/00_创作意图.md')

    def test_intent_change_changes_package_digest(self):
        output = self.ok('package', 'K0001', '--write')
        path = re.search(r'^READ_PACKAGE=(.+)$', output, re.M).group(1)
        before = (self.project / path).read_bytes()
        self.fixture.改表(str(self.project / '00_设定层/00_创作意图.md'), '明确不想写成的样子', '禁止以金钱交易替代父女和解')
        output = self.ok('package', 'K0001', '--write')
        path2 = re.search(r'^READ_PACKAGE=(.+)$', output, re.M).group(1)
        self.assertNotEqual(before, (self.project / path2).read_bytes())

    def test_revision_apply_and_rollback_restore_both_files(self):
        root = self.change()
        files = ['00_设定层/01_固定设定.md', '05_正文/K0001.md']
        before = {f: (self.project / f).read_bytes() for f in files}
        after = {f: (root / f).read_bytes() for f in files}
        digest = self.digest()
        for f in files:
            self.assertEqual((self.project / f).read_bytes(), before[f])
        output = self.ok('revise', '--apply', '--approve', digest)
        self.assertIn('已提交全局修订', output)
        for f in files:
            self.assertEqual((self.project / f).read_bytes(), after[f])
        self.ok('rollback')
        for f in files:
            self.assertEqual((self.project / f).read_bytes(), before[f])

    def test_revision_candidate_change_invalidates_approval(self):
        root = self.change()
        digest = self.digest()
        p = root / '00_设定层/01_固定设定.md'
        p.write_text(p.read_text() + '\n后加的修订。\n')
        code, output = self.run_cli('revise', '--apply', '--approve', digest)
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('旧钉孔', (self.project / '00_设定层/01_固定设定.md').read_text())

    def test_revision_unrelated_base_change_invalidates_approval(self):
        self.change()
        digest = self.digest()
        p = self.project / '00_设定层/00_创作意图.md'
        p.write_text(p.read_text() + '\n更新了作者承诺。\n')
        code, output = self.run_cli('revise', '--apply', '--approve', digest)
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('旧钉孔', (self.project / '00_设定层/01_固定设定.md').read_text())

    def test_revision_cannot_write_tools(self):
        code, output = self.run_cli('revise', '--prepare', '--file', '_工具/novel.py')
        self.assertNotEqual(code, 0, output)

    def test_revision_rejects_symlink(self):
        root = self.change()
        path = root / '00_设定层/01_固定设定.md'
        path.unlink()
        path.symlink_to(self.project / '00_设定层/01_固定设定.md')
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)

    def test_revision_rejects_missing_approval(self):
        self.change()
        code, output = self.run_cli('revise', '--apply')
        self.assertNotEqual(code, 0, output)

    def test_revision_bad_body_never_changes_formal_files(self):
        root = self.change()
        path = root / '05_正文/K0001.md'
        path.write_text(path.read_text() + '\n这句话让文件头字数不再准确。\n')
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('旧钉孔', (self.project / '00_设定层/01_固定设定.md').read_text())

    def test_revision_failure_rolls_back_all_files(self):
        self.change()
        digest = self.digest()
        files = ['00_设定层/01_固定设定.md', '05_正文/K0001.md']
        before = {f: (self.project / f).read_bytes() for f in files}
        env = dict(os.environ, NOVEL_SELFTEST_FAULTS='1', NOVEL_FAIL_AFTER='1')
        code, output = self.run_cli('revise', '--apply', '--approve', digest, env=env)
        self.assertNotEqual(code, 0, output)
        for f in files:
            self.assertEqual((self.project / f).read_bytes(), before[f])

    def test_revision_does_not_overwrite_existing_candidate(self):
        root = self.change()
        path = root / '00_设定层/01_固定设定.md'
        before = path.read_bytes()
        code, output = self.run_cli('revise', '--prepare', '--file', '00_设定层/01_固定设定.md')
        self.assertNotEqual(code, 0, output)
        self.assertEqual(path.read_bytes(), before)

    def test_revision_crash_recovers_and_can_retry(self):
        self.change()
        digest = self.digest()
        files = ['00_设定层/01_固定设定.md', '05_正文/K0001.md', '图谱.html', 'project.json']
        before = {f: (self.project / f).read_bytes() for f in files}
        env = dict(os.environ, NOVEL_SELFTEST_FAULTS='1', NOVEL_HARD_CRASH_AFTER='1')
        code, output = self.run_cli('revise', '--apply', '--approve', digest, env=env)
        self.assertEqual(code, 97, output)
        self.ok('recover')
        for f in files:
            self.assertEqual((self.project / f).read_bytes(), before[f])
        self.assertEqual(self.digest(), digest)
        self.ok('revise', '--apply', '--approve', digest)
        self.assertIn('旧钉孔', (self.project / files[0]).read_text())

    def test_reuse_confirmed_route_needs_only_selected_direction(self):
        card = self.project / '06_归档/章节卡_K0001.md'
        text = card.read_text()
        text = re.sub(r'(?ms)^### 走向 B.*?(?=^## 用户选择)', '', text)
        text = text.replace('| 选择 | A |', '| 选择 | A |\n| 方案来源 | 沿用已确认路线 |\n| 沿用依据 | 作者已确认的第一章大纲与封门动作 |')
        card.write_text(text)
        self.ok('package', 'K0001')
        card.write_text(text.replace('作者已确认的第一章大纲与封门动作', ''))
        code, output = self.run_cli('package', 'K0001')
        self.assertNotEqual(code, 0, output)
        card.write_text(text)
        self.committed()

    def test_old_facts_keep_explicit_long_term_items(self):
        module = load('读取包')
        facts = '### K0001（已确认）\n\n- 正文事实：' + '普通动作。' * 40 + '\n- 长期保留：她无法辨认红色。\n  原因在本章事故中确认。\n- 角色判断：她误以为信件已寄出。\n'
        result = module.裁事实(facts, {'K0001': 1, 'K0006': 6}, 'K0006', 4)
        self.assertIn('她无法辨认红色', result)
        self.assertIn('原因在本章事故中确认', result)
        self.assertIn('01_运行层/06_事实记录.md', result)
        self.assertNotIn('原条目见 06b', result)

    def test_plugin_owned_setting_can_be_revised_but_check_cannot(self):
        self.committed()
        self.ok('plugin', 'install', 'speculative')
        root = self.prepare('00_设定层/插件/speculative.md')
        path = root / '00_设定层/插件/speculative.md'
        path.write_text(path.read_text() + '\n本轮修订只限制规则的适用时间。\n')
        self.ok('revise', '--apply', '--approve', self.digest())
        code, output = self.run_cli('revise', '--prepare', '--file', '02_检查层/插件/speculative.md')
        self.assertNotEqual(code, 0, output)

    def test_revision_title_is_derived_and_rollback_restores_it(self):
        self.committed()
        before = json.loads((self.project / 'project.json').read_text())
        root = self.prepare('项目配置.md')
        self.fixture.改表(str(root / '项目配置.md'), '书名', '《院门》')
        self.ok('revise', '--apply', '--approve', self.digest())
        after = json.loads((self.project / 'project.json').read_text())
        self.assertEqual(after['title'], '《院门》')
        self.assertEqual(after['initialization'], before['initialization'])
        self.ok('rollback')
        self.assertEqual(json.loads((self.project / 'project.json').read_text()), before)

    def test_v38_header_wrong_id_is_rejected_by_revision_and_doctor(self):
        self.committed()
        rel = '05_正文/K0001.md'
        root = self.prepare(rel)
        bad = (root / rel).read_text().replace('永久ID:K0001', '永久ID:K9999')
        (root / rel).write_text(bad)
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('永久 ID', output)
        self.assertNotIn('REVISION_SHA256=', output)
        (self.project / rel).write_text(bad)
        code, output = self.run_cli('doctor')
        self.assertNotEqual(code, 0, output)
        self.assertIn('永久 ID', output)

    def test_v38_header_missing_duplicate_and_mismatched_fields(self):
        self.committed()
        rel = '05_正文/K0001.md'
        root = self.prepare(rel)
        path = root / rel
        good = path.read_text()
        for old, new in [('展示章号:1', '展示章号:2'), ('视角:陈守田', '视角:别人'),
                         ('字数:26', '字数:26 | 字数:26'), ('字数:26 | ', ''),
                         ('永久ID:K0001 | ', ''), ('状态:已定稿', '状态:初稿')]:
            with self.subTest(field=old, replacement=new):
                self.assertIn(old, good)
                path.write_text(good.replace(old, new))
                code, output = self.run_cli('revise')
                self.assertNotEqual(code, 0, output)
                self.assertNotIn('REVISION_SHA256=', output)

    def test_v38_old_chapter_card_identity_is_checked_without_full_gate(self):
        self.committed()
        rel = '06_归档/章节卡_K0001.md'
        root = self.prepare(rel)
        self.fixture.改表(str(root / rel), '永久 ID', 'K9999')
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('章卡', output)

    def test_v38_chapter_commit_uses_same_header_checks(self):
        self.release.prepare_chapter_candidate(str(self.project))
        path = self.project / '_候选/K0001/05_正文/K0001.md'
        path.write_text(path.read_text().replace('永久ID:K0001', '永久ID:K9999'))
        code, output = self.run_cli('commit', 'K0001')
        self.assertNotEqual(code, 0, output)
        self.assertFalse((self.project / '05_正文/K0001.md').exists())

    def test_v38_semantic_edit_without_review_is_blocked(self):
        self.committed()
        rel = '05_正文/K0001.md'
        before = (self.project / rel).read_bytes()
        root = self.prepare(rel)
        path = root / rel
        path.write_text(path.read_text().replace('没有署名', '署着真名'))
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('关联核对', output)
        self.assertNotIn('REVISION_SHA256=', output)
        self.assertEqual((self.project / rel).read_bytes(), before)

    def test_v38_reviewed_body_and_facts_commit_and_archive_together(self):
        self.committed()
        rels = ['05_正文/K0001.md', '01_运行层/06_事实记录.md']
        root = self.prepare(*rels)
        before = {rel: (self.project / rel).read_bytes() for rel in rels}
        for rel in rels:
            path = root / rel
            path.write_text(path.read_text().replace('没有署名', '署着真名'))
        self.complete_review('已同步信件署名事实，其余状态与本次章卡梗概经测试核对保留。')
        output = self.ok('revise')
        digest = re.search(r'^REVISION_SHA256=([0-9a-f]{64})$', output, re.M).group(1)
        self.ok('revise', '--apply', '--approve', digest)
        records = list((self.project / '06_归档').glob('修订核对_*.json'))
        self.assertEqual(len(records), 1)
        self.assertTrue(all(item['status'] == '已核对' for item in json.loads(records[0].read_text())['items']))
        self.assertFalse((self.project / '_候选/REVISE_关联核对.json').exists())
        for rel in rels:
            self.assertIn('署着真名', (self.project / rel).read_text())
        self.ok('rollback')
        self.assertFalse(records[0].exists())
        for rel in rels:
            self.assertEqual((self.project / rel).read_bytes(), before[rel])

    def test_v38_review_cannot_omit_impacted_paths(self):
        self.change()
        self.complete_review()
        path = self.project / '_候选/REVISE_关联核对.json'
        review = json.loads(path.read_text())
        review['items'][0]['paths'] = []
        path.write_text(json.dumps(review))
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('范围被改变', output)
        self.ok('revise', '--review')
        repaired = json.loads(path.read_text())
        self.assertTrue(repaired['items'][0]['paths'])
        self.assertEqual(repaired['items'][0]['status'], '待核对')

    def test_v38_review_is_invalidated_by_candidate_edit(self):
        root = self.change()
        self.complete_review()
        path = root / '00_设定层/01_固定设定.md'
        path.write_text(path.read_text() + '\n新加入的一条设定。\n')
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('关联核对已失效', output)
        self.ok('revise', '--review')
        record = json.loads((self.project / '_候选/REVISE_关联核对.json').read_text())
        self.assertTrue(all(item['status'] == '待核对' for item in record['items']))

    def test_v38_review_is_invalidated_by_unrelated_baseline_edit(self):
        self.change()
        self.complete_review()
        path = self.project / '00_设定层/02_风格样本.md'
        path.write_text(path.read_text() + '\n新的风格约定。\n')
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('关联核对已失效', output)

    def test_v38_review_edit_invalidates_approval(self):
        self.change()
        digest = self.digest()
        path = self.project / '_候选/REVISE_关联核对.json'
        record = json.loads(path.read_text())
        record['items'][0]['note'] = '这是一条在批准之后替换过的说明。'
        path.write_text(json.dumps(record))
        code, output = self.run_cli('revise', '--apply', '--approve', digest)
        self.assertNotEqual(code, 0, output)
        self.assertIn('批准摘要已失效', output)

    def test_v38_partial_review_and_symlink_are_rejected(self):
        self.change()
        self.ok('revise', '--review')
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('关联核对未完成', output)
        path = self.project / '_候选/REVISE_关联核对.json'
        path.unlink()
        path.symlink_to(self.project / 'project.json')
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('符号链接', output)

    def test_v38_impact_review_includes_later_chapters(self):
        self.committed()
        source = self.project / '05_正文/K0001.md'
        (self.project / '05_正文/K0002.md').write_text(source.read_text().replace('K0001', 'K0002'))
        root = self.prepare('05_正文/K0001.md')
        path = root / '05_正文/K0001.md'
        path.write_text(path.read_text().replace('没有署名', '没有落款'))
        self.ok('revise', '--review')
        record = json.loads((self.project / '_候选/REVISE_关联核对.json').read_text())
        later = next(item for item in record['items'] if item['group'] == '后续正文')
        self.assertIn('05_正文/K0002.md', later['paths'])

    def experiential_card(self, mode='过渡'):
        card = self.project / '06_归档/章节卡_K0001.md'
        block = self.release._结论块(self.ok('repeat', 'K0001', '--card'))
        self.release._填旧版卡(str(self.project), 'K0001', 1, block)  # 3.8 体验呈现属于 3.x 旧卡语义
        text = card.read_text().replace('| 工作模式 | 完整 |', '| 工作模式 | ' + mode + ' |')
        if mode == '完整':
            text = text.replace('| 章节重心 | |', '| 章节重心 | 体验呈现 |')
        for field in ('阻力来自哪里', '越过阻力要付出的具体代价', '章末不可逆变化',
                      '结束时谁获得了什么', '哪件事本章不能解释', '哪个承诺必须兑现', '所得', '代价'):
            text = re.sub(r'(?m)^\|\s*' + re.escape(field) + r'\s*\|[^\n]*$', '| ' + field + ' | |', text)
        text = re.sub(r'(?m)^[23]\. .+$', '', text)
        text = re.sub(r'(?ms)^### 走向 B.*?(?=^## 用户选择)', '', text)
        card.write_text(text)
        return card

    def test_v38_transition_can_pass_without_forced_conflict(self):
        self.experiential_card()
        self.ok('package', 'K0001')
        self.release.prepare_chapter_candidate(str(self.project))
        audit = self.project / '_候选/K0001/06_归档/流程审计.md'
        audit.write_text(audit.read_text().replace('| K0001 | 完整 |', '| K0001 | 过渡 |'))
        output = self.ok('commit', 'K0001')
        digest = re.search(r'^CANDIDATE_SHA256=([0-9a-f]{64})$', output, re.M).group(1)
        self.ok('commit', 'K0001', '--apply', '--approve', digest)

    def test_v38_complete_chapter_can_choose_experiential_focus(self):
        self.experiential_card('完整')
        self.ok('package', 'K0001')
        self.committed()

    def test_v38_experiential_still_requires_concrete_detail_and_continuity(self):
        card = self.experiential_card()
        good = card.read_text()
        card.write_text(re.sub(r'(?m)^1\. .+$', '1.', good))
        code, output = self.run_cli('package', 'K0001')
        self.assertNotEqual(code, 0, output)
        self.assertIn('第 1 条未填写', output)
        card.write_text(good)
        self.fixture.改表(str(card), '伤势、物件、位置与时间限制', '')
        code, output = self.run_cli('package', 'K0001')
        self.assertNotEqual(code, 0, output)

    def test_v38_exploration_stays_outside_formal_package(self):
        scratch = self.project / '_候选/探索/人物相处.md'
        scratch.parent.mkdir(parents=True)
        scratch.write_text('EXPLORATION_ONLY_SENTINEL\n此处只是未确认的探索假设。\n')
        before = (self.project / '01_运行层/06_事实记录.md').read_bytes()
        output = self.ok('package', 'K0001', '--write')
        path = re.search(r'^READ_PACKAGE=(.+)$', output, re.M).group(1)
        self.assertNotIn('EXPLORATION_ONLY_SENTINEL', (self.project / path).read_text())
        self.assertEqual((self.project / '01_运行层/06_事实记录.md').read_bytes(), before)
        self.assertFalse((self.project / '05_正文/K0001.md').exists())

    def legacy_header_fixture(self):
        self.committed()
        manifest = self.project / 'project.json'
        data = json.loads(manifest.read_text())
        data.update(migrated_from='legacy-markdown', archive_required_from='K0002')
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        body = self.project / '05_正文/K0001.md'
        full = body.read_text()
        body.write_text('<!-- 永久ID:K0001 | 状态:已定稿 -->\n' + full.partition('\n')[2])
        return body, full

    def test_v38_migrated_header_is_preserved_but_revision_must_complete_it(self):
        body, full = self.legacy_header_fixture()
        before = body.read_bytes()
        self.assertIn('迁移旧章沿用原文件头', self.ok('doctor'))
        self.assertEqual(body.read_bytes(), before)
        root = self.prepare('05_正文/K0001.md')
        candidate = root / '05_正文/K0001.md'
        candidate.write_text(body.read_text().replace('没有署名', '没有落款'))
        code, output = self.run_cli('revise')
        self.assertNotEqual(code, 0, output)
        self.assertIn('补齐现行文件头', output)
        candidate.write_text(full.replace('没有署名', '没有落款'))
        self.ok('revise', '--apply', '--approve', self.digest())
        self.assertIn('展示章号:1', body.read_text())

    def test_v38_migrated_header_still_rejects_wrong_existing_identity(self):
        body, full = self.legacy_header_fixture()
        for text in (body.read_text().replace('K0001', 'K9999'), full.replace('展示章号:1', '展示章号:9')):
            body.write_text(text)
            code, output = self.run_cli('doctor')
            self.assertNotEqual(code, 0, output)

    def test_v38_legacy_exception_does_not_cover_new_ids(self):
        self.legacy_header_fixture()
        manifest = self.project / 'project.json'
        data = json.loads(manifest.read_text())
        data['archive_required_from'] = 'K0001'
        manifest.write_text(json.dumps(data))
        code, output = self.run_cli('doctor')
        self.assertNotEqual(code, 0, output)
        self.assertIn('文件头缺少', output)


if __name__ == '__main__':
    unittest.main()
