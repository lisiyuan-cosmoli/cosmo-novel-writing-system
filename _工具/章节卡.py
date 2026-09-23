#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""章节卡结构校验。

读取包阶段核对开写所需内容，提交阶段再核对提交前勾选项。
它只能证明字段已经填写，不能证明内容确由用户本人提供或读过。
"""
from __future__ import print_function

import re


# 自由文本中的待确认标记优先于勾选框，避免未确认内容进入正式提交。
待确认标记 = ("待用户确认", "待确认", "待你确认", "待作者确认", "待选择", "待改选",
              "待补充", "待定", "未确认", "尚未确认", "供用户审阅", "待审阅")

PLACEHOLDERS = (
    "（填写）", "（填这里）", "待填写", "待补", "待定", "TODO", "TBD",
    "XXX", "（示例", "示例文件", "完整 / 过渡", "未检查 / 无历史正文 / 已完成",
)


def _clean(value):
    return (value or "").replace("**", "").replace("`", "").strip()


def _filled(value):
    value = _clean(value)
    if not value:
        return False
    return not any(marker.lower() in value.lower() for marker in PLACEHOLDERS)


def _substantive(value):
    value = _clean(value)
    return _filled(value) and value not in ("无", "没有", "暂无", "不适用", "—", "-")


def _section(text, heading):
    pattern = r"(?ms)^##\s+" + re.escape(heading) + r"\s*$\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text or "")
    return match.group(1) if match else ""


def _subsection(text, heading):
    pattern = r"(?ms)^###\s+" + re.escape(heading) + r"\s*$\n(.*?)(?=^###\s+|^##\s+|\Z)"
    match = re.search(pattern, text or "")
    return match.group(1) if match else ""


def _rows(section):
    rows = []
    for line in (section or "").splitlines():
        if not line.strip().startswith("|"):
            continue
        source = line.strip()[1:-1] if line.strip().endswith("|") else line.strip()[1:]
        raw, buffer, index = [], [], 0
        while index < len(source):
            if source[index] == "\\" and index + 1 < len(source) and source[index + 1] == "|":
                buffer.append("|")
                index += 2
                continue
            if source[index] == "|":
                raw.append("".join(buffer))
                buffer = []
            else:
                buffer.append(source[index])
            index += 1
        raw.append("".join(buffer))
        cells = [_clean(cell) for cell in raw]
        if len(cells) < 2 or set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def _mapping(section):
    result = {}
    for row in _rows(section):
        if row[0] in ("项", "字段"):
            continue
        result[row[0]] = row[1] if len(row) > 1 else ""
    return result


def _data_rows(section, header_first):
    rows = _rows(section)
    if rows and header_first in rows[0][0]:
        rows = rows[1:]
    return rows


def _need(errors, mapping, label, section_name, allowed=None, substantive=False):
    value = mapping.get(label)
    if not (_substantive(value) if substantive else _filled(value)):
        errors.append("%s：%s 未填写" % (section_name, label))
        return None
    if allowed and _clean(value) not in allowed:
        errors.append("%s：%s 必须是 %s" %
                      (section_name, label, "、".join(allowed)))
    return _clean(value)


def _direction_ok(section, experiential=False):
    values = _mapping(section)
    if experiential:
        return all(_substantive(values.get(label)) for label in ("核心行动", "章末状态"))
    return all(_substantive(values.get(label)) for label in
               ("核心行动", "所得", "代价", "章末状态"))


def 找待确认(text, 合作方式=None):
    """扫出章节卡里所有仍标着「待确认」的位置。**唯一判据，各入口共用。**

    合作方式为 ai_draft 时，AI 代拟本身合法，但"待用户确认"仍然是待确认——
    授权代拟等于授权它去拟，不等于用户已经看过并认可这一份。
    """
    命中 = []
    for no, line in enumerate((text or "").split("\n"), 1):
        s = line.strip()
        if not s or s.startswith("<!--"):
            continue
        标 = [w for w in 待确认标记 if w in s]
        if not 标:
            continue
        摘 = s if len(s) <= 60 else s[:58] + "…"
        命中.append((no, 标[0], 摘))
    return 命中


def identity_errors(text, kid, display_no=None):
    """供体检、修订与逐章校验共用，不重跑旧章的创作流程。"""
    errors = []
    text = text or ""
    if not re.fullmatch(r"K\d{4}", str(kid or "")):
        return ["调用方给出的永久 ID 不合法"]

    basic = _mapping(_section(text, "基本信息"))
    card_kid = _need(errors, basic, "永久 ID", "基本信息")
    if card_kid and card_kid != kid:
        errors.append("基本信息：永久 ID 是 %s，不是当前章节 %s" % (card_kid, kid))
    card_display = _need(errors, basic, "展示章号", "基本信息")
    if card_display and not re.fullmatch(r"\d+", card_display):
        errors.append("基本信息：展示章号必须是正整数")
    elif card_display and display_no is not None and int(card_display) != int(display_no):
        errors.append("基本信息：展示章号 %s 与分章大纲 %s 不一致" %
                      (card_display, display_no))
    return errors


def _repeat_errors(errors, text, kid, display_no, continuity):
    # 3.6 起「重复动作清单」的表直接挂在二级标题下，没有 ### 取样范围 这一层。
    # 这里按**结构**取整节，不认那个会漂移的小标题名——3.6.0 就是栽在这上面：
    # 模板删掉小标题、解析器还在找它，结果 repeat --card 的输出贴进去也判未填写，
    # 而 215 项测试全绿（夹具还停在 3.5 的结构上）。
    # 3.5 及以前的卡把表放在 ### 取样范围 下，那一层仍然优先认，迁移不返工。
    legacy_section = _subsection(text, "取样范围")
    repeat = _mapping(legacy_section if legacy_section
                      else _section(text, "重复动作清单"))

    # 重复证据状态：新卡写在「重复动作清单」表里（repeat --card 一次产出整块，
    # 不用把同一个状态在两处各填一遍），旧卡写在「连续性约束」里。
    # 3.6.0 的模板两处都有，用户多半只填了其中一处——所以**哪处填了认哪处**，
    # 都没填时才按这张卡自己的结构决定错误报在哪一节，不让人去找一个不存在的栏。
    if _filled(repeat.get("重复证据状态")):
        状态源, 状态节 = repeat, "重复动作清单"
    elif _filled(continuity.get("重复证据状态")):
        状态源, 状态节 = continuity, "连续性约束"
    elif "重复证据状态" in repeat:
        状态源, 状态节 = repeat, "重复动作清单"
    else:
        状态源, 状态节 = continuity, "连续性约束"
    repeat_status = _need(errors, 状态源, "重复证据状态", 状态节,
                          ("无历史正文", "已完成"))
    if repeat_status == "无历史正文":
        if display_no is not None and int(display_no) != 1:
            errors.append("重复动作清单：只有第一章可以写“无历史正文”")
    elif repeat_status == "已完成":
        # 3.6：检索由 novel.py repeat 执行，这里只核对结论块。
        # 旧卡里写 grep 命令的写法继续接受——迁移不该把已经写好的卡判成不合格。
        旧式 = any(k in repeat for k in ("实际执行的动作检索命令", "本次取样的永久 ID"))
        if 旧式:
            for label in ("本次取样的永久 ID", "实际执行的动作检索命令",
                          "实际执行的对白检索命令", "实际执行的章末检索命令", "命中总行数"):
                _need(errors, repeat, label, "重复动作清单")
            sample_ids = list(dict.fromkeys(re.findall(r"K\d{4}",
                                                       _clean(repeat.get("本次取样的永久 ID")))))
        else:
            for label in ("取样章", "命中总行数", "检索方式", "本章处理"):
                _need(errors, repeat, label, "重复动作清单")
            方式 = _clean(repeat.get("检索方式"))
            if 方式 and "repeat" not in 方式:
                errors.append("重复动作清单：检索方式应由 novel.py repeat 生成，"
                              "当前写的是「%s」" % 方式[:30])
            sample_ids = list(dict.fromkeys(re.findall(r"K\d{4}",
                                                       _clean(repeat.get("取样章")))))
        if not sample_ids:
            errors.append("重复动作清单：取样章没有可解析的章节")
        elif kid in sample_ids:
            errors.append("重复动作清单：取样范围不能把当前未写章节 %s 算作历史正文" % kid)
        hits = _clean(repeat.get("命中总行数"))
        match = re.fullmatch(r"(\d+)(?:\s*行)?", hits)
        if hits and not match:
            errors.append("重复动作清单：命中总行数必须写成整数或“整数 行”")
        if match and int(match.group(1)) > 0 and not 旧式:
            if not _substantive(repeat.get("本章处理")):
                errors.append("重复动作清单：有命中时必须写明本章怎么处理")



HOOK_TYPES = ("新信息", "危险逼近", "关系变化", "选择当口", "身份揭露", "兑现在即", "弧末收束")


def 是新版(text):
    """4.0 瘦身章卡以「## 三拍 🔒」一节为标志；旧卡继续按旧结构校验。"""
    return bool(re.search(r"(?m)^##\s+三拍\s*🔒\s*$", text or ""))


