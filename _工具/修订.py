#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全局修订：显式选文件、预览差异、绑定全项目基线、整笔事务提交。"""
import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

import v2_core as core
import 事务
import 落盘

CANDIDATE = '_候选/REVISE'
REVIEW = '_候选/REVISE_关联核对.json'


def review_bytes(project):
    if core.path_has_symlink(project, REVIEW):
        raise core.ProjectError('关联核对文件不能是符号链接')
    path = os.path.join(project, REVIEW)
    if os.path.lexists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
        raise core.ProjectError('关联核对必须是普通文件')
    return core.read_bytes(path)


def impact_groups(project, entries):
    """按文件职责保守列出影响范围，不猜测自然语言中的因果关系。"""
    changed = [item for item in entries if core.read_bytes(os.path.join(project, item['path'])) != item['data']]
    affected, global_change = set(), False
    for item in changed:
        rel = item['path']
        match = re.fullmatch(r'05_正文/(K[0-9]{4})\.md', rel)
        if match:
            before = core.read_text(os.path.join(project, rel), '')
            after = item['data'].decode('utf-8')
            if before.partition('\n')[2] != after.partition('\n')[2]:
                affected.add(match.group(1))
        elif rel.startswith(('00_设定层/', '01_运行层/')):
            global_change = True
    if not affected and not global_change:
        return []
    planned = {item['path'] for item in entries}
    def present(paths):
        return sorted({rel for rel in paths if rel in planned or os.path.isfile(os.path.join(project, rel))})
    # 大纲的展示顺序决定后续章；无法解析时把全部正文列为待核对。
    outline = core.read_text(os.path.join(project, '00_设定层/03_分章大纲.md'), '')
    order = {m.group(1): int(m.group(2)) for m in re.finditer(
        r'^\|\s*(K[0-9]{4})\s*\|\s*([0-9]+)\s*\|', outline, re.M)}
    first = min((order.get(kid, -1) for kid in affected), default=-1)
    body_paths = present(['05_正文/' + name for name in os.listdir(os.path.join(project, '05_正文'))
                          if re.fullmatch(r'K[0-9]{4}\.md', name)] +
                         [rel for rel in planned if re.fullmatch(r'05_正文/K[0-9]{4}\.md', rel)])
    later = [rel for rel in body_paths if global_change or first < 0 or
             order.get(os.path.basename(rel)[:-3], first + 1) > first]
    archive = []
    for name in os.listdir(os.path.join(project, '06_归档')):
        match = re.match(r'(?:章节卡|梗概)_(K[0-9]{4})(?:_|\.)', name)
        if match and (global_change or match.group(1) in affected):
            archive.append('06_归档/' + name)
    exact, _ = allowed_paths(project)
    plugins = [rel for rel in exact if rel.startswith('00_设定层/插件/') or
               (rel.startswith(('01_运行层/', '06_归档/')) and rel not in
                core.load_json(os.path.join(project, 'revision-policy.json'))['mutable_files'])]
    groups = [
        ('事实与阶段摘要', ['01_运行层/06_事实记录.md', '01_运行层/06b_事实记录_已归档段.md']),
        ('当前状态与伏笔', ['01_运行层/04_状态快照.md', '01_运行层/05_伏笔表.md']),
        ('大纲与本次章卡梗概', ['00_设定层/03_分章大纲.md'] + archive),
        ('后续正文' if not global_change else '现有正文', later),
        ('插件用户资料', plugins),
    ]
    return [{'group': name, 'paths': present(paths)} for name, paths in groups if present(paths)]


def review_basis(project, entries):
    rows, _ = 落盘.候选摘要(project, 'REVISE', entries)
    return core.canonical_digest({'files': rows, 'baseline': baseline(project)})


