#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5.0 人物声音：量每个反复出场的人说话的方式，找出谁跟谁听起来是同一个人。

这一层回答“这句话为什么只能是他说的”。只做测量和只读报告；
声音表 00_设定层/05_人物声音.md 的写入走 revise 事务。

启用判据只有一条：声音表存在且至少有一个人的四行已填写。
旧项目同步后会补入空模板，空模板不启用，旧项目的包与提交不受影响。

命令：
    python3 _工具/人物声音.py <项目目录>            全书各人的说话方式与两两相似
    python3 _工具/人物声音.py <项目目录> --by-arc   按弧看漂移，对单调下滑报警
"""
import argparse
import collections
import itertools
import json
import math
import pathlib
import re
import statistics
import sys

# 句末语气词：真人说话有，书面句子没有
TONE = '吧呢啊嘛哈呀哦嗯诶唉呗啦么'
# 称谓：爱不爱叫人
ADDR = '您叔姨嫂哥姐弟妹总董师傅老板'
# 迟疑与打断：口语的碎
HESIT = ('那个', '就是', '我跟你', '你听我', '怎么说', '反正', '其实')
SPEECH = '说道问答笑喊叫骂应嘟哝嘀咕补充打断插嘴开口反问'


def load(project):
    d = pathlib.Path(project).expanduser().resolve()
    body = d / '05_正文'
    if not body.is_dir():
        sys.exit(f'找不到正文目录：{body}')
    files = sorted(body.glob('K*.md'))
    if not files:
        sys.exit(f'{body} 里没有 K*.md')
    title = d.name
    pj = d / 'project.json'
    if pj.exists():
        try:
            title = json.loads(pj.read_text('utf-8')).get('title') or title
        except (ValueError, OSError):
            pass
    return title, files


def names_from_settings(project):
    """从固定设定里取登记在册的人名，再从正文补出高频未登记者。"""
    d = pathlib.Path(project).expanduser().resolve()
    f = d / '00_设定层/01_固定设定.md'
    reg = []
    if f.exists():
        s = f.read_text('utf-8')
        reg += re.findall(r'^### (?:人物：)?(\S+?)[，,]?\s*$', s, re.M)
        blk = re.search(r'### 次要人物(.*?)(?=^## |\Z)', s, re.S | re.M)
        if blk:
            for item in re.findall(r'^[-*] ([^：\n]+)：', blk.group(1), re.M):
                reg += re.split(r'[、,，]', item)
    out = []
    for n in reg:
        n = re.sub(r'（.*?）', '', n).strip()
        n = re.sub(r'^(女主|男主|首个相识者|主角)[，,]?', '', n).strip()
        if 2 <= len(n) <= 4 and re.fullmatch(r'[一-龥]+', n):
            out.append(n)
    return list(dict.fromkeys(out))


def discover(text, known):
    """正文里出现 >=8 次、像人名或称谓的，补进候选。"""
    c = collections.Counter()
    for m in re.finditer(r'[一-龥]{1,3}(?:经理|总监|老板|厂长|律师|主任|教授|队长|医生|护士|所长|站长)', text):
        c[m.group()] += 1
    for m in re.finditer(r'[一-龥]{2,3}', text):
        pass
    extra = [n for n, k in c.items() if k >= 8 and not any(n in r or r in n for r in known)]
    return extra


def attribute(files, names):
    """把台词归给说话人。优先「名字＋说话动词」紧邻引号，其次同段最近人名。"""
    said = collections.defaultdict(list)
    strong = collections.Counter()
    total = 0
    q_re = re.compile(r'[“"]([^”"\n]{2,})[”"]')
    for f in files:
        for para in f.read_text('utf-8').split('\n'):
            if '“' not in para and '"' not in para:
                continue
            quotes = list(q_re.finditer(para))
            if not quotes:
                continue
            bare = q_re.sub(lambda m: '\x00' * (m.end() - m.start()), para)
            for qm in quotes:
                total += 1
                who, hard = None, False
                # 引号前 12 字里：名字 + 说话动词
                before = bare[max(0, qm.start() - 14):qm.start()]
                after = bare[qm.end():qm.end() + 14]
                for n in names:
                    if re.search(re.escape(n) + r'[^\x00]{0,4}[' + SPEECH + r']', before) or \
                       re.search(re.escape(n) + r'[^\x00]{0,4}[' + SPEECH + r']', after):
                        who, hard = n, True
                        break
                if who is None:
                    hits = [(bare.rfind(n, 0, qm.start()), n) for n in names]
                    hits = [h for h in hits if h[0] >= 0]
                    if hits:
                        who = max(hits)[1]
                if who:
                    said[who].append(qm.group(1))
                    if hard:
                        strong[who] += 1
    return said, strong, total


def profile(lines):
    j = ''.join(lines)
    n = len(lines)
    L = [len(s) for s in lines]
    return {
        '台词': n,
        '均长': statistics.mean(L),
        '短句': sum(1 for x in L if x <= 6) / n,
        '长句': sum(1 for x in L if x >= 25) / n,
        '问句': sum(1 for s in lines if '？' in s or '?' in s) / n,
        '语气': sum(j.count(c) for c in TONE) / n,
        '称谓': sum(j.count(c) for c in ADDR) / n,
        '迟疑': sum(j.count(w) for w in HESIT) / n,
    }


AXES = ['均长', '短句', '长句', '问句', '语气', '称谓', '迟疑']


def arcs_of(project):
    """从弧卡里读章节范围：| 范围 | K0007—K0012（6 章） |。读不到就按 6 章一段。"""
    d = pathlib.Path(project).expanduser().resolve()
    out = []
    for f in sorted((d / '00_设定层').glob('弧卡_*.md')):
        m = re.search(r'范围\s*\|\s*K0*(\d+)\s*[—\-–~]\s*K0*(\d+)', f.read_text('utf-8'))
        if m:
            out.append((f.stem.replace('弧卡_', ''), int(m.group(1)), int(m.group(2))))
    return out


def by_arc(files, names, spans, floor=6):
    """每弧一份 profile，报告漂移。"""
    if not spans:
        spans = [(f'{i+1}段', i * 6 + 1, i * 6 + 6) for i in range((len(files) + 5) // 6)]
    buckets = collections.defaultdict(list)
    for f in files:
        try:
            k = int(re.sub(r'\D', '', f.stem))
        except ValueError:
            continue
        for label, a, b in spans:
            if a <= k <= b:
                buckets[label].append(f)
                break
    per = {}
    for label in [s[0] for s in spans]:
        if label not in buckets:
            continue
        said, _strong, _t = attribute(buckets[label], names)
        for who, lines in said.items():
            if len(lines) >= floor:
                per.setdefault(who, {})[label] = profile(lines)
    order = [s[0] for s in spans]
    print('\n【按弧看漂移】每弧至少 %d 句才计入；样本少的行只看方向，不当结论' % floor)
    print(f'{"人物":<7}{"弧":<6}{"台词":>4}{"均长":>7}{"短句":>7}{"问句":>7}{"语气":>6}{"称谓":>6}')
    print('-' * 60)
    for who, m in sorted(per.items(), key=lambda x: -sum(v['台词'] for v in x[1].values())):
        if len(m) < 2:
            continue
        seen = [a for a in order if a in m]
        for a in seen:
            v = m[a]
            print(f'{who if a == seen[0] else "":<7}{a:<6}{v["台词"]:>4}{v["均长"]:>7.1f}'
                  f'{v["短句"]:>7.0%}{v["问句"]:>7.0%}{v["语气"]:>6.2f}{v["称谓"]:>6.2f}')
        tone = [m[a]['语气'] for a in seen]
        leng = [m[a]['均长'] for a in seen]
        notes = []
        if len(tone) >= 3 and all(x >= y for x, y in zip(tone, tone[1:])) and tone[0] - tone[-1] >= 0.06:
            notes.append(f'语气词单调下滑 {tone[0]:.2f}→{tone[-1]:.2f}，正在变成书面语')
        if abs(leng[-1] - leng[0]) >= 6:
            notes.append(f'均长 {leng[0]:.1f}→{leng[-1]:.1f}，句子长度换了一个人')
        for n in notes:
            print(f'{"":<7}↳ {n}')
        print()
    print('  变化本身不是错：人物会成长。但变化要么写在弧卡里，要么就是漂移——')
    print('  分辨办法是给每人定一个「不许变的量」当锚，变了其他项仍然是他。\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--min', type=int, default=15, help='至少多少句台词才纳入')
    ap.add_argument('--pairs', type=int, default=6, help='列出最像的几对')
    ap.add_argument('--by-arc', action='store_true',
                    help='按弧切开，看每个人的声音有没有漂移')
    a = ap.parse_args()

    title, files = load(a.project)
    text = '\n'.join(f.read_text('utf-8') for f in files)
    known = names_from_settings(a.project)
    names = sorted(set(known) | set(discover(text, known)), key=len, reverse=True)
    said, strong, total = attribute(files, names)

    if a.by_arc:
        by_arc(files, names, arcs_of(a.project))
    rows = {k: profile(v) for k, v in said.items() if len(v) >= a.min}
    if len(rows) < 2:
        sys.exit(f'{title}：够 {a.min} 句台词的角色不足 2 个，无法比较。')

    got = sum(len(v) for v in said.values())
    cover = got / total if total else 0
    print(f'\n{"="*72}\n声音体检　{title}　{len(files)} 章\n{"="*72}')
    print(f'全书对白 {total} 句，归得出说话人 {got} 句（{cover:.0%}）')
    if cover < 0.5:
        print('  ← 覆盖率过低。这本书的对白多为不带说话人标签的独立段落，'
              '脚本判不出谁在说，\n    下面的数只代表能判定的那部分，不代表全书。')
    print()
    print(f'{"人物":<8}{"台词":>5}{"确信":>6}{"均长":>7}{"短句":>7}{"长句":>7}{"问句":>7}{"语气":>7}{"称谓":>7}{"迟疑":>7}')
    print('-' * 72)
    for k, p in sorted(rows.items(), key=lambda x: -x[1]['均长']):
        conf = strong[k] / p['台词']
        print(f'{k:<8}{p["台词"]:>5}{conf:>6.0%}{p["均长"]:>7.1f}'
              f'{p["短句"]:>7.0%}{p["长句"]:>7.0%}{p["问句"]:>7.0%}'
              f'{p["语气"]:>7.2f}{p["称谓"]:>7.2f}{p["迟疑"]:>7.2f}')

    # 全书级信号
    print('\n【全书信号】')
    thin = len(rows) < 4
    tone = [p['语气'] for p in rows.values()]
    hes = [p['迟疑'] for p in rows.values()]
    print(f'  语气词密度  中位 {statistics.median(tone):.2f} 句/次，最高 {max(tone):.2f}'
          f'{"　← 偏低：人人都在说完整书面句" if statistics.median(tone) < 0.15 else ""}')
    print(f'  迟疑与碎句  中位 {statistics.median(hes):.2f} 句/次'
          f'{"　← 偏低：没有人打断自己或说半句改口" if statistics.median(hes) < 0.08 else ""}')
    if thin:
        print(f'  说够 {a.min} 句的角色只有 {len(rows)} 个'
              '　← 本身就是信号：这本书几乎只有主角在说话')
    else:
        for ax in AXES:
            v = [p[ax] for p in rows.values()]
            m = statistics.mean(v)
            cv = statistics.pstdev(v) / m if m else 0
            if cv < 0.25:
                print(f'  「{ax}」变异系数仅 {cv:.2f}　← 这一项上所有人几乎一样')

    # 两两相似：按各轴标准分算欧氏距离。人数太少时标准分无意义，跳过。
    if thin:
        print('\n【两两相似】角色不足 4 个，标准分没有意义，跳过。'
              f'　可降低门槛重跑：--min {max(5, a.min // 2)}')
        print('\n说明：说话人用「名字＋说话动词」紧邻引号判定，判不出的退回同段最近人名，'
              '所以「确信」一列低于 50% 的行要当参考值看。\n这套数只量说话方式，不判断人物写得好不好。\n')
        return
    z = {}
    for ax in AXES:
        v = [p[ax] for p in rows.values()]
        m, sd = statistics.mean(v), statistics.pstdev(v) or 1
        for k in rows:
            z.setdefault(k, {})[ax] = (rows[k][ax] - m) / sd
    dist = []
    for x, y in itertools.combinations(rows, 2):
        d = math.sqrt(sum((z[x][ax] - z[y][ax]) ** 2 for ax in AXES))
        dist.append((d, x, y))
    dist.sort()
    print(f'\n【听起来最像的 {a.pairs} 对】（距离越小越像；< 1.0 基本分不出）')
    for d, x, y in dist[:a.pairs]:
        flag = '　← 分不出' if d < 1.0 else ('　← 偏近' if d < 1.5 else '')
        print(f'  {d:>5.2f}  {x} ／ {y}{flag}')
    print(f'\n【最不像的 3 对】')
    for d, x, y in dist[-3:][::-1]:
        print(f'  {d:>5.2f}  {x} ／ {y}')
    print('\n说明：说话人用「名字＋说话动词」紧邻引号判定，判不出的退回同段最近人名，'
          '所以「确信」一列低于 50% 的行要当参考值看。\n这套数只量说话方式，不判断人物写得好不好。\n')


if __name__ == '__main__':
    main()


# ── 声音表的解析与启用判据（供读取包、体检调用）────────────────

VOICE_REL = "00_设定层/05_人物声音.md"
_占位 = ("____", "（填写）", "（填这里）", "待定", "TODO", "TBD")
_四行 = ("句子倾向", "语言习惯", "绝不会说", "变化线与锚")


def _有料(v):
    v = (v or "").strip()
    if not v:
        return False
    return not any(t in v for t in _占位)


def 声音表解析(text):
    """返回 [(人名, {行名: 内容}), ...]；只取「### 人物：」小节。"""
    if not text:
        return []
    out = []
    for m in re.finditer(r'^### 人物：(.*?)\s*$(.*?)(?=^### |^## |\Z)',
                         text, re.S | re.M):
        name = m.group(1).strip()
        rows = {}
        for lm in re.finditer(r'^- \*\*(.+?)\*\*：(.*)$', m.group(2), re.M):
            rows[lm.group(1).strip()] = lm.group(2).strip()
        out.append((name, rows))
    return out


def 声音表检查(text):
    """返回缺项列表；空列表表示至少有一个人的四行都已填写（即启用）。"""
    if text is None:
        return ["%s 不存在" % VOICE_REL]
    people = 声音表解析(text)
    if not people:
        return ["声音表里没有「### 人物：」小节"]
    ok = [n for n, rows in people
          if _有料(n) and all(_有料(rows.get(k)) for k in _四行)]
    if not ok:
        return ["声音表存在但没有任何一个人的四行填全（空模板不启用）"]
    return []


def 声音表片段(text, limit=None):
    """给读取包用：只带填全的人，省掉空模板和说明文字。"""
    people = [(n, rows) for n, rows in 声音表解析(text)
              if _有料(n) and all(_有料(rows.get(k)) for k in _四行)]
    if not people:
        return None
    if limit:
        people = people[:limit]
    buf = []
    for n, rows in people:
        buf.append("### 人物：%s" % n)
        for k in _四行:
            buf.append("- **%s**：%s" % (k, rows[k]))
        buf.append("")
    tail = re.search(r'^## 全书底噪(.*?)(?=^## |\Z)', text, re.S | re.M)
    if tail:
        buf.append("## 全书底噪" + tail.group(1).rstrip())
    return "\n".join(buf).strip()
