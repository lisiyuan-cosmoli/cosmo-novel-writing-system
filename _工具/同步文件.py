#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 system-manifest.json 同步母版拥有的共享文件。"""
from __future__ import print_function

import argparse
import json
import os

import v2_core as core
import 事务


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEM = core.load_json(os.path.join(ROOT, "system-manifest.json"), {}) or {}
白名单 = list(SYSTEM.get("sync_files", []))
# 种子文件：**只在目标缺失时补入，存在就原样保留**。
# 项目级词表、豁免表这类文件属于用户数据，放进普通同步清单会把积累的内容覆盖掉。
种子 = list(SYSTEM.get("seed_files", []))
混合 = list(SYSTEM.get("merge_files", []))


def _区块范围(text, spec, label):
    """只接受唯一、成对且顺序正确的标记；损坏不能当成空基线。"""
    起, 止 = spec.get("begin"), spec.get("end")
    if not isinstance(起, str) or not isinstance(止, str) or not 起 or not 止 or 起 == 止:
        raise core.ProjectError("%s 的区块标记声明无效" % label)
    if text.count(起) != 1 or text.count(止) != 1:
        raise core.ProjectError("%s 的区块标记必须各有且仅有一个；请核对缺失或重复标记" % label)
    start, end = text.index(起), text.index(止)
    if start + len(起) > end:
        raise core.ProjectError("%s 的区块标记顺序错误" % label)
    return start, end + len(止)


def _合并一份(project, spec):
    """母版内容为准，但把项目里的指定区块原样搬回去。

    `11_文风基线.md` 是混合文件：上半部分是母版的生成约束，中间那块是
    `style --baseline` 从**本书语料**算出来的基线。整份同步会把作者算好的
    基线盖成"未建立"——这类文件既不能当母版文件覆盖，也不能当用户文件不管。
    """
    rel = spec["path"]
    源 = core.read_text(os.path.join(ROOT, rel))
    现 = core.read_text(os.path.join(project, rel))
    if 源 is None:
        raise core.ProjectError("母版缺 %s" % rel)
    源起, 源止 = _区块范围(源, spec, "母版 " + rel)
    if 现 is None:
        return 源.encode("utf-8"), "新增"
    现起, 现止 = _区块范围(现, spec, "项目 " + rel)
    块 = 现[现起:现止]
    合 = 源[:源起] + 块 + 源[源止:]
    说明 = "保住项目区块"
    if 合 == 现:
        return None, "无差异"
    return 合.encode("utf-8"), 说明


def _混合差异(project, keep=()):
    out = []
    for spec in 混合:
        if spec["path"] in keep:
            continue
        data, 说明 = _合并一份(project, spec)
        if data is not None:
            out.append((spec["path"], data, 说明))
    return out


def _插件托管差异(project, project_data):
    """已启用插件里、母版托管的文件与母版模板的差异。

    v3.4 只同步 04_题材插件/_包/.../templates/ 下的模板，**不碰项目里已经装好的
    02_检查层/插件/*.md**。实测从 v3.3 同步到 v3.4，新版逐章题材检查一个字都
    没进旧项目，而 verify 还报成功——一次看起来成功的伪升级。

    返回 [(相对路径, 插件ID, 新内容, 状态)]，状态为 干净 或 已改过。
    """
    registry = core.load_json(os.path.join(ROOT, "04_题材插件", "plugin-registry.json"))
    by_id = {x.get("id"): x for x in (registry or {}).get("plugins", []) if isinstance(x, dict)}
    记录 = project_data.get("plugin_files") or {}
    out = []
    for pid in project_data.get("enabled_plugins", []):
        entry = by_id.get(pid)
        if not entry or not entry.get("manifest"):
            continue
        包根 = os.path.dirname(os.path.join(ROOT, "04_题材插件", entry["manifest"]))
        manifest = core.load_json(os.path.join(ROOT, "04_题材插件", entry["manifest"]))
        if not isinstance(manifest, dict):
            continue
        for item in manifest.get("files", []):
            if item.get("owner") != "system":
                continue
            rel = item["target"]
            if not core.safe_relative(rel):
                continue
            新 = core.read_bytes(os.path.join(包根, item["source"]))
            现 = core.read_bytes(os.path.join(project, rel))
            if 新 is None or 现 == 新:
                continue
            记 = (记录.get(pid) or {}).get(rel)
            if not 记:
                状态 = "无记录"          # 3.5 之前装的，判不出改没改，一律先归档
            elif 现 is not None and core.sha256_bytes(现) == 记:
                状态 = "干净"
            else:
                状态 = "已改过"
            out.append((rel, pid, 新, 状态))
    return sorted(out)


