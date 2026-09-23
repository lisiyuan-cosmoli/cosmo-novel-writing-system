#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 公共内核。

这里保存项目版本、原子写入、项目清单和公共路径规则。业务检查仍由
体检.py 与提交包.py 承担，避免在升级时重写已经被真实项目验证过的规则。
"""
from __future__ import print_function

import datetime
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import tempfile
import uuid


SYSTEM_VERSION = "6.0"
# 4.1 题材文风档（登记表在 04_题材插件/文风档/registry.json；缺省按 literary 处理）
VOICE_PROFILES = ("literary", "webnovel", "romance", "genre")
SCHEMA_VERSION = 2
PROJECT_FORMAT = "novel-project"
SUPPORTED_PYTHON = ">=3.9"
GRAPH_STALE_TOLERANCE = 2      # 秒。体检与提交闸门共用，避免两处判断不一致
SUPPORTED_PLUGINS = {
    "suspense": "悬疑推理",
    "romance": "言情情感",
    "speculative": "科幻奇幻",
    "serial": "网文连载",
}


INIT_STATES = ("draft", "confirmed", "legacy")
COOP_MODES = ("author_led", "guided", "ai_draft", "import")


class ProjectError(RuntimeError):
    pass


def body_header_errors(text, kid, display=None, viewpoint=None, status=None, legacy=False):
    """体检与提交共用的正文身份检查；不依赖当前写到哪一章。"""
    first, _, body = (text or '').partition('\n')
    match = re.fullmatch(r'\s*<!--\s*(.*?)\s*-->\s*', first)
    if not match:
        return ['正文第一行缺少合法文件头']
    fields, errors = {}, []
    for cell in match.group(1).split('|'):
        pair = re.fullmatch(r'\s*([^:：]+?)\s*[:：]\s*(.*?)\s*', cell)
        if not pair:
            errors.append('文件头字段格式错误')
            continue
        key, value = pair.groups()
        if key in fields:
            errors.append('文件头字段重复 ' + key)
        fields[key] = value
    for key in ('永久ID', '展示章号', '视角', '字数', '状态'):
        if (not legacy or key in ('永久ID', '状态') or key in fields) and not fields.get(key):
            errors.append('文件头缺少 ' + key)
    if fields.get('永久ID') != kid:
        errors.append('正文永久 ID 与文件名不一致，应为 ' + kid)
    number = fields.get('展示章号', '')
    if (number or not legacy) and not re.fullmatch(r'[1-9][0-9]*', number):
        errors.append('正文展示章号必须是正整数')
    elif number and display is not None and int(number) != int(display):
        errors.append('正文展示章号与大纲不一致')
    if viewpoint and (not legacy or '视角' in fields) and fields.get('视角') != viewpoint:
        errors.append('正文视角与大纲不一致')
    states = ('初稿', '已定稿', '待返工', '已废弃')
    if fields.get('状态') not in states:
        errors.append('正文状态不合法')
    if status in states and fields.get('状态') != status:
        errors.append('正文状态与大纲不一致')
    count = fields.get('字数', '')
    measured = len(re.sub(r'[\s#\-*>|]', '', body))
    if (count or not legacy) and (not re.fullmatch(r'[0-9]+', count) or int(count) != measured):
        errors.append('正文抬头字数与实测不一致')
    return errors


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def read_text(path, default=None):
    try:
        with io.open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        return default


def read_bytes(path, default=None):
    try:
        with io.open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return default


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    data = read_bytes(path)
    return sha256_bytes(data) if data is not None else None


def _fsync_dir(path):
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def atomic_write_bytes(path, data, mode=None):
    """同目录原子替换；未指定权限时保留已有普通文件的权限。"""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    if mode is None:
        try:
            old = os.lstat(path)
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISREG(old.st_mode):
                mode = stat.S_IMODE(old.st_mode)
    fd, temp_path = tempfile.mkstemp(prefix=".novel-write-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        _fsync_dir(parent)
    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def atomic_write_text(path, text, mode=None):
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def atomic_write_json(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)


def load_json(path, default=None):
    text = read_text(path)
    if text is None:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ProjectError("JSON 无法解析 %s %s" % (path, exc))


def load_json_lenient(path, default=None):
    """读不到或解析不了都返回 default。

    只用于**本身不承载恢复信息**的运行元数据，例如事务锁。锁文件是先
    O_EXCL 创建、后写内容的，进程在这个窗口被强杀会留下零字节文件；
    如果那样就让每条命令抛异常，等于用一个空文件把整个项目锁死。
    承载恢复信息的事务日志不能走这里，见 事务._read_journal。
    """
    text = read_text(path)
    if text is None:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def safe_relative(rel):
    if (not isinstance(rel, str) or not rel or
            any(ord(char) < 32 or ord(char) == 127 for char in rel)):
        return False
    if os.path.isabs(rel):
        return False
    norm = os.path.normpath(rel).replace(os.sep, "/")
    return norm != ".." and not norm.startswith("../") and norm == rel.replace(os.sep, "/")


def path_has_symlink(root, rel=""):
    """返回 root/rel 路径链上的首个符号链接；没有则返回 None。"""
    current = os.path.abspath(root)
    if os.path.islink(current):
        return current
    for part in rel.replace("\\", "/").split("/"):
        if not part:
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            return current
    return None


class UnsafePathError(ProjectError):
    pass


def safe_output_dir(project, rel, create=True):
    """把 project/rel 解析成一个**确定落在项目内**的真实目录，必要时创建。

    v3.4 只在内容扫描里拒绝符号链接，而 `_备份`、`_读取包` 这类**输出目录**
    本身被排除表跳过，从来没被检查过。实测把它们做成指向项目外的软链，
    backup 和 brief --write 会安静地把文件写到项目外面去。

    这里逐级 lstat：任何一级是符号链接、或者最终真实路径不在项目内，一律拒绝。
    所有写入入口共用这一个函数，不各写一份近似判断。
    """
    project = os.path.abspath(project)
    根真 = os.path.realpath(project)
    if os.path.islink(project):
        raise UnsafePathError("项目根目录本身是符号链接，拒绝写入 %s" % project)
    if not safe_relative(rel):
        raise UnsafePathError("非法输出路径 %r" % rel)
    current = project
    for part in rel.replace(os.sep, "/").split("/"):
        if not part:
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            try:
                指向 = os.readlink(current)
            except OSError:
                指向 = "读不到目标"
            raise UnsafePathError(
                "输出路径经过符号链接，拒绝写入：%s → %s\n"
                "  它可能把文件写到项目外面。把它换成真实目录再试。"
                % (os.path.relpath(current, project), 指向))
        if os.path.exists(current) and not os.path.isdir(current):
            raise UnsafePathError("输出路径上的 %s 不是目录"
                                  % os.path.relpath(current, project))
        if not os.path.exists(current):
            if not create:
                raise UnsafePathError("输出目录不存在 %s" % os.path.relpath(current, project))
            os.mkdir(current, 0o755)
    真 = os.path.realpath(current)
    if 真 != 根真 and not 真.startswith(根真 + os.sep):
        raise UnsafePathError("输出目录解析后落在项目外，拒绝写入 %s" % 真)
    return current


def load_chapter_policy(project):
    """读取项目内、候选提交不可修改的章节写入白名单。"""
    path = os.path.join(os.path.abspath(project), "chapter-policy.json")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ProjectError("缺 chapter-policy.json，先从母版同步项目")
    if value.get("format") != "novel-chapter-commit-policy":
        raise ProjectError("chapter-policy.json format 不合法")
    if value.get("schema_version") != 1:
        raise ProjectError("chapter-policy.json schema_version 不受支持")
    for key in ("core_mutable_files", "kid_files", "kid_patterns"):
        rows = value.get(key)
        if not isinstance(rows, list) or any(not isinstance(x, str) or not x for x in rows):
            raise ProjectError("chapter-policy.json 的 %s 必须是非空字符串数组" % key)
    return value


def canonical_digest(value):
    """对机器清单生成稳定、完整的 SHA-256。"""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def project_manifest_path(project):
    return os.path.join(os.path.abspath(project), "project.json")


def load_project(project, required=True):
    path = project_manifest_path(project)
    value = load_json(path)
    if value is None:
        if required:
            raise ProjectError("缺 project.json，请先运行迁移")
        return None
    errors = validate_project(value)
    if errors:
        raise ProjectError("project.json 不合法  " + "；".join(errors))
    return value


def validate_project(value):
    errors = []
    if not isinstance(value, dict):
        return ["根节点必须是对象"]
    if value.get("format") != PROJECT_FORMAT:
        errors.append("format 必须是 %s" % PROJECT_FORMAT)
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version 必须是 %d" % SCHEMA_VERSION)
    if not re.fullmatch(r"[0-9a-f]{32}", str(value.get("project_id", ""))):
        errors.append("project_id 必须是 32 位十六进制标识")
    decision = value.get("plugin_decision")
    if decision not in ("undecided", "none", "selected"):
        errors.append("plugin_decision 只能是 undecided、none 或 selected")
    plugins = value.get("enabled_plugins")
    if not isinstance(plugins, list) or any(not isinstance(x, str) for x in plugins):
        errors.append("enabled_plugins 必须是字符串数组")
    elif len(plugins) != len(set(plugins)):
        errors.append("enabled_plugins 不能重复")
    elif any(x not in SUPPORTED_PLUGINS for x in plugins):
        errors.append("enabled_plugins 含未知插件 %s" %
                      "、".join(sorted(x for x in plugins if x not in SUPPORTED_PLUGINS)))
    elif decision == "none" and plugins:
        errors.append("plugin_decision 为 none 时 enabled_plugins 必须为空")
    elif decision == "selected" and not plugins:
        errors.append("plugin_decision 为 selected 时至少启用一个插件")
    baseline = value.get("archive_required_from")
    if not re.fullmatch(r"K\d{4}", str(baseline or "")):
        errors.append("archive_required_from 必须是四位永久 ID")
    if not isinstance(value.get("system_version"), str) or not value.get("system_version"):
        errors.append("system_version 必须是非空字符串")
    voice = value.get("voice_profile")
    if voice is not None and voice not in VOICE_PROFILES:
        errors.append("voice_profile 只能是 %s" % "、".join(VOICE_PROFILES))
    errors.extend(_validate_initialization(value.get("initialization")))
    return errors


def _validate_initialization(value):
    """开书状态。**缺失是合法的**——v3.2 及更早的项目没有这一段，
    由 sync 或 migrate 按实际内容补写，绝不在校验阶段替它猜一个。"""
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["initialization 必须是对象"]
    errors = []
    status = value.get("status")
    if status not in INIT_STATES:
        errors.append("initialization.status 只能是 %s" % "、".join(INIT_STATES))
    mode = value.get("mode")
    if mode is not None and mode not in COOP_MODES:
        errors.append("initialization.mode 只能为空或 %s" % "、".join(COOP_MODES))
    digest = value.get("approved_sha256")
    if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
        errors.append("initialization.approved_sha256 必须是完整的 64 位 SHA-256")
    if status == "confirmed" and not digest:
        errors.append("initialization 为 confirmed 时必须保存批准摘要")
    if status != "confirmed" and digest:
        errors.append("只有 confirmed 状态才能保存批准摘要")
    return errors


def init_state(value):
    """返回项目的开书状态。没有这一段的旧项目按 legacy 处理，见 migrate/sync。"""
    block = (value or {}).get("initialization")
    if not isinstance(block, dict):
        return "legacy"
    return block.get("status") if block.get("status") in INIT_STATES else "legacy"


def load_foundation_policy(project):
    """开书候选的写入白名单。与 chapter-policy 同构，默认拒绝。"""
    path = os.path.join(os.path.abspath(project), "foundation-policy.json")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ProjectError("缺 foundation-policy.json，先从母版同步项目")
    if value.get("format") != "novel-foundation-commit-policy":
        raise ProjectError("foundation-policy.json format 不合法")
    if value.get("schema_version") != 1:
        raise ProjectError("foundation-policy.json schema_version 不受支持")
    rows = value.get("foundation_mutable_files")
    if not isinstance(rows, list) or any(not isinstance(x, str) or not x for x in rows):
        raise ProjectError("foundation-policy.json 的 foundation_mutable_files 必须是非空字符串数组")
    return value


def _project_title(project):
    config = read_text(os.path.join(project, "项目配置.md"), "") or ""
    for line in config.splitlines():
        if line.lstrip().startswith("|") and "书名" in line:
            cells = [x.strip().strip("*") for x in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[1] and cells[1] not in ("（填写）", "填写"):
                return cells[1]
    return os.path.basename(os.path.abspath(project))


def _outline_rows(project):
    text = read_text(os.path.join(project, "00_设定层", "03_分章大纲.md"), "") or ""
    rows = []
    for line in text.splitlines():
        match = re.match(r"^\|\s*(K\d{4})\s*\|\s*(\d+)\s*\|.*\|\s*([^|]*)\|\s*$", line)
        if match:
            rows.append((match.group(1), int(match.group(2)), match.group(3).strip()))
    return sorted(rows, key=lambda row: row[1])


def infer_archive_baseline(project):
    """找出章卡和梗概连续齐全的已定稿尾段。新书从 K0001 开始。"""
    finalized = [row[0] for row in _outline_rows(project) if "已定稿" in row[2]]
    if not finalized:
        return "K0001"
    complete_tail = []
    archive = os.path.join(project, "06_归档")
    for kid in reversed(finalized):
        card = any(os.path.isfile(os.path.join(archive, name)) for name in
                   ("章节卡_%s.md" % kid, "场景卡_%s.md" % kid))
        synopsis = False
        try:
            for name in os.listdir(archive):
                if name.startswith("梗概_%s" % kid):
                    data = read_text(os.path.join(archive, name), "") or ""
                    if data.strip():
                        synopsis = True
                        break
        except OSError:
            pass
        if not (card and synopsis):
            break
        complete_tail.append(kid)
    return complete_tail[-1] if complete_tail else "K%04d" % (
        max(int(kid[1:]) for kid in finalized) + 1)


def infer_plugins(project):
    enabled = []
    config = read_text(os.path.join(project, "项目配置.md"), "") or ""
    candidates = (
        ("suspense", "05b_线索兑现表.md", "05b_"),
        ("romance", "05c_情感节拍表.md", "05c_"),
        ("speculative", "05d_规则使用记录.md", "05d_"),
        ("serial", "05e_钩子与爽点表.md", "05e_"),
    )
    for plugin_id, filename, marker in candidates:
        if os.path.isfile(os.path.join(project, "01_运行层", filename)) and re.search(r"-\s*\[[xX]\].*" + marker, config):
            enabled.append(plugin_id)
    if enabled:
        return "selected", enabled
    if "未启用" in config:
        return "none", []
    return "undecided", []


def has_real_body(project):
    """项目是否已经进入创作阶段。

    **不能只看已定稿**：初稿、待返工同样说明书已经开写了。把这种项目标成
    draft 会在升级后突然拦住一本正在写的书。
    """
    outline = read_text(os.path.join(project, "00_设定层", "03_分章大纲.md"), "") or ""
    for line in outline.splitlines():
        if re.match(r"^\|\s*K\d{4}\s*\|", line):
            cells = [c.strip().replace("**", "") for c in line.strip().strip("|").split("|")]
            status = cells[-1] if cells else ""
            if any(word in status for word in ("已定稿", "初稿", "待返工")):
                return True
    body_dir = os.path.join(project, "05_正文")
    if os.path.isdir(body_dir):
        for name in os.listdir(body_dir):
            if not re.fullmatch(r"K\d{4}\.md", name):
                continue
            text = read_text(os.path.join(body_dir, name), "") or ""
            body = text.split("\n", 1)[1] if "\n" in text else ""
            if len(re.sub(r"[\s#\-*>|]", "", body)) >= 200:
                return True
    return False


def infer_init_block(project):
    """给没有开书状态的项目推断一个。已经在写的标 legacy，空项目标 draft。

    **绝不静默标成 confirmed**——那等于替用户签字。
    """
    return {
        "status": "legacy" if has_real_body(project) else "draft",
        "mode": None,
        "confirmed_at": None,
        "approved_sha256": None,
    }


def new_project_manifest(project, migrated_from=None):
    decision, plugins = infer_plugins(project) if migrated_from else ("undecided", [])
    now = utc_now()
    value = {
        "archive_required_from": infer_archive_baseline(project) if migrated_from else "K0001",
        "created_at": now,
        "enabled_plugins": plugins,
        "format": PROJECT_FORMAT,
        "plugin_decision": decision,
        "project_id": uuid.uuid4().hex,
        "schema_version": SCHEMA_VERSION,
        "system_version": SYSTEM_VERSION,
        "initialization": (infer_init_block(project) if migrated_from else {
            "status": "draft",
            "mode": None,
            "confirmed_at": None,
            "approved_sha256": None,
        }),
        "time_model": "free_text",
        "title": _project_title(project),
        "updated_at": now,
    }
    if migrated_from:
        value["migrated_from"] = migrated_from
    return value


def update_project(project, mutate):
    value = load_project(project)
    changed = json.loads(json.dumps(value, ensure_ascii=False))
    mutate(changed)
    changed["updated_at"] = utc_now()
    errors = validate_project(changed)
    if errors:
        raise ProjectError("更新后的 project.json 不合法  " + "；".join(errors))
    return changed


def tool_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_exclusions():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "排除表.py")
    spec = importlib.util.spec_from_file_location("novel_exclusions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_template(root):
    return os.path.isfile(os.path.join(root, "_工具", "我是母版.txt"))


def resolve_project(path):
    value = os.path.abspath(path or os.getcwd())
    if not os.path.isdir(value):
        raise ProjectError("项目目录不存在 %s" % value)
    return value
