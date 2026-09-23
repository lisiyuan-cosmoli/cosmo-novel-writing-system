#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6.0 创作模式与可选研究的隔离行为测试；不读写真实作品。"""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import 引擎 as engine
import 开书 as foundation

ROOT = Path(__file__).resolve().parent.parent
LEGACY = '''# 04 读者引擎
## 一、读者承诺
读者看到主人公怎样完成共同约定。
## 二、核心爽感单元
| 项 | 内容 |
|---|---|
| 触发 | 接到具体挑战 |
| 兑现 | 完成约定 |
| 放大 | 合作关系改变 |
## 三、升级阶梯
| 级 | 大致章段 | 数值或能力 | 舞台 |
|---|---|---|---|
| 1 | 1—3 | 完成个人约定 | 家中 |
| 2 | 4—6 | 完成共同约定 | 社区 |
## 四、对手名单
| 对手 | 想要什么 |
|---|---|
| 竞争者 | 优先取得机会 |
'''
OLD_EMPTY = '''# 04 读者引擎
## 一、读者承诺
读者点开这本书，是为了看到 ________。
## 二、核心爽感单元
| 项 | 内容 |
|---|---|
| 触发 | 例：主角真心想要一样东西 |
| 兑现 | 例：具体的回报 |
| 放大 | 例：有人看见 |
## 三、升级阶梯
| 级 | 大致章段 | 数值或能力 | 舞台 |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
## 四、对手名单
| 对手 | 想要什么 |
|---|---|
| | |
'''


def general_card():
    text = (ROOT / engine.ENGINE_REL).read_text(encoding='utf-8')
    return (text.replace('________', '旧友共同度过一次普通的周末', 1)
            .replace('| 主要期待 | |', '| 主要期待 | 从具体日常中认识彼此的变化 |', 1)
            .replace('| | |\n', '| 周末 | 从寒暄到一起整理旧物，理解彼此生活的不同 |\n', 1))