def _deny_words():
    text = core.read_text(os.path.join(ROOT, "_工具", "母版禁词.txt"), "") or ""
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def _precheck(project):
    errors = []
    project = os.path.abspath(project)
    if project == ROOT:
        errors.append("源与目标不能相同")
    if not core.is_template(ROOT):
        errors.append("源目录没有母版标记")
    if not os.path.isdir(project):
        errors.append("目标目录不存在")
        return errors
    if core.is_template(project):
        errors.append("目标看起来是母版")
    try:
        data = core.load_project(project)
        if data.get("schema_version") != SYSTEM.get("schema_version"):
            errors.append("目标结构版本与母版不一致，请先迁移")
    except Exception as exc:
        errors.append("目标不像一个 v2 项目  %s" % exc)
    if len(白名单) != len(set(白名单)):
        errors.append("system-manifest.json 的 sync_files 有重复路径")
    重叠 = set(白名单) & set(种子)
    if 重叠:
        errors.append("同一路径不能既是 sync_files 又是 seed_files：" + "、".join(sorted(重叠)))
    for rel in 种子:
        if not core.safe_relative(rel):
            errors.append("种子清单含非法路径 %r" % rel)
        elif not os.path.isfile(os.path.join(ROOT, rel)):
            errors.append("种子源文件缺失 %s" % rel)
    for rel in 白名单:
        if not core.safe_relative(rel):
            errors.append("同步清单含非法路径 %r" % rel)
        elif not os.path.isfile(os.path.join(ROOT, rel)):
            errors.append("同步源文件缺失 %s" % rel)
    for spec in 混合:
        rel = spec.get("path")
        if not core.safe_relative(rel or ""):
            errors.append("merge_files 含非法路径 %r" % rel)
            continue
        源 = core.read_text(os.path.join(ROOT, rel))
        if 源 is None:
            errors.append("混合文件源缺失 %s" % rel)
        else:
            try:
                _区块范围(源, spec, "母版 " + rel)
            except core.ProjectError as exc:
                errors.append(str(exc))
    if set(x.get("path") for x in 混合) & set(白名单):
        errors.append("同一路径不能既是 sync_files 又是 merge_files")

    words = _deny_words()
    for rel in 白名单:
        text = core.read_text(os.path.join(ROOT, rel))
        if text is None:
            continue
        hits = [word for word in words if word in text]
        if hits:
            errors.append("同步文件 %s 含母版禁词 %s" % (rel, "、".join(hits[:4])))
    return errors


def _seed_diff(project):
    """只列出目标缺失的种子文件。已存在的一律不动。"""
    return [rel for rel in 种子 if not os.path.exists(os.path.join(project, rel))]


def _diff(project):
    rows = []
    for rel in 白名单:
        source = os.path.join(ROOT, rel)
        target = os.path.join(project, rel)
        source_hash = core.sha256_file(source)
        target_hash = core.sha256_file(target)
        if source_hash != target_hash:
            rows.append((rel, "新增" if target_hash is None else "更新",
                         source_hash, target_hash))
    return rows


def _custom_plugins(project, data):
    registry = core.load_json(os.path.join(ROOT, '04_题材插件/plugin-registry.json')) or {}
    preserved = set()
    for entry in registry.get('plugins', []):
        pid, rel = entry['id'], '04_题材插件/' + entry['manifest']
        local = core.load_json(os.path.join(project, rel), {}) or {}
        source = core.load_json(os.path.join(ROOT, rel), {}) or {}
        installed = (data.get('plugin_version') or {}).get(pid, '')
        # Custom package versions are independent of the core release. Never replace with an older stock package.
        if (local.get('version') != source.get('version') and
                (any(mark in str(local.get('version', '')) for mark in ('-book', '-local', '+')) or '-book' in installed or '-local' in installed)):
            preserved.add(pid)
    return preserved