def prepare_review(project):
    entries = collect(project)
    groups = impact_groups(project, entries)
    if not groups:
        print('本次没有正文内容或设定账本改动，无需关联核对。')
        return
    basis = review_basis(project, entries)
    old_bytes = review_bytes(project)
    old = core.load_json(os.path.join(project, REVIEW)) if old_bytes else None
    old_items = old.get('items') if isinstance(old, dict) else None
    if (isinstance(old, dict) and old.get('format') == 'novel-revision-review-v1'
            and old.get('basis') == basis and isinstance(old_items, list)
            and all(isinstance(item, dict) for item in old_items)
            and [{'group': item.get('group'), 'paths': item.get('paths')} for item in old_items] == groups):
        print('关联核对仍对应本次内容，保留已填写结论：' + REVIEW)
        return
    payload = {'format': 'novel-revision-review-v1', 'basis': basis,
               'scope': '保守列举文件职责与后续正文；不能证明语义一致或真人审阅',
               'items': [dict(group, status='待核对', note='') for group in groups]}
    core.safe_output_dir(project, '_候选')
    core.atomic_write_json(os.path.join(project, REVIEW), payload)
    print('已生成关联核对。阅读清单中的文件后，将各组 status 改为 已核对，并在 note 写明修改或保留理由。')
    print(REVIEW)
    if old_bytes:
        print('内容已改变，旧结论已失效，本次按新范围重新生成。')


def checked_review(project, entries):
    groups = impact_groups(project, entries)
    if not groups:
        return None
    data = review_bytes(project)
    if data is None:
        raise core.ProjectError('缺少关联核对。先运行 novel.py revise --review，再核对清单。')
    try:
        review = json.loads(data)
    except (ValueError, UnicodeError):
        raise core.ProjectError('关联核对 JSON 无法解析')
    if (not isinstance(review, dict) or review.get('format') != 'novel-revision-review-v1'
            or review.get('basis') != review_basis(project, entries)):
        raise core.ProjectError('关联核对已失效，候选或基线改变；运行 revise --review 重新生成')
    items = review.get('items')
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise core.ProjectError('关联核对清单格式不合法')
    if [{'group': item.get('group'), 'paths': item.get('paths')} for item in items] != groups:
        raise core.ProjectError('关联核对范围被改变，不能删除或换掉核对对象')
    for item in items:
        note = item.get('note')
        if (item.get('status') != '已核对' or not isinstance(note, str) or
                len(note.strip()) < 6 or any(word in note for word in ('待核对', '待确认', '待填写'))):
            raise core.ProjectError('关联核对未完成：' + item['group'] + '；须说明修改或保留的具体理由')
    return data


def allowed_paths(project):
    policy = core.load_json(os.path.join(project, 'revision-policy.json'))
    if (not isinstance(policy, dict) or policy.get('format') != 'novel-revision-policy'
            or policy.get('schema_version') != 1
            or not isinstance(policy.get('mutable_files'), list)
            or not isinstance(policy.get('patterns'), list)):
        raise core.ProjectError('修订白名单缺失或损坏，请先从母版 sync')
    exact = set(policy['mutable_files'])
    if not all(core.safe_relative(rel) for rel in exact):
        raise core.ProjectError('修订白名单含非法路径')
    patterns = [re.compile(pattern) for pattern in policy['patterns']]
    data = core.load_project(project)
    registry = core.load_json(os.path.join(project, '04_题材插件/plugin-registry.json'))
    if not isinstance(registry, dict) or not isinstance(registry.get('plugins'), list):
        raise core.ProjectError('插件注册表无法读取')
    by_id = {item.get('id'): item for item in registry['plugins'] if isinstance(item, dict)}
    for plugin_id in data.get('enabled_plugins', []):
        entry = by_id.get(plugin_id, {})
        rel = '04_题材插件/' + entry.get('manifest', '')
        if not core.safe_relative(rel):
            raise core.ProjectError('插件清单路径不合法')
        manifest = core.load_json(os.path.join(project, rel))
        if not isinstance(manifest, dict) or manifest.get('id') != plugin_id:
            raise core.ProjectError('已启用插件清单缺失或损坏 ' + plugin_id)
        for item in manifest.get('files', []):
            if item.get('owner') != 'user':
                continue
            target = item.get('target')
            if not core.safe_relative(target) or not target.startswith(('00_设定层/插件/', '01_运行层/', '06_归档/')):
                raise core.ProjectError('插件用户文件路径不合法 ' + str(target))
            exact.add(target)
    return exact, patterns


