#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append-only operational feedback. DATA only; never changes story or commit HEAD."""
import argparse
import json
import os
import re

import v2_core as core
import 事务
from 开书探索 import read_file

RECORD = '06_归档/运行问题.jsonl'
MANUAL = '02_检查层/17_运行反馈与升级记录.md'
KINDS = ('目标偏离', '写作质量', '流程负担', '技术故障', '状态记录', '研究不足', '其他')
STATES = ('待分析', '待处理', '待验证', '已解决', '保留观察', '不升级', '重新打开')
SOURCE_KINDS = ('当前对话', '保存记录转引', '工具输出', '代理观察')


def validate_event(value):
    if not isinstance(value, dict):
        raise core.ProjectError('运行问题事件必须是对象')
    for key in ('issue_id', 'kind', 'status', 'summary', 'source', 'analysis',
                'action', 'verification', 'decision', 'scope'):
        if key not in value:
            raise core.ProjectError('运行问题事件缺 ' + key)
    if not isinstance(value['issue_id'], str) or not re.fullmatch(r'ISS-[A-Za-z0-9_-]{1,64}', value['issue_id']):
        raise core.ProjectError('issue_id 必须为 ISS- 开头的安全编号')
    if value['kind'] not in KINDS or value['status'] not in STATES:
        raise core.ProjectError('运行问题类别或状态无效')
    for key in ('summary', 'analysis', 'action', 'verification', 'decision', 'scope'):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 12000:
            raise core.ProjectError('运行问题字段必须有明确说明（未知也要说明）：' + key)
    source = value['source']
    if not isinstance(source, dict) or source.get('kind') not in SOURCE_KINDS:
        raise core.ProjectError('运行问题必须区分直接对话、保存记录转引、工具输出与代理观察')
    for key in ('locator', 'excerpt', 'coverage'):
        if not isinstance(source.get(key), str) or not source[key].strip():
            raise core.ProjectError('来源缺 ' + key + '；不得虚构完整对话覆盖')
    if value['status'] == '已解决' and value['verification'].strip() in ('未验证', '待验证', '无', '不适用'):
        raise core.ProjectError('没有验证依据不能标为已解决')
    if value['status'] == '不升级' and value['decision'].strip() in ('待定', '无'):
        raise core.ProjectError('不升级必须说明属于个书取舍、正常探索或证据不足等理由')
    return value


def events(project):
    raw = read_file(project, RECORD, optional=True)
    if raw is None:
        return []
    try:
        lines = raw.decode('utf-8').splitlines()
    except UnicodeError:
        raise core.ProjectError('运行问题记录不是有效 UTF-8 文本')
    result = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = validate_event(json.loads(line))
            payload = {k: v for k, v in event.items() if k not in ('recorded_at', 'event_sha256')}
            if event.get('event_sha256') != core.canonical_digest(payload):
                raise core.ProjectError('事件摘要不一致')
        except (ValueError, core.ProjectError) as exc:
            raise core.ProjectError('运行问题第 %d 行异常：%s' % (number, exc))
        result.append(event)
    return result


def latest(project):
    result = {}
    for item in events(project):
        result[item['issue_id']] = item
    return result


def quality_followups(project, limit=3):
    """只返回本书未关闭的质量线索；不把事件摘要当作编辑结论。"""
    items = [item for item in latest(project).values()
             if item['kind'] in ('写作质量', '目标偏离', '研究不足')
             and item['status'] not in ('已解决', '不升级')]
    # Most recently updated issues first, even if the issue was opened long ago.
    positions = {item['issue_id']: n for n, item in enumerate(events(project))}
    items.sort(key=lambda item: positions[item['issue_id']], reverse=True)
    return items[:limit], len(items)


def summary(project):
    items = list(latest(project).values())
    active = [x for x in items if x['status'] not in ('已解决', '不升级')]
    return '%d 项，%d 项待跟进；feedback 查看来源与过程；记录不构成创作授权' % (len(items), len(active))


