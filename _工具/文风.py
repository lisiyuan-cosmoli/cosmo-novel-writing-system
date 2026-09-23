#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文风度量：把"AI 感"里可计算的那部分量出来。

设计立场
    基线**不是母版定的**，是本书自己的正样本加**用户明确认可的**已定稿章节算出来的。母版写死
    一个"句长方差应大于 X"，等于把一种审美强加给所有题材。悬疑的短促和言情
    的绵长各有各的基线，工具不评判哪个好，只报告本章偏离了本书多少。

    因此本文件只有两类内容：**度量仪器**（句读、密度、感官分布的词表）和
    **指纹表命中**（_工具/AI腔词表.txt）。前者是尺子，后者是模型指纹，
    两者都不表达"应该怎么写"。

    不打总分。分数会变成目标，而这些指标全都能刷——把长句拆开塞几个短句，
    分数立刻好看，文本更碎。只报分布、只报行号。
"""
from __future__ import print_function

import argparse
import io
import math
import os
import re
import sys
from collections import Counter

import v2_core as core


句末 = '。！？…'
引号对 = (('「', '」'), ('“', '”'), ('『', '』'), ('《', '》'))

# ── 度量仪器：这些词表用来"数"，不用来"判好坏" ──────────────
比喻词 = ('像', '仿佛', '宛如', '犹如', '似的', '好似', '如同', '一般')
连接词 = ('然而', '但是', '于是', '因此', '与此同时', '接着', '紧接着', '随后',
          '同时', '不过', '而后', '所以', '因为', '虽然', '尽管', '既然')
情绪直陈 = ('悲伤', '愤怒', '绝望', '喜悦', '温柔', '痛苦', '恐惧', '焦虑',
            '欣慰', '悲哀', '复杂', '不安', '释然', '难过', '开心', '紧张',
            '兴奋', '委屈', '愧疚', '茫然')
感官 = {
    '视': ('看', '望', '瞥', '盯', '瞧', '目光', '视线', '颜色', '光', '影'),
    '听': ('听', '声', '响', '静', '喊', '叫', '低语', '脚步'),
    '触': ('摸', '碰', '握', '按', '压', '冷', '烫', '疼', '痒', '粗糙', '滑'),
    '嗅': ('闻', '味道', '气味', '香', '臭', '腥'),
    '味': ('尝', '甜', '苦', '咸', '酸', '辣'),
}
成对结构 = (r'不是[^\n]{1,12}而是', r'既[^\n]{1,10}又[^\n]{1,10}',
            r'一边[^\n]{1,10}一边', r'越[^\n]{1,8}越',
            r'[^\n，。]{2,8}、[^\n，。]{2,8}、[^\n，。]{2,8}[，。]')


# ══════════════ 文本切分 ══════════════

def 取正文(text):
    """去掉机器抬头与 Markdown 结构行，只留真正的正文。"""
    lines = []
    for line in (text or '').replace('\r\n', '\n').split('\n'):
        s = line.strip()
        if s.startswith('<!--') or s.startswith('#') or s.startswith('>'):
            continue
        if s.startswith('|') or s.startswith('```'):
            continue
        lines.append(line)
    return '\n'.join(lines)


def 分段(text):
    return [p.strip() for p in re.split(r'\n\s*\n', text or '') if p.strip()]


def 分句(text):
    """按句末标点切句，把紧跟其后的引号并进同一句。"""
    out, buf = [], []
    chars = list(text or '')
    i = 0
    while i < len(chars):
        ch = chars[i]
        buf.append(ch)
        if ch in 句末:
            while i + 1 < len(chars) and chars[i + 1] in '”」』"\'）)':
                i += 1
                buf.append(chars[i])
            s = ''.join(buf).strip()
            if s:
                out.append(s)
            buf = []
        i += 1
    tail = ''.join(buf).strip()
    if tail:
        out.append(tail)
    return [s for s in out if re.search(r'[一-鿿]', s)]


def 净字(text):
    return len(re.sub(r'[\s#\-*>|]', '', text or ''))


def _均值(xs):
    return sum(xs) / float(len(xs)) if xs else 0.0


def _标准差(xs):
    if len(xs) < 2:
        return 0.0
    m = _均值(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / float(len(xs) - 1))


def _每千字(n, 总字):
    return round(n * 1000.0 / 总字, 2) if 总字 else 0.0


# ══════════════ 度量 ══════════════

def 度量(raw):
    """返回一份可比较的分布指标。所有密度都按每千字归一。"""
    text = 取正文(raw)
    总字 = len(re.sub(r'\s', '', text))
    段 = 分段(text)
    句 = 分句(text)
    句长 = [len(re.sub(r'[\s“”「」『』]', '', s)) for s in 句]
    段句数 = [len(分句(p)) for p in 段]

    对白字 = 0
    for 左, 右 in 引号对:
        for m in re.finditer(re.escape(左) + r'([^' + re.escape(右) + r']{0,400})' + re.escape(右), text):
            对白字 += len(m.group(1))
    # 直引号左右同形，按行取奇数段。实际稿件里 " 用得很多，尤其是模型输出。
    # 这里的切片**不能复用 段**：段 保存的是全文段落，被覆盖后 段数 会变成
    # 最后一行的引号切片数（三段文本报成 1 段）。
    for line in text.split('\n'):
        for 记号 in ('"', "'"):
            引片 = line.split(记号)
            if len(引片) >= 3:
                对白字 += sum(len(引片[i]) for i in range(1, len(引片), 2))

    命中 = lambda words: sum(text.count(w) for w in words)
    感官计 = {k: 命中(v) for k, v in 感官.items()}
    感官总 = sum(感官计.values()) or 1

    return {
        '总字': 总字,
        '句数': len(句),
        '句长均值': round(_均值(句长), 1),
        '句长标准差': round(_标准差(句长), 1),
        '句长变异系数': round(_标准差(句长) / _均值(句长), 3) if _均值(句长) else 0.0,
        '短句占比': round(sum(1 for x in 句长 if x <= 8) / float(len(句长)), 3) if 句长 else 0.0,
        '长句占比': round(sum(1 for x in 句长 if x >= 40) / float(len(句长)), 3) if 句长 else 0.0,
        '段数': len(段),
        '段句数均值': round(_均值(段句数), 1),
        '段句数标准差': round(_标准差(段句数), 1),
        '对白占比': round(对白字 / float(总字), 3) if 总字 else 0.0,
        '比喻密度': _每千字(命中(比喻词), 总字),
        '连接词密度': _每千字(命中(连接词), 总字),
        '情绪直陈密度': _每千字(命中(情绪直陈), 总字),
        '成对结构密度': _每千字(sum(len(re.findall(p, text)) for p in 成对结构), 总字),
        '感官分布': {k: round(v / float(感官总), 3) for k, v in 感官计.items()},
    }


对比项 = ('句长均值', '句长标准差', '句长变异系数', '短句占比', '长句占比',
          '段句数均值', '对白占比', '比喻密度', '连接词密度',
          '情绪直陈密度', '成对结构密度')


# ══════════════ 指纹表 ══════════════

def _读词表(path):
    """返回 [(类别, 原文, 编译好的正则)]。坏正则不许把工具搞崩。"""
    out, 类别, 坏 = [], '未分类', []
    text = core.read_text(path, '') or ''
    for line in text.split('\n'):
        s = line.strip()
        if not s:
            continue
        if s.startswith('#'):
            if len(s) > 1 and not s.startswith('# '):
                类别 = s[1:].strip()
            continue
        s = s.split('##')[0].strip()
        if not s:
            continue
        try:
            out.append((类别, s, re.compile(s)))
        except re.error as exc:
            坏.append('%s：%s（%s）' % (os.path.basename(path), s, exc))
    return out, 坏


def 载入词表(project):
    条目, 坏 = [], []
    # 4.1：所选文风档声明的类别是本书的题材语汇，不算 AI 腔（只作用于母版通用层）
    try:
        import 文风档
        允许 = set(文风档.允许类别(project))
    except Exception:
        允许 = set()
    for name in ('AI腔词表.txt', 'AI腔词表_本项目.txt'):
        rows, bad = _读词表(os.path.join(project, '_工具', name))
        if name == 'AI腔词表.txt':
            rows = [r for r in rows if r[0] not in 允许]
        条目.extend(rows)
        坏.extend(bad)
    豁免, bad = _读词表(os.path.join(project, '_工具', '允许AI腔.txt'))
    坏.extend(bad)
    return 条目, [p for _, _, p in 豁免], 坏


def 指纹命中(raw, 条目, 豁免):
    """逐行扫描，返回 [(类别, 条目原文, 行号, 行内容, 命中文本)]。

    同一行里互相重叠的命中只保留最长的那条。「嘴角勾起一抹」和「一抹苦涩」
    指的是同一处毛病，报三遍只会把真正要改的地方淹掉。
    """
    命中 = []
    for no, line in enumerate((raw or '').split('\n'), 1):
        s = line.strip()
        if not s or s.startswith(('<!--', '#', '>', '|')):
            continue
        if any(p.search(s) for p in 豁免):
            continue
        本行 = []
        for 类别, 原文, pat in 条目:
            for m in pat.finditer(s):
                本行.append((m.start(), m.end(), 类别, 原文, m.group(0)))
        本行.sort(key=lambda x: (x[0] - x[1], x[0]))       # 长的在前
        留 = []
        for a, b, 类别, 原文, hit in 本行:
            if any(a >= c and b <= d for c, d, _, _, _ in 留):
                continue
            留.append((a, b, 类别, 原文, hit))
        for a, b, 类别, 原文, hit in sorted(留):
            命中.append((类别, 原文, no, s, hit))
    return 命中


# 4.1.1 条款腔：固定设定为了堵漏洞把规则写成条款，照搬进系统提示或对话就不像
# 日常语言。合成例子：“需完成装配并通过复核后予以奖励”。只看【】和“”，叙述里的
# “不真实”“实际上”不算。对话只查公文味最重的词：人物说“实际”“本人”很正常。
通知段 = re.compile(r'【[^】\n]{1,120}】')
对话段 = re.compile(r'“[^”\n]{1,300}”')
通知条款词 = re.compile(r'真实|实际|本人|结算|口径|对应|需完成|尚未|用于|视为|予以|方可|不予|适用|'
                   r'上述|前述|该笔|本单|计入')
对话条款词 = re.compile(r'结算|口径|视为|予以|方可|不予|上述|前述|该笔|本单')


def 条款腔(raw):
    """返回 [(行号, '系统提示'|'对话', 片段, [词...])]。只提醒，不拦提交。"""
    out = []
    for no, line in enumerate((raw or '').split('\n'), 1):
        s = line.strip()
        if not s or s.startswith(('<!--', '#', '>', '|')):
            continue
        for 类, 段式, 词式 in (('系统提示', 通知段, 通知条款词), ('对话', 对话段, 对话条款词)):
            for m in 段式.finditer(s):
                词 = sorted(set(词式.findall(m.group(0))), key=m.group(0).index)
                if 词:
                    out.append((no, 类, m.group(0), 词))
    return out


def 报告条款腔(行):
    if not 行:
        _出('  条款腔：没有命中。')
        return
    _出('  条款腔：命中 %d 处（系统提示或对话里出现设定、账本式的限定词）' % len(行))
    for no, 类, 段, 词 in 行[:12]:
        _出('      第 %-5d 行  %s「%s」    %s' % (no, 类, '、'.join(词),
                                            段 if len(段) <= 40 else 段[:38] + '…'))
    if len(行) > 12:
        _出('      …另有 %d 处' % (len(行) - 12))
    _出('    现实里会有人这么说吗？设定里的限定写给作者和检查看，正文用人物日常的说法。')
    _出('    公文、合同原文照录，或人物本来就这么说话时保留。')


# ══════════════ 基线 ══════════════

最小基线字数 = 2000


# §A 里除了用户的正样本，还可能有两种**不能算正样本**的东西：
#   占位符（模板里的「（待粘贴）」「在此粘贴」之类）
#   `### 临时样本` —— AI 按目标声音自拟、供用户确认或否掉的段落
# 它们都在 `## A.` 这一节内，`\n## ` 的切法切不掉三级标题。
# 把 AI 自拟的样本算成正样本，正是 R73 要防的那个回路：模型写样本 →
# 样本成标准 → 拿它衡量模型写的下一章，而每一步都显示「符合基线」。
占位标记 = ('在此粘贴', '待粘贴', '（示例', '请粘贴', 'TODO')


def 取正样本(project, text=None):
    if text is None:
        text = core.read_text(os.path.join(project, '00_设定层', '02_风格样本.md'), '') or ''
    if '## A.' not in text:
        return ''
    section = re.split(r'\n## ', text.split('## A.', 1)[1])[0]
    # 三级标题起就不再是用户正样本（临时样本、样本分析都挂在 §A 下面）
    section = re.split(r'(?m)^###\s', section)[0]
    blocks = [b for b in re.findall(r'```(?:text)?\n(.*?)```', section, re.S)
              if not any(mark in b for mark in 占位标记)]
    return '\n'.join(blocks).strip()


def 认可章节(project, text=None):
    """从 02_风格样本.md 读用户明确认可为文风样本的章号。

    已定稿只说明这一章的账目走完了流程，**不说明作者认可它的文风**。
    模型写的正文默认不进基线——否则第一章的模型腔会变成后面所有章的标准，
    形成一个作者察觉不到的自我强化回路。
    """
    if text is None:
        text = core.read_text(os.path.join(project, '00_设定层', '02_风格样本.md'), '') or ''
    m = re.search(r'(?m)^\s*[|>-]?\s*(?:认可为文风样本的章节|文风认可章节)\s*[|：:]\s*([^|\n]*)', text)
    if not m:
        return []
    return list(dict.fromkeys(re.findall(r'K\d{4}', m.group(1))))


def _定稿章节(project):
    """Only parse the ordered registry; counting chapters does not read prose."""
    outline = core.read_text(os.path.join(project, '00_设定层', '03_分章大纲.md'), '') or ''
    rows = []
    for line in outline.split('\n'):
        if not re.match(r'^\|\s*K\d{4}\s*\|', line):
            continue
        cells = [c.strip().replace('**', '') for c in line.strip().strip('|').split('|')]
        if len(cells) >= 2 and re.fullmatch(r'K\d{4}', cells[0]) and cells[1].isdigit() \
                and '已定稿' in cells[-1]:
            rows.append((cells[0], int(cells[1])))
    rows.sort(key=lambda r: r[1])
    return rows


def _读定稿正文(project, rows, 允许):
    out = []
    for kid, _ in rows:
        if 允许 is not None and kid not in 允许:
            continue
        body = core.read_text(os.path.join(project, '05_正文', '%s.md' % kid))
        if body:
            out.append((kid, body))
    return out


def 前两章正文(project, kid=None):
    """4.1.2：按展示顺序取本章之前最近两章已定稿正文，供情绪词重复提醒对照。"""
    rows = [r for r in _定稿章节(project) if r[0] != kid]
    序 = dict(_定稿章节(project))
    if kid in 序:
        rows = [r for r in rows if r[1] < 序[kid]]
    return [t for _, t in _读定稿正文(project, rows[-2:], None)]


def 已定稿正文(project, 仅认可=True):
    """按大纲展示章号取正文；默认只读取明确认可的章节。"""
    允许 = set(认可章节(project)) if 仅认可 else None
    return _读定稿正文(project, _定稿章节(project), 允许)


def _基线来源(project):
    """Fresh source bytes and digest, without distribution calculations or writes."""
    text = core.read_text(os.path.join(project, '00_设定层', '02_风格样本.md'), '') or ''
    样本 = 取正样本(project, text)
    名单 = 认可章节(project, text)
    rows = _定稿章节(project)
    允许 = set(名单)
    章 = _读定稿正文(project, rows, 允许)
    语料 = [('正样本', 样本)] if 样本.strip() else []
    语料.extend(章)
    合并 = '\n\n'.join(t for _, t in 语料)
    return {'样本': 样本, '章': 章, '合并': 合并,
            '字数': len(re.sub(r'\s', '', 取正文(合并))),
            '未认可登记数': sum(kid not in 允许 for kid, _ in rows),
            '摘要': core.canonical_digest({'正样本': 样本, '认可名单': 名单,
                                           '认可正文': [(kid, 取正文(body)) for kid, body in 章]})}


def 建基线(project):
    """返回 (基线字典 或 None, 说明行列表)。"""
    说明 = []
    来源 = _基线来源(project)
    样本, 章 = 来源['样本'], 来源['章']
    合并, 字数 = 来源['合并'], 来源['字数']
    说明.append('语料：正样本 %s ＋ **用户认可的**正文 %d 章（%s），合计 %s 字'
                % ('有' if 样本.strip() else '无', len(章),
                   '、'.join(k for k, _ in 章) or '无', format(字数, ',')))
    未认可 = 来源['未认可登记数']
    if 未认可 > 0:
        说明.append('另有 %d 章在大纲登记为定稿但**未被认可为文风样本**，不进基线。' % 未认可)
        说明.append('  已定稿只说明账目走完流程，不说明你认可它的文风。')
        说明.append('  要把某章纳入基线，在 02_风格样本.md 写一行：')
        说明.append('  | 认可为文风样本的章节 | K0003、K0005 |')
    if 字数 < 最小基线字数:
        说明.append('不足 %s 字 → **不出分布层基线**，本次只报指纹命中。'
                    % format(最小基线字数, ','))
        说明.append('  统计量在这个体量上不稳定，给一个数字比不给更糟。')
        说明.append('  补正样本，或再认可几章（认可名单在 02_风格样本.md）。')
        return None, 说明
    基线 = 度量(合并)
    基线['_语料字数'] = 字数
    基线['_章数'] = len(章)
    基线['_来源摘要'] = 来源['摘要']
    逐章 = [度量(t) for _, t in 章]
    if len(逐章) >= 3:
        基线['_逐章标准差'] = {k: round(_标准差([m[k] for m in 逐章]), 3) for k in 对比项}
        说明.append('已认可章 ≥3 → 偏离按**逐章标准差的倍数**报告，可靠度较高。')
    else:
        说明.append('已认可章 <3 → 偏离按**百分比**报告；认可的章攒够会自动换成标准差倍数。')
    return 基线, 说明


def 偏离(本章, 基线):
    """返回 [(指标, 本章值, 基线值, 偏离描述, 是否显著)]。"""
    out = []
    stds = 基线.get('_逐章标准差')
    for k in 对比项:
        a, b = 本章.get(k, 0.0), 基线.get(k, 0.0)
        if stds and stds.get(k):
            n = (a - b) / stds[k]
            out.append((k, a, b, '%+.1f 倍标准差' % n, abs(n) >= 2.0))
        elif b:
            pct = (a - b) / b * 100.0
            out.append((k, a, b, '%+.0f%%' % pct, abs(pct) >= 40.0))
        elif a:
            # 基线为零、本章非零，是最值得看的一种情况：这本书**从不这样写**。
            # v1 把它写成"不比较"，恰好把最强的信号扔掉了。
            out.append((k, a, b, '本书基线为零，本章 %s' % a, True))
        else:
            out.append((k, a, b, '两边都是零', False))
    return out


# ══════════════ 可疑搭配发现 ══════════════

def 可疑搭配(草稿, 基线语料, 已知, 专名, 上限=25):
    """拿草稿和本书语料做 n-gram 对比，找出"模型爱用、作者不爱用"的搭配。

    词表是过去发现的缓存，**这个函数才是跨模型通用的部分**：换一个模型、
    模型更新一版，指纹会变，但"它比作者更爱说某个搭配"这件事测法不变。
    """
    def grams(text):
        c = Counter()
        for line in 取正文(text).split('\n'):
            s = re.sub(r'[^一-鿿]', '\x00', line)
            for seg in s.split('\x00'):
                for n in (3, 4, 5, 6, 7):
                    for i in range(len(seg) - n + 1):
                        c[seg[i:i + n]] += 1
        return c
    a, b = grams(草稿), grams(基线语料)
    草字 = max(1, len(re.sub(r'\s', '', 取正文(草稿))))
    基字 = max(1, len(re.sub(r'\s', '', 取正文(基线语料))))
    行 = []
    for g, n in a.items():
        if n < 2:
            continue
        if any(p.search(g) for p in 已知):
            continue
        if any(name and name in g for name in 专名):
            continue
        草率 = n * 10000.0 / 草字
        基率 = b.get(g, 0) * 10000.0 / 基字
        if 基率 * 3 >= 草率:
            continue
        行.append((草率 - 基率, g, n, b.get(g, 0)))
    # 差值相同的先给长的：短片段总是被长搭配包含，先留短的会把真正的那条挤掉。
    行.sort(key=lambda r: (r[0], len(r[1])), reverse=True)
    保留 = []
    for 差, g, n, m in 行:
        if any(g in keep[1] for keep in 保留):
            continue
        保留.append((差, g, n, m))
    return 保留[:上限]


# ══════════════ 基线区块的读写 ══════════════

基线rel = '02_检查层/11_文风基线.md'
起标记 = '<!-- 文风基线：以下区块由 novel.py style --baseline 生成，不要手改 -->'
止标记 = '<!-- 文风基线区块结束 -->'


def 基线区块(基线, 说明):
    lines = [起标记]
    if 基线 is None:
        lines.append('状态：**未建立**（' + 说明[1].split('→')[0].strip() + '）')
        lines.append('生成正文时仍要遵守下面的通用约束；分布层暂时无法核对。')
    else:
        lines.append('状态：**已建立**　语料 %s 字，已定稿 %d 章'
                     % (format(基线['_语料字数'], ','), 基线['_章数']))
        if 基线.get('_来源摘要'):
            lines.append('语料来源摘要：' + 基线['_来源摘要'])
        lines.append('')
        lines.append('| 指标 | 本书基线 |')
        lines.append('|---|---|')
        for k in 对比项:
            lines.append('| %s | %s |' % (k, 基线[k]))
        感 = 基线['感官分布']
        lines.append('| 感官分布（视/听/触/嗅/味） | %s |'
                     % ' / '.join('%s' % 感[x] for x in ('视', '听', '触', '嗅', '味')))
        lines.append('')
        lines.append('这些数字来自**本书自己的正样本与用户明确认可的已定稿章节**，不是通用标准。')
        lines.append('已定稿只说明账目走完流程，不等于你认可它的文风——'
                     '认可章节在 `00_设定层/02_风格样本.md` 里显式列出。')
        lines.append('写作时不必凑数，但明显偏离时要能说出为什么。')
    lines.append(止标记)
    return '\n'.join(lines)


def 写入基线(project, 基线, 说明):
    path = os.path.join(project, 基线rel)
    text = core.read_text(path)
    if text is None:
        raise core.ProjectError('缺 %s，先从母版同步' % 基线rel)
    块 = 基线区块(基线, 说明)
    if 起标记 in text and 止标记 in text:
        head = text.split(起标记)[0]
        tail = text.split(止标记, 1)[1]
        new = head + 块 + tail
    else:
        new = text.rstrip() + '\n\n' + 块 + '\n'
    return {基线rel: new.encode('utf-8')}


def 基线提醒(project):
    """按实际认可语料提示；普通定稿数量与探索文件不构成重建依据。"""
    当前 = _基线来源(project)
    已存 = core.read_text(os.path.join(project, 基线rel), '') or ''
    if 当前['字数'] < 最小基线字数:
        return '语料不足', '正样本与明确认可章节不足 2,000 字，暂不建立分布基线；不为凑数自动认可正文。'
    if '状态：**已建立**' not in 已存:
        return '可建立', '已有足量认可语料，可先试算 style --baseline，再按授权写入。'
    记录 = re.search(r'语料来源摘要：([0-9a-f]{64})', 已存)
    if not 记录:
        return '来源待核', '旧基线没有语料来源摘要；需要使用时核对认可语料并重算，不因新增普通定稿而重建。'
    if 记录.group(1) != 当前['摘要']:
        return '需更新', '正样本、认可名单或认可正文已变化；重算 style --baseline 后再按授权写入。'
    return '已建立', ''


# ══════════════ 报告 ══════════════

def _出(s=''):
    print(s, flush=True)


def 报告命中(命中):
    if not 命中:
        _出('  指纹层：没有命中。')
        return
    分组 = {}
    for 类别, 原文, no, line, hit in 命中:
        分组.setdefault(类别, []).append((no, hit, line))
    _出('  指纹层：命中 %d 处' % len(命中))
    for 类别 in sorted(分组):
        _出('    【%s】%d 处' % (类别, len(分组[类别])))
        for no, hit, line in 分组[类别][:12]:
            段 = line if len(line) <= 46 else line[:44] + '…'
            _出('      第 %-5d 行  「%s」    %s' % (no, hit, 段))
        if len(分组[类别]) > 12:
            _出('      …另有 %d 处' % (len(分组[类别]) - 12))


def 报告偏离(rows):
    _出('  分布层：本章 ／ 本书基线 ／ 偏离')
    for k, a, b, desc, 显著 in rows:
        _出('    %s %-14s %-10s %-10s %s' % ('!' if 显著 else ' ', k, a, b, desc))
    显 = [r for r in rows if r[4]]
    if 显:
        _出('    标 ! 的 %d 项偏离明显。这不是错误，是"和这本书别的地方不一样"，' % len(显))
        _出('    需要你判断是这一章确实该这样，还是模型带跑了。')


def 改写提示词(kid, 命中, 偏离行, 基线, 条款=()):
    """把报告变成一段可以直接贴给模型的定点改写指令。"""
    out = ['```text',
           '下面是定位线索。先按本书声音判断是否影响阅读，只修改确认有问题的地方；有作用的命中可以保留。',
           '']
    if 基线:
        out.append('本书正样本的实际写法（不是通用标准，是这本书自己的）：')
        for k in ('句长均值', '句长变异系数', '短句占比', '比喻密度', '情绪直陈密度'):
            out.append('  %s = %s' % (k, 基线.get(k)))
        out.append('')
    if 命中:
        out.append('一、这些行命中了高频表达，但命中不等于错误。确认重复或不合人物后再修改，保留原意与信息。')
        out.append('    可以采用动作、内心判断、直接情绪或其他符合本书声音的表达，不统一替换成小动作：')
        按行 = {}
        for 类别, 原文, no, line, hit in 命中:
            按行.setdefault(no, [line, []])[1].append('%s／%s' % (hit, 类别))
        for no in sorted(按行)[:20]:
            line, hits = 按行[no]
            out.append('  第 %d 行  命中：%s' % (no, '、'.join(hits)))
            out.append('      %s' % line)
        if len(按行) > 20:
            out.append('  …另有 %d 行，先改这些' % (len(按行) - 20))
        out.append('')
    if 条款:
        out.append('一之二、这些系统提示或对话里有设定、账本式的限定词。改成人物日常会说的话，')
        out.append('    规则的意思不变；公文、合同原文照录时保留：')
        for no, 类, 段, 词 in list(条款)[:20]:
            out.append('  第 %d 行  %s  %s（%s）' % (no, 类, 段, '、'.join(词)))
        out.append('')
    显 = [r for r in 偏离行 if r[4]]
    if 显:
        out.append('二、下面这些统计量与本书基线差得多。**它们只是差异，不是错误，')
        out.append('    也不是要你去追平的数字。** 不要为了让数字好看而拆句、堆短句、')
        out.append('    加连接词或补比喻——那样改出来的文本一定更差。')
        out.append('    请对照原文判断：这一章是不是确实该这样写？说得出理由就保留。')
        for k, a, b, desc, _ in 显:
            out.append('  %s：本章 %s，本书基线 %s（%s）' % (k, a, b, desc))
        out.append('')
    out.append('三、改完逐条说明改了什么、为什么。没有把握的行保留原样并说明。')
    out.append('```')
    return '\n'.join(out)


# ══════════════ 命令入口 ══════════════

def main(argv=None):
    parser = argparse.ArgumentParser(prog='style', description='文风度量与去 AI 腔定位')
    parser.add_argument('kid', nargs='?', help='要检查的章节永久 ID')
    parser.add_argument('project', nargs='?', default='.')
    parser.add_argument('--baseline', action='store_true', help='重建本书文风基线')
    parser.add_argument('--apply', action='store_true', help='把基线写入 11_文风基线.md')
    parser.add_argument('--draft', help='直接检查一个草稿文件')
    parser.add_argument('--suspect', help='拿这个文件或目录和本书语料做词频对比，发现新的 AI 腔')
    parser.add_argument('--prompt', action='store_true', help='额外输出可直接使用的定点改写提示词')
    args = parser.parse_args(argv)
    # kid 与 project 都是可选位置参数：只给一个且不像永久 ID 时，那是项目路径。
    # 不容错的话，`style <项目> --baseline` 会把项目当章节 ID，project 退回
    # 当前目录——在母版目录里跑就会往母版写东西。
    if args.kid and not re.fullmatch(r'K\d{4}', args.kid) and args.project == '.':
        args.project, args.kid = args.kid, None

    project = core.resolve_project(args.project)
    条目, 豁免, 坏 = 载入词表(project)
    W = 74
    _出('=' * W)

    if args.baseline:
        _出('文风基线 · %s' % os.path.basename(project))
        _出('=' * W)
        基线, 说明 = 建基线(project)
        for line in 说明:
            _出('  ' + line)
        if not args.apply:
            _出('')
            _出('※ 这是试算。写入 %s 用：' % 基线rel)
            _出('  python3 novel.py style --baseline --apply')
            return 0
        import 事务
        changes = 写入基线(project, 基线, 说明)
        tx = 事务.apply_changes(project, changes, 'style baseline',
                              metadata={'baseline': bool(基线)})
        _出('')
        _出('✓ 基线已写入 %s，事务 %s' % (基线rel, tx['id']))
        _出('  它会作为 CONTROL 跟随正式读取包进入每一章。')
        return 0

    目标名, raw = None, None
    if args.draft or args.suspect:
        path = args.draft or args.suspect
        if os.path.isdir(path):
            # 单章的 n-gram 样本太少。跨平台排查的真实用法是"把我在某个平台
            # 写的那几章一起喂进去"，所以这里接受目录。
            files = sorted(os.path.join(path, n) for n in os.listdir(path)
                           if n.endswith('.md') and not n.startswith('.'))
            parts = [core.read_text(f) for f in files]
            parts = [x for x in parts if x]
            if not parts:
                _出('✗ %s 里没有可读的 .md' % path)
                return 2
            raw = '\n\n'.join(parts)
            目标名 = '%s（%d 份）' % (os.path.basename(path.rstrip('/')), len(parts))
        else:
            raw = core.read_text(path)
            if raw is None:
                _出('✗ 读不到 %s' % path)
                return 2
            目标名 = os.path.basename(path)
    elif args.kid:
        if not re.fullmatch(r'K\d{4}', args.kid):
            _出('✗ 永久 ID 形如 K0001。收到：%s' % args.kid)
            return 2
        for rel in ('_候选/%s/05_正文/%s.md' % (args.kid, args.kid),
                    '05_正文/%s.md' % args.kid):
            raw = core.read_text(os.path.join(project, rel))
            if raw:
                目标名 = rel
                break
        if raw is None:
            _出('✗ 找不到 %s 的正文（候选区与正式区都没有）' % args.kid)
            return 2
    else:
        _出('✗ 需要一个永久 ID，或 --draft／--suspect <文件>，或 --baseline')
        return 2

    if args.suspect:
        _出('可疑搭配发现 · %s' % 目标名)
        _出('=' * W)
        样本 = 取正样本(project)
        章 = [t for _, t in 已定稿正文(project)]
        语料 = '\n\n'.join([样本] + 章)
        if len(re.sub(r'\s', '', 取正文(语料))) < 最小基线字数:
            _出('  本书语料不足 %s 字，无法做对比。' % format(最小基线字数, ','))
            _出('  这个功能靠"模型爱用、你不爱用"的差值工作，语料太少差值没有意义。')
            return 1
        已知 = [p for _, _, p in 条目] + 豁免
        专名 = [l.strip() for l in (core.read_text(
            os.path.join(project, '_工具', '专名表.txt'), '') or '').split('\n')
            if l.strip() and not l.strip().startswith('#')]
        行 = 可疑搭配(raw, 语料, 已知, 专名)
        if not 行:
            _出('  没有发现明显高于本书语料的搭配。')
            return 0
        _出('  下面这些搭配在本次草稿里的密度明显高于你自己的语料。')
        _out_hdr = '  %-14s %6s %6s   %s'
        _出(_out_hdr % ('搭配', '草稿', '语料', '每万字差'))
        for 差, g, n, m in 行:
            _出('  %-14s %6d %6d   %+.1f' % (g, n, m, 差))
        _出('')
        _出('  挑出确实是套话的，加进 _工具/AI腔词表_本项目.txt。')
        _出('  ※ 高频不等于套话：人物口头禅、本书专有说法也会出现在这里，由你判断。')
        return 0

    _出('文风检查 · %s' % 目标名)
    _出('=' * W)
    for line in 坏:
        _出('  △ 词表里有条目不是合法正则，已跳过：%s' % line)

    try:
        import 文风档
        _档, _显式 = 文风档.当前档(project)
        _出('  文风档：%s%s' % ((文风档.档信息(project) or {}).get('name', _档),
                                '' if _显式 else '（未选择，按文学克制处理）'))
    except Exception:
        文风档 = None
    命中 = 指纹命中(raw, 条目, 豁免)
    报告命中(命中)
    条款 = 条款腔(raw)
    报告条款腔(条款)
    if 文风档 and 文风档.外放档(project):
        样本 = 取正样本(project)
        本章度量 = 文风档.表现度量(raw)
        样本度量 = 文风档.表现度量(样本) if 样本 else {}
        提醒 = 文风档.漂移提醒(本章度量, 样本度量) if 样本度量 else []
        _出('  表现力（每千字，对照正样本）：' + '；'.join(
            '%s %.1f／%.1f' % (k, 本章度量[k], 样本度量.get(k, 0))
            for k in ('情绪直写', '内心独白', '旁人反应')))
        for x in 提醒:
            _出('  △ ' + x)
        重复 = 文风档.重复提醒(raw, 前两章正文(project, args.kid))
        for x in 重复:
            _出('  △ 情绪词重复：' + x)
        if 提醒 or 重复:
            _出('    补情绪时换着说：动作、话语、具体后果都算直说，别补同一批计数词来消提醒。')
    _出('')

    基线, 说明 = 建基线(project)
    for line in 说明:
        _出('  ' + line)
    偏离行 = []
    if 基线:
        本章 = 度量(raw)
        偏离行 = 偏离(本章, 基线)
        _出('')
        报告偏离(偏离行)
    _出('')
    句 = 分句(取正文(raw))
    if 句:
        _出('  章末落点（只呈现，不判断）：%s' % (句[-1][:60]))
    _出('=' * W)
    _出('※ 本命令只度量，不打分、不拦提交。这些数字全都能刷，刷了文本更差。')
    _出('※ 人物声音、情绪写法是否合乎本书所选文风档——机器看不见，')
    _出('  留给 02_检查层/08 的第二遍，按包内文风档的「语言检查」核对。')
    if args.prompt and (命中 or 条款 or [r for r in 偏离行 if r[4]]):
        _出('')
        _出('— 定点改写提示词（可直接使用）—')
        _出(改写提示词(args.kid or 目标名, 命中, 偏离行, 基线, 条款))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
