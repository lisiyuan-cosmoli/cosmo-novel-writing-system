#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重复动作检索：工具自己跑，不再让人抄命令和命中行。

为什么改成命令
    手工重复动作清单会累积历史命中，并要求抄写命令、行数与片段。

    这些全是机械劳动，而且抄完只能证明"有人打过一条命令"，证明不了检索
    真的跑过。工具自己跑，减少重复填写，又让这项检查
    从"证明打过命令"变成"真的跑过"。

    章节卡里只留**结论**：本章打算怎么处理命中项。

用法
    python3 novel.py repeat K0008              查最近三章
    python3 novel.py repeat K0008 --window 5   自定窗口
    python3 novel.py repeat K0008 --card       输出可直接贴进章节卡的结论块
"""
from __future__ import print_function

import argparse
import io
import os
import re
import sys
from collections import Counter

import v2_core as core


动作词 = ('挠', '撑', '举', '摸', '按', '搓', '抖', '顿', '点头', '摇头', '低头',
          '抬手', '沉默', '攥', '握', '扣', '掀', '推', '拧', '蹲', '站住', '停住')
对白词 = ('谢谢', '麻烦', '没事', '应该的', '算了', '行了', '就这样', '不用',
          '你说', '我知道', '别问', '走吧')
默认窗口 = 3


def _净(text):
    首行, _, 正文 = (text or '').partition('\n')
    if not 首行.strip().startswith('<!--'):
        正文 = text or ''
    return 正文


def 批内草稿(project, kid):
    """4.0 批次写作：前一章草稿还在 _候选/K0019-K0021/05_正文/ 里，没有定稿也要取样。"""
    root = os.path.join(project, '_候选')
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return None
    for name in names:
        m = re.fullmatch(r'(K\d{4})-(K\d{4})', name)
        path = os.path.join(root, name, '05_正文', '%s.md' % kid)
        if m and os.path.isfile(path) and not os.path.islink(path):
            return path
    return None


def _正文路径(project, kid):
    formal = os.path.join(project, '05_正文', '%s.md' % kid)
    return formal if os.path.isfile(formal) else 批内草稿(project, kid)


def 取窗口(project, kid, 窗口):
    """按展示章号取本章之前最近的 N 个已定稿章。永久 ID 不参与顺序推断。"""
    大纲 = core.read_text(os.path.join(project, '00_设定层', '03_分章大纲.md'), '') or ''
    行 = []
    for line in 大纲.split('\n'):
        if not re.match(r'^\|\s*K\d{4}\s*\|', line):
            continue
        c = [x.strip().replace('**', '') for x in line.strip().strip('|').split('|')]
        if len(c) >= 2 and re.fullmatch(r'K\d{4}', c[0]) and c[1].isdigit():
            行.append((c[0], int(c[1]), c[-1]))
    行.sort(key=lambda r: r[1])
    本 = next((n for k, n, _ in 行 if k == kid), None)
    if 本 is None:
        return None, []
    可用 = [(k, n) for k, n, s in 行
            if n < 本 and (('已定稿' in s
                           and os.path.isfile(os.path.join(project, '05_正文', '%s.md' % k)))
                          or 批内草稿(project, k))]
    return 本, [k for k, _ in 可用[-窗口:]]


def 扫(project, 章列表):
    """返回 {类别: [(词, 次数, [(章, 行号, 原文)])]}。"""
    结果 = {'动作': {}, '对白': {}, '章末': []}
    for kid in 章列表:
        文 = core.read_text(_正文路径(project, kid) or '', '') or ''
        行 = _净(文).split('\n')
        for no, line in enumerate(行, 1):
            s = line.strip()
            if not s:
                continue
            for 词 in 动作词:
                if 词 in s:
                    结果['动作'].setdefault(词, []).append((kid, no, s))
            for 词 in 对白词:
                if 词 in s:
                    结果['对白'].setdefault(词, []).append((kid, no, s))
        实 = [l.strip() for l in 行 if l.strip()]
        if 实:
            结果['章末'].append((kid, 实[-1]))
    return 结果


def 归并(命中表, 下限=2):
    """只留跨章或多次出现的。单章出现一次不是重复。"""
    出 = []
    for 词, 行 in 命中表.items():
        章 = {k for k, _, _ in 行}
        if len(行) >= 下限 or len(章) >= 2:
            出.append((词, len(行), sorted(章), 行))
    return sorted(出, key=lambda x: (-len(x[2]), -x[1], x[0]))


def 取卡栏(project, kid, 名):
    文 = core.read_text(os.path.join(project, '06_归档', '章节卡_%s.md' % kid), '') or ''
    for line in 文.split('\n'):
        s = line.strip()
        if s.startswith('|') and 名 in s:
            c = [x.strip().replace('**', '') for x in s.strip('|').split('|')]
            if len(c) >= 2 and c[1]:
                return c[1]
    return ''


def 取三拍钩子(project, kid):
    """4.0 瘦身卡没有「章末不可逆变化」一栏，章末钩子写在「三拍」表第三格。"""
    文 = core.read_text(os.path.join(project, '06_归档', '章节卡_%s.md' % kid), '') or ''
    m = re.search(r'(?ms)^##\s+三拍[^\n]*\n(.*?)(?=^##\s|\Z)', 文)
    for line in (m.group(1) if m else '').split('\n'):
        s = line.strip()
        if not s.startswith('|') or '开头兑现' in s:
            continue
        c = [x.strip().replace('**', '') for x in s.strip('|').split('|')]
        if len(c) >= 3 and c[2] and not set(''.join(c)) <= set('-: '):
            return c[2]
    return ''


def 推进对比(project, 章列表):
    """并排最近几章的「章末不可逆变化」。

    每章都写着"他更确定了""关系更紧张了"这类东西时，书没有在动——
    而逐章读永远看不出来，因为每一章单看都说得过去。
    """
    出 = []
    for kid in 章列表:
        变 = 取卡栏(project, kid, '章末不可逆变化') or 取三拍钩子(project, kid)
        得 = 取卡栏(project, kid, '结束时谁获得了什么')
        出.append((kid, 变, 得))
    return 出


def 章末形态(条目):
    """章末落点按结尾类型粗分，只做提示。"""
    def 类(s):
        if re.search(r'[""「」].{0,20}$', s):
            return '对白收'
        if re.search(r'(没有|不再|再也|终于|只是|而已|罢了)', s):
            return '判断收'
        if re.search(r'\d|点|分|天亮|夜里|早上', s):
            return '时间收'
        return '动作或物件收'
    return [(k, 类(s), s[:40]) for k, s in 条目]


def main(argv=None):
    parser = argparse.ArgumentParser(prog='repeat', description='重复动作检索')
    parser.add_argument('kid')
    parser.add_argument('project', nargs='?', default='.')
    parser.add_argument('--window', type=int, default=默认窗口)
    parser.add_argument('--card', action='store_true', help='输出可贴进章节卡的结论块')
    args = parser.parse_args(argv)
    if args.kid and not re.fullmatch(r'K\d{4}', args.kid) and args.project == '.':
        args.project, args.kid = args.kid, args.project
    if not re.fullmatch(r'K\d{4}', args.kid or ''):
        print('✗ 永久 ID 形如 K0001。收到：%s' % args.kid)
        return 2
    project = core.resolve_project(args.project)
    本, 章列表 = 取窗口(project, args.kid, max(1, args.window))
    if 本 is None:
        print('✗ %s 不在分章大纲里' % args.kid)
        return 2
    if not 章列表:
        print('本章之前没有已定稿正文 —— 重复证据状态：无历史正文')
        if args.card:
            print()
            print('— 贴进章节卡「重复动作清单」的结论块 —')
            print('```text')
            print('| 重复证据状态 | 无历史正文 |')
            print('| 取样章 | 无（本章之前没有已定稿正文） |')
            print('| 命中总行数 | 0 行 |')
            print('| 检索方式 | novel.py repeat %s --window %d（工具执行，非手抄） |'
                  % (args.kid, args.window))
            print('| 本章处理 | 无历史正文，无需处理 |')
            print('```')
        return 0

    结果 = 扫(project, 章列表)
    动作 = 归并(结果['动作'])
    对白 = 归并(结果['对白'])
    末 = 章末形态(结果['章末'])
    总命中 = sum(n for _, n, _, _ in 动作) + sum(n for _, n, _, _ in 对白)

    W = 72
    print('=' * W)
    print('重复动作检索 · %s · 取样 %s' % (args.kid, '、'.join(章列表)))
    print('=' * W)
    print('  工具已实际扫描 %d 章，命中 %d 行。**不需要你再抄命令或行号。**'
          % (len(章列表), 总命中))
    print()
    for 名, 表 in (('动作', 动作), ('对白骨架', 对白)):
        if not 表:
            print('  %s：没有跨章重复。' % 名)
            continue
        print('  %s：%d 项跨章或多次出现' % (名, len(表)))
        for 词, 次, 章, 行 in 表[:8]:
            print('    「%s」%d 次，跨 %d 章（%s）' % (词, 次, len(章), '、'.join(章)))
            for kid, no, s in 行[:2]:
                print('        %s 第 %d 行：%s' % (kid, no, s if len(s) <= 46 else s[:44] + '…'))
        if len(表) > 8:
            print('    …另有 %d 项' % (len(表) - 8))
        print()
    print('  章末落点形态：')
    for kid, 型, s in 末:
        print('    %s  %-10s %s' % (kid, 型, s))
    形 = Counter(t for _, t, _ in 末)
    重 = [t for t, n in 形.items() if n >= 2]
    if 重:
        print('    ⚠ 连续用了同一种收法：%s。这是提醒，不是禁止——'
              '有意的回环要写明作用。' % '、'.join(重))
    推进 = 推进对比(project, 章列表)
    if any(变 for _k, 变, _d in 推进):
        print()
        print('  章末不可逆变化（并排看，不是逐章看）：')
        for kid, 变, 得 in 推进:
            print('    %s  %s' % (kid, (变 or '（章卡没写）')[:56]))
        虚 = ('更', '越发', '愈', '进一步', '继续', '依然', '仍然', '加深', '坚定', '紧张')
        软 = [k for k, 变, _d in 推进 if 变 and any(w in 变 for w in 虚)
              and not re.search(r'[0-9一二三四五六七八九十]|死|走|拿|给|烧|开|锁|断|写', 变)]
        if len(软) >= 2:
            print('    ⚠ %s 的「不可逆变化」都是程度词（更、越发、依然……），'
                  '没有一件具体的事。' % '、'.join(软))
            print('      这一类读起来通顺，但书没有在动 —— 逐章读看不出来，并排才看得见。')
    print()
    print('※ 命中不等于毛病。字面不同但承担同一功能才算重复；'
          '人物专属的小动作有意反复是设计。')
    print('※ 本命令只定位，判断留给第二遍（连续性与语言）。')

    if args.card:
        print()
        print('— 贴进章节卡「重复动作清单」的结论块 —')
        print('```text')
        print('| 重复证据状态 | 已完成 |')
        print('| 取样章 | %s |' % '、'.join(章列表))
        print('| 命中总行数 | %d 行 |' % 总命中)
        print('| 检索方式 | novel.py repeat %s --window %d（工具执行，非手抄） |'
              % (args.kid, args.window))
        if 动作 or 对白:
            前三 = (动作 + 对白)[:3]
            print('| 本章处理 | %s |' % '；'.join(
                '「%s」禁止再用或写明理由' % 词 for 词, _n, _c, _r in 前三))
        else:
            print('| 本章处理 | 无跨章重复，无需处理 |')
        print('```')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