def _local_conflicts(project, data, rows):
    baseline = data.get('system_file_hashes') or SYSTEM.get('previous_sync_baselines', {}).get(data.get('system_version'), {})
    conflicts = []
    for rel, action, new, current in rows:
        if current is None:
            continue
        old = baseline.get(rel)
        if old is None or old != current:
            conflicts.append(rel)
    return conflicts


def _最终插件版本(project, project_data, shared_changes, custom):
    """从本次保留/更新决策后的项目包登记版本，不依赖检查文件是否变化。"""
    def read_json(rel):
        raw = shared_changes[rel] if rel in shared_changes else core.read_bytes(os.path.join(project, rel))
        try:
            value = json.loads(raw.decode("utf-8"))
        except (AttributeError, ValueError, UnicodeError):
            raise core.ProjectError("无法核对同步后的插件文件 " + rel)
        if not isinstance(value, dict):
            raise core.ProjectError("同步后的插件文件格式错误 " + rel)
        return value

    if not project_data.get("enabled_plugins"):
        return {}
    registry = read_json("04_题材插件/plugin-registry.json")
    by_id = {x.get("id"): x for x in registry.get("plugins", []) if isinstance(x, dict)}
    versions = {}
    for pid in project_data.get("enabled_plugins", []):
        entry = by_id.get(pid) or {}
        if not core.safe_relative(entry.get("manifest", "")):
            raise core.ProjectError("同步后的注册表缺少已安装插件 " + pid)
        manifest = read_json("04_题材插件/" + entry["manifest"])
        version = manifest.get("version")
        if manifest.get("id") != pid or not isinstance(version, str) or not version:
            raise core.ProjectError("同步后的插件包身份或版本无效 " + pid)
        # 本书定制版本不能由母版重新登记。它仍需与本书自己的包相符。
        if pid in custom and (project_data.get("plugin_version") or {}).get(pid) != version:
            raise core.ProjectError("本书插件登记版本与本书包不一致，请先核对 " + pid)
        versions[pid] = version
    return versions


