# -*- coding: utf-8 -*-
"""悬疑插件专属：揭晓之前，这条线索到底有没有出现在正文里。

外部评估要过一张「公平推理证据表」，被 v3.6 一并拒了，理由是"每章多填字段"。
那个理由对另外四项成立，对这一项不成立——它要的东西机器真的能验：

    某条线索的**首现章号**，是不是真的早于**揭晓章号**；
    首现的那一章，事实记录里是不是真的登记过这条线索。

这不需要读懂语义，只要比对编号和查一次登记。提示词做不到这件事，它只能
提醒人自己去想；而"揭晓时用了读者没见过的线索"恰恰是人最容易漏的一种。

只在悬疑插件启用时触发。通用流程不增加任何字段——用的全是 05b 线索兑现表
和 06 事实记录里**已经要求填**的列。
"""
import re

# 线索兑现表的两张表列名不同，都要认。
_首现列 = ('首次出现章',)
_揭晓列 = ('实际揭晓章', '结清章')
_计划列 = ('计划揭晓章',)


def _表(文本):
    """把 markdown 里所有表切成 [(表头单元格, [数据行单元格])]。"""
    出 = []
    头 = None; 体 = []
    for 行 in (文本 or '').split('\n'):
        s = 行.strip()
        if not s.startswith('|'):
            if 头: 出.append((头, 体)); 头 = None; 体 = []
            continue
        单元 = [c.strip().replace('**', '') for c in s.strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', c) for c in 单元 if c):
            continue                      # 分隔行
        if 头 is None:
            头 = 单元
        else:
            体.append(单元)
    if 头: 出.append((头, 体))
    return 出


def _取(头, 行, 候选):
    for 名 in 候选:
        if 名 in 头:
            i = 头.index(名)
            if i < len(行):
                return 行[i].strip()
    return ''


def _章号(值):
    """从单元格里抠出 K 加四位数字。抠不出来返回 None。"""
    m = re.search(r'K(\d{4})', 值 or '')
    return int(m.group(1)) if m else None


def _空(值):
    return (not 值) or 值 in ('—', '-', '无', '待定', '未定', '/')


def 登记章节(事实文, 事实归档文):
    """{章号int: 该章事实记录段落原文}。用来查线索首现时有没有登记。"""
    出 = {}
    for 文 in (事实文 or '', 事实归档文 or ''):
        当前 = None
        for 行 in 文.split('\n'):
            m = re.match(r'^#{2,4}\s*(K\d{4})', 行.strip())
            if m:
                当前 = _章号(m.group(1))
                出.setdefault(当前, [])
                continue
            if 当前 is not None:
                出[当前].append(行)
    return {k: '\n'.join(v) for k, v in 出.items()}


def 核对(线索文, 归档文, 事实文, 事实归档文, 正文章号, 本章号=None):
    """返回 (阻断项, 提醒项)。

    正文章号：05_正文 里真实存在的章号集合（int）。
    本章号  ：当前提交的章号，用来判断"计划揭晓章已经过了"。
    """
    阻断 = []; 提醒 = []
    登记 = 登记章节(事实文, 事实归档文)
    for 文 in (线索文, 归档文):
        for 头, 体 in _表(文):
            if not 头 or '线索 ID' not in 头[0]:
                continue
            for 行 in 体:
                cid = 行[0].strip().replace('**', '') if 行 else ''
                if not re.fullmatch(r'C\d+', cid):
                    continue
                首 = _取(头, 行, _首现列)
                揭 = _取(头, 行, _揭晓列)
                计 = _取(头, 行, _计划列)
                首n = _章号(首); 揭n = _章号(揭)

                if not _空(揭) and 揭n is None:
                    阻断.append('%s 揭晓章「%s」不是合法章号（要写成 K0007）' % (cid, 揭))
                    continue
                if 揭n is None:
                    # 还没揭晓：只提醒计划揭晓章是不是已经过去了
                    计n = _章号(计)
                    if 计n and 本章号 and 计n < 本章号:
                        提醒.append('%s 计划在 K%04d 揭晓，现在已经到 K%04d 了，'
                                    '它还挂在未揭晓' % (cid, 计n, 本章号))
                    continue

                # 揭晓了 —— 三道公平性检查
                if _空(首) or 首n is None:
                    阻断.append('%s 在 K%04d 揭晓，但首次出现章是空的。'
                                '揭晓一条从没铺过的线索，读者没有机会推理'
                                % (cid, 揭n))
                    continue
                if 首n > 揭n:
                    阻断.append('%s 首现 K%04d 排在揭晓 K%04d 之后，章号反了'
                                % (cid, 首n, 揭n))
                    continue
                if 首n == 揭n:
                    阻断.append('%s 当章铺、当章揭（都在 K%04d）。读者没有推理的余地，'
                                '这是通知不是揭晓。真要这样写，把首现章改成它真正'
                                '第一次出现的那一章' % (cid, 首n))
                    continue
                if 正文章号 and 首n not in 正文章号:
                    阻断.append('%s 声称首现于 K%04d，但 05_正文 里没有这一章。'
                                '铺垫不在纸上' % (cid, 首n))
                    continue
                段 = 登记.get(首n, '')
                # \b 在中文里不成立：中文字符在 unicode 下算 \w，"C1的线索"
                # 会被判成没登记。用前后不是字母数字来定界，同时仍然区分 C1 与 C10。
                if 段 and not re.search(r'(?<![0-9A-Za-z])%s(?![0-9A-Za-z])'
                                        % re.escape(cid), 段):
                    提醒.append('%s 声称首现于 K%04d，但那一章的事实记录里没登记它。'
                                '要么当时漏登了，要么首现章号填错了' % (cid, 首n))
    return 阻断, 提醒
