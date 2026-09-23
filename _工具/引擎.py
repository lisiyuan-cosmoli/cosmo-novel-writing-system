#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读者引擎卡、弧卡、悬念账与批次范围。

这一层回答“读者为什么点下一章”。它只做解析和只读报告；
引擎卡、弧卡的写入走 revise 事务，悬念账随章节或批次提交写入。

启用判据只有一条：00_设定层/04_读者引擎.md 存在且核心栏已经填写。
旧项目同步后会补入空模板，空模板不启用，旧项目的提交不受影响；
新书在开书阶段由 D11 要求填好，所以从第一章起就启用。
6.0 新卡显式选择通用或升级对抗；没有模式栏的旧卡沿用升级对抗校验，
不会因升级自动改写本书模式。模式随原 D11 或 revise 摘要批准。
启用后，章末钩子的提交检查只作用于作者已批准弧卡范围内的章节；
弧卡之外的章节由 status、package 与体检提醒先建弧卡，不在提交时阻断。

命令：
    python3 novel.py engine [--prepare]          引擎层状态；--prepare 把引擎卡与悬念账放进 REVISE 候选
    python3 novel.py arc [--new A02 K0019-K0027] 列出弧卡；--new 从模板建一张弧卡到 REVISE 候选
    python3 novel.py hooks K0019-K0021          末句检查材料与悬念账警报（只读）