def output(call, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = call(*args)
    return result, stream.getvalue()


class CreativeModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='novel-creative-mode-')
        self.project = Path(self.temp.name) / 'book'
        self.project.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rel, text):
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def setup_arc(self, card):
        self.write(engine.ENGINE_REL, card)
        self.write(engine.OUTLINE_REL, '# 大纲\n## 章节表\n'
                   '| K0001 | 1 | 人物 | 场景 | 未写 |\n'
                   '| K0002 | 2 | 人物 | 场景 | 未写 |\n')
        self.write(engine.ARC_TEMPLATE_REL, (ROOT / engine.ARC_TEMPLATE_REL).read_text(encoding='utf-8'))
        self.write(engine.LEDGER_REL, '# 悬念账\n## 活动悬念\n## 章末钩子记录\n')

    def test_new_general_template_stays_disabled_until_three_requirements_filled(self):
        text = (ROOT / engine.ENGINE_REL).read_text(encoding='utf-8')
        self.assertEqual(engine.引擎模式(text), '通用')
        errors = engine.引擎卡检查(text)
        for field in ('读者承诺', '主要期待', '阶段发展'):
            self.assertTrue(any(field in item for item in errors), errors)
        self.assertFalse(any('对手' in item or '升级阶梯' in item for item in errors), errors)

    def test_general_life_story_passes_without_opponent_or_escalation(self):
        text = general_card()
        self.assertEqual(engine.引擎卡检查(text), [])
        self.write(engine.ENGINE_REL, text)
        self.assertTrue(engine.启用(str(self.project)))
        self.assertEqual(engine.创作模式(str(self.project)), '通用')

    def test_each_general_requirement_is_enforced(self):
        text = general_card()
        for old, new, expected in (
            ('旧友共同度过一次普通的周末', '________', '读者承诺'),
            ('从具体日常中认识彼此的变化', '', '主要期待'),
            ('从寒暄到一起整理旧物，理解彼此生活的不同', '', '阶段发展'),
        ):
            with self.subTest(field=expected):
                errors = engine.引擎卡检查(text.replace(old, new, 1))
                self.assertTrue(any(expected in item for item in errors), errors)

    def test_legacy_card_keeps_its_mode_and_requirements(self):
        self.assertEqual(engine.引擎模式(LEGACY), '升级对抗')
        self.assertEqual(engine.引擎卡检查(LEGACY), [])
        errors = engine.引擎卡检查(LEGACY.replace('| 竞争者 | 优先取得机会 |', '| | |'))
        self.assertTrue(any('对手名单' in item for item in errors), errors)

    def test_old_unfilled_seed_still_does_not_enable_engine(self):
        self.write(engine.ENGINE_REL, OLD_EMPTY)
        before = (self.project / engine.ENGINE_REL).read_bytes()
        self.assertFalse(engine.启用(str(self.project)))
        self.assertGreaterEqual(len(engine.引擎卡检查(OLD_EMPTY)), 4)
        self.assertEqual((self.project / engine.ENGINE_REL).read_bytes(), before)

    def test_explicit_escalation_keeps_old_validation(self):
        text = '| 创作模式 | 升级对抗 |\n' + LEGACY
        self.assertEqual(engine.引擎卡检查(text), [])
        self.assertTrue(engine.引擎卡检查(general_card().replace('| 创作模式 | 通用 |', '| 创作模式 | 升级对抗 |')))

    def test_unknown_or_duplicate_mode_is_not_silently_selected(self):
        for text in (
            general_card().replace('| 创作模式 | 通用 |', '| 创作模式 | 自动 |'),
            general_card() + '\n| 创作模式 | 升级对抗 |\n',
            general_card() + '\n| 创作模式 | 通用 |\n',
        ):
            with self.subTest(text=text[-45:]):
                self.assertEqual(engine.引擎模式(text), '')
                self.assertTrue(any('创作模式' in item for item in engine.引擎卡检查(text)))

    def test_malformed_unknown_mode_is_not_legacy(self):
        text = '| 创作模式 | 自动\n' + LEGACY
        self.assertEqual(engine.引擎模式(text), '')
        self.assertTrue(any('创作模式' in item for item in engine.引擎卡检查(text)))

    def test_malformed_general_mode_is_not_legacy(self):
        for declaration in ('| 创作模式 | 通用', '创作模式 | 通用 |', '创作模式：通用'):
            with self.subTest(declaration=declaration):
                text = declaration + '\n' + LEGACY
                self.assertEqual(engine.引擎模式(text), '')
                self.assertTrue(any('创作模式' in item for item in engine.引擎卡检查(text)))

    def test_malformed_duplicate_mode_does_not_hide_behind_valid_general_mode(self):
        text = general_card() + '\n| 创作模式 | 升级对抗\n'
        self.assertEqual(engine.引擎模式(text), '')
        self.assertTrue(any('创作模式' in item for item in engine.引擎卡检查(text)))

    def test_foundation_d11_accepts_general_card_without_escalation(self):
        intent = '\n'.join('| %s | %s |' % (name, 'ai_draft' if name == '合作方式' else '测试约定')
                           for name in foundation.意图必填)
        decisions = '\n'.join('| D%02d | %s | 测试原案 | %s | 测试理由 | 用户原案 | 已确认 |'
                              % (i, name, '方向生成' if name == '文风方向' else '测试选择')
                              for i, name in enumerate(foundation.必需决策, 1))
        reader = {foundation.意图rel: intent, foundation.决策rel: decisions,
                  engine.ENGINE_REL: general_card()}.get
        errors = foundation.核开书内容(None, reader)[0]
        self.assertFalse(any(item.startswith('读者引擎卡：') for item in errors), errors)

    def test_candidate_reader_and_formal_reader_remain_separate(self):
        self.write(engine.ENGINE_REL, LEGACY)
        self.assertEqual(engine.创作模式(str(self.project)), '升级对抗')
        self.assertEqual(engine.创作模式(str(self.project), lambda rel: general_card()), '通用')
        self.assertEqual((self.project / engine.ENGINE_REL).read_text(encoding='utf-8'), LEGACY)

    def test_general_reports_do_not_require_fixed_suspense_count(self):
        self.setup_arc(general_card())
        self.assertNotIn('3—5', output(engine.报告_engine, str(self.project))[1])
        self.assertNotIn('3—5', output(engine.报告_hooks, str(self.project), 'K0001')[1])
        self.write(engine.ENGINE_REL, LEGACY)
        self.assertIn('3—5', output(engine.报告_engine, str(self.project))[1])
        self.assertIn('3—5', output(engine.报告_hooks, str(self.project), 'K0001')[1])

    def test_general_recognition_and_quiet_ending_use_existing_hook_format(self):
        self.setup_arc(general_card())
        self.write('00_设定层/弧卡_A01.md', '| 范围 | K0001—K0002 |\n')
        for kind in ('新信息', '关系变化', '弧末收束（理由：本章体验已完整）'):
            with self.subTest(kind=kind):
                self.write(engine.LEDGER_REL, '## 章末钩子记录\n'
                           '| K0001 | 她第一次意识到两人的习惯已经不同 | %s | 无 | 无 |\n' % kind)
                self.assertEqual(engine.钩子问题(str(self.project), 'K0001'), [])
        self.write(engine.LEDGER_REL, '## 章末钩子记录\n| K0001 | 体验已结束 | 弧末收束 | 无 | 无 |\n')
        self.assertTrue(engine.钩子问题(str(self.project), 'K0001'))

    def test_new_arc_inherits_unapproved_revision_mode_without_changing_formal_card(self):
        self.setup_arc(LEGACY)
        self.write('_候选/REVISE/' + engine.ENGINE_REL, general_card())
        code, report = output(engine.new_arc, str(self.project), 'A01', 'K0001-K0002')
        self.assertEqual(code, 0, report)
        arc = (self.project / '_候选/REVISE/00_设定层/弧卡_A01.md').read_text(encoding='utf-8')
        self.assertIn('| 创作模式 | 通用 |', arc)
        self.assertEqual((self.project / engine.ENGINE_REL).read_text(encoding='utf-8'), LEGACY)

    def test_new_arc_retains_legacy_mode_and_refuses_invalid_mode(self):
        self.setup_arc(LEGACY)
        code, report = output(engine.new_arc, str(self.project), 'A01', 'K0001-K0002')
        self.assertEqual(code, 0, report)
        self.assertIn('| 创作模式 | 升级对抗 |',
                      (self.project / '_候选/REVISE/00_设定层/弧卡_A01.md').read_text(encoding='utf-8'))
        self.write('_候选/REVISE/' + engine.ENGINE_REL, '| 创作模式 | 未知 |\n' + LEGACY)
        code, report = output(engine.new_arc, str(self.project), 'A02', 'K0001-K0002')
        self.assertNotEqual(code, 0, report)
        self.assertFalse((self.project / '_候选/REVISE/00_设定层/弧卡_A02.md').exists())

    def test_large_cli_prompt_says_research_optional_and_is_read_only(self):
        project = Path(self.temp.name) / 'cli-book'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'novel.py'), 'init', str(project)],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = {str(p.relative_to(project)): p.read_bytes() for p in project.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, '-B', str(project / 'novel.py'), 'outline', '--prompt', '--scope', 'large'],
                                cwd=project, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('本轮榜单正文研究可选', result.stdout)
        self.assertIn('本轮不做', result.stdout)
        self.assertNotIn('必须开展本轮相关榜单正文研究', result.stdout)
        self.assertEqual({str(p.relative_to(project)): p.read_bytes() for p in project.rglob('*') if p.is_file()}, before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