def safe_summary(project):
    try:
        return summary(project)
    except (core.ProjectError, UnicodeError, OSError) as exc:
        return '运行问题记录异常：' + str(exc) + '；未视为无问题'


def record(project, source):
    if core.is_template(project):
        raise core.ProjectError('母版不能保存作品运行问题；只保存空模板和通用规则')
    path = os.path.abspath(source)
    if os.path.islink(path) or not os.path.isfile(path):
        raise core.ProjectError('事件输入必须为普通 JSON 文件')
    if os.path.getsize(path) > 100000:
        raise core.ProjectError('事件输入过大；只保留必要对话摘录与证据位置')
    item = core.load_json(path)
    validate_event(item)
    if set(item) - {'issue_id', 'kind', 'status', 'summary', 'source', 'analysis', 'action', 'verification', 'decision', 'scope'}:
        raise core.ProjectError('事件含未知字段；记录时间与摘要由工具生成')
    digest = core.canonical_digest(item)
    handle = 事务._acquire(project)
    try:
        if 事务.inspect(project) is not None:
            raise core.ProjectError('存在未完成事务；先处理恢复，未追加问题记录')
        prior = events(project)
        if any(x['event_sha256'] == digest for x in prior):
            print('✓ 同一事件已存在，未重复写入 ' + item['issue_id'])
            return
        item['event_sha256'], item['recorded_at'] = digest, core.utc_now()
        prior.append(item)
        core.safe_output_dir(project, '06_归档')
        # One atomic replacement under the shared lock; no multi-file transaction or story HEAD.
        # The existing prefix is retained byte-for-byte, including human formatting.
        raw = read_file(project, RECORD, optional=True) or b''
        if raw and not raw.endswith(b'\n'):
            raw += b'\n'
        raw += (json.dumps(item, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
        core.atomic_write_bytes(os.path.join(project, RECORD), raw)
    finally:
        事务._release(handle)
    print('✓ 已追加运行问题事件 ' + item['issue_id'] + ' / ' + item['status'])
    print('保存来源与处理过程；未修改故事、授权状态或最近一次创作提交。')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='feedback', description=__doc__)
    parser.add_argument('project', nargs='?', default='.')
    parser.add_argument('--record', help='追加已从可见对话或记录中整理的 JSON 事件')
    parser.add_argument('--issue', help='查看某一问题全部历史事件')
    parser.add_argument('--prompt', action='store_true')
    args = parser.parse_args(argv)
    project = core.resolve_project(args.project)
    core.load_project(project)
    if args.record:
        record(project, args.record)
    elif args.prompt:
        print('读取 ' + MANUAL + '，从本轮可见对话提取实质性问题；没有新问题不填表。')
        print('记录作者原话或明确标记转引/代理概括，来源位置、覆盖范围、原判断、纠正、受影响环节、行动和验证。')
        print('同一问题沿用 issue_id 追加事件；意见被推翻时保留旧事件。软件通过与阅读改善分别验证。')
        print('外部审读接续须在来源与验证中写明报告位置、报告及正文版本、实际范围、补充或替代的旧结论；正文未重读须明说。')
        print('历史报告及 JSON 是当时快照；存在纠正时追加同一问题的新事件，不能只取旧通过字段。结论冲突未消解前保留待分析，不把观察变成返工授权。')
        print('无完整对话时注明缺失，不声称自动读取其他任务；作品数据留在本书，通用改动经维护审查后进入母版。')
    elif args.issue:
        history = [item for item in events(project) if item['issue_id'] == args.issue]
        if history:
            print('最新记录 DATA（按追加顺序；仍须核对正文版本，记录不构成授权）：')
            print(json.dumps(history[-1], ensure_ascii=False, indent=2))
            if len(history) > 1:
                print('以下为历史事件 DATA，不覆盖上方最新记录：')
                for item in history[:-1]:
                    print(json.dumps(item, ensure_ascii=False, indent=2))
    else:
        print('运行问题：' + summary(project))
        for item in latest(project).values():
            print('%s | %s | %s | %s' % (item['issue_id'], item['kind'], item['status'], item['summary']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
