#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从下载目录原地开始，或从母版另建干净的新书项目。

工具会排除版本库、运行历史、候选区、读取包和母版专用文件。

用法：
    python3 _工具/新建项目.py <新项目目录>

以下安全约定仅指另建目录的 init；原地 start 使用下方可恢复事务：
  · 目标必须尚不存在，且不是普通文件或符号链接
  · 目标不得等于母版、不得位于母版内部、不得是母版的上级目录
  · 先在**目标父目录**里建临时目录，全部复制完并通过排除项与文件数核对，
    才 `os.replace` 改名成正式目标 —— **任一步失败，正式目标都不会出现**
  · 失败后清理本轮临时目录；本工具**不删除用户原有的任何文件**
"""
import io, json, os, shutil, sys, tempfile

import 事务

import v2_core as core

排除目录 = {'.git', '.hg', '.svn', '_快照', '_备份', '_读取包', '_候选', '_候选存根', '_to_delete',
            '.novel', '__pycache__', '.pytest_cache', '.idea', '.vscode'}
排除文件 = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}
# 母版拥有但**绝不进新项目**（判据被复制走，项目就能冒充母版）
母版专用 = {'_工具/我是母版.txt', '_工具/母版禁词.txt', '_工具/母版检查.py',
            '_工具/同步自测.py', '_工具/新建项目.py', '_工具/新书自测.py',
            '_工具/发布自测.py', '_工具/同步文件.py', '_工具/同步流程文件.sh',
            '_工具/迁移项目.py', '_工具/读取包自测.py', 'system-manifest.json',
            '设计札记.md', '交付验收报告.md', 'CHANGELOG.md', '_候选_README.md',
            '技术文档.md', '_工具/优化自测.py', '_工具/阶段反馈自测.py',
            '_工具/读取效率自测.py', '_工具/运行效率自测.py', '_工具/修订效率自测.py',
            '_工具/入口自测.py', '_工具/数据保护自测.py', '_工具/工作流自测.py', '_工具/创作模式自测.py',
            '.gitignore', '.gitattributes', 'CONTRIBUTING.md', 'SECURITY.md',
            'CODE_OF_CONDUCT.md', 'CODEOWNERS', 'RELEASING.md', 'README.en.md'}


# 对外展示、平台入口与仓库维护资料只属于母版，不带入具体作品。
# 按根目录相对路径排除，保留插件等目录下可能同名的运行资料。
母版专用目录 = {'docs', 'scripts', '.github', 'tests'}

def _内(子, 父):
    子, 父 = os.path.abspath(子), os.path.abspath(父)
    return os.path.commonpath([子, 父]) == 父 and 子 != 父


def 路径检查(母, 新):
    e = []
    # 不存在的末级目标也要解析父路径，防止目录别名绕过母版隔离。
    母a, 新a = os.path.realpath(母), os.path.realpath(新)
    if not 新a or 新a == os.sep:
        e.append('目标路径非法')
    if 新a == 母a:
        e.append('目标不能就是母版自己')
    if _内(新a, 母a):
        e.append('目标不能位于母版内部：%s' % 新a)
    if _内(母a, 新a):
        e.append('目标是母版的上级目录，不允许：%s' % 新a)
    if os.path.islink(os.path.abspath(新)):
        e.append('目标是符号链接，不允许：%s' % 新)
    elif os.path.isfile(新a):
        e.append('目标是一个普通文件，不允许：%s' % 新a)
    elif os.path.exists(新a):
        e.append('目标目录已存在，**不覆盖任何已有内容**：%s' % 新a)
    父 = os.path.dirname(新a)
    if not os.path.isdir(父):
        e.append('目标的父目录不存在：%s' % 父)
    elif not os.access(父, os.W_OK):
        e.append('目标的父目录不可写：%s' % 父)
    return e


def 应带的文件(母):
    out = []
    for root, dirs, files in os.walk(母):
        dirs[:] = [d for d in dirs if d not in 排除目录
                   and os.path.relpath(os.path.join(root, d), 母).replace(os.sep, '/')
                   not in 母版专用目录]
        for f in files:
            if f in 排除文件:
                continue
            rel = os.path.relpath(os.path.join(root, f), 母).replace(os.sep, '/')
            if rel in 母版专用:
                continue
            out.append(rel)
    return sorted(out)


def 建(母, 新, 注入失败=None):
    """返回 (错误列表, 带过去的文件列表)。**正式目标只在全部成功后才出现。**"""
    e = 路径检查(母, 新)
    if e:
        return e, []
    if not os.path.exists(os.path.join(母, '_工具', '我是母版.txt')):
        return ['源目录没有母版标记 _工具/我是母版.txt，它不是母版'], []
    应带 = 应带的文件(母)
    新a = os.path.realpath(新)
    临 = tempfile.mkdtemp(prefix='.新建项目-', dir=os.path.dirname(新a))
    try:
        for i, rel in enumerate(应带):
            if 注入失败 is not None and i == 注入失败:
                raise RuntimeError('（测试注入的中途失败）')
            dst = os.path.join(临, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(母, rel), dst)
        清单 = core.new_project_manifest(临)
        清单['title'] = os.path.basename(新a)
        source_manifest = core.load_json(os.path.join(母, 'system-manifest.json'), {}) or {}
        清单['system_file_hashes'] = {rel: core.sha256_file(os.path.join(母, rel))
                                      for rel in source_manifest.get('sync_files', [])}
        core.atomic_write_json(os.path.join(临, 'project.json'), 清单)
        for rel in ('.novel/transactions', '.novel/commits', '.novel/runtime'):
            os.makedirs(os.path.join(临, rel), exist_ok=True)
        实带 = 应带的文件(临)
        坏 = []
        预期 = sorted(应带 + ['project.json'])
        if 实带 != 预期:
            坏.append('临时目录文件清单与预期不符（应 %d 份，实 %d 份）' % (len(预期), len(实带)))
        误入 = [r for r in 母版专用 if os.path.exists(os.path.join(临, r))]
        if 误入:
            坏.append('母版专用文件混入：' + '、'.join(误入))
        维护目录 = [d for d in 母版专用目录 if os.path.exists(os.path.join(临, d))]
        if 维护目录:
            坏.append('母版维护目录混入：' + '、'.join(sorted(维护目录)))
        脏 = [d for d in 排除目录 if d != '.novel' and os.path.exists(os.path.join(临, d))]
        if 脏:
            坏.append('排除目录混入：' + '、'.join(脏))
        if 坏:
            raise RuntimeError('；'.join(坏))
        # 按发布清单核对：v2 只比对"复制清单"，没人拿 project_required_files
        # 验过新项目，于是 init 出来缺什么要等到用的时候才知道。
        清单文件 = core.load_json(os.path.join(母, 'system-manifest.json'), {}) or {}
        必需 = [rel for rel in 清单文件.get('project_required_files', [])
                if not os.path.isfile(os.path.join(临, rel))]
        if 必需:
            raise RuntimeError('新项目缺发布清单要求的文件：' + '、'.join(必需[:8]))
        再核 = 路径检查(母, 新a)
        if 再核:
            raise RuntimeError('；'.join(再核))
        os.replace(临, 新a)          # 只有到这一步，正式目标才出现
        临 = None
        return [], 预期
    except Exception as ex:
        return ['新建失败：%s' % ex], []
    finally:
        if 临 and os.path.isdir(临):
            try:
                shutil.rmtree(临)
            except Exception:
                # 有些通道不允许删除。留痕并改名，绝不静默留下一个看起来像项目的目录。
                try:
                    os.replace(临, 临 + '-删我')
                    print('⚠ 临时目录删不掉，已改名为 %s-删我，请手工删除' % 临)
                except Exception:
                    print('⚠ 临时目录既删不掉也改不了名：%s' % 临)


def 原地开始(root, fault_after=None):
    """将下载目录登记为作品；只新增身份并归档母版标记，不改创作资料。

    使用已有可恢复事务，在锁内检查身份、清单和路径。已有作品只读返回；
    软件维护不会调用此入口。故障参数仅供隔离测试传入。
    """
    root = os.path.abspath(root)
    identity = os.path.join(root, 'project.json')
    if os.path.lexists(identity):
        if core.path_has_symlink(root, 'project.json'):
            raise core.ProjectError('项目身份不能是符号链接')
        core.load_project(root)
        return False

    def plan():
        if os.path.lexists(identity):
            raise core.ProjectError('其他任务已创建项目，请重新读取状态，不重复初始化')
        if not core.is_template(root):
            raise core.ProjectError('当前目录缺少项目身份或下载标记；请检查原项目，不自动重建')
        manifest_path = os.path.join(root, 'system-manifest.json')
        if core.path_has_symlink(root, 'system-manifest.json'):
            raise core.ProjectError('发布清单不能经过符号链接')
        manifest = core.load_json(manifest_path)
        if not isinstance(manifest, dict) or manifest.get('format') != 'novel-system-release':
            raise core.ProjectError('缺少有效的发布清单，请重新下载完整系统')
        for key in ('project_required_files', 'sync_files'):
            rows = manifest.get(key)
            if not isinstance(rows, list) or not rows:
                raise core.ProjectError('发布清单缺少 ' + key)
            for rel in rows:
                if key == 'project_required_files' and rel == 'project.json':
                    continue  # 本次创建的身份，不是下载包中的输入。
                if (not core.safe_relative(rel) or core.path_has_symlink(root, rel)
                        or not os.path.isfile(os.path.join(root, rel))):
                    raise core.ProjectError('发布清单文件缺失或路径不安全：%s' % rel)
        # 缺身份但已有小说运行数据时，不冒充一本空白新书。
        body = os.path.join(root, '05_正文')
        if any(name.startswith('K') and name.endswith('.md') for name in os.listdir(body)):
            raise core.ProjectError('发现已有正文但缺 project.json，请先核对原项目身份')
        if os.path.lexists(os.path.join(root, '_候选')):
            raise core.ProjectError('发现候选但缺 project.json，请先核对原项目身份')
        value = core.new_project_manifest(root)
        value['system_file_hashes'] = {
            rel: core.sha256_file(os.path.join(root, rel)) for rel in manifest['sync_files']}
        changes = {'project.json': (json.dumps(value, ensure_ascii=False, indent=2,
                                              sort_keys=True) + '\n').encode('utf-8')}
        for rel in ('_工具/我是母版.txt', '_工具/母版禁词.txt',
                    '_工具/母版检查.py', '_候选_README.md'):
            if core.path_has_symlink(root, rel):
                raise core.ProjectError('母版标记不能经过符号链接：%s' % rel)
            if os.path.lexists(os.path.join(root, rel)):
                if not os.path.isfile(os.path.join(root, rel)):
                    raise core.ProjectError('母版标记必须是普通文件：%s' % rel)
                changes[rel] = None
        return {'changes': changes, 'label': '在下载文件夹开始创作',
                'metadata': {'kind': 'start'}}

    def validate():
        core.load_project(root)
        return not core.is_template(root)

    事务.apply_changes(root, plan=plan, validator=validate, fault_after=fault_after)
    print('✓ 已在当前文件夹开始创作，现有资料保留。')
    print('  接下来按 START_HERE.md 与作者讨论；需要空白系统时重新下载。')
    return True


def main(argv):
    if len(argv) != 1 or argv[0].startswith('-'):
        print(__doc__)
        return 2
    母 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    新 = os.path.abspath(argv[0])
    e, 带 = 建(母, 新)
    if e:
        print('✗ 新建失败（正式目标未创建）：')
        for x in e:
            print('   ·', x)
        return 2
    print('✓ 已从母版建出新项目：%s' % 新)
    print('  带过去 %d 份文件。' % len(带))
    print('  已排除：%s' % '、'.join(sorted(排除目录)))
    print('  母版专用（一份都没带）：%s' % '、'.join(sorted(母版专用)))
    print()
    print('接下来：')
    print('  1. 走 START_HERE，把 00_设定层 与 项目配置 填完。')
    print('  2. 填新项目的 _工具/专名表.txt。')
    print('  3. 运行 python3 novel.py plugin none，或按需要安装 suspense、romance、speculative、serial。')
    print()
    print('随时用 python3 novel.py status 看当前还差什么。')
    print()
    print('**在 1、2 完成之前，读取包会拒绝出简报**——')
    print('一个看起来成功的简报，比一个失败的简报危险得多。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
