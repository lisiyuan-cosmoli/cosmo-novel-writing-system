#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取包去重回归。只从当前母版建立纯合成项目，不访问真实作品。

所有生成物位于临时目录并在退出时清理；不修改传入母版。
"""
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


def _run_checks(project=None):
    root = Path(project or Path(__file__).resolve().parent.parent).resolve()
    checks, profiles = [], {}

    def check(name, passed, detail=''):
        checks.append({'name': name, 'passed': bool(passed), 'detail': str(detail)})

    def load(name):
        spec = importlib.util.spec_from_file_location('read_efficiency_' + name,
                                                    root / '_工具' / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def cli(book, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        run = subprocess.run([sys.executable, '-B', str(book / 'novel.py')] + list(args),
                             cwd=book, capture_output=True, text=True, env=env)
        return run.returncode, run.stdout + run.stderr

    def require(book, *args):
        code, output = cli(book, *args)
        if code:
            raise RuntimeError('%r: %s' % (args, output[-1800:]))
        return output

    def emitted(book, output):
        match = re.search(r'^READ_PACKAGE=(.+)$', output, re.M)
        if not match:
            raise RuntimeError('成功读取包缺少路径：' + output[-500:])
        path = Path(match.group(1).strip())
        return (path if path.is_absolute() else book / path).read_text(encoding='utf-8')

    saved_path = list(sys.path)
    sys.path.insert(0, str(root / '_工具'))
    fixture = None
    try:
        module = load('读取包')
        fixture = load('新书自测')
        release = load('发布自测')
        with tempfile.TemporaryDirectory(prefix='novel-read-efficiency-') as temp:
            book = Path(temp) / 'synthetic'
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            run = subprocess.run([sys.executable, '-B', str(root / 'novel.py'), 'init', str(book)],
                                 capture_output=True, text=True, env=env)
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr)
            fixture.开书(str(book))
            fixture.章卡(str(book))
            emitted(book, require(book, 'brief', 'K0001', '--write'))
            emitted(book, require(book, 'package', 'K0001', '--write'))
            release.prepare_chapter_candidate(str(book))
            preview = require(book, 'commit', 'K0001')
            digest = re.search(r'^CANDIDATE_SHA256=([a-f0-9]{64})$', preview, re.M).group(1)
            require(book, 'commit', 'K0001', '--apply', '--approve', digest)
            require(book, 'doctor')
            check('当前模板合成开书、简报、正式包与首章提交链', True)

            # 以下为容量与锚定用的合成扩充，不能声称逐章经过创作或文学验证。
            outline_path = book / '00_设定层/03_分章大纲.md'
            outline = outline_path.read_text(encoding='utf-8')
            prefix = outline[:re.search(r'^\|\s*K0001', outline, re.M).start()]
            outline_path.write_text(prefix + '\n'.join(
                '| K%04d | %d | 陈守田 | 老宅 | 合成场景%d | 合成结果%d | %s |' %
                (n, n, n, n, '已定稿' if n < 13 else '未写') for n in range(1, 16)) + '\n', encoding='utf-8')
            facts = '# 合成事实记录\n\n### 记忆段 K0001 至 K0002 阶段摘要\n\n阶段摘要必须保留。\n'
            for n in range(1, 13):
                kid = 'K%04d' % n
                body = '第%d章片段起点。' % n + ''.join(
                    '第%d章第%d条合成观察，人物查看物品并记录变化。\n' % (n, j) for j in range(45)) + '第%d章片段终点。' % n
                measured = len(re.sub(r'[\s#\-*>|]', '', body))
                (book / ('05_正文/%s.md' % kid)).write_text(
                    '<!-- 永久ID:%s | 展示章号:%d | 视角:陈守田 | 字数:%d | 状态:已定稿 -->\n%s' %
                    (kid, n, measured, body), encoding='utf-8')
                (book / ('06_归档/梗概_%s_合成.md' % kid)).write_text('# %s\n\n合成观察。\n' % kid, encoding='utf-8')
                facts += '\n### %s（已确认）\n\n- 正文事实：%s\n- 长期保留：第%d章长期事实。\n  第%d章长期补充。\n- 角色判断：合成推测。\n' % (
                    kid, '合成事实。' * 60, n, n)
            (book / '01_运行层/06_事实记录.md').write_text(facts, encoding='utf-8')
            card_path = book / '06_归档/章节卡_K0013.md'
            card = (book / '06_归档/章节卡_K0001.md').read_text(encoding='utf-8').replace('K0001', 'K0013').replace(
                '| 展示章号 | 1 |', '| 展示章号 | 13 |')
            repeat = require(book, 'repeat', 'K0013', '--window', '3', '--card')
            block = re.search(r'```text\n(.*?)\n```', repeat, re.S).group(1)
            card = re.sub(r'(## 重复动作清单\n).*?(?=## 场景清单)',
                          lambda m: m.group(1) + '\n| 项 | 记录 |\n|---|---|\n' + block + '\n\n', card, flags=re.S)

            def old_request(request):
                card_path.write_text(card.replace('| 需要调阅的旧章 | 无 |',
                                                  '| 需要调阅的旧章 | %s |' % request), encoding='utf-8')

            for profile in ('fast', 'standard', 'full'):
                old_request('无')
                normal = emitted(book, require(book, 'package', 'K0013', '--profile', profile, '--write'))
                old_request('K0012§「第12章片段起点。」→「第12章片段终点。」')
                output = require(book, 'package', 'K0013', '--profile', profile, '--write')
                packed = emitted(book, output)
                assembled = module.装配(str(book), 'K0013', False, profile)
                sections = [row for row in assembled.来源 if row[0] == '05_正文/K0012.md']
                full = [body for _, scope, _, body in sections if scope == '全文']
                notes = [body for _, scope, _, body in sections if '仅来源定位' in scope]
                check(profile + ' 已带全文的片段只保留来源定位',
                      len(full) == 1 and len(notes) == 1 and '第12章第20条合成观察' not in notes[0])
                source = (book / '05_正文/K0012.md').read_text(encoding='utf-8')
                start = source.index('第12章片段起点。')
                end = source.index('第12章片段终点。') + len('第12章片段终点。')
                check(profile + ' 来源定位精确且边界仍为 DATA',
                      bool(notes) and ('第 %d–%d 字符' % (start + 1, end)) in notes[0]
                      and '<!-- ===== DATA ｜ 05_正文/K0012.md ／ 片段' in packed)
                check(profile + ' 重复生成同包及声明改变摘要',
                      packed == emitted(book, require(book, 'package', 'K0013', '--profile', profile, '--write'))
                      and normal != packed)
                profiles[profile] = {'without_anchor_chars': len(normal), 'with_anchor_chars': len(packed),
                                     'net_chars': assembled.净内容, 'reference_note_chars': len(notes[0]) if notes else None}

            # 即使最近章全文已经入包，错误锚点仍必须阻断并且零写出。
            body_path = book / '05_正文/K0012.md'
            saved_body = body_path.read_text(encoding='utf-8')
            cases = (
                ('缺失首锚', 'K0012§「不存在的首锚」→「第12章片段终点。」', saved_body),
                ('反向锚点', 'K0012§「第12章片段终点。」→「第12章片段起点。」', saved_body),
                ('重复首锚', 'K0012§「第12章片段起点。」→「第12章片段终点。」', saved_body + '第12章片段起点。'),
                ('重复尾锚', 'K0012§「第12章片段起点。」→「第12章片段终点。」', saved_body + '第12章片段终点。'),
            )
            for name, request, body in cases:
                old_request(request); body_path.write_text(body, encoding='utf-8')
                before = sorted(path.name for path in (book / '_读取包').iterdir())
                code, output = cli(book, 'package', 'K0013', '--profile', 'fast', '--write')
                after = sorted(path.name for path in (book / '_读取包').iterdir())
                check(name + ' 在已有全文时仍拒绝且不产生包', code != 0 and 'READ_PACKAGE=' not in output and before == after)
            body_path.write_text(saved_body, encoding='utf-8')
            old_request('K0001§「第1章片段起点。」→「第1章片段终点。」')
            packed = emitted(book, require(book, 'package', 'K0013', '--profile', 'fast', '--write'))
            assembled = module.装配(str(book), 'K0013', False, 'fast')
            parts = [body for rel, scope, _, body in assembled.来源 if rel == '05_正文/K0001.md' and scope.startswith('片段')]
            check('未带全文的历史章节仍实际装入锚定片段', len(parts) == 1 and '第1章第20条合成观察' in parts[0])

            order = {'K%04d' % n: n for n in range(1, 14)}
            trimmed = module.裁事实(facts, order, 'K0013', 2)
            check('多个旧事实只共享一条截取说明', trimmed.count('截取预览，不代表全部事实') == 1)
            check('全部旧条目保留 ID 与可追溯路径', all(
                '01_运行层/06_事实记录.md · K%04d 条目' % n in trimmed for n in range(1, 11)))
            check('新旧长期保留项及缩进补充完整保留', all(
                '- 长期保留：第%d章长期事实。\n  第%d章长期补充。' % (n, n) in trimmed for n in range(1, 13)))
            check('阶段摘要与最近两章完整条目保留', '阶段摘要必须保留。' in trimmed and
                  trimmed.count('合成事实。' * 60) == 2 and trimmed.count('- 角色判断：合成推测。') == 2)
            check('未知当前章与空输入保持既有兼容', module.裁事实(facts, {}, 'K9999', 2) == facts
                  and module.裁事实(None, {}, 'K9999', 2) is None)
            unknown = facts + '\n### K9999\n\n未知章节全文必须保留。\n'
            check('未知历史顺序条目不裁剪', '### K9999\n\n未知章节全文必须保留。' in module.裁事实(unknown, order, 'K0013', 2))
            fresh = '### K0012\n\n- 正文事实：最近一章。\n'
            check('没有旧条目时不新增公共说明', module.裁事实(fresh, order, 'K0013', 2) == fresh)
    except Exception as exc:
        check('读取效率回归执行完整性', False, repr(exc))
    finally:
        if fixture is not None:
            shutil.rmtree(fixture.本轮沙盘, ignore_errors=True)
        sys.path[:] = saved_path
    return {'passed': sum(row['passed'] for row in checks), 'failed': sum(not row['passed'] for row in checks),
            'tests': checks, 'profiles': profiles,
            'scope': '纯合成软件与流程验证；不证明文学质量'}


class ReadingEfficiencyTests(unittest.TestCase):
    def test_current_template_reading_flow_and_efficiency(self):
        result = _run_checks()
        for row in result['tests']:
            with self.subTest(name=row['name']):
                self.assertTrue(row['passed'], row['detail'])
        print(json.dumps({'passed': result['passed'], 'failed': result['failed'],
                          'profiles': result['profiles'], 'scope': result['scope']},
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    unittest.main()