def collect(project):
    if core.path_has_symlink(project, CANDIDATE):
        raise core.ProjectError('修订候选路径经过符号链接')
    root = os.path.join(project, CANDIDATE)
    if not os.path.isdir(root):
        raise core.ProjectError('没有修订候选，请先 revise --prepare --file <路径>')
    entries, errors = 落盘.收候选(root)
    import 运行反馈
    if any(item['path'] == 运行反馈.RECORD for item in entries):
        raise core.ProjectError('运行日志只能通过 feedback 追加，不能混入创作修订')
    exact, patterns = allowed_paths(project)
    errors += 落盘.核候选路径(project, entries, exact, patterns)
    if errors:
        raise core.ProjectError('；'.join(errors).replace('本章可写白名单', '全局修订白名单'))
    if not entries:
        raise core.ProjectError('修订候选为空')
    import 开书探索
    开书探索.verify_archive(project, entries)
    import 结构复盘
    for item in entries:
        if item['path'] == 结构复盘.RECORD:
            结构复盘.parse_record(item['data'])
    for item in entries:
        if 开书探索.is_material(item['path']):
            continue
        try:
            text = item['data'].decode('utf-8')
        except UnicodeError:
            raise core.ProjectError('修订文件必须是 UTF-8 文本 ' + item['path'])
        if not text.strip():
            raise core.ProjectError('不允许用空文件删除内容，请保留必要结构 ' + item['path'])
    return entries


def baseline(project):
    """绑定创作与系统文件及 HEAD；单独校验、不绑定追加式运行日志。"""
    import 运行反馈
    # feedback never changes story HEAD and is not a revision target. Appending a
    # valid observation must not invalidate an unchanged manuscript approval.
    # Corruption and symlinks still fail; all story, policy and candidate hashes
    # remain bound. The transaction does not overwrite or roll back this log.
    运行反馈.events(project)
    excluded = core.load_exclusions()
    rows = []
    for current, dirs, files in os.walk(project, followlinks=False):
        kept = []
        for name in dirs:
            rel = os.path.relpath(os.path.join(current, name), project).replace(os.sep, '/')
            if excluded.跳过(rel):
                continue
            if core.path_has_symlink(project, rel):
                raise core.ProjectError('项目有效内容含符号链接 ' + rel)
            kept.append(name)
        dirs[:] = kept
        for name in files:
            rel = os.path.relpath(os.path.join(current, name), project).replace(os.sep, '/')
            if excluded.跳过(rel) or name == '.DS_Store':
                continue
            path = os.path.join(project, rel)
            if core.path_has_symlink(project, rel) or not stat.S_ISREG(os.lstat(path).st_mode):
                raise core.ProjectError('项目有效内容不是普通文件 ' + rel)
            data = core.read_bytes(path)
            if data is None:
                raise core.ProjectError('项目文件无法读取 ' + rel)
            if rel == 运行反馈.RECORD:
                continue
            rows.append((rel, core.sha256_bytes(data)))
    return {'head': 事务.head(project), 'files': sorted(rows)}


def snapshot(project):
    entries = collect(project)
    rows, _ = 落盘.候选摘要(project, 'REVISE', entries)
    if not any(row['before_sha256'] != row['candidate_sha256'] for row in rows):
        raise core.ProjectError('候选与正式文件相同，没有修订内容')
    payload = {'format': 'novel-revision-v2', 'files': rows, 'baseline': baseline(project),
               'review_sha256': core.sha256_bytes(review_bytes(project) or b'')}
    return entries, rows, core.canonical_digest(payload)


def prepare(project, files):
    if not files:
        raise core.ProjectError('--prepare 至少需要一个 --file <项目内路径>')
    exact, patterns = allowed_paths(project)
    entries = []
    for rel in sorted(set(files)):
        errors = 落盘.核候选路径(project, [{'path': rel}], exact, patterns)
        if errors:
            raise core.ProjectError('；'.join(errors))
        data = core.read_bytes(os.path.join(project, rel))
        if data is None:
            raise core.ProjectError('准备修订只能复制已有文件 ' + rel)
        entries.append({'path': rel, 'data': data})
    parent = core.safe_output_dir(project, '_候选')
    target = os.path.join(project, CANDIDATE)
    if os.path.lexists(target):
        raise core.ProjectError('REVISE 候选已经存在，请继续处理，不能覆盖')
    if review_bytes(project) is not None:
        raise core.ProjectError('仍有上次关联核对，请先核对并移走 ' + REVIEW)
    temp = tempfile.mkdtemp(prefix='.revision-', dir=parent)
    try:
        for item in entries:
            core.atomic_write_bytes(os.path.join(temp, item['path']), item['data'])
        os.rename(temp, target)
        temp = None
    finally:
        if temp:
            shutil.rmtree(temp)
    print('✓ 已准备 %d 份修订文件，请只编辑 %s，完成后运行 novel.py revise' % (len(entries), CANDIDATE))