def _validate_v4(text, kid, display_no, phase, 合作方式):
    errors = identity_errors(text, kid, display_no)
    basic = _mapping(_section(text, "基本信息"))
    _need(errors, basic, "工作模式", "基本信息", ("完整", "过渡"))
    for label in ("所属弧与批", "视角人物", "时间与上一章间隔", "主要地点"):
        _need(errors, basic, label, "基本信息", substantive=True)

    beats = _data_rows(_section(text, "三拍 🔒"), "开头兑现")
    if not any(len(row) >= 4 and all(_substantive(cell) for cell in row[:4]) for row in beats):
        errors.append("三拍：开头兑现、中段、章末钩子、钩子类型四格都要填写")
    else:
        row = next(r for r in beats if len(r) >= 4 and all(_substantive(c) for c in r[:4]))
        kind = re.split(r"[（(]", _clean(row[3]), 1)[0].strip()
        if kind not in HOOK_TYPES:
            errors.append("三拍：钩子类型「%s」不在 %s 之内" % (kind, "／".join(HOOK_TYPES)))

    concrete = _section(text, "必须出现的具体信息 🔒")
    first = [m.group(2) for m in (re.match(r"^\s*([1-3])[.、]\s*(.*)$", line)
                                  for line in concrete.splitlines()) if m and m.group(1) == "1"]
    if not first or not _substantive(first[-1]):
        errors.append("必须出现的具体信息：第 1 条未填写")

    knowledge = _data_rows(_section(text, "知情变化"), "人物或读者")
    if not any(len(row) >= 3 and all(_substantive(cell) for cell in row[:3]) for row in knowledge):
        errors.append("知情变化：至少填写一行三列完整记录")

    continuity = _mapping(_section(text, "连续性约束"))
    for label in ("伏笔与悬念编号", "已启用插件需要推进的记录", "需要调阅的旧章",
                  "本章不能出现的人物、信息或地点", "伤势、物件、位置与时间限制"):
        _need(errors, continuity, label, "连续性约束")

    _repeat_errors(errors, text, kid, display_no, continuity)

    source = _mapping(_section(text, "来源"))
    how = _need(errors, source, "方案来源", "来源", ("沿用弧卡", "本章比较"))
    _need(errors, source, "依据", "来源", substantive=True)
    _need(errors, source, "是否含 AI 代拟内容", "来源", ("是", "否"))
    if how == "本章比较":
        ok = [letter for letter in ("A", "B", "C") if _direction_ok(_subsection(text, "走向 " + letter))]
        if len(ok) < 2:
            errors.append("来源：本章比较时至少写出两个完整走向（### 走向 A、### 走向 B）")

    待 = 找待确认(text, 合作方式)
    if 待:
        位置 = "；".join("第 %d 行「%s」%s" % (no, 标, 摘) for no, 标, 摘 in 待[:4])
        if phase == "commit":
            errors.append("仍有 %d 处标着待确认，不能定稿：%s。"
                          "勾选框不能覆盖这个判断——先让用户确认或改写这些位置"
                          % (len(待), 位置))
        else:
            errors.append("提示·待确认：%d 处仍标着待确认（%s）。"
                          "可以据此写草稿，但定稿前必须解决" % (len(待), 位置))
    if phase == "commit":
        checks = re.findall(r"(?m)^\s*-\s*\[([ xX])\]\s+(.+)$", _section(text, "提交前核对"))
        if len(checks) < 7:
            errors.append("提交前核对：七项核对清单不完整")
        unchecked = [label.strip() for mark, label in checks if mark.lower() != "x"]
        if unchecked:
            errors.append("提交前核对：仍有 %d 项未勾选" % len(unchecked))
    elif phase != "package":
        errors.append("未知校验阶段 %s" % phase)
    return errors


