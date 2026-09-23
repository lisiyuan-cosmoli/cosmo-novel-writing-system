#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开书孵化：第一章之前的基础创作决定，走和章节提交同一套闸门。

为什么要有这道闸门
    v3.2 之前，"这本书初始化好了没有"只看有没有定稿正文，而初始化检查只能
    证明**字段非空**。于是最典型的失败长这样：作者说了个题材，模型顺手把
    一句话故事、核心问题、人物档案、结构路标全填满了，看起来完成度很高，
    后续创作可能偏离作者意图，字段非空不能证明方案已确认。

    字段非空挡不住这个。所以开书阶段和章节阶段用同一套机制：候选区、试算、
    完整摘要批准、可恢复事务。机制一致是有价值的——只需要学一套心智模型。

它能证明什么，不能证明什么
    能证明：十一项基础决定被逐条提出过、有明确来源、在批准时全部已确认，
    并且用户看到的那份清单在写入前没有被换掉。
    不能证明：批准者的现实身份，也不能证明用户真的读过每个候选。
    所以它不叫"用户参与证明"，叫"决定记录与内容绑定批准"。

用法
    python3 novel.py foundation --prepare        建候选区
    python3 novel.py foundation                  试算，一次列出全部缺项
    python3 novel.py foundation --apply --approve <完整SHA256>
