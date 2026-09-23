#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步工具回归测试。所有变更只发生在临时项目。"""
from __future__ import print_function

import os
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_core as _core          # noqa: E402  版本号从内核取，不在测试里写死

RESULTS = []


def _record(name, passed, detail=""):
    RESULTS.append((name, bool(passed), detail))


def _run(args, env=None):
    result = subprocess.run(args, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout + result.stderr


def _snapshot(project):
    return {str(p.relative_to(project)): (p.stat().st_mtime_ns, p.stat().st_mode,
                                          hashlib.sha256(p.read_bytes()).hexdigest())
            for p in Path(project).rglob('*') if p.is_file()}


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _sync_boundaries(sandbox):
    """当前模板的保留、损坏输入及插件最终登记回归，不使用真实作品。"""
    root = Path(ROOT)
    sequence = [0]

    def cli(project, *args, source=root):
        return _run([sys.executable, '-B', str(source / 'novel.py'), *map(str, args)])

    def new(label, plugin=False):
        sequence[0] += 1
        project = Path(sandbox) / ('boundary-%02d-%s' % (sequence[0], label))
        code, output = cli(project, 'init', project)
        if code:
            raise RuntimeError('测试项目创建失败 ' + output)
        if plugin:
            code, output = cli(project, 'plugin', 'install', 'serial', project, source=project)
            if code:
                raise RuntimeError('测试插件安装失败 ' + output)
        return project

    def metadata(project):
        return json.loads((project / 'project.json').read_text(encoding='utf-8'))

    def old_readme(project):
        (project / 'README.md').write_text('SYNTHETIC_OLD_SHARED_FILE\n', encoding='utf-8')
        data = metadata(project)
        data['system_file_hashes']['README.md'] = _core.sha256_file(str(project / 'README.md'))
        _write_json(project / 'project.json', data)

    spec = json.loads((root / 'system-manifest.json').read_text(encoding='utf-8'))['merge_files'][0]
    rel, begin, end = spec['path'], spec['begin'], spec['end']
    original = (root / rel).read_text(encoding='utf-8')
    p = new('keep')
    text = original + '\nSYNTHETIC_AUTHOR_RULE_OUTSIDE_BLOCK\n'
    (p / rel).write_text(text, encoding='utf-8')
    old_readme(p)
    before = _snapshot(p)
    code, output = cli(p, 'sync', p, '--check', '--keep-local', rel)
    _record('混合文件 keep-local 的检查零写入并显示保留',
            code == 0 and _snapshot(p) == before and '保留本地修改 ' + rel in output,
            output[-300:])
    code, output = cli(p, 'sync', p, '--keep-local', rel)
    _record('实际同步其他文件时 keep-local 仍保留整份混合文件',
            code == 0 and (p / rel).read_text(encoding='utf-8') == text
            and (p / 'README.md').read_bytes() == (root / 'README.md').read_bytes(), output[-300:])
    before = _snapshot(p)
    code, output = cli(p, 'sync', p, '--keep-local', 'project.json')
    _record('项目登记不是共享文件不可接受保留选项后暗中改写',
            code == 1 and _snapshot(p) == before and '项目登记' in output, output[-300:])
    p = new('keep-missing-seed')
    seed = json.loads((root / 'system-manifest.json').read_text(encoding='utf-8'))['seed_files'][0]
    (p / seed).unlink()
    before = _snapshot(p)
    code, output = cli(p, 'sync', p, '--keep-local', seed)
    _record('明确保留缺失种子现状不补入且报告与实际一致',
            code == 0 and _snapshot(p) == before and '缺失种子' in output, output[-300:])

    bad_blocks = [
        ('缺两端', 'SYNTHETIC_BOOK_BASELINE\n'),
        ('缺结束', begin + '\nSYNTHETIC_BOOK_BASELINE\n'),
        ('缺开始', 'SYNTHETIC_BOOK_BASELINE\n' + end),
        ('倒置', end + '\nSYNTHETIC_BOOK_BASELINE\n' + begin),
        ('重复开始', begin + '\n' + begin + '\nSYNTHETIC_BOOK_BASELINE\n' + end),
        ('重复结束', begin + '\nSYNTHETIC_BOOK_BASELINE\n' + end + '\n' + end),
    ]
    for label, text in bad_blocks:
        p = new('bad-marker')
        (p / rel).write_text(text, encoding='utf-8')
        before = _snapshot(p)
        check, report = cli(p, 'sync', p, '--check')
        code, output = cli(p, 'sync', p)
        _record('目标区块%s时检查和同步均拒绝且零写入' % label,
                check == 1 and code == 1 and _snapshot(p) == before
                and '区块标记' in report and '区块标记' in output, output[-300:])
    code, output = cli(p, 'sync', p, '--keep-local', rel)
    _record('损坏目标可明确 keep-local 整份保留而不假装修复',
            code == 0 and _snapshot(p) == before, output[-300:])

    for label, block in [('空区块', begin + end),
                         ('未建立', begin + '\n状态：**未建立**\n' + end),
                         ('已有基线', begin + '\nSYNTHETIC_BOOK_BASELINE\n' + end)]:
        p = new('valid-block')
        (p / rel).write_text('SYNTHETIC_OLD_OUTER\n' + block + '\n', encoding='utf-8')
        expected = original[:original.index(begin)] + block + original[original.index(end) + len(end):]
        code, output = cli(p, 'sync', p)
        _record('合法%s原样合并并更新外围规则' % label,
                code == 0 and (p / rel).read_text(encoding='utf-8') == expected, output[-300:])
    p = new('missing-block-file')
    (p / rel).unlink()
    code, output = cli(p, 'sync', p)
    _record('缺失混合文件补入当前空白模板',
            code == 0 and (p / rel).read_bytes() == (root / rel).read_bytes(), output[-300:])

    source = Path(sandbox) / 'damaged-source'
    shutil.copytree(ROOT, str(source), ignore=shutil.ignore_patterns('.git', '__pycache__', '.DS_Store'))
    p = new('source-check')
    before = _snapshot(p)
    for label, text in bad_blocks:
        (source / rel).write_text(text, encoding='utf-8')
        check, report = cli(p, 'sync', p, '--check', '--keep-local', rel, source=source)
        code, output = cli(p, 'sync', p, '--keep-local', rel, source=source)
        _record('母版区块%s时即使 keep-local 也拒绝且目标零写入' % label,
                check == 1 and code == 1 and _snapshot(p) == before
                and '母版 ' + rel in report and '母版 ' + rel in output, output[-300:])

    registry = json.loads((root / '04_题材插件/plugin-registry.json').read_text(encoding='utf-8'))
    entry = next(x for x in registry['plugins'] if x['id'] == 'serial')
    package_rel = '04_题材插件/' + entry['manifest']
    current_package = json.loads((root / package_rel).read_text(encoding='utf-8'))
    target_version = current_package['version']
    check_rel = next(x['target'] for x in current_package['files'] if x.get('owner') == 'system')
    user_rel = next(x['target'] for x in current_package['files'] if x.get('owner') == 'user')

    def old_package(project):
        package = json.loads((project / package_rel).read_text(encoding='utf-8'))
        package['version'] = '0.0.0-synthetic'
        _write_json(project / package_rel, package)
        data = metadata(project)
        data['plugin_version']['serial'] = package['version']
        data['system_file_hashes'][package_rel] = _core.sha256_file(str(project / package_rel))
        _write_json(project / 'project.json', data)
        return data

    p = new('metadata-only', plugin=True)
    old = old_package(p)
    verified, report = cli(p, 'plugin', 'verify', 'serial', p, source=p)
    before = _snapshot(p)
    check, check_output = cli(p, 'sync', p, '--check')
    _record('仅包元数据变化的检查列出版本登记且零写入',
            verified == 0 and check == 0 and _snapshot(p) == before
            and 'plugin_version / serial' in check_output, check_output[-300:])
    code, output = cli(p, 'sync', p)
    verified, report = cli(p, 'plugin', 'verify', 'serial', p, source=p)
    _record('检查字节不变时仍更新登记版本并通过本项目插件核验',
            code == 0 and verified == 0
            and metadata(p)['plugin_version']['serial'] == target_version
            and metadata(p)['plugin_files'] == old['plugin_files'], output[-300:] + report[-200:])

    p = new('keep-installed-check', plugin=True)
    old = old_package(p)
    local_check = (p / check_rel).read_bytes() + b'\nSYNTHETIC_LOCAL_PLUGIN_RULE\n'
    (p / check_rel).write_bytes(local_check)
    code, output = cli(p, 'sync', p, '--keep-local', check_rel)
    verified, report = cli(p, 'plugin', 'verify', 'serial', p, source=p)
    _record('包登记升级仍保留指定本地检查及其旧安装基线',
            code == 0 and verified == 0 and (p / check_rel).read_bytes() == local_check
            and metadata(p)['plugin_files'] == old['plugin_files']
            and metadata(p)['plugin_version']['serial'] == target_version, output[-300:])

    p = new('keep-package', plugin=True)
    old = old_package(p)
    original_package = (p / package_rel).read_bytes()
    old_readme(p)
    code, output = cli(p, 'sync', p, '--keep-local', package_rel)
    verified, report = cli(p, 'plugin', 'verify', 'serial', p, source=p)
    _record('明确保留旧包时登记依据最终项目包而非母版包',
            code == 0 and verified == 0 and (p / package_rel).read_bytes() == original_package
            and metadata(p)['plugin_version']['serial'] == old['plugin_version']['serial'], output[-300:])

    p = new('custom-package', plugin=True)
    package = json.loads((p / package_rel).read_text(encoding='utf-8'))
    package['version'] = target_version + '-book-synthetic.1'
    _write_json(p / package_rel, package)
    data = metadata(p)
    data['plugin_version']['serial'] = package['version']
    _write_json(p / 'project.json', data)
    protected = [package_rel, check_rel, user_rel, '04_题材插件/' + entry['name'] + '.md']
    for name in protected[1:]:
        (p / name).write_bytes((p / name).read_bytes() + b'\nSYNTHETIC_BOOK_CUSTOMIZATION\n')
    saved = {name: (p / name).read_bytes() for name in protected}
    old_readme(p)
    code, output = cli(p, 'sync', p)
    verified, report = cli(p, 'plugin', 'verify', 'serial', p, source=p)
    _record('同步其他文件时定制包版本检查手册与用户文件保持',
            code == 0 and verified == 0 and all((p / name).read_bytes() == raw for name, raw in saved.items())
            and metadata(p)['plugin_version']['serial'] == package['version'], output[-300:])

    p = new('repair-registration', plugin=True)
    data = metadata(p)
    data['plugin_version']['serial'] = '0.0.0-synthetic'
    _write_json(p / 'project.json', data)
    (p / user_rel).unlink()
    code, output = cli(p, 'sync', p)
    _record('既有登记不一致可修复且不因无关用户内容缺失阻断同步',
            code == 0 and metadata(p)['plugin_version']['serial'] == target_version
            and not (p / user_rel).exists(), output[-300:])

    p = new('registration-validator', plugin=True)
    old_package(p)
    before = {name: (p / name).read_bytes() for name in [package_rel, 'project.json', check_rel]}
    script = '''import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import 同步文件 as sync
original = sync.事务.apply_changes
def inject(project, *args, **kwargs):
    validator = kwargs['validator']
    def check():
        path = pathlib.Path(project) / 'project.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['plugin_version']['serial'] = 'invalid-injected-version'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return validator()
    kwargs['validator'] = check
    return original(project, *args, **kwargs)
sync.事务.apply_changes = inject
raise SystemExit(sync.main([sys.argv[2]]))
'''
    code, output = _run([sys.executable, '-B', '-c', script, str(root / '_工具'), str(p)])
    _record('写后登记版本被破坏时拒绝成功并回滚本次同步',
            code == 1 and '同步完成' not in output
            and all((p / name).read_bytes() == raw for name, raw in before.items())
            and not (p / '.novel/transaction.json').exists(), output[-300:])


def main():
    sandbox = tempfile.mkdtemp(prefix="novel-sync-test-%s-" % uuid.uuid4().hex[:8])
    project = os.path.join(sandbox, "project")
    try:
        code, output = _run([sys.executable, os.path.join(ROOT, "novel.py"),
                             "init", project])
        _record("创建测试项目", code == 0, output[-300:])
        if code != 0:
            return 1
        sync = os.path.join(ROOT, "_工具", "同步文件.py")
        manifest_path = os.path.join(project, "project.json")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        manifest["system_version"] = "2.0.0"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        readme = os.path.join(project, "README.md")
        original = open(readme, "rb").read()
        with open(readme, "wb") as handle:
            handle.write(b"local-old-version\n")

        manifest['system_file_hashes']['README.md'] = hashlib.sha256(b'local-old-version\n').hexdigest()
        with open(manifest_path, 'w', encoding='utf-8') as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        code, output = _run([sys.executable, sync, "--check", project])
        _record("--check 只报告", code == 0 and
                open(readme, "rb").read() == b"local-old-version\n"
                and json.load(open(manifest_path, encoding="utf-8"))["system_version"] == "2.0.0"
                and "只报告" in output, output[-300:])

        env = dict(os.environ)
        env["NOVEL_SELFTEST_FAULTS"] = "1"
        env["NOVEL_SYNC_FAIL_AFTER"] = "1"
        code, output = _run([sys.executable, sync, project], env=env)
        _record("替换中途失败会回滚", code == 1 and
                open(readme, "rb").read() == b"local-old-version\n"
                and not os.path.exists(os.path.join(project, ".novel", "transaction.json")),
                output[-300:])

        code, output = _run([sys.executable, sync, project])
        _record("正常同步后哈希一致", code == 0 and
                open(readme, "rb").read() == open(os.path.join(ROOT, "README.md"), "rb").read(),
                output[-300:])
        _record("同步在同一事务内更新项目补丁版本", code == 0 and
                json.load(open(manifest_path, encoding="utf-8"))["system_version"]
                == _core.SYSTEM_VERSION,
                output[-300:])

        os.unlink(readme)
        code, output = _run([sys.executable, sync, project], env=env)
        _record("本轮新增文件在失败后撤销", code == 1 and not os.path.exists(readme),
                output[-300:])

        code, output = _run([sys.executable, sync, project])
        _record("缺失共享文件可以完整补回", code == 0 and
                open(readme, "rb").read() == original, output[-300:])
        _sync_boundaries(sandbox)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    print("=" * 68)
    print("同步工具自测")
    print("=" * 68)
    failed = 0
    for name, passed, detail in RESULTS:
        print("%s %s%s" % ("✓" if passed else "✗", name,
                           "" if passed else "  " + detail.replace("\n", " ")[:180]))
        failed += 0 if passed else 1
    print("=" * 68)
    print("%d / %d 通过" % (len(RESULTS) - failed, len(RESULTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
