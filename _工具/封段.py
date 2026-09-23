#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记忆段封段：把已经写成阶段摘要的章节事实从 06 移进 06b。

为什么要有这个命令
    `06_事实记录.md` 按窗口读取，历史预览与阶段摘要仍会累计。不封段，读取包会随章数
    线性膨胀，最后在某一章直接撞破硬上限，命令失败。v2 把封段写成了模板
    注释里的一句话，没有命令、没有提醒、没有检查，等于把一条承重流程交给
    作者去记。这里把**机械搬运**交给工具，**阶段摘要仍然由人写**——
    摘要是这一段还要留给后文的东西，工具不知道该留什么。

用法
    python3 novel.py seal K0001 K0010            # 试算
    python3 novel.py seal K0001 K0010 --apply    # 正式封段（走事务，可回退）
"""
from __future__ import print_function

import argparse
import io
import os
import re

import v2_core as core
import 事务


事实rel = '01_运行层/06_事实记录.md'
归档rel = '01_运行层/06b_事实记录_已归档段.md'
占位词 = ('（填写）', '（填这里）', '待定', '待补', 'TODO', 'TBD', '（示例')


def _读(project, rel):
    return core.read_text(os.path.join(project, rel))


def _章号(kid):
    return int(kid[1:])


def _大纲状态(project):
    """永久 ID → 状态列。顺序以大纲行序为准。"""
    text = _读(project, '00_设定层/03_分章大纲.md') or ''
    out = {}
    for line in text.splitlines():
        if not re.match(r'^\|\s*K\d{4}\s*\|', line):
            continue
        cells = [c.strip().replace('**', '') for c in line.strip().strip('|').split('|')]
        if re.fullmatch(r'K\d{4}', cells[0]):
            out[cells[0]] = cells[-1] if len(cells) > 1 else ''
    return out


def 切条目(text):
    """把事实记录切成 [(永久ID, 原文段落)]，只认 `### K####` 开头的章节条目。"""
    out = []
    pattern = re.compile(r'(?ms)^###\s+(K\d{4})\b.*?(?=^###\s|^##\s|\Z)')
    for match in pattern.finditer(text or ''):
        out.append((match.group(1), match.group(0)))
    return out


def 找摘要(text, 起, 止):
    """范围对应的阶段摘要必须**已经写好**才允许封段。返回 (是否合格, 说明)。"""
    head = re.compile(r'(?ms)^###\s+记忆段\s+%s\s+至\s+%s\s+阶段摘要\s*$(.*?)(?=^###\s|^##\s|\Z)'
                      % (起, 止))
    match = head.search(text or '')
    if not match:
        return False, ('06_事实记录.md 里找不到 `### 记忆段 %s 至 %s 阶段摘要`。\n'
                       '     封段前先把这一段要留给后文的内容写成摘要——'
                       '工具不替你决定哪些细节可以丢。' % (起, 止))
    body = [l for l in match.group(1).splitlines()
            if l.strip() and not l.lstrip().startswith(('>', '#'))]
    joined = ' '.join(body)
    if len(joined.strip()) < 40:
        return False, '阶段摘要正文只有 %d 字符，太短，不足以替代被移走的详细条目' % len(joined.strip())
    if any(w in joined for w in 占位词):
        return False, '阶段摘要里还留着占位文字'
    return True, '已写，%d 字符' % len(joined.strip())


def 计划(project, 起, 止):
    """返回 (变更字典, 报告行, 错误列表)。变更为空表示不该继续。"""
    报告, 错误 = [], []
    事实 = _读(project, 事实rel)
    归档 = _读(project, 归档rel)
    if 事实 is None:
        错误.append('%s 取不到' % 事实rel)
    if 归档 is None:
        错误.append('%s 取不到' % 归档rel)
    if 错误:
        return {}, 报告, 错误

    if _章号(起) > _章号(止):
        错误.append('起始永久 ID 必须不大于结束永久 ID')
        return {}, 报告, 错误

    状态 = _大纲状态(project)
    范围 = [k for k in 状态 if _章号(起) <= _章号(k) <= _章号(止)]
    缺登记 = [k for k in 范围 if '已定稿' not in 状态.get(k, '')]
    if not 范围:
        错误.append('分章大纲里没有 %s 到 %s 之间的章节' % (起, 止))
    if 缺登记:
        错误.append('这些章还没有标已定稿，不能封段：%s' % '、'.join(sorted(缺登记)))

    条目 = 切条目(事实)
    命中 = [(kid, seg) for kid, seg in 条目 if _章号(起) <= _章号(kid) <= _章号(止)]
    命中ID = [kid for kid, _ in 命中]
    if not 命中:
        错误.append('06_事实记录.md 的范围内没有可搬运的章节条目（可能已经封过段）')
    漏 = sorted(set(范围) - set(命中ID))
    if 漏 and not 缺登记:
        错误.append('这些已定稿章在 06 里没有条目，先补齐再封段：%s' % '、'.join(漏))
    重 = [kid for kid in 命中ID if re.search(r'(?m)^###\s+%s\b' % kid, 归档)]
    if 重:
        错误.append('06b 里已经有这些条目，拒绝重复归档：%s' % '、'.join(sorted(重)))

    好, 说明 = 找摘要(事实, 起, 止)
    报告.append('阶段摘要：%s' % 说明)
    if not 好:
        错误.append(说明)
    if 错误:
        return {}, 报告, 错误

    新事实 = 事实
    for _, seg in 命中:
        新事实 = 新事实.replace(seg, '', 1)
    新事实 = re.sub(r'\n{4,}', '\n\n\n', 新事实).rstrip() + '\n'

    块 = ''.join(seg if seg.endswith('\n') else seg + '\n' for _, seg in 命中)
    新归档 = 归档.rstrip() + ('\n\n## 记忆段 %s 至 %s\n\n' % (起, 止)) + 块.strip() + '\n'

    报告.append('搬运 %d 条：%s' % (len(命中), '、'.join(命中ID)))
    报告.append('06_事实记录.md  %s → %s 字符' %
                (format(len(事实), ','), format(len(新事实), ',')))
    报告.append('06b_已归档段.md  %s → %s 字符' %
                (format(len(归档), ','), format(len(新归档), ',')))
    changes = {事实rel: 新事实.encode('utf-8'), 归档rel: 新归档.encode('utf-8')}
    return changes, 报告, []


def main(argv=None):
    parser = argparse.ArgumentParser(prog='seal', description='把已写成阶段摘要的章节事实移入 06b')
    parser.add_argument('起始')
    parser.add_argument('结束')
    parser.add_argument('project', nargs='?', default='.')
    parser.add_argument('--apply', action='store_true', help='正式写入（默认只试算）')
    args = parser.parse_args(argv)

    for value in (args.起始, args.结束):
        if not re.fullmatch(r'K\d{4}', value):
            print('✗ 永久 ID 形如 K0001。收到：%s' % value)
            return 2
    project = core.resolve_project(args.project)
    核心 = core.load_project(project)
    if 核心 is None:
        print('✗ 缺 project.json')
        return 2

    print('=' * 60)
    print('封段 · %s 至 %s · %s' % (args.起始, args.结束, '正式写入' if args.apply else '试算'))
    print('=' * 60)
    changes, 报告, 错误 = 计划(project, args.起始, args.结束)
    for line in 报告:
        print('  · ' + line)
    if 错误:
        print('✗ 不能封段：')
        for line in 错误:
            print('   · ' + line)
        return 1

    if not args.apply:
        print()
        print('※ 这是试算，没有改任何文件。确认后运行：')
        print('  python3 novel.py seal %s %s --apply' % (args.起始, args.结束))
        return 0

    def 复核():
        text = _读(project, 事实rel) or ''
        剩 = [kid for kid, _ in 切条目(text)
              if _章号(args.起始) <= _章号(kid) <= _章号(args.结束)]
        好, _说明 = 找摘要(text, args.起始, args.结束)
        return (not 剩) and 好, '封段后 06 里仍有 %s，或摘要丢失' % '、'.join(剩)

    tx = 事务.apply_changes(project, changes,
                          'seal %s-%s' % (args.起始, args.结束),
                          validator=复核,
                          metadata={'seal_from': args.起始, 'seal_to': args.结束})
    print()
    print('✓ 已封段。事务 %s，需要时可用 python3 novel.py rollback 回退。' % tx['id'])
    print('  06 只保留阶段摘要，详细条目在 06b，闸门仍会在两份里查本章条目。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