"""
from __future__ import print_function

import io
import json
import os
import re
import sys

ENGINE_REL = "00_设定层/04_读者引擎.md"
LEDGER_REL = "01_运行层/05f_悬念账.md"
ARC_DIR = "00_设定层"
ARC_TEMPLATE_REL = "01_运行层/07b_弧卡_模板.md"
ARC_NAME = re.compile(r"^弧卡_(A\d{2})\.md$")
OUTLINE_REL = "00_设定层/03_分章大纲.md"

HOOK_TYPES = ("新信息", "危险逼近", "关系变化", "选择当口", "身份揭露", "兑现在即", "弧末收束")
BATCH_DEFAULT = 3
BATCH_HARD = 5
STALE_AFTER = 8
TAIL_CHARS = 300

占位词 = ("（填写）", "（填这里）", "待定", "TODO", "TBD")
创作模式值 = ("通用", "升级对抗")


# ══════════════════ 通用读取 ══════════════════

def 读(P, rel):
    try:
        with io.open(os.path.join(P, rel), encoding="utf-8") as handle:
            return handle.read().replace("\r\n", "\n")
    except (IOError, OSError, UnicodeDecodeError):
        return None


def _清(v):
    return (v or "").replace("**", "").replace("`", "").strip()


def _有料(v):
    v = _清(v)
    if not v or v.startswith("例："):
        return False
    return not any(w in v for w in 占位词)


def _行(text):
    """表格数据行 → 单元格列表；跳过分隔行。"""
    out = []
    for line in (text or "").split("\n"):
        s = line.strip()
        if not s.startswith("|") or not s.endswith("|"):
            continue
        cells = [_清(c) for c in s.strip("|").split("|")]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        out.append(cells)
    return out


def _节(text, heading):
    """取 `## 标题` 开头的一整节（到下一个二级标题为止）。按结构取，不认小标题名。"""
    if not text:
        return ""
    m = re.search(r"(?m)^## [^\n]*%s[^\n]*$" % re.escape(heading), text)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"(?m)^## ", rest)
    return rest[:n.start()] if n else rest


def 大纲序(P, 读取=None):
    """永久 ID → 展示章号，只认 `## 章节表` 一节里的章节行。"""
    text = (读取 or (lambda rel: 读(P, rel)))(OUTLINE_REL) or ""
    body = _节(text, "章节表") or text
    out = {}
    for line in body.split("\n"):
        m = re.match(r"^\|\s*(K\d{4})\s*\|\s*(\d{1,4})\s*\|", line)
        if m:
            out.setdefault(m.group(1), int(m.group(2)))
    return out


# ══════════════════ 读者引擎卡 ══════════════════

def 引擎模式(text):
    """返回模式名；无模式栏的旧卡沿用升级对抗，未知或重复声明返回空串。"""
    # 先识别显式字段，再校验表格形状。_行会略过缺尾竖线的行，直接依赖它
    # 会把拼坏的模式声明误当作旧卡缺省，甚至漏掉第二个冲突声明。
    declarations = [line.strip() for line in (text or "").splitlines()
                    if re.match(r"^\|?\s*创作模式\s*(?:\||[:：]|$)", _清(line))]
    if not declarations:
        return "升级对抗"
    if len(declarations) != 1:
        return ""
    rows = [c for c in _行(declarations[0]) if c and c[0] == "创作模式"]
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] not in 创作模式值:
        return ""
    return rows[0][1]


def 创作模式(P, 读取=None):
    """与启用使用同一读取器；正式查询不会擅自采用未批准候选。"""
    return 引擎模式((读取 or (lambda rel: 读(P, rel)))(ENGINE_REL))


def 引擎卡检查(text):
    """返回缺项列表；空列表表示核心栏已填写。模板里的「例：」提示视为未填。"""
    if text is None:
        return ["%s 不存在" % ENGINE_REL]
    缺 = []
    模式 = 引擎模式(text)
    if not 模式:
        缺.append("创作模式须唯一填写为通用或升级对抗")
    承诺 = _节(text, "读者承诺")
    承诺行 = [l.strip() for l in 承诺.split("\n") if l.strip() and not l.strip().startswith(">")]
    if not any(_有料(l.replace("________", "")) and "________" not in l for l in 承诺行):
        缺.append("一、读者承诺未填写")
    if 模式 == "通用":
        期待 = {c[0]: c[1] for c in _行(_节(text, "阅读期待")) if len(c) >= 2}
        if not _有料(期待.get("主要期待")):
            缺.append("二、阅读期待：主要期待未填写")
        阶段 = [c for c in _行(_节(text, "阶段发展")) if c and c[0] != "阶段"]
        if not any(len(c) >= 2 and _有料(c[0]) and _有料(c[1]) for c in 阶段):
            缺.append("三、阶段发展至少一项具体内容")
        return 缺
    if not 模式:
        return 缺
    单元 = {c[0]: c[1] for c in _行(_节(text, "核心爽感单元")) if len(c) >= 2}
    for 标 in ("触发", "兑现", "放大"):
        if not _有料(单元.get(标)):
            缺.append("二、核心爽感单元：%s 未填写" % 标)
    阶梯 = [c for c in _行(_节(text, "升级阶梯")) if c and c[0] not in ("级",)]
    if sum(1 for c in 阶梯 if len(c) >= 3 and sum(1 for x in c[2:] if _有料(x)) >= 2) < 2:
        缺.append("三、升级阶梯至少两级写出具体内容")
    对手 = [c for c in _行(_节(text, "对手")) if c and c[0] not in ("对手",)]
    if not any(_有料(c[0]) and len(c) > 1 and _有料(c[1]) for c in 对手):
        缺.append("四、对手名单至少一行")
    return 缺


def 启用(P, 读取=None):
    text = (读取 or (lambda rel: 读(P, rel)))(ENGINE_REL)
    return text is not None and not 引擎卡检查(text)


# ══════════════════ 弧卡 ══════════════════

def 弧卡列表(P, 读取=None, 额外=()):
    """返回 [{id, rel, start, end, text}]。额外：候选区里尚未正式的弧卡 (rel, text)。"""
    out = {}
    folder = os.path.join(P, ARC_DIR)
    names = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        pass
    items = []
    for name in names:
        m = ARC_NAME.match(name)
        if m:
            rel = "%s/%s" % (ARC_DIR, name)
            items.append((rel, (读取 or (lambda r: 读(P, r)))(rel)))
    items.extend(额外)
    for rel, text in items:
        m = ARC_NAME.match(os.path.basename(rel))
        if not m or text is None:
            continue
        范围 = ""
        for c in _行(text):
            if len(c) >= 2 and c[0] == "范围":
                范围 = c[1]
                break
        ids = re.findall(r"K\d{4}", 范围)
        out[m.group(1)] = {"id": m.group(1), "rel": rel, "text": text,
                           "start": ids[0] if ids else None,
                           "end": ids[1] if len(ids) > 1 else (ids[0] if ids else None)}
    return [out[k] for k in sorted(out)]


def 所属弧(P, kid, 序=None, 弧=None):
    序 = 序 if 序 is not None else 大纲序(P)
    n = 序.get(kid)
    if n is None:
        return None
    for arc in (弧 if 弧 is not None else 弧卡列表(P)):
        a, b = 序.get(arc["start"]), 序.get(arc["end"])
        if a is not None and b is not None and a <= n <= b:
            return arc
    return None


# ══════════════════ 悬念账 ══════════════════

def 悬念账(text):
    """返回 {'active': [row], 'hooks': {kid: {...}}, 'order': [kid]}。"""
    活动 = []
    for c in _行(_节(text, "活动悬念")):
        if c and re.fullmatch(r"Q\d{2,}", c[0]):
            活动.append({"id": c[0], "question": c[1] if len(c) > 1 else "",
                         "opened": c[3] if len(c) > 3 else "",
                         "last": c[4] if len(c) > 4 else "",
                         "state": c[-1]})
    钩 = {}
    顺序 = []
    for c in _行(_节(text, "章末钩子记录")):
        if c and re.fullmatch(r"K\d{4}", c[0]):
            钩[c[0]] = {"hook": c[1] if len(c) > 1 else "",
                        "type": c[2] if len(c) > 2 else "",
                        "paid": c[3] if len(c) > 3 else "",
                        "opened": c[4] if len(c) > 4 else ""}
            顺序.append(c[0])
    return {"active": 活动, "hooks": 钩, "order": 顺序}


def 活动数(账):
    return sum(1 for q in 账["active"] if q["state"].startswith("活动"))


def 钩子类型(值):
    """类型格可写「弧末收束（理由：…）」。返回 (类型, 是否带理由)。"""
    v = _清(值)
    带理由 = "理由" in v
    v = re.split(r"[（(]", v, 1)[0].strip()
    return v, 带理由


def 钩子问题(P, kid, 读取=None, 序=None):
    """章节提交闸门用：引擎层启用且本章在弧卡范围内时，本章必须在悬念账登记一条事实型章末钩子。"""
    读取 = 读取 or (lambda rel: 读(P, rel))
    text = 读取(LEDGER_REL)
    if text is None:
        return ["引擎层已启用，但 %s 取不到" % LEDGER_REL]
    账 = 悬念账(text)
    row = 账["hooks"].get(kid)
    if row is None:
        return ["悬念账「章末钩子记录」没有 %s 这一行" % kid]
    问题 = []
    if not _有料(row["hook"]):
        问题.append("%s 的章末钩子为空" % kid)
    类型, 带理由 = 钩子类型(row["type"])
    if 类型 not in HOOK_TYPES:
        问题.append("%s 的钩子类型「%s」不在 %s 之内" % (kid, 类型 or "空", "／".join(HOOK_TYPES)))
    elif 类型 == "弧末收束":
        序 = 序 if 序 is not None else 大纲序(P, 读取)
        arc = 所属弧(P, kid, 序)
        if not (arc and arc["end"] == kid) and not 带理由:
            问题.append("%s 不是所属弧的最后一章，却用了弧末收束；"
                        "改用事实型钩子，或在类型格写明（理由：…）" % kid)
    return 问题


# ══════════════════ 批次范围 ══════════════════

def 批上限(P):
    try:
        with io.open(os.path.join(P, "project.json"), encoding="utf-8") as handle:
            value = json.load(handle).get("batch_max", BATCH_DEFAULT)
    except (IOError, OSError, ValueError):
        value = BATCH_DEFAULT
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= BATCH_HARD:
        value = BATCH_DEFAULT
    return value


def 解析批次(P, 值, 序=None, 上限=None):
    """'K0019' → ([K0019], None)；'K0019-K0021' → 按展示章号取连续章节。"""
    m = re.fullmatch(r"(K\d{4})(?:-(K\d{4}))?", 值 or "")
    if not m:
        return None, "永久 ID 或批次必须写成 K0019 或 K0019-K0021，当前是「%s」" % 值
    a, b = m.group(1), m.group(2) or m.group(1)
    if a == b:
        return [a], None
    序 = 序 if 序 is not None else 大纲序(P)
    if a not in 序 or b not in 序:
        return None, "批次起止章必须都在分章大纲里（%s、%s）" % (a, b)
    lo, hi = 序[a], 序[b]
    if hi < lo:
        return None, "批次结束章不能早于起始章"
    kids = [k for k, n in sorted(序.items(), key=lambda x: x[1]) if lo <= n <= hi]
    上限 = 上限 or 批上限(P)
    if len(kids) > 上限:
        return None, ("一批最多 %d 章（project.json 的 batch_max，硬上限 %d），当前 %d 章"
                      % (上限, BATCH_HARD, len(kids)))
    return kids, None


# ══════════════════ 只读报告 ══════════════════

def _正文(P, kid, 批名=None):
    for rel in (("_候选/%s/05_正文/%s.md" % (批名, kid)) if 批名 else None,
                "_候选/%s/05_正文/%s.md" % (kid, kid), "05_正文/%s.md" % kid):
        if rel:
            text = 读(P, rel)
            if text is not None:
                return rel, text
    return None, None


def _净尾(text, n=TAIL_CHARS):
    body = text.split("\n", 1)[1] if text.startswith("<!--") else text
    body = re.sub(r"(?m)^#.*$", "", body).strip()
    return body[-n:]


def 报告_engine(P):
    text = 读(P, ENGINE_REL)
    print("=" * 72)
    print("读者引擎层 · %s" % os.path.basename(os.path.abspath(P)))
    print("=" * 72)
    if text is None:
        print("  引擎卡：未建立（%s 不存在）。旧项目运行 sync 会补入空模板；" % ENGINE_REL)
        print("          运行 novel.py engine --prepare 把它放进修订候选。")
    else:
        缺 = 引擎卡检查(text)
        print("  引擎卡：%s" % ("已填写，引擎层启用" if not 缺 else "未完成，引擎层未启用"))
        print("  创作模式：%s" % (引擎模式(text) or "声明无效"))
        for x in 缺:
            print("    · " + x)
    序 = 大纲序(P)
    弧 = 弧卡列表(P)
    print("  弧卡：%s" % ("、".join("%s（%s—%s）" % (a["id"], a["start"], a["end"]) for a in 弧) or "无"))
    账文 = 读(P, LEDGER_REL)
    if 账文 is None:
        print("  悬念账：未建立")
    else:
        账 = 悬念账(账文)
        建议 = "（建议 3—5）" if 引擎模式(text) == "升级对抗" else "（数量按本书需要）"
        print("  悬念账：活动 %d 个%s，章末钩子已登记 %d 章" % (活动数(账), 建议, len(账["hooks"])))
    定稿 = [k for k in sorted(序, key=lambda k: 序[k])
            if os.path.isfile(os.path.join(P, "05_正文", k + ".md"))]
    if 定稿 and 弧:
        末 = 定稿[-1]
        arc = 所属弧(P, 末, 序, 弧)
        print("  最新正文 %s：%s" % (末, ("属于弧卡 " + arc["id"]) if arc else "不在任何弧卡范围内"))
    print("※ 本命令只读。引擎卡与弧卡的修改走 revise 事务，由作者批准。")
    return 0


def _放进修订(P, files):
    """把 (rel, bytes) 放进 _候选/REVISE；已存在的候选文件一律不覆盖。"""
    root = os.path.join(P, "_候选", "REVISE")
    写了 = []
    for rel, data in files:
        target = os.path.join(root, rel)
        if os.path.exists(target):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)
        写了.append(rel)
    return 写了


def _源(P, rel, template_rel=None):
    path = os.path.join(P, rel)
    if os.path.isfile(path):
        return open(path, "rb").read()
    if template_rel and os.path.isfile(os.path.join(P, template_rel)):
        return open(os.path.join(P, template_rel), "rb").read()
    return None


def prepare_engine(P):
    files = []
    for rel in (ENGINE_REL, LEDGER_REL, OUTLINE_REL):
        data = _源(P, rel)
        if data is None:
            print("✗ %s 不存在。先运行 novel.py sync 补入 4.0 模板。" % rel)
            return 1
        files.append((rel, data))
    写了 = _放进修订(P, files)
    print("✓ 修订候选已就绪：%s" % ("、".join(写了) if 写了 else "三份文件都已在 _候选/REVISE，未覆盖"))
    print("  编辑 _候选/REVISE 中的引擎卡与悬念账，再运行 novel.py revise --review 与 novel.py revise。")
    return 0


def new_arc(P, arc_id, 范围):
    if not re.fullmatch(r"A\d{2}", arc_id or ""):
        print("✗ 弧卡编号写成 A01、A02……")
        return 2
    kids, err = 解析批次(P, 范围, 上限=99)
    if err:
        print("✗ " + err)
        return 2
    rel = "%s/弧卡_%s.md" % (ARC_DIR, arc_id)
    if os.path.exists(os.path.join(P, rel)) or os.path.exists(os.path.join(P, "_候选", "REVISE", rel)):
        print("✗ %s 已存在，不覆盖" % rel)
        return 1
    template = _源(P, ARC_TEMPLATE_REL)
    if template is None:
        print("✗ 缺弧卡模板 %s，先运行 novel.py sync" % ARC_TEMPLATE_REL)
        return 1
    text = template.decode("utf-8").replace("弧卡 A01", "弧卡 %s" % arc_id)
    引擎文 = 读(P, "_候选/REVISE/" + ENGINE_REL)
    if 引擎文 is None:
        引擎文 = 读(P, ENGINE_REL)
    模式 = 引擎模式(引擎文)
    if not 模式:
        print("✗ 引擎卡创作模式声明无效，先核对；未创建弧卡")
        return 1
    text = re.sub(r"(?m)^\| 创作模式 \|[^\n]*\|$", "| 创作模式 | %s |" % 模式, text, count=1)
    text = re.sub(r"(?m)^\| 范围 \|[^\n]*\|$", "| 范围 | %s—%s（%d 章） |" % (kids[0], kids[-1], len(kids)), text, 1)
    files = [(rel, text.encode("utf-8"))]
    for extra in (OUTLINE_REL, LEDGER_REL):
        data = _源(P, extra)
        if data is not None:
            files.append((extra, data))
    写了 = _放进修订(P, files)
    print("✓ 已放进 _候选/REVISE：%s" % "、".join(写了))
    print("  填好弧卡，在原大纲登记规划行，再 revise --review、revise 试算，交作者批准。")
    return 0


def 报告_hooks(P, 值):
    序 = 大纲序(P)
    kids, err = 解析批次(P, 值, 序, 上限=BATCH_HARD)
    if err:
        print("✗ " + err)
        return 2
    批名 = 值 if len(kids) > 1 else None
    账文 = 读(P, "_候选/%s/%s" % (值, LEDGER_REL)) or 读(P, LEDGER_REL)
    账 = 悬念账(账文) if 账文 else {"active": [], "hooks": {}, "order": []}
    print("=" * 72)
    print("末句检查 · %s" % 值)
    print("=" * 72)
    模式 = 创作模式(P)
    if 模式 == "通用":
        print("把下面几段连着读，核对阅读期待、体验或认识怎样延续；自然收束可以成立，不为制造悬念追加事件。")
    else:
        print("把下面几段连着读，写一句“读者为什么会点下一章”。写不出来就是问题。")
    类型序 = []
    for kid in kids:
        rel, text = _正文(P, kid, 批名)
        print()
        print("── %s（%s）" % (kid, rel or "没有正文"))
        if text:
            print(_净尾(text))
        row = 账["hooks"].get(kid)
        if row:
            类型, _ = 钩子类型(row["type"])
            类型序.append(类型)
            print("   悬念账钩子：%s ｜ %s" % (row["hook"] or "（空）", row["type"] or "（空）"))
        else:
            类型序.append(None)
            print("   悬念账钩子：未登记")
    print()
    警 = []
    for i in range(1, len(类型序)):
        if 类型序[i] and 类型序[i] == 类型序[i - 1]:
            警.append("%s 与上一章钩子同为「%s」" % (kids[i], 类型序[i]))
    n = 活动数(账)
    if 模式 == "升级对抗" and 账文 and not 3 <= n <= 5:
        警.append("活动悬念 %d 个，建议常驻 3—5 个" % n)
    末 = 序.get(kids[-1], 0)
    for q in 账["active"]:
        ids = re.findall(r"K\d{4}", q["last"] or q["opened"])
        if q["state"].startswith("活动") and ids and ids[-1] in 序 and 末 - 序[ids[-1]] > STALE_AFTER:
            警.append("%s 已超过 %d 章没有推进" % (q["id"], STALE_AFTER))
    if 警:
        print("警报（提醒，不阻断）：")
        for x in 警:
            print("  · " + x)
    else:
        print("警报：无")
    print("※ 只读。机器只备材料，读者会不会点下一章由作者判断。")
    return 0


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="引擎.py")
    parser.add_argument("command", choices=("engine", "arc", "hooks"))
    parser.add_argument("project")
    parser.add_argument("target", nargs="?")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--new", nargs=2, metavar=("编号", "范围"))
    args = parser.parse_args(argv)
    P = args.project
    if args.command == "engine":
        return prepare_engine(P) if args.prepare else 报告_engine(P)
    if args.command == "arc":
        if args.new:
            return new_arc(P, args.new[0], args.new[1])
        序 = 大纲序(P)
        弧 = 弧卡列表(P)
        if not 弧:
            print("没有弧卡。建第一张：python3 novel.py arc --new A01 K0001-K0008")
            return 0
        for a in 弧:
            done = sum(1 for k, n in 序.items()
                       if a["start"] in 序 and a["end"] in 序 and 序[a["start"]] <= n <= 序[a["end"]]
                       and os.path.isfile(os.path.join(P, "05_正文", k + ".md")))
            print("%s  %s—%s  已写 %d 章  %s" % (a["id"], a["start"], a["end"], done, a["rel"]))
        return 0
    if not args.target:
        print("✗ hooks 需要章节或批次，例如 K0019-K0021")
        return 2
    return 报告_hooks(P, args.target)


if __name__ == "__main__":
    raise SystemExit(main())