"""
from __future__ import print_function

import argparse
import io
import os
import re
import shutil
import sys

import v2_core as core
import 事务


候选名 = "INIT"
意图rel = "00_设定层/00_创作意图.md"
决策rel = "06_归档/开书决策记录.md"

必需决策 = ("合作方式", "核心创作承诺", "不可替代元素", "主角核心欲望",
            "核心困难选择", "结局方向", "创作禁区", "结构路线", "暂定书名",
            "文风方向", "读者引擎")
文风来源 = ("用户自写", "授权引用", "候选选定", "方向生成")
合法来源 = ("用户原案", "AI 提案后用户选择", "用户修改后确认", "AI 代拟且用户批准")
合法状态 = ("待定", "已确认", "已废弃")
意图必填 = ("合作方式", "本书不可替代的具体元素", "主角核心欲望",
            "核心困难选择", "关系或情感承诺", "大致结局方向", "明确不想写成的样子")
占位词 = ("（填写）", "（填这里）", "待定", "待补", "TODO", "TBD", "（示例")


def 出(value=""):
    print(value, flush=True)


class 意图冲突(ValueError):
    """创作意图同一栏出现互相冲突的值。"""


def _清(v):
    return (v or "").replace("**", "").replace("`", "").strip()


def _有料(v):
    v = _清(v)
    return bool(v) and not any(w in v for w in 占位词)


def 表行(text):
    """返回所有表格数据行的单元格列表，跳过分隔行。"""
    rows = []
    for line in (text or "").split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [_清(c) for c in s.strip("|").split("|")]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def _取(意图, 标):
    for k, v in (意图 or {}).items():
        if 标 in k:
            return v
    return ""


def 读意图(text):
    """两列表格 → {标签: 内容}。同一标签出现多个**不同**值时抛错。

    v3.4 用 setdefault 只留第一条，第二条静默丢弃——同一栏写了两个互相冲突
    的合作方式，工具会安静地按第一个走。冲突必须报出来，不能替用户挑一个。
    """
    out, 冲突 = {}, []
    for cells in 表行(text):
        if len(cells) < 2 or cells[0] in ("项", "取值", "字段", "事项"):
            continue
        标, 值 = cells[0], cells[1]
        if 标 in out and _清(out[标]) != _清(值) and _有料(out[标]) and _有料(值):
            冲突.append("%s（「%s」与「%s」）" % (标, out[标], 值))
        out.setdefault(标, 值)
    if 冲突:
        raise 意图冲突("创作意图里同一栏出现互相冲突的值：" + "；".join(冲突))
    return out


def 读决策(text):
    """七列决策表 → [{...}]，只取有决策 ID 的行。"""
    out = []
    for cells in 表行(text):
        if len(cells) < 7 or not re.fullmatch(r"D\d{2,}", cells[0]):
            continue
        out.append({
            "id": cells[0], "类别": cells[1], "候选": cells[2],
            "选择": cells[3], "理由": cells[4], "来源": cells[5], "状态": cells[6],
        })
    return out


def 核开书内容(project, 读):
    """一次列全部缺项。**不在第一条就返回**——解除一条才看见下一条是返工的来源。"""
    缺 = []
    意图文 = 读(意图rel)
    if 意图文 is None:
        缺.append("%s 取不到" % 意图rel)
        意图 = {}
    else:
        try:
            意图 = 读意图(意图文)
        except 意图冲突 as exc:
            缺.append(str(exc))
            意图 = {}
        for 标 in 意图必填:
            # 按包含匹配：模板里写的是「核心困难选择（他必须在什么之间选）」，
            # 用户也可能微调措辞。要求逐字相等只会制造一条谁也想不到的缺项。
            if not any(标 in k and _有料(v) for k, v in 意图.items()):
                缺.append("创作意图：%s 未填写" % 标)
    模式 = _清(_取(意图, "合作方式"))
    if 模式 and 模式 not in core.COOP_MODES:
        缺.append("创作意图：合作方式只能是 %s，当前是「%s」"
                  % ("、".join(core.COOP_MODES), 模式))
        模式 = ""

    决策文 = 读(决策rel)
    if 决策文 is None:
        缺.append("%s 取不到" % 决策rel)
        return 缺, 模式, []
    行 = 读决策(决策文)
    按类别 = {}
    for row in 行:
        if row["状态"] == "已废弃":
            continue
        按类别.setdefault(row["类别"], []).append(row)
    # 同一类别只能有一条当前有效记录。v3.4 取 rows[-1]，已确认那行会被后面
    # 的待定行盖掉，反过来也一样——顺序决定结论，那不是判据。
    for 类别, rows in sorted(按类别.items()):
        if len(rows) > 1:
            缺.append("开书决策：%s 有 %d 条当前有效记录（%s）。"
                      "同一类别只能留一条，旧的标已废弃"
                      % (类别, len(rows), "、".join(r["id"] for r in rows)))

    # 4.1：新书开书须明确选择题材文风档（D10 的声音落在哪一档）。
    if project is not None:
        import 文风档
        if not 文风档.当前档(project)[1]:
            缺.append("文风档未选择：python3 novel.py voice --profile literary|webnovel|romance|genre")
    # D11（4.0）：读者引擎卡本身也要真的填好。决策表写“已确认”而卡还是模板，
    # 等于只确认了一句话；引擎层靠这张卡进每一份读取包。
    import 引擎
    引擎文 = 读(引擎.ENGINE_REL)
    if 引擎文 is None:
        缺.append("%s 取不到（D11 读者引擎）" % 引擎.ENGINE_REL)
    else:
        缺.extend("读者引擎卡：" + x for x in 引擎.引擎卡检查(引擎文))

    for 类别 in 必需决策:
        rows = 按类别.get(类别)
        if not rows:
            缺.append("开书决策：缺「%s」这一项" % 类别)
            continue
        row = rows[-1]
        if row["状态"] not in 合法状态:
            缺.append("开书决策：%s 的状态「%s」不是 %s 之一"
                      % (类别, row["状态"] or "空", "／".join(合法状态)))
            continue
        if row["状态"] != "已确认":
            缺.append("开书决策：%s 仍是「%s」，未确认" % (类别, row["状态"]))
            continue
        if not _有料(row["选择"]):
            缺.append("开书决策：%s 已标已确认，但用户选择是空的" % 类别)
        if row["来源"] not in 合法来源:
            缺.append("开书决策：%s 的来源「%s」不在允许取值里（%s）"
                      % (类别, row["来源"] or "空", "、".join(合法来源)))
            continue
        # author_led 默认不代拟；单项明确委托沿用现有来源与理由记录，
        # 不要求改变整书合作方式。记录自洽不等于证明现实授权确实发生。
        代拟批准 = row["来源"] == "AI 代拟且用户批准"
        if 模式 == "author_led" and row["来源"] not in (
                "用户原案", "用户修改后确认", "AI 代拟且用户批准"):
            缺.append("开书决策：author_led 模式下 %s 的来源不能是「%s」"
                      % (类别, row["来源"]))
        if 代拟批准 and not _有料(row["理由"]):
            缺.append("开书决策：%s 标为 AI 代拟且用户批准，必须写明批准理由" % 类别)
        if 类别 == "文风方向":
            取值 = _清(row["选择"])
            if 取值 not in 文风来源:
                缺.append("开书决策：文风方向的选择必须是 %s 之一，当前是「%s」"
                          % ("、".join(文风来源), 取值 or "空"))
            elif 取值 in ("候选选定", "方向生成"):
                候选 = [x for x in re.split(r"／|/|、|；|;", row["候选"]) if _有料(x)]
                # 明确方向下的单项委托可以只试写一段。方向放候选栏，
                # 委托范围及采纳原因放既有理由栏；不另加批准字段。
                单项委托 = len(候选) == 1 and 代拟批准 and _有料(row["理由"])
                if len(候选) < 2 and not 单项委托:
                    缺.append("开书决策：文风方向选了「%s」，"
                              "「候选或用户原案」栏要写出候选之间的差别（两个以上）。"
                              "已有明确方向且只委托一段时，记录该方向，来源用 AI 代拟且用户批准，"
                              "并在理由里说明委托范围与采纳原因" % 取值)
        if 模式 == "guided" and 类别 in ("核心创作承诺", "结构路线"):
            候选 = [x for x in re.split(r"／|/|、|；|;", row["候选"]) if _有料(x)]
            # 规范化后去重：只改空格标点的"两个候选"不是两个候选
            规范 = {re.sub(r"[\s，。、；;,.！!？?「」“”\"'（）()]+", "", x) for x in 候选}
            规范.discard("")
            if len(候选) < 2:
                缺.append("开书决策：guided 模式下 %s 至少要留下两个互相区分的候选，"
                          "当前只有 %d 个。只给一个候选让人点头，不是选择"
                          % (类别, len(候选)))
            elif len(规范) < 2:
                缺.append("开书决策：%s 的候选去掉空格标点之后是同一个，"
                          "不算两个候选" % 类别)
    return 缺, 模式, 行


def 允许路径(project):
    policy = core.load_foundation_policy(project)
    allowed = set(policy["foundation_mutable_files"])
    registry = core.load_json(os.path.join(project, "04_题材插件", "plugin-registry.json"))
    if not isinstance(registry, dict) or not isinstance(registry.get("plugins"), list):
        raise core.ProjectError("插件注册表无法读取，不能安全计算开书白名单")
    by_id = {item.get("id"): item for item in registry["plugins"] if isinstance(item, dict)}
    data = core.load_project(project)
    for plugin_id in data.get("enabled_plugins", []):
        entry = by_id.get(plugin_id)
        if not entry or not entry.get("manifest"):
            raise core.ProjectError("已启用插件 %s 没有合法清单" % plugin_id)
        manifest_rel = os.path.join("04_题材插件", entry["manifest"]).replace(os.sep, "/")
        manifest = core.load_json(os.path.join(project, manifest_rel))
        if not isinstance(manifest, dict) or manifest.get("id") != plugin_id:
            raise core.ProjectError("插件 %s 清单损坏" % plugin_id)
        targets = {item.get("target") for item in manifest.get("files", [])
                   if isinstance(item, dict)}
        for rel in manifest.get("foundation_files", []) or []:
            # 插件只能把**自己声明过的**设定文件放进开书候选，
            # 而且只能是 00_设定层/插件/ 下的，不能借开书扩大到别处。
            if not core.safe_relative(rel) or rel not in targets \
                    or not rel.startswith("00_设定层/插件/"):
                raise core.ProjectError("插件 %s 的开书可写路径不合法 %s" % (plugin_id, rel))
            allowed.add(rel)
    return allowed


def 收候选(project, root):
    entries, errors = [], []
    if core.path_has_symlink(project, os.path.relpath(root, project)):
        return [], ["候选路径经过符号链接"]
    for cur, dirs, files in os.walk(root, followlinks=False):
        kept = []
        for name in dirs:
            full = os.path.join(cur, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if name == ".DS_Store":
                continue
            if os.path.islink(full):
                errors.append(rel + "（候选目录是符号链接）")
                continue
            kept.append(name)
        dirs[:] = kept
        for name in files:
            if name == ".DS_Store":
                continue
            full = os.path.join(cur, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full):
                errors.append(rel + "（候选文件是符号链接）")
                continue
            data = core.read_bytes(full)
            if data is None:
                errors.append(rel + "（候选文件无法读取）")
                continue
            entries.append({"path": rel, "data": data})
    return sorted(entries, key=lambda x: x["path"]), sorted(errors)


def 核候选路径(project, entries, allowed):
    errors = []
    for item in entries:
        rel = item["path"]
        if not core.safe_relative(rel):
            errors.append(rel + "（路径逃逸或非规范路径）")
            continue
        import 开书探索
        policy = core.load_foundation_policy(project)
        material_allowed = (policy.get("discovery_materials") is True and 开书探索.is_material(rel))
        if rel not in allowed and not material_allowed:
            errors.append(rel + "（不在开书可写白名单）")
            continue
        parent = os.path.dirname(rel)
        if parent and not os.path.isdir(os.path.join(project, parent)):
            errors.append(rel + "（正式项目里没有目标目录）")
            continue
        linked = core.path_has_symlink(project, rel)
        if linked:
            errors.append(rel + "（正式目标路径经过符号链接 %s）" % linked)
    return errors


def 候选摘要(project, entries, 模式, plugins):
    rows = []
    for item in entries:
        before = core.read_bytes(os.path.join(project, item["path"]))
        rows.append({
            "before_sha256": core.sha256_bytes(before) if before is not None else None,
            "candidate_sha256": core.sha256_bytes(item["data"]),
            "path": item["path"],
            "size": len(item["data"]),
            "state": "add" if before is None else "modify",
        })
    payload = {"files": rows, "format": "novel-foundation-v1",
               "mode": 模式, "plugins": sorted(plugins)}
    return rows, core.canonical_digest(payload)


def prepare(project):
    root = os.path.join(project, "_候选", 候选名)
    if core.path_has_symlink(project, "_候选/" + 候选名):
        出("✗ 候选路径经过符号链接，拒绝创建")
        return 1
    if os.path.lexists(root):
        出("✗ 候选区已经存在：%s" % root)
        出("  不覆盖已有内容。要重来就先自己删掉它。")
        return 1
    allowed = 允许路径(project)
    带 = []
    for rel in sorted(allowed):
        src = os.path.join(project, rel)
        if not os.path.isfile(src) or os.path.islink(src):
            continue
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        带.append(rel)
    出("✓ 已建开书候选区，带入 %d 份空白基础文件：" % len(带))
    for rel in 带:
        出("    · " + rel)
    出()
    出("在候选区里和用户一起完成这些内容，再运行 python3 novel.py foundation 试算。")
    出("FOUNDATION_CANDIDATE=_候选/%s" % 候选名)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="foundation", description="开书孵化与 INIT 提交")
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve")
    args = parser.parse_args(argv)

    project = core.resolve_project(args.project)
    data = core.load_project(project)
    if args.approve is not None and not re.fullmatch(r"[0-9a-f]{64}", args.approve.lower()):
        出("✗ 批准摘要必须是完整的 64 位 SHA-256")
        return 2

    if args.prepare:
        return prepare(project)

    状态 = core.init_state(data)
    W = 60
    出("=" * W)
    出("开书闸门 · %s" % ("正式写入" if args.apply else "试算（不碰正式文件）"))
    出("=" * W)
    出("  当前开书状态：%s" % 状态)
    if 状态 == "confirmed":
        出("  ※ 本项目已经完成开书确认。再次运行会用新的候选覆盖基础设定，")
        出("    这仍然要走同一道摘要批准，但请确认这确实是你想做的事。")

    root = os.path.join(project, "_候选", 候选名)
    if core.path_has_symlink(project, "_候选/" + 候选名):
        出("✗ 开书候选路径经过符号链接，拒绝读取或写入")
        return 1
    if not os.path.isdir(root):
        出("✗ 开书候选区不存在或不是普通目录：%s" % root)
        出("  先运行 python3 novel.py foundation --prepare")
        return 1
    entries, collect_errors = 收候选(project, root)
    if collect_errors:
        出("✗ 候选区含不安全对象：")
        for e in collect_errors:
            出("    · " + e)
        return 1
    if not entries:
        出("✗ 候选区为空。输入缺失不等于没有问题。")
        return 1

    allowed = 允许路径(project)
    path_errors = 核候选路径(project, entries, allowed)
    if path_errors:
        出("✗ 候选文件路径不合法：")
        for e in path_errors:
            出("    · " + e)
        出("  开书候选只能改基础设定、决策与研究归档。project.json、脚本、执行契约、")
        出("  策略文件和系统说明都不能混进来——状态变更由本工具生成并纳入同一笔事务。")
        return 1

    import 开书探索
    开书探索.verify_archive(project, entries)
    import 结构复盘
    for item in entries:
        if item['path'] == 结构复盘.RECORD:
            结构复盘.parse_record(item['data'])
    候选内容 = {item["path"]: item["data"] for item in entries}

    def 读候选(rel):
        if rel in 候选内容:
            return 候选内容[rel].decode("utf-8", errors="replace")
        return core.read_text(os.path.join(project, rel))

    缺, 模式, 决策行 = 核开书内容(project, 读候选)
    # 插件必须核对当前候选，不能只校验正式区的空模板。
    插件 = _载入(os.path.join(project, "_工具", "插件.py"), "novel_foundation_plugin")
    for plugin_id in data.get("enabled_plugins", []):
        ok, errors = 插件.verify(project, plugin_id, reader=读候选)
        if not ok:
            缺.extend("插件 %s：%s" % (plugin_id, error) for error in errors)

    # 基础设定本身仍要过读取包那套开书检查，不重复实现一遍
    读取包 = _载入(os.path.join(project, "_工具", "读取包.py"), "novel_readpkg")
    import tempfile
    影 = tempfile.mkdtemp(prefix="novel-foundation-")
    try:
        shadow = os.path.join(影, os.path.basename(project))
        os.makedirs(shadow)
        for rel in sorted(set(list(allowed) + [
                "项目配置.md", "00_设定层/01_固定设定.md", "00_设定层/02_风格样本.md",
                "00_设定层/03_分章大纲.md", "01_运行层/04_状态快照.md",
                "_工具/专名表.txt", "project.json"])):
            src = os.path.join(project, rel)
            dst = os.path.join(shadow, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if rel in 候选内容:
                core.atomic_write_bytes(dst, 候选内容[rel])
            elif os.path.isfile(src) and not os.path.islink(src):
                shutil.copy2(src, dst)
        缺.extend("基础设定：" + x for x in 读取包.初始化缺项(shadow, "K0001"))
        定声 = _载入(os.path.join(project, "_工具", "定声.py"), "novel_voice")
        缺.extend("文风：" + x for x in 定声.核对(shadow, 开书=True))
    finally:
        shutil.rmtree(影, ignore_errors=True)

    rows, digest = 候选摘要(project, entries, 模式, data.get("enabled_plugins", []))
    出()
    出("  合作方式：%s" % (模式 or "未确定"))
    出("  已登记决策：%d 条，其中已确认 %d 条"
       % (len(决策行), sum(1 for r in 决策行 if r["状态"] == "已确认")))
    待定 = [r["类别"] for r in 决策行 if r["状态"] == "待定"]
    if 待定:
        出("  仍待确认：%s" % "、".join(待定))
    出("  已启用插件：%s" % ("、".join(data.get("enabled_plugins", [])) or "无"))
    出()
    出("  候选文件 %d 份（完整摘要）：" % len(rows))
    for row in rows:
        出("    [%s] %s" % ("新增" if row["state"] == "add" else "替换", row["path"]))
        出("      BEFORE    %s" % (row["before_sha256"] or "(不存在)"))
        出("      CANDIDATE %s  %d bytes" % (row["candidate_sha256"], row["size"]))

    if 缺:
        出()
        出("✗ 开书尚未完成，缺 %d 项（一次列全，不逐条卡）：" % len(缺))
        for x in 缺:
            出("    · " + x)
        出()
        出("  本次没有改动任何正式文件。")
        return 1

    出()
    出("FOUNDATION_CANDIDATE_SHA256=%s" % digest)
    if not args.apply:
        出()
        出("※ 这是试算。把上面的候选清单和摘要完整展示给用户，确认后使用：")
        出("  %s" % _建议命令(project, digest))
        return 0
    if not args.approve:
        出()
        出("✗ 正式写入缺少 --approve <FOUNDATION_CANDIDATE_SHA256>。")
        return 1
    if args.approve.lower() != digest:
        出()
        出("✗ 批准摘要与当前候选不一致。候选、正式基线或插件决定已经变化，请重新试算。")
        出("  当前摘要：%s" % digest)
        return 1

    import json

    def 锁内复核():
        """**在事务锁内**重读候选、重算摘要、比对批准值（同 落盘.py 的理由）。"""
        fresh, fresh_errors = 收候选(project, root)
        fresh_path_errors = 核候选路径(project, fresh, allowed)
        当前 = core.load_project(project)
        fresh_rows, fresh_digest = 候选摘要(
            project, fresh, 模式, 当前.get("enabled_plugins", []))
        if fresh_errors or fresh_path_errors or fresh_digest != digest:
            细节 = "；".join(fresh_errors + fresh_path_errors) or ("当前摘要 %s" % fresh_digest)
            raise 事务.TransactionError(
                "审批后候选、正式基线或插件决定发生变化，拒绝写入。请重新试算。  " + 细节)
        changes = {item["path"]: item["data"] for item in fresh}
        updated = dict(当前)
        updated["initialization"] = {
            "status": "confirmed",
            "mode": 模式,
            "confirmed_at": core.utc_now(),
            "approved_sha256": digest,
        }
        内容 = {item["path"]: item["data"] for item in fresh}
        配置 = 内容.get("项目配置.md")
        书名 = _书名(配置.decode("utf-8", errors="replace") if 配置
                    else (core.read_text(os.path.join(project, "项目配置.md")) or ""))
        if 书名:
            updated["title"] = 书名
        updated["updated_at"] = core.utc_now()
        errs = core.validate_project(updated)
        if errs:
            raise 事务.TransactionError("更新后的 project.json 不合法：%s" % "；".join(errs))
        changes["project.json"] = (json.dumps(updated, ensure_ascii=False, indent=2,
                                              sort_keys=True) + "\n").encode("utf-8")
        return {"changes": changes, "label": "foundation INIT",
                "metadata": {"foundation_sha256": digest, "mode": 模式}}

    def 写后复核():
        缺2, _模式2, _行2 = 核开书内容(project, lambda rel: core.read_text(
            os.path.join(project, rel)))
        if 缺2:
            return False, "写后仍缺 %d 项" % len(缺2)
        for plugin_id in data.get("enabled_plugins", []):
            ok, errors = 插件.verify(project, plugin_id)
            if not ok:
                return False, "插件写后核对失败：" + "；".join(errors)
        if core.init_state(core.load_project(project)) != "confirmed":
            return False, "开书状态没有写进 project.json"
        return True, ""

    tx = 事务.apply_changes(project, plan=锁内复核, validator=写后复核)
    if core.path_has_symlink(project, "_候选/" + 候选名):
        出("※ 正式提交已完成，但候选路径现在经过符号链接，未清理候选区。")
    else:
        shutil.rmtree(root, ignore_errors=True)
    出()
    出("✓ 开书已确认。事务 %s" % tx["id"])
    出("  开书状态 → confirmed，合作方式 %s" % 模式)
    出("  现在可以生成 K0001 的简报了：python3 novel.py brief K0001 --write")
    出("  ※ 通过只说明十一项基础决定都有记录且已确认，不说明这个故事一定成立。")
    return 0


def _书名(配置文):
    for line in (配置文 or "").split("\n"):
        if line.lstrip().startswith("|") and "书名" in line:
            cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and _有料(cells[1]):
                return cells[1]
    return None


def _建议命令(project, digest):
    project = os.path.abspath(project)
    if os.path.abspath(os.getcwd()) == project:
        return "python3 novel.py foundation --apply --approve %s" % digest
    return 'python3 novel.py foundation "%s" --apply --approve %s' % (project, digest)


def _载入(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
