#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""题材中立的项目体检。

这里只检查能够从文件中客观证明的结构、引用、状态和产物一致性。
内容质量与题材规则分别交给人工复读和已启用插件。
"""
from __future__ import print_function

import argparse
from collections import Counter
import glob
import importlib.util
import io
import os
import re
import sys


TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)


def _load(name):
    path = os.path.join(TOOL_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("doctor_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def graph_tracked_paths(project, has_manifest=True):
    """Graph freshness inputs shared by diagnosis and revision writes."""
    tracked = [
        "00_设定层/03_分章大纲.md", "01_运行层/04_状态快照.md",
        "01_运行层/05_伏笔表.md", "01_运行层/06_事实记录.md",
        "01_运行层/06b_事实记录_已归档段.md",
    ]
    if has_manifest:
        try:
            modules = _load("模块表")
            for _, detail in modules.启用详情(project):
                tracked.extend(detail.get("运行表", []))
        except Exception:
            pass
    return tracked


def _read(project, rel, default=""):
    try:
        with io.open(os.path.join(project, rel), "r", encoding="utf-8") as handle:
            return handle.read().replace("\r\n", "\n")
    except (OSError, UnicodeError):
        return default


def _outline(project):
    text = _read(project, "00_设定层/03_分章大纲.md")
    rows, malformed = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not re.match(r"^\|\s*K\d+", line):
            continue
        cells = [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"K\d{4}", cells[0]) or not cells[1].isdigit():
            malformed.append("第 %d 行" % number)
            continue
        rows.append({
            "id": cells[0],
            "display": int(cells[1]),
            "viewpoint": cells[2],
            "status": cells[-1],
            "line": line,
        })
    return text, rows, malformed


def _data_rows(text, prefix):
    return [line for line in text.splitlines()
            if re.match(r"^\|\s*%s\d+\s*\|" % re.escape(prefix), line)]


def _table_section(text, heading):
    if heading not in text:
        return ""
    return re.split(r"\n## ", text.split(heading, 1)[1])[0]


def inspect(project):
    project = os.path.abspath(project)
    errors, warnings, passed = [], [], []

    def check(name, condition, detail=""):
        (passed if condition else errors).append((name, detail or "无"))

    def warn(问题名, 通过名, condition, detail=""):
        """condition 为真 = 有问题。

        v2 两种情况共用同一个名字，于是健康项目会印出
        「✓ 事实记录引用了不存在的正文」这种自相矛盾的行，
        而这份输出正是要交给代理转述给用户的。所以两种情况各给一个名字。
        """
        if condition:
            warnings.append((问题名, detail or "无"))
        else:
            passed.append((通过名, detail or "无"))

    if not os.path.isdir(project):
        return [("项目目录存在", project)], [], []

    core = None
    try:
        core = _load("v2_core")
    except Exception as exc:
        errors.append(("公共内核可载入", str(exc)))

    manifest = None
    if core:
        try:
            manifest = core.load_project(project, required=False)
            if manifest is None:
                warnings.append(("项目尚未迁移到 v2", "缺 project.json。请从新版母版运行 migrate"))
            else:
                check("project.json 结构合法", True)
                check("插件决定已经明确",
                      manifest.get("plugin_decision") in ("none", "selected"),
                      "当前为 %s" % manifest.get("plugin_decision"))
        except Exception as exc:
            errors.append(("project.json 结构合法", str(exc)))

    # v2 的清单漏了几份真正承重的文件（chapter-policy.json、代理执行协议、
    # project.json、事务与内核模块），缺了它们照样印「核心文件齐全」。
    required = [
        "novel.py", "project.json", "chapter-policy.json", "revision-policy.json", "_工具/修订.py",
        "_工具/引擎.py", "_工具/文风档.py",
        "AGENTS.md", "CLAUDE.md", "START_HERE.md", "项目配置.md",
        "00_设定层/01_固定设定.md", "00_设定层/02_风格样本.md",
        "00_设定层/03_分章大纲.md", "01_运行层/04_状态快照.md",
        "01_运行层/05_伏笔表.md", "01_运行层/06_事实记录.md",
        "01_运行层/06b_事实记录_已归档段.md",
        "01_运行层/07_章节卡_模板.md",
        "02_检查层/代理执行协议.md", "02_检查层/执行契约.md",
        "02_检查层/08_四遍检查提示词.md", "02_检查层/11_文风基线.md",
        "foundation-policy.json", "00_设定层/00_创作意图.md",
        "06_归档/开书决策记录.md", "_工具/开书.py", "_工具/题材手册.py", "_工具/重复.py", "_工具/定声.py",
        "02_检查层/13_已推翻判断表.md", "06_归档/流程审计.md",
        "04_题材插件/plugin-registry.json",
        "_工具/专名表.txt", "_工具/排除表.py", "_工具/模块表.py",
        "_工具/提交包.py", "_工具/落盘.py", "_工具/读取包.py",
        "_工具/章节卡.py", "_工具/v2_core.py", "_工具/事务.py",
        "_工具/封段.py", "_工具/状态.py", "_工具/文风.py", "_工具/novel.py",
        "_工具/AI腔词表.txt",
    ]
    missing = [rel for rel in required if not os.path.isfile(os.path.join(project, rel))]
    check("核心文件齐全", not missing, "缺 " + "、".join(missing))

    mother_files = [rel for rel in ("_工具/我是母版.txt", "_工具/母版禁词.txt",
                                    "_工具/母版检查.py", "_候选_README.md")
                    if os.path.exists(os.path.join(project, rel))]
    check("项目不含母版或候选说明残留", not mother_files, "发现 " + "、".join(mother_files))

    outline_text, rows, malformed = _outline(project)
    check("分章大纲行格式有效", not malformed, "格式错误 " + "、".join(malformed))
    ids = [row["id"] for row in rows]
    displays = [row["display"] for row in rows]
    duplicate_ids = sorted(kid for kid, count in Counter(ids).items() if count > 1)
    duplicate_displays = sorted(number for number, count in Counter(displays).items() if count > 1)
    check("永久 ID 唯一", not duplicate_ids, "重复 " + "、".join(duplicate_ids))
    check("展示章号唯一", not duplicate_displays,
          "重复 " + "、".join(str(x) for x in duplicate_displays))
    order = [row["display"] for row in rows]
    check("大纲展示章号严格递增",
          all(a < b for a, b in zip(order, order[1:])), "顺序 " + repr(order[:20]))
    total = max(displays) if displays else 0

    body_paths = sorted(glob.glob(os.path.join(project, "05_正文", "K*.md")))
    body_ids = []
    invalid_names = []
    for path in body_paths:
        name = os.path.basename(path)
        if re.fullmatch(r"K\d{4}\.md", name):
            body_ids.append(name[:-3])
        else:
            invalid_names.append(name)
    check("正文文件名使用四位永久 ID", not invalid_names, "错误 " + "、".join(invalid_names))
    missing_outline = sorted(set(body_ids) - set(ids))
    check("每份正文都在大纲中登记", not missing_outline, "未登记 " + "、".join(missing_outline))
    written = {row["id"] for row in rows if "初稿" in row["status"] or "定稿" in row["status"]}
    missing_body = sorted(written - set(body_ids))
    check("大纲标为已写的章节都有正文", not missing_body, "缺 " + "、".join(missing_body))

    finalized = [row for row in rows if "已定稿" in row["status"]]
    finalized_ids = {row["id"] for row in finalized}
    header_finalized, bad_headers, dirty = set(), [], []
    process_marks = [
        r"(?<![A-Za-z0-9])K\d{4}(?![A-Za-z0-9])",
        r"【[^】\n]{0,12}(?:代拟|AI|作者推断|版本|梗概|场景卡|提交包)[^】\n]{0,12}】",
        r"^\s*(?:模式|版本|永久\s*ID)\s*[：:]",
    ]
    identity_errors = []
    row_by_id = {row['id']: row for row in rows}
    historical_before = (manifest or {}).get('archive_required_from', '')
    migrated = bool((manifest or {}).get('migrated_from'))
    legacy_headers = []
    try:
        card_tool = _load('章节卡')
    except Exception as exc:
        card_tool = None
        errors.append(('章节卡校验器可载入', str(exc)))
    for path in body_paths:
        kid = os.path.basename(path)[:-3]
        text = _read(project, "05_正文/" + os.path.basename(path))
        row = row_by_id.get(kid, {})
        # 只兼容显式迁移项目的旧永久 ID；不能用调换展示顺序放宽新章。
        legacy_header = bool(migrated and re.fullmatch(r'K[0-9]{4}', historical_before)
                             and re.fullmatch(r'K[0-9]{4}', kid) and kid < historical_before)
        if core:
            identity_errors.extend(kid + '：' + error for error in core.body_header_errors(
                text, kid, row.get('display'), row.get('viewpoint'), row.get('status'), legacy=legacy_header))
            if legacy_header and core.body_header_errors(text, kid, row.get('display'), row.get('viewpoint'), row.get('status')):
                legacy_headers.append(kid)
        card = _read(project, '06_归档/章节卡_%s.md' % kid)
        if card and card_tool:
            identity_errors.extend(kid + ' 章卡：' + error for error in
                                   card_tool.identity_errors(card, kid, row.get('display')))
        first, body = (text.split("\n", 1) + [""])[:2]
        if "状态:已定稿" in first:
            header_finalized.add(kid)
        match = re.search(r"字数:(\d+)", first)
        if match:
            measured = len(re.sub(r"[\s#\-*>|]", "", body))
            if int(match.group(1)) != measured:
                bad_headers.append("%s 抬头 %s 实测 %d" % (kid, match.group(1), measured))
        for pattern in process_marks:
            hit = re.search(pattern, body, re.M)
            if hit:
                dirty.append("%s 含 %s" % (kid, hit.group(0)[:24]))
                break
    check("正文抬头字数与实测一致", not bad_headers, "；".join(bad_headers[:8]))
    check("正文文件头、章卡与大纲身份一致", not identity_errors, "；".join(identity_errors[:12]))
    if legacy_headers:
        warnings.append(('迁移旧章沿用原文件头，修订时补齐现行字段', '、'.join(legacy_headers[:12])))
    check("正文不含内部创作标记", not dirty, "；".join(dirty[:8]))
    mismatch = sorted(finalized_ids ^ header_finalized)
    check("大纲与正文的定稿状态一致", not mismatch, "不一致 " + "、".join(mismatch))

    facts = (_read(project, "01_运行层/06_事实记录.md") + "\n" +
             _read(project, "01_运行层/06b_事实记录_已归档段.md"))
    fact_ids = set(re.findall(r"^###\s*(K\d{4})\b", facts, re.M))
    check("已定稿正文都有事实记录", not (finalized_ids - fact_ids),
          "缺 " + "、".join(sorted(finalized_ids - fact_ids)))
    warn("事实记录引用了不存在的正文", "事实记录只引用已存在的正文",
         bool(fact_ids - set(body_ids)),
         "多出 " + "、".join(sorted(fact_ids - set(body_ids))))

    audit = _read(project, "06_归档/流程审计.md")
    audit_ids = {match.group(1) for match in
                 re.finditer(r"^\|\s*(K\d{4})\s*\|[^\n]*(?:完成|未触发|跳过)", audit, re.M)}
    check("已定稿正文都有流程审计", not (finalized_ids - audit_ids),
          "缺 " + "、".join(sorted(finalized_ids - audit_ids)))

    snapshot = _read(project, "01_运行层/04_状态快照.md")
    snapshot_match = re.search(r"^>\s*状态[：:].*更新至\s+(K\d{4})", snapshot, re.M)
    expected_snapshot = max(finalized, key=lambda row: row["display"])["id"] if finalized else "K0000"
    check("状态快照抬头存在", bool(snapshot_match))
    if snapshot_match:
        check("状态快照推进到最新定稿章",
              snapshot_match.group(1) == expected_snapshot,
              "快照 %s，最新定稿 %s" % (snapshot_match.group(1), expected_snapshot))

    seeds = _read(project, "01_运行层/05_伏笔表.md")
    seed_rows = _data_rows(seeds, "F")
    bad_seed_rows = []
    for line in seed_rows:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[1] or not re.search(r"K\d{4}", cells[2]):
            bad_seed_rows.append(cells[0] if cells else line[:20])
        references = re.findall(r"K\d{4}", line)
        unknown = [kid for kid in references if kid not in ids]
        if unknown:
            bad_seed_rows.append("%s 引用 %s" % (cells[0], "、".join(unknown)))
    check("伏笔数据行具备内容、埋设章和有效引用",
          not bad_seed_rows, "问题 " + "；".join(bad_seed_rows[:8]))

    if manifest:
        try:
            plugin = _load("插件")
            plugin_errors = []
            for plugin_id in manifest.get("enabled_plugins", []):
                good, detail = plugin.verify(project, plugin_id)
                if not good:
                    plugin_errors.extend("%s  %s" % (plugin_id, item) for item in detail)
            check("已启用插件按自身声明完整安装",
                  not plugin_errors, "；".join(plugin_errors[:12]))
        except Exception as exc:
            errors.append(("插件声明可核验", str(exc)))

    if manifest and finalized:
        baseline = manifest.get("archive_required_from")
        display_by_id = {row["id"]: row["display"] for row in rows}
        baseline_display = display_by_id.get(baseline)
        if baseline_display is None:
            try:
                baseline_display = int(str(baseline)[1:])
            except Exception:
                baseline_display = 10 ** 9
        missing_cards, missing_synopses = [], []
        archive_dir = os.path.join(project, "06_归档")
        archive_names = os.listdir(archive_dir) if os.path.isdir(archive_dir) else []
        synopsis_by_id = {}
        for name in archive_names:
            match = re.match(r'^梗概_(K\d{4})', name)
            if match:
                synopsis_by_id.setdefault(match.group(1), []).append(name)
        for row in finalized:
            if row["display"] < baseline_display:
                continue
            kid = row["id"]
            if not os.path.isfile(os.path.join(project, "06_归档", "章节卡_%s.md" % kid)):
                missing_cards.append(kid)
            synopsis = [name for name in synopsis_by_id.get(kid, [])
                        if os.path.isfile(os.path.join(project, "06_归档", name))
                        and _read(project, "06_归档/" + name).strip()]
            if not synopsis:
                missing_synopses.append(kid)
        check("归档基线之后的定稿章都有章节卡",
              not missing_cards, "缺 " + "、".join(missing_cards))
        check("归档基线之后的定稿章都有梗概",
              not missing_synopses, "缺 " + "、".join(missing_synopses))

    graph = os.path.join(project, "图谱.html")
    if finalized:
        if not os.path.isfile(graph):
            warnings.append(("图谱尚未生成", "运行 python3 _工具/生成图谱.py <项目>"))
        else:
            graph_time = os.path.getmtime(graph)
            tracked = graph_tracked_paths(project, bool(manifest))
            tolerance = _load("v2_core").GRAPH_STALE_TOLERANCE
            stale = [rel for rel in tracked if os.path.isfile(os.path.join(project, rel))
                     and os.path.getmtime(os.path.join(project, rel)) > graph_time + tolerance]
            warn("图谱比账本旧", "图谱不比账本旧", bool(stale), "较新 " + "、".join(stale))

    if manifest:
        state = core.init_state(manifest) if core else "legacy"
        block = manifest.get("initialization")
        check("开书状态字段结构合法",
              block is None or (isinstance(block, dict) and block.get("status") in
                                ("draft", "confirmed", "legacy")),
              "initialization = %r" % (block,))
        if state == "confirmed":
            check("已确认开书的项目保存了批准摘要与合作方式",
                  bool((block or {}).get("approved_sha256")) and
                  (block or {}).get("mode") in (None,) + tuple(core.COOP_MODES),
                  "摘要 %s ／ 模式 %s" % ((block or {}).get("approved_sha256"),
                                          (block or {}).get("mode")))
            decisions = _read(project, "06_归档/开书决策记录.md")
            pending = [line for line in decisions.splitlines()
                       if re.match(r"^\|\s*D\d{2,}\s*\|", line) and line.rstrip().endswith("待定 |")]
            check("已确认开书的项目没有仍处于待定的基础决定",
                  not pending, "仍有 %d 条待定" % len(pending))
        elif state == "draft" and finalized:
            errors.append(("开书状态与实际内容矛盾",
                           "状态是 draft，却已有 %d 章定稿。运行 sync 或 foundation 修正"
                           % len(finalized)))
        elif state == "legacy":
            warnings.append(("项目未经 3.3 开书确认",
                             "legacy 可以继续写；补做用 novel.py foundation --prepare"))

    # ── 4.1 题材文风档 ─────────────────────────────────
    try:
        voice = _load("文风档")
        pid, chosen = voice.当前档(project)
        rel, text = voice.档正文(project)
        check("文风档在登记表中且文件可读", rel is not None and text is not None,
              "voice_profile=%s" % pid)
        warn("尚未选择文风档，按文学克制处理", "已选择文风档", not chosen,
             "novel.py voice --profile <档>")
    except Exception as exc:
        errors.append(("文风档模块可载入", str(exc)))

    # ── 4.0 读者引擎层：只提醒，不阻断。引擎卡填好才启用，旧项目照常可写。
    try:
        engine = _load("引擎")
    except Exception as exc:
        engine = None
        errors.append(("引擎层模块可载入", str(exc)))
    if engine and manifest:
        engine_text = engine.读(project, engine.ENGINE_REL)
        if engine_text is None:
            warn("未建立读者引擎卡", "读者引擎卡存在", bool(finalized),
                 "旧项目运行 sync 补入模板，再用 novel.py engine --prepare 填写")
        else:
            missing = engine.引擎卡检查(engine_text)
            warn("读者引擎卡未填写，引擎层未启用", "读者引擎卡已填写，引擎层启用",
                 bool(missing), "；".join(missing[:4]) or "已启用")
            if not missing:
                ledger = engine.读(project, engine.LEDGER_REL)
                if ledger is None:
                    errors.append(("引擎层启用时悬念账存在", "缺 %s" % engine.LEDGER_REL))
                else:
                    n = engine.活动数(engine.悬念账(ledger))
                    # 开篇几章还在铺问题，定稿满三章以后才按 3—5 个提醒
                    if engine.引擎模式(engine_text) == '升级对抗':
                        warn("活动悬念不在 3—5 个", "活动悬念 3—5 个",
                             len(finalized) >= 3 and not 3 <= n <= 5, "当前 %d 个" % n)
                if finalized:
                    order = engine.大纲序(project)
                    last = sorted((row["id"] for row in finalized), key=lambda k: order.get(k, 0))[-1]
                    arc = engine.所属弧(project, last, order)
                    warn("最新定稿章不在任何弧卡范围内", "最新定稿章有所属弧卡",
                         arc is None, "%s；用 novel.py arc --new 建弧卡" % last)

    # ── 5.0 人物声音层：只提醒，不阻断。声音表填了才启用，旧项目照常可写。
    try:
        voice_mod = _load("人物声音")
    except Exception as exc:
        voice_mod = None
        errors.append(("人物声音模块可载入", str(exc)))
    if voice_mod and manifest:
        vpath = os.path.join(project, voice_mod.VOICE_REL)
        vtext = None
        if os.path.isfile(vpath):
            with io.open(vpath, encoding="utf-8") as fh:
                vtext = fh.read()
        if vtext is None:
            warn("未建立人物声音表", "人物声音表存在", bool(finalized),
                 "旧项目运行 sync 补入模板；出场满三章的角色各补四行")
        else:
            vmiss = voice_mod.声音表检查(vtext)
            n = len([1 for _n, _r in voice_mod.声音表解析(vtext) if _r])
            # 一章未定稿时谁会出场满三章还不知道，不提醒；有定稿了空表才是问题。
            warn("人物声音表尚未填写，声音层未启用", "人物声音表已填写，声音层启用",
                 bool(vmiss) and bool(finalized),
                 "；".join(vmiss[:2]) if vmiss else "已登记 %d 人" % n)

    style_text = _read(project, "02_检查层/11_文风基线.md")
    if style_text:
        import 文风
        style_state, style_note = 文风.基线提醒(project)
        warn('文风基线' + style_state, '文风基线来源一致',
             bool(style_note) and len(finalized) >= 1, style_note)
    else:
        warnings.append(("缺 02_检查层/11_文风基线.md", "从新版母版 sync 补入"))

    candidate_root = os.path.join(project, "_候选")
    pending = []
    if os.path.isdir(candidate_root):
        pending = [name for name in os.listdir(candidate_root)
                   if (name in ('INIT', 'REVISE') or re.fullmatch(r'K\d{4}(?:-K\d{4})?', name))
                   and os.path.isdir(os.path.join(candidate_root, name))]
    warn("候选提交仍未处理", "没有悬着的候选提交", bool(pending),
         "待处理 " + "、".join(sorted(pending)))

    print("=" * 72)
    print("项目体检  全书 %d 章  正文 %d 份  已定稿 %d 章" %
          (total, len(body_ids), len(finalized_ids)))
    print("=" * 72)
    for name, detail in errors:
        print("✗ 错误  %s  %s" % (name, detail))
    for name, detail in warnings:
        print("△ 注意  %s  %s" % (name, detail))
    for name, _ in passed:
        print("✓ %s" % name)
    print("=" * 72)
    print("错误 %d ／ 注意 %d ／ 通过 %d" %
          (len(errors), len(warnings), len(passed)))
    print("机器体检只证明结构与记录自洽，不证明正文内容正确或好看。")
    return errors, warnings, passed


def main(argv=None):
    parser = argparse.ArgumentParser(description="小说项目体检")
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--template", action="store_true")
    args = parser.parse_args(argv)
    project = os.path.abspath(args.project)
    if args.template:
        try:
            return _load("母版检查").检查(project)
        except Exception as exc:
            print("✗ 母版检查无法运行  %s" % exc)
            return 2
    errors, _, _ = inspect(project)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