def main(argv=None):
    parser = argparse.ArgumentParser(description="同步母版共享文件")
    parser.add_argument("project")
    parser.add_argument("--check", action="store_true", help="只显示差异")
    parser.add_argument('--keep-local', action='append', default=[], help='明确保留有本地修改的共享文件；不覆盖为母版版本')
    parser.add_argument('--replace-local', action='append', default=[], help='经审阅后明确用母版替换指定本地修改；已安装检查旧版仍归档')
    args = parser.parse_args(argv)
    project = os.path.abspath(args.project)
    errors = _precheck(project)
    if errors:
        print("✗ 预检查不通过，未写任何文件")
        for item in errors:
            print("  · " + item)
        return 1
    watched = set(白名单 + 种子 + [x['path'] for x in 混合] + ['project.json'])
    watched.update(x[0] for x in _插件托管差异(project, core.load_project(project)))
    expected = {rel: core.sha256_file(os.path.join(project, rel)) for rel in watched}
    rows = _diff(project)
    seeds = _seed_diff(project)
    project_data = core.load_project(project)
    custom = _custom_plugins(project, project_data)
    registry = core.load_json(os.path.join(ROOT, '04_题材插件/plugin-registry.json')) or {}
    custom_dirs = ['04_题材插件/' + os.path.dirname(x['manifest']) + '/' for x in registry.get('plugins', []) if x['id'] in custom]
    custom_manuals = {'04_题材插件/' + x['name'] + '.md' for x in registry.get('plugins', []) if x['id'] in custom}
    keep = set(args.keep_local)
    replace_local = set(args.replace_local)
    if keep & replace_local:
        print('✗ 同一路径不能同时保留和替换')
        return 1
    if any(rel not in watched - {'project.json'} for rel in keep | replace_local):
        print('✗ --keep-local / --replace-local 只能指定共享文件清单中的路径；项目登记由同步事务维护')
        return 1
    preserved = sorted(keep | {row[0] for row in rows if row[0] in custom_manuals or any(row[0].startswith(d) for d in custom_dirs)})
    rows = [row for row in rows if row[0] not in preserved]
    seeds = [rel for rel in seeds if rel not in keep]
    conflicts = [rel for rel in _local_conflicts(project, project_data, rows) if rel not in replace_local]
    # Missing baselines are also conflicts; an archive is not a substitute for preserving behavior.
    插件行 = [row for row in _插件托管差异(project, project_data) if row[1] not in custom and row[0] not in keep]
    conflicts.extend(row[0] for row in 插件行 if row[3] in ('已改过', '无记录') and row[0] not in replace_local)
    for pid in sorted(custom):
        print('  保留本书插件 ' + pid + '（包、版本、逐章检查及用户数据保持）')
    for rel in preserved:
        print('  保留本地修改 ' + rel)
    if conflicts:
        print('✗ 检测到共享文件本地修改：' + '、'.join(conflicts))
        print('先合并到受审维护版本，或逐项 --keep-local 明确保留；审阅后放弃本地改动可 --replace-local 指定路径。未写任何文件。')
        return 1
    shared_changes = {rel: core.read_bytes(os.path.join(ROOT, rel)) for rel, _, _, _ in rows}
    try:
        混合行 = _混合差异(project, keep)
        插件版本 = _最终插件版本(project, project_data, shared_changes, custom)
    except core.ProjectError as exc:
        print("✗ 预检查不通过，未写任何文件  %s" % exc)
        print("若是混合文件标记问题，请先核对标记；保留整份本地文件可逐项使用 --keep-local。")
        return 1
    版本登记变化 = any((project_data.get("plugin_version") or {}).get(pid) != version
                       for pid, version in 插件版本.items())
    target_version = SYSTEM.get("system_version")
    version_change = project_data.get("system_version") != target_version
    # 旧项目没有开书状态。按实际内容推断：在写的标 legacy，空的标 draft。
    # 绝不静默标 confirmed——那等于替用户签字。
    init_block = None
    if not isinstance(project_data.get("initialization"), dict):
        init_block = core.infer_init_block(project)
    if not rows and not seeds and not version_change and not init_block and not 插件行 and not 混合行 and not 版本登记变化:
        print("✓ 共享文件无差异")
        if 种子:
            existing_seeds = sum(os.path.exists(os.path.join(project, rel)) for rel in 种子)
            print("  种子文件 %d 份已存在，保持原样未动。" % existing_seeds)
            if existing_seeds < len(种子):
                print("  另有 %d 份缺失种子按 --keep-local 保留现状，未补入。" % (len(种子) - existing_seeds))
        return 0
    print("将变化 %d 份" % (len(rows) + len(seeds) + len(插件行) + len(混合行)
                            + (1 if version_change else 0) + (1 if init_block else 0)
                            + (1 if 版本登记变化 else 0)))
    for rel, action, source_hash, target_hash in rows:
        print("  %-4s %-48s %s ← %s" %
              (action, rel, source_hash[:12], (target_hash or "无")[:12]))
    for rel in seeds:
        print("  %-4s %-48s %s" % ("补入", rel, "缺失，写入空模板；已存在的种子文件不会被动"))
    保留 = [rel for rel in 种子 if os.path.exists(os.path.join(project, rel))]
    for rel in 保留:
        print("  %-4s %-48s %s" % ("保留", rel, "已存在，内容不动"))
    for rel, _data, 说明 in 混合行:
        print("  %-4s %-48s %s" % ("合并", rel, "母版内容更新，%s" % 说明))
    for rel, pid, _新, 状态 in 插件行:
        说明 = {
            "干净": "插件 %s 的母版托管文件，安装后没改过，直接更新" % pid,
            "已改过": "插件 %s 的母版托管文件，你改过 → 旧版先归档再更新" % pid,
            "无记录": "插件 %s 装于 3.5 之前，无安装记录 → 旧版先归档再更新" % pid,
        }[状态]
        print("  %-4s %-48s %s" % ("升级" if 状态 == "干净" else "归档并升级", rel, 说明))
    if version_change:
        print("  %-4s %-48s %s ← %s" %
              ("升级", "project.json / system_version", target_version,
               project_data.get("system_version", "无")))
    if 版本登记变化:
        for pid, version in sorted(插件版本.items()):
            old = (project_data.get("plugin_version") or {}).get(pid)
            if old != version:
                print("  登记 project.json / plugin_version / %s  %s ← %s（以最终本项目包为准）" % (pid, version, old or "无"))
    if init_block:
        print("  %-4s %-48s %s" %
              ("补入", "project.json / initialization",
               "%s（%s）" % (init_block["status"],
                            "已有正文，可以继续写" if init_block["status"] == "legacy"
                            else "空项目，需要先完成 foundation")))
    if args.check:
        print("✓ --check 只报告，未写任何文件")
        return 0

    changes = dict(shared_changes)
    for rel in seeds:
        changes[rel] = core.read_bytes(os.path.join(ROOT, rel))
    for rel, data, _说明 in 混合行:
        changes[rel] = data
    归档根 = os.path.join("06_归档", "插件", "同步归档",
                          core.utc_now().replace(":", "")).replace(os.sep, "/")
    托管新哈希 = {}
    for rel, pid, 新, 状态 in 插件行:
        if 状态 in ("已改过", "无记录"):
            旧 = core.read_bytes(os.path.join(project, rel))
            if 旧 is not None:
                changes[os.path.join(归档根, rel).replace(os.sep, "/")] = 旧
        changes[rel] = 新
        托管新哈希.setdefault(pid, {})[rel] = core.sha256_bytes(新)
    if version_change or init_block or 托管新哈希 or rows or seeds or 混合行 or 版本登记变化:
        updated = dict(project_data)
        updated["system_version"] = target_version
        if init_block:
            updated["initialization"] = init_block
        if 托管新哈希:
            表 = dict(updated.get("plugin_files") or {})
            for pid, 哈希 in 托管新哈希.items():
                表[pid] = dict(表.get(pid) or {}, **哈希)
            updated["plugin_files"] = 表
        if 插件版本:
            updated["plugin_version"] = dict(updated.get("plugin_version") or {}, **插件版本)
        hashes = dict(updated.get('system_file_hashes') or SYSTEM.get('previous_sync_baselines', {}).get(project_data.get('system_version'), {}))
        for rel in 白名单:
            if rel not in preserved and rel not in custom_manuals and not any(rel.startswith(d) for d in custom_dirs):
                hashes[rel] = core.sha256_file(os.path.join(ROOT, rel))
        updated['system_file_hashes'] = hashes
        updated['updated_at'] = core.utc_now()
        changes["project.json"] = (json.dumps(updated, ensure_ascii=False, indent=2,
                                               sort_keys=True) + "\n").encode("utf-8")

    def validate():
        bad = [rel for rel, _, _, _ in rows
               if core.sha256_file(os.path.join(ROOT, rel)) !=
               core.sha256_file(os.path.join(project, rel))]
        bad.extend(rel for rel, _pid, 新, _s in 插件行
                   if core.read_bytes(os.path.join(project, rel)) != 新)
        bad.extend(rel for rel, data, _s in 混合行
                   if core.read_bytes(os.path.join(project, rel)) != data)
        try:
            after = core.load_project(project)
            if after.get("system_version") != target_version:
                bad.append("project.json / system_version")
            if init_block and not isinstance(after.get("initialization"), dict):
                bad.append("project.json / initialization")
            # 只核对本次同步的包及登记一致性；不以本书用户内容缺项阻断系统迁移。
            actual_versions = _最终插件版本(project, after, {}, custom)
            for pid, version in 插件版本.items():
                if actual_versions.get(pid) != version or (after.get("plugin_version") or {}).get(pid) != version:
                    bad.append("project.json / plugin_version / " + pid)
        except Exception:
            bad.append("project.json")
        return not bad, "写后哈希不一致 " + "、".join(bad)

    def guarded_plan():
        for rel, digest in expected.items():
            if core.sha256_file(os.path.join(project, rel)) != digest:
                raise core.ProjectError('同步规划后目标发生变化，未写入，请重新检查：' + rel)
        return {'changes': changes, 'label': 'sync system ' + str(target_version),
                'metadata': {'system_version': target_version, 'preserved_local': preserved, 'preserved_plugins': sorted(custom)}}

    try:
        tx = 事务.apply_changes(
            project,
            changes,
            "sync system %s" % SYSTEM.get("system_version", "unknown"),
            validator=validate,
            fault_after=(os.environ.get("NOVEL_SYNC_FAIL_AFTER")
                         if 事务._faults_enabled() else None),
            metadata={"system_version": SYSTEM.get("system_version")},
            plan=guarded_plan,
        )
    except Exception as exc:
        print("✗ 同步失败  %s" % exc)
        if os.path.lexists(os.path.join(project, ".novel", "transaction.json")):
            print("仍有待处理事务记录；请先核对 doctor/status 的事务状态，不要视为已经恢复。")
        return 1
    print("✓ 同步完成，SHA-256 复核通过，事务 %s" % tx["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