def validate(project):
    tool = os.path.join(os.path.dirname(__file__), '体检.py')
    result = subprocess.run([sys.executable, tool, project], capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode != 0 or not re.search(r'错误 0 ／ 注意 \d+ ／ 通过 \d+', output):
        raise core.ProjectError('修订项目体检未通过\n' + output)


def build_changes(project, entries):
    """影子内重建图谱与派生标题；正式文件在全部检查通过前不变。"""
    temp, shadow = 落盘.建影子(project)
    changes = {item['path']: item['data'] for item in entries}
    try:
        for rel, data in changes.items():
            match = re.fullmatch(r'05_正文/(K[0-9]{4})\.md', rel)
            if match and data != core.read_bytes(os.path.join(project, rel)):
                errors = core.body_header_errors(data.decode('utf-8'), match.group(1))
                if errors:
                    raise core.ProjectError('修订正文须补齐现行文件头：' + '；'.join(errors))
            core.atomic_write_bytes(os.path.join(shadow, rel), data)
        if '项目配置.md' in changes:
            manifest = core.load_project(shadow)
            title = core._project_title(shadow)
            if title != manifest.get('title'):
                manifest['title'] = title
                core.atomic_write_json(os.path.join(shadow, 'project.json'), manifest)
                changes['project.json'] = core.read_bytes(os.path.join(shadow, 'project.json'))
        tool = os.path.join(os.path.dirname(__file__), '生成图谱.py')
        result = subprocess.run([sys.executable, tool, shadow], capture_output=True, text=True)
        graph = core.read_bytes(os.path.join(shadow, '图谱.html'))
        if result.returncode != 0 or graph is None:
            raise core.ProjectError('修订图谱生成失败\n' + result.stdout + result.stderr)
        changes['图谱.html'] = graph
        validate(shadow)
        review = checked_review(project, entries)
        if review is not None:
            rel = '06_归档/修订核对_' + core.sha256_bytes(review)[:20] + '.json'
            changes[rel] = review
        # 完整候选仍绑定批准与基线；仅实际有变的文件进入写入事务。
        # 派生图谱也先生成并验证，不能凭候选文件名猜测它是否会变化。
        actual = {rel: data for rel, data in changes.items()
                  if data != core.read_bytes(os.path.join(project, rel))}
        # 图谱还有现行的修改时间契约。账本变化或图谱已旧时，即使渲染
        # 字节相同也需要刷新；纯复盘记录不触碰这组输入。
        import 体检
        tracked = 体检.graph_tracked_paths(project)
        graph_path = os.path.join(project, '图谱.html')
        graph_time = os.path.getmtime(graph_path) if os.path.isfile(graph_path) else 0
        stale = any(os.path.isfile(os.path.join(project, rel)) and
                    os.path.getmtime(os.path.join(project, rel)) >
                    graph_time + core.GRAPH_STALE_TOLERANCE for rel in tracked)
        if stale or any(rel in actual for rel in tracked):
            actual['图谱.html'] = graph
        return actual
    finally:
        shutil.rmtree(temp)


def preview(project, entries, rows):
    print('全局修订候选，共 %d 份，全部绑定本次批准。只写变化文件及需刷新时间的图谱，改书名时同步 project.json 的 title。图谱仍重新生成并验证。' % len(rows))
    for item, row in zip(entries, rows):
        rel = item['path']
        print('\n%s\n  BEFORE %s\n  AFTER  %s' % (rel, row['before_sha256'] or '(不存在)', row['candidate_sha256']))
        if row['before_sha256'] == row['candidate_sha256']:
            print('  未改变，保留为批准依据，不重复写入。')
            continue
        import 开书探索
        if 开书探索.is_material(rel):
            print('  原始材料副本，%d 字节；摘要只证明字节一致，内容须由作者或代理阅读。' % len(item['data']))
            continue
        before = (core.read_bytes(os.path.join(project, rel)) or b'').decode('utf-8').splitlines()
        after = item['data'].decode('utf-8').splitlines()
        diff = list(difflib.unified_diff(before, after, fromfile=rel, tofile=CANDIDATE + '/' + rel, lineterm=''))
        print('\n'.join(diff[:100]))
        if len(diff) > 100:
            print('△ 差异超过 100 行，另有 %d 行，请打开候选文件阅读完整修改。' % (len(diff) - 100))
    for group in impact_groups(project, entries):
        print('\n需关联核对：' + group['group'])
        print('\n'.join('  ' + path for path in group['paths']))
    data = review_bytes(project)
    if data:
        print('\n本次关联核对记录（随批准摘要绑定并归档）：\n' + data.decode('utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='revise')
    parser.add_argument('project', nargs='?', default='.')
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--review', action='store_true')
    parser.add_argument('--file', action='append', default=[])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve')
    args = parser.parse_args(argv)
    try:
        project = core.resolve_project(args.project)
        if 事务.inspect(project) is not None:
            raise core.ProjectError('存在未完成事务，请先检查并显式 recover')
        if args.prepare:
            if args.apply or args.approve or args.review:
                raise core.ProjectError('--prepare 不能同时提交')
            prepare(project, args.file)
            return 0
        if args.file:
            raise core.ProjectError('--file 只用于 --prepare')
        if args.review:
            if args.apply or args.approve:
                raise core.ProjectError('--review 不能同时提交')
            prepare_review(project)
            return 0
        if args.apply and not re.fullmatch(r'[0-9a-f]{64}', args.approve or ''):
            raise core.ProjectError('正式修订需要 --apply --approve <完整 REVISION_SHA256>')
        entries, rows, digest = snapshot(project)
        reviewed_bytes = review_bytes(project)
        if args.apply and args.approve != digest:
            raise core.ProjectError('批准摘要已失效，候选或项目基线发生变化，请重新试算')
        preview(project, entries, rows)
        if not args.apply:
            changes = build_changes(project, entries)
            if snapshot(project)[2] != digest:
                raise core.ProjectError('试算期间内容改变，请重新试算')
            print('\n实际写入清单（含派生文件）：')
            print('\n'.join('  ' + rel for rel in sorted(changes)))
            print('\n✓ 影子体检通过，只说明结构和可计算记录成立。')
            print('REVISION_SHA256=' + digest)
            print('确认正文、设定和账本后执行：python3 novel.py revise %s --apply --approve %s' % (shlex.quote(project), digest))
            return 0

        def plan():
            fresh, fresh_rows, fresh_digest = snapshot(project)
            if fresh_digest != args.approve:
                raise core.ProjectError('锁内复核发现候选或基线已变化，请重新试算')
            changes = build_changes(project, fresh)
            if snapshot(project)[2] != fresh_digest:
                raise core.ProjectError('校验期间内容改变，拒绝覆盖')
            return {'changes': changes, 'label': 'global revision',
                    'metadata': {'revision_sha256': fresh_digest, 'candidate_files': fresh_rows}}

        def postcheck():
            validate(project)
            return True

        tx = 事务.apply_changes(project, plan=plan, validator=postcheck,
                               fault_after=os.environ.get('NOVEL_FAIL_AFTER') if 事务._faults_enabled() else None,
                               hard_crash_after=os.environ.get('NOVEL_HARD_CRASH_AFTER') if 事务._faults_enabled() else None)
        try:
            remaining = collect(project)
            if remaining == entries:
                shutil.rmtree(os.path.join(project, CANDIDATE))
                if review_bytes(project) == reviewed_bytes and reviewed_bytes is not None:
                    os.unlink(os.path.join(project, REVIEW))
            else:
                print('△ 候选被另行修改，保留候选目录供核对。')
        except (OSError, core.ProjectError) as exc:
            print('△ 正式提交已完成，候选清理未完成：' + str(exc))
        print('✓ 已提交全局修订，事务 ' + tx['id'])
        print('需要撤销时先看 history；本修订仍是最近一笔提交时运行 rollback。')
        return 0
    except (OSError, ValueError, core.ProjectError, 事务.TransactionError) as exc:
        print('✗ ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
