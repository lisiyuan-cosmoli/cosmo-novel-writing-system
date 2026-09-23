#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一屏项目状态。

给"刚接手这个项目的人或代理"看的：现在写到哪、上一笔是什么、
还有什么没决定、带宽还剩多少。

它**只读**：不恢复事务、不删锁、不写 project.json、不建任何临时文件。
项目有未完成事务时它照常报告，但不替用户决定恢复——恢复会改写正式文件，
只能由 `novel.py recover` 显式触发。
"""
from __future__ import print_function

import argparse
import os
import re
import sys

import v2_core as core
import 事务


def _读(project, rel):
    return core.read_text(os.path.join(project, rel), '') or ''


def _大纲(project):
    rows = []
    for line in _读(project, '00_设定层/03_分章大纲.md').splitlines():
        if not re.match(r'^\|\s*K\d{4}\s*\|', line):
            continue
        cells = [c.strip().replace('**', '') for c in line.strip().strip('|').split('|')]
        if re.fullmatch(r'K\d{4}', cells[0]) and cells[1].isdigit():
            rows.append((cells[0], int(cells[1]), cells[-1]))
    rows.sort(key=lambda row: row[1])
    return rows


def _活项阻塞(project):
    text = _读(project, '项目配置.md')
    if '## 八、' not in text:
        return None
    section = re.split(r'\n## ', text.split('## 八、', 1)[1])[0]
    out = []
    for line in section.splitlines():
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 3:
            continue
        flag = cells[2].replace('*', '').replace(' ', '').replace('️', '')
        if flag == '🔴阻塞':
            out.append('#%s %s' % (cells[0], cells[1][:40]))
    return out


def _已写净字(project, finalized, context=None):
    净 = 0
    for kid, _no, _s in finalized:
        rel = '05_正文/%s.md' % kid
        data = context.files.get(rel) if context is not None else None
        try:
            文 = data.decode('utf-8') if data is not None else _读(project, rel)
        except UnicodeError:
            文 = ''
        m = re.search(r'字数:(\d+)', 文.split('\n', 1)[0] if 文 else '')
        净 += int(m.group(1)) if m else len(re.sub(r'[\s#\-*>|]', '',
                    文.split('\n', 1)[1] if 文 and '\n' in 文 else ''))
    return 净


def _目标(project):
    """返回 (目标总字数, 预计章数)。取不到就返回 None，**不猜**。

    三条要当心的：
      · 「每章约 2000 字」不是总字数。带"每章"的行不参与总字数。
      · 值里写「不设」表示故意不设目标 —— 不设是一个决定，不是漏填。
        但同一行的章数照样要读，所以只跳过字数、不跳过整行。
      · 表头文字里也可能出现「不设」（"字数可写「不设」"），所以只看值那一格。
    """
    文 = (_读(project, '项目配置.md') + '\n' +
          _读(project, '00_设定层/01_固定设定.md'))
    字 = 章 = None
    for line in 文.split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            continue
        格 = [x.strip().replace('**', '') for x in s.strip('|').split('|')]
        if len(格) < 2:
            continue
        标, 值 = 格[0], 格[1]
        if not re.search(r'目标.{0,4}字数|字数\s*/\s*章数|预计章数|章数', 标):
            continue
        if 章 is None:
            m = re.search(r'(\d{1,4})\s*章', 值)
            if m:
                章 = int(m.group(1))
        if 字 is None and '不设' not in 值 and '每章' not in 标:
            m = re.search(r'(\d+(?:\.\d+)?)\s*万', 值)
            if m:
                字 = int(float(m.group(1)) * 10000)
            else:
                # 只认"总字数"语境下的裸数字，且要够大；「每章 2000 字」不算
                m = re.search(r'(\d{4,})\s*字', 值)
                if m and '每章' not in 值:
                    字 = int(m.group(1))
    return 字, 章


def _决策统计(project):
    """返回 (已确认数, 仍待确认的类别)。读不到就当零，调用方不据此放行。"""
    text = _读(project, '06_归档/开书决策记录.md')
    已确认, 待定 = 0, []
    for line in text.split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip().replace('**', '') for c in s.strip('|').split('|')]
        if len(cells) < 7 or not re.fullmatch(r'D\d{2,}', cells[0]):
            continue
        if cells[6] == '已确认':
            已确认 += 1
        elif cells[6] == '待定':
            待定.append(cells[1])
    return 已确认, 待定


def main(argv=None):
    parser = argparse.ArgumentParser(prog='status', description='一屏项目状态')
    parser.add_argument('project', nargs='?', default='.')
    args = parser.parse_args(argv)
    project = core.resolve_project(args.project)
    manifest = core.load_project(project, required=False)

    W = 72
    print('=' * W)
    print('项目状态  %s' % (manifest.get('title') if manifest else os.path.basename(project)))
    print('=' * W)

    待办 = []
    review_context = None
    if manifest is None:
        print('  结构版本    缺 project.json —— 这不是一个 v3 项目')
        待办.append('先在新版母版运行 python3 novel.py migrate "<本项目>" --apply')
    else:
        print('  系统版本    %s（结构 schema %s）' %
              (manifest.get('system_version'), manifest.get('schema_version')))
        import 开书探索
        try:
            print('  开书研究    ' + 开书探索.status_line(project))
        except core.ProjectError as exc:
            print('  开书研究    记录异常：' + str(exc))
            待办.append('按需核对研究记录；未把异常解释为研究完成')
        import 结构复盘
        review_context = 结构复盘.ReadContext(project)
        print('  结构复盘    ' + 结构复盘.safe_summary(project, review_context))
        import 运行反馈
        print('  运行问题    ' + 运行反馈.safe_summary(project))
        状态 = core.init_state(manifest)
        块 = manifest.get('initialization') or {}
        标签 = {'draft': '尚未确认（不能写第一章）',
                'confirmed': '已确认',
                'legacy': '旧项目（可以继续写，未经 3.3 开书确认）'}
        print('  开书状态    %s　%s' % (状态, 标签.get(状态, '')))
        if 状态 == 'confirmed':
            print('  合作方式    %s' % (块.get('mode') or '未记录'))
        候选INIT = os.path.isdir(os.path.join(project, '_候选', 'INIT'))
        if 状态 == 'draft':
            if 候选INIT:
                待办.append('开书候选区已存在，继续填完再运行 python3 novel.py foundation')
            else:
                待办.append('先完成开书：python3 novel.py foundation --prepare')
        elif 状态 == 'legacy':
            待办.append('本项目未经 3.3 开书确认。想补做时运行 python3 novel.py foundation --prepare')
        elif 候选INIT:
            待办.append('_候选/INIT 还在，处理掉或删除它')
        已确认, 待定 = _决策统计(project)
        if 已确认 or 待定:
            print('  开书决策    已确认 %d 项%s' %
                  (已确认, ('，仍待确认：' + '、'.join(待定)) if 待定 else ''))

        decision = manifest.get('plugin_decision')
        plugins = manifest.get('enabled_plugins') or []
        if decision == 'undecided':
            print('  题材插件    尚未表态')
            待办.append('明确插件决定：python3 novel.py plugin none，或 plugin install <插件>')
        elif decision == 'none':
            print('  题材插件    明确不启用（核心流程完整可用）')
        else:
            print('  题材插件    %s' % '、'.join(plugins))
        print('  归档基线    %s' % manifest.get('archive_required_from'))

    rows = _大纲(project)
    finalized = [row for row in rows if '已定稿' in row[2]]
    pending = [row for row in rows
               if '已定稿' not in row[2] and not re.search(r'已废弃', row[2])]
    print('  大纲进度    全书 %d 章，已定稿 %d 章' % (len(rows), len(finalized)))
    if finalized:
        print('  最新定稿    %s（第 %d 章）' % (finalized[-1][0], finalized[-1][1]))
    if pending:
        print('  下一章      %s（第 %d 章，状态：%s）' %
              (pending[0][0], pending[0][1], pending[0][2] or '空'))

    try:
        import 文风档
        _pid, _chosen = 文风档.当前档(project)
        print('  文风档      %s%s' % ((文风档.档信息(project) or {}).get('name', _pid),
                                       '' if _chosen else '（未选择，按文学克制处理）'))
    except Exception as exc:
        print('  文风档      读取异常：%s' % exc)
    # 4.0 读者引擎层：一行看清是否启用、当前弧、活动悬念与最近钩子类型
    try:
        import 引擎
        引擎文 = 引擎.读(project, 引擎.ENGINE_REL)
        if 引擎文 is None:
            print('  读者引擎    未建立（旧项目：sync 补模板后用 engine --prepare 填写）')
        elif 引擎.引擎卡检查(引擎文):
            print('  读者引擎    模板未填写，引擎层未启用')
        else:
            序 = 引擎.大纲序(project)
            账 = 引擎.悬念账(引擎.读(project, 引擎.LEDGER_REL) or '')
            下 = pending[0][0] if pending else (finalized[-1][0] if finalized else None)
            弧 = 引擎.所属弧(project, 下, 序) if 下 else None
            近 = [引擎.钩子类型(账['hooks'][k]['type'])[0] for k in 账['order'][-3:]]
            print('  读者引擎    已启用；%s；活动悬念 %d 个；最近钩子 %s' % (
                ('当前弧 %s（%s—%s）' % (弧['id'], 弧['start'], 弧['end'])) if 弧 else '下一章不在任何弧卡内',
                引擎.活动数(账), '、'.join(近) or '无'))
            if not 弧 and 下:
                待办.append('下一章 %s 不在任何弧卡范围内：先 novel.py arc --new 建弧卡，交作者批准' % 下)
    except Exception as exc:
        print('  读者引擎    读取异常：%s' % exc)

    snapshot = re.search(r'^>\s*状态[：:].*更新至\s+(K\d{4})', _读(project, '01_运行层/04_状态快照.md'), re.M)
    print('  状态快照    更新至 %s' % (snapshot.group(1) if snapshot else '抬头读不到'))

    # ── 事务 ────────────────────────────────────────
    try:
        head = 事务.head(project)
        undone = 事务.undone_ids(project)
        rows_tx = 事务.history(project, 1)
        if rows_tx:
            print('  最近提交    %s  %s' % (rows_tx[0].get('id'), rows_tx[0].get('label', '')))
        else:
            print('  最近提交    还没有')
        if head and head in undone:
            print('              ⚠ HEAD 指向的这笔已被撤销')
    except 事务.TransactionError as exc:
        print('  事务状态    异常：%s' % str(exc).splitlines()[0])
        待办.append('先处理事务异常，再做任何正式写入')

    if os.path.isfile(os.path.join(project, '.novel', 'transaction.json')):
        待办.append('有未恢复事务：python3 novel.py recover')

    candidate_root = os.path.join(project, '_候选')
    pending_candidates = sorted(name for name in os.listdir(candidate_root)
                                if (name in ('INIT', 'REVISE') or re.fullmatch(r'K\d{4}(?:-K\d{4})?', name))
                                and os.path.isdir(os.path.join(candidate_root, name))) \
        if os.path.isdir(candidate_root) else []
    if pending_candidates:
        print('  未处理候选  %s' % '、'.join(pending_candidates))
        待办.append('候选区还有 %s，按已有授权继续核对；未决定前保留候选' % '、'.join(pending_candidates))
    if os.path.isdir(os.path.join(candidate_root, '探索')):
        print('  探索资料    已保留；不属于待提交候选，不要求清理')

    # ── 带宽 ────────────────────────────────────────
    config = _读(project, '项目配置.md')
    goal = re.search(r'读取包目标\s*[：:]\s*(\d[\d,]*)', config)
    facts = len(_读(project, '01_运行层/06_事实记录.md'))
    print('  事实资料存量  %s 字符（原始事实文件，不是读取包实际占用）' % format(facts, ','))
    if goal:
        goal_value = int(goal.group(1).replace(',', ''))
        print('  读取包目标  %s 字符；实际占用以 package 的预算检查为准' % format(goal_value, ','))

    style_text = _读(project, '02_检查层/11_文风基线.md')
    if not style_text:
        待办.append('缺 02_检查层/11_文风基线.md，从新版母版 sync 补入')
    else:
        import 文风
        style_state, style_note = 文风.基线提醒(project)
        print('  文风基线    ' + style_state)
        if style_note and finalized:
            待办.append(style_note)

    # ── 字数预测（LENGTH-008）────────────────────────
    目标字, 计划章 = _目标(project)
    if finalized and not 目标字 and 计划章:
        # 明确不设字数目标的项目：只报事实，不报偏离，也不给"该写多少"的建议。
        净 = _已写净字(project, finalized, review_context)
        print('  写作进度    章节 %d／%d；已写 %s 字，平均每章 %d 字（未设字数目标）'
              % (len(finalized), 计划章, format(净, ','), 净 / float(len(finalized))))
    elif finalized and 目标字 and 计划章:
        净 = _已写净字(project, finalized, review_context)
        均 = 净 / float(len(finalized))
        推算 = 均 * 计划章
        章比 = len(finalized) * 100.0 / 计划章
        字比 = 净 * 100.0 / 目标字
        print('  字数进度    已写 %s ／ 目标 %s（%.0f%%）；章节 %d／%d（%.0f%%）'
              % (format(净, ','), format(目标字, ','), 字比, len(finalized), 计划章, 章比))
        print('              平均每章 %d 字，按此推算完稿约 %s 字' % (均, format(int(推算), ',')))
        if len(finalized) >= 3:
            偏 = (推算 - 目标字) * 100.0 / 目标字
            if abs(偏) > 15:
                需 = (目标字 - 净) / float(max(1, 计划章 - len(finalized)))
                待办.append('按当前节奏推算完稿约 %s 字，偏离目标 %+.0f%%。'
                            '后续每章需平均 %d 字才能达标——也可以改目标或加章数，'
                            '不要靠补描写凑字数' % (format(int(推算), ','), 偏, 需))
            if abs(章比 - 字比) > 10:
                待办.append('章节完成 %.0f%% 但字数只完成 %.0f%%，两者相差超过十个百分点，'
                            '复核一下章数与目标是否还合适' % (章比, 字比))

    # ── 用户可见进度是否过期（STATE-010）──────────────
    配置文 = _读(project, '项目配置.md')
    m = re.search(r'\|\s*当前进度[^|]*\|([^|]*)\|', 配置文)
    if m:
        写着 = m.group(1).strip()
        实际 = finalized[-1][0] if finalized else 'K0000'
        if 实际 not in 写着:
            待办.append('项目配置 §一 的「当前进度」写着「%s」，实际已定稿到 %s。'
                        '这一栏容易过期，改掉它或删掉这一行——大纲和正文才是章节状态的判据'
                        % (写着[:20], 实际))

    blocked = _活项阻塞(project)
    if blocked is None:
        待办.append('项目配置 §八 活项表读不到 —— 读不到不等于没有阻塞')
    elif blocked:
        print('  内容阻塞    %d 项' % len(blocked))
        for item in blocked:
            print('              🔴 ' + item)
        待办.append('§八 有 %d 项 🔴阻塞，正式读取包和提交都会被挡住' % len(blocked))

    print('=' * W)
    if 待办:
        print('待办 %d 项：' % len(待办))
        for item in 待办:
            print('  · ' + item)
    else:
        print('没有待办。下一步：python3 novel.py brief <下一章永久ID> --write')
    print('※ 本命令只读结构与记录，一个字节都不改；也不判断故事本身。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