def validate(text, kid, display_no=None, phase="package", 合作方式=None):
    """返回错误列表。phase 可为 package 或 commit。"""
    if 是新版(text):
        return _validate_v4(text or "", kid, display_no, phase, 合作方式)
    errors = identity_errors(text, kid, display_no)
    text = text or ""
    basic = _mapping(_section(text, "基本信息"))
    mode = _need(errors, basic, "工作模式", "基本信息", ("完整", "过渡"))
    focus = _clean(basic.get('章节重心')) or ('体验呈现' if mode == '过渡' else '情节推进')
    if focus not in ('情节推进', '体验呈现'):
        errors.append('基本信息：章节重心必须是情节推进或体验呈现')
    experiential = focus == '体验呈现'
    for label in ("视角人物", "时间与上一章间隔", "主要地点"):
        _need(errors, basic, label, "基本信息", substantive=True)

    change = _mapping(_section(text, "本章变化"))
    required_change = ["章首状态", "本章主要行动", "读者带走的问题或期待"]
    if not experiential:
        required_change += ["阻力来自哪里", "越过阻力要付出的具体代价", "章末不可逆变化", "结束时谁获得了什么"]
    for label in required_change:
        _need(errors, change, label, "本章变化", substantive=True)

    concrete = _section(text, "必须出现的具体信息 🔒")
    numbered = []
    for line in concrete.splitlines():
        match = re.match(r"^\s*([1-3])[.、]\s*(.*)$", line)
        if match:
            numbered.append((match.group(1), match.group(2)))
    for number in (("1",) if experiential else ("1", "2", "3")):
        values = [value for no, value in numbered if no == number]
        if not values or not _substantive(values[-1]):
            errors.append("必须出现的具体信息：第 %s 条未填写" % number)

    anchor = _mapping(_section(text, "硬锚点 🔒"))
    anchor_labels = ("最后落在哪个动作或事实",) if experiential else ("最后落在哪个动作或事实", "哪件事本章不能解释", "哪个承诺必须兑现")
    for label in anchor_labels:
        _need(errors, anchor, label, "硬锚点", substantive=True)

    knowledge = _data_rows(_section(text, "知情范围"), "人物或读者")
    if not any(len(row) >= 4 and all(_substantive(cell) for cell in row[:4]) for row in knowledge):
        errors.append("知情范围：至少填写一行四列完整记录")

    continuity = _mapping(_section(text, "连续性约束"))
    for label in ("需要照应的伏笔 ID", "已启用插件需要推进的记录", "需要调阅的旧章",
                  "本章不能出现的人物、信息或地点", "伤势、物件、位置与时间限制"):
        _need(errors, continuity, label, "连续性约束")

    _repeat_errors(errors, text, kid, display_no, continuity)

    scenes = _data_rows(_section(text, "场景清单"), "序号")
    scene_columns = (0, 1, 2, 4) if experiential else (0, 1, 2, 3, 4)
    if not any(len(row) >= 5 and all(_substantive(row[i]) for i in scene_columns) for row in scenes):
        errors.append("场景清单：至少填写一行五列完整场景")

    directions = {letter: _direction_ok(_subsection(text, "走向 " + letter), experiential)
                  for letter in ("A", "B", "C")}
    choice = _mapping(_section(text, "用户选择"))
    source = _clean(choice.get("方案来源")) or "本章比较"
    if source not in ("本章比较", "沿用已确认路线"):
        errors.append("用户选择：方案来源必须是本章比较或沿用已确认路线")
    reuse = source == "沿用已确认路线"
    if reuse:
        _need(errors, choice, "沿用依据", "用户选择", substantive=True)
    if not reuse and not experiential and mode == "完整" and not all(directions.values()):
        errors.append("走向选择：完整模式必须填写 A、B、C 三个完整走向")
    if not reuse and not experiential and mode == "过渡" and sum(1 for value in directions.values() if value) < 2:
        errors.append("走向选择：过渡模式必须填写一个主走向和一个替代走向")

    selected = _need(errors, choice, "选择", "用户选择")
    if selected:
        letter = selected.strip().upper().replace("走向", "").strip()
        if letter not in directions or not directions[letter]:
            errors.append("用户选择：选择必须指向已经完整填写的 A、B 或 C")
    _need(errors, choice, "选择理由", "用户选择", substantive=True)
    _need(errors, choice, "是否含 AI 代拟内容", "用户选择", ("是", "否"))

    # 待确认门禁：package 阶段提醒，commit 阶段阻断。
    待 = 找待确认(text, 合作方式)
    if 待:
        位置 = "；".join("第 %d 行「%s」%s" % (no, 标, 摘) for no, 标, 摘 in 待[:4])
        if phase == "commit":
            errors.append("仍有 %d 处标着待确认，不能定稿：%s。"
                          "勾选框不能覆盖这个判断——先让用户确认或改写这些位置"
                          % (len(待), 位置))
        else:
            errors.append("提示·待确认：%d 处仍标着待确认（%s）。"
                          "可以据此写草稿，但定稿前必须解决" % (len(待), 位置))

    if phase == "commit":
        checks = re.findall(r"(?m)^\s*-\s*\[([ xX])\]\s+(.+)$",
                            _section(text, "提交前核对"))
        if len(checks) < 7:
            errors.append("提交前核对：七项核对清单不完整")
        unchecked = [label.strip() for mark, label in checks if mark.lower() != "x"]
        if unchecked:
            errors.append("提交前核对：仍有 %d 项未勾选" % len(unchecked))
    elif phase != "package":
        errors.append("未知校验阶段 %s" % phase)
    return errors


校验 = validate
