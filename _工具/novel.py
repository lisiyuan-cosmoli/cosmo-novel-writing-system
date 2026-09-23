#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COSMO 小说创作系统 v3 统一命令入口。"""
from __future__ import print_function

import argparse
import importlib.util
import os
import re
import subprocess
import sys

import v2_core as core
import 事务


TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOL_DIR)


def _run(script, args):
    path = os.path.join(TOOL_DIR, script)
    # 子进程直接写同一个 fd。父进程被重定向时 print 是带缓冲的，不先刷
    # 就会出现"父进程的告警排在子进程输出后面"甚至被截断在管道尾部。
    sys.stdout.flush()
    sys.stderr.flush()
    result = subprocess.run([sys.executable, path] + list(args))
    return result.returncode


def _load(name):
    path = os.path.join(TOOL_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("novel_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project(path, 写入=True, 允许待恢复=False):
    """解析项目，并按命令性质决定遇到未完成事务时怎么办。

    v3.0 在这里无条件调用 recover_pending —— 那是一次**写入**：实测运行
    一次 status 就能把崩溃前的正文改回去。恢复必须由用户显式触发，所以
    这里只做两件事：只读命令报告状态，写入命令拒绝继续。
    """
    project = core.resolve_project(path)
    state = 事务.inspect(project)                    # 只读，任何情况下不写文件
    if state is not None:
        if 写入 and not 允许待恢复:
            if state["state"] == "corrupt":
                raise 事务.TransactionError(state["detail"])
            raise 事务.TransactionError(
                "发现未完成的事务 %s（%s）。%s。\n"
                "  确认现状后显式运行：python3 novel.py recover\n"
                "  在那之前本命令不会改动任何正式文件。"
                % (state["id"], state["phase"], state["detail"]))
        print("△ 存在未完成的事务 %s：%s" % (state["id"] or "（日志损坏）", state["detail"]))
        print("   本次不会自动恢复。需要恢复时显式运行 python3 novel.py recover。")
    core.load_project(project)
    return project


def build_parser():
    parser = argparse.ArgumentParser(
        prog="novel",
        description="COSMO 小说创作系统 v3。所有正式操作从这里进入。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start", help="在下载的当前文件夹开始创作；已有项目只查看状态")

    p = sub.add_parser("init", help="从母版新建项目")
    p.add_argument("target")

    p = sub.add_parser("doctor", help="项目体检")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--template", action="store_true")

    for name, help_text in (("brief", "生成开工简报（可写 K0008-K0010 一次规划多章）"),
                            ("package", "生成正式读取包（单章，或 K0019-K0021 一批）")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("kid")
        p.add_argument("project", nargs="?", default=".")
        p.add_argument("--write", action="store_true")
        p.add_argument("--profile", choices=("fast", "standard", "full"),
                       default="standard", help="读取档位：fast 最省，full 带更多历史")

    p = sub.add_parser("commit", help="验证候选并提交（单章，或 K0019-K0021 一批）")
    p.add_argument("kid")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--approve", help="试算输出的完整 CANDIDATE_SHA256")

    p = sub.add_parser("revise", help="全局修订：旧章、设定和账本一起预览与提交")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--review", action="store_true", help="根据当前改动生成关联核对清单")
    p.add_argument("--file", action="append", default=[])
    p.add_argument("--apply", action="store_true")
    p.add_argument("--approve", help="试算输出的完整 REVISION_SHA256")

    p = sub.add_parser("recover", help="恢复中断事务")
    p.add_argument("project", nargs="?", default=".")

    p = sub.add_parser("rollback", help="回退最近一次事务")
    p.add_argument("project", nargs="?", default=".")

    p = sub.add_parser("history", help="查看事务历史")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("status", help="一屏看清项目当前状态")
    p.add_argument("project", nargs="?", default=".")

    p = sub.add_parser("outline", help="大纲论证与滚动复盘，不自动判定质量")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--scope", choices=("auto", "opening", "small", "large"), default="auto")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--prompt", action="store_true")
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--refresh", action="store_true")
    group.add_argument("--reading", action="store_true")
    group.add_argument("--interview", action="store_true", help="阶段总结与作者开放访谈任务（只读）")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=4)

    p = sub.add_parser("feedback", help="运行问题来源、处理与验证记录")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--record")
    p.add_argument("--issue")
    p.add_argument("--prompt", action="store_true")

    p = sub.add_parser("discover", help="按需开书探索：已有材料、研究记录与候选归档")
    p.add_argument("project", nargs="?", default=".")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--import", dest="source")
    group.add_argument("--stage", action="store_true")
    group.add_argument("--prompt", action="store_true")

    p = sub.add_parser("voice", help="开书阶段的文风共创：定这本书是什么声音")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--prompt", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--foundation", action="store_true")
    p.add_argument("--recommend", action="store_true", help="输出给代理的文风参考推荐任务，不联网")
    p.add_argument("--apply", help="把这个文件写入 §A 正样本")
    p.add_argument("--profile", nargs="?", const="", help="查看或选择题材文风档（literary/webnovel/romance/genre）")

    p = sub.add_parser("repeat", help="重复动作检索（工具执行，替代手抄 grep）")
    p.add_argument("kid")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--window", type=int, default=3)
    p.add_argument("--card", action="store_true", help="输出可贴进章节卡的结论块")

    p = sub.add_parser("engine", help="读者引擎层状态；--prepare 把引擎卡与悬念账放进修订候选")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--prepare", action="store_true")
    p = sub.add_parser("arc", help="列出弧卡；--new A02 K0019-K0027 从模板建弧卡到修订候选")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--new", nargs=2, metavar=("编号", "范围"))
    p = sub.add_parser("hooks", help="末句检查材料与悬念账警报（只读）")
    p.add_argument("kid")
    p.add_argument("project", nargs="?", default=".")
    p = sub.add_parser("guide", help="调阅题材手册（不进读取包，按需调阅）")
    p.add_argument("plugin", nargs="?")
    p.add_argument("project", nargs="?", default=".")

    p = sub.add_parser("foundation", help="开书孵化：第一章之前的基础决定")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--prepare", action="store_true", help="建立 _候选/INIT")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--approve", help="试算输出的完整 FOUNDATION_CANDIDATE_SHA256")

    p = sub.add_parser("style", help="文风度量与去 AI 腔定位")
    p.add_argument("kid", nargs="?")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--baseline", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--draft")
    p.add_argument("--suspect")
    p.add_argument("--prompt", action="store_true")

    p = sub.add_parser("seal", help="封段：把已写成阶段摘要的章节事实移入 06b")
    p.add_argument("start")
    p.add_argument("end")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("backup", help="创建压缩备份")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--note", default="")

    p = sub.add_parser("restore", help="把备份恢复到新目录")
    p.add_argument("archive")
    p.add_argument("target")

    p = sub.add_parser("migrate", help="迁移旧项目")
    p.add_argument("project")
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("sync", help="同步 v2 项目的共享文件")
    p.add_argument("project")
    p.add_argument("--check", action="store_true")
    p.add_argument("--keep-local", action="append", default=[])
    p.add_argument("--replace-local", action="append", default=[])

    p = sub.add_parser("plugin", help="管理题材插件")
    p.add_argument("plugin_args", nargs=argparse.REMAINDER)

    sub.add_parser("release-test", help="运行发布级自测")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "start":
            if not os.path.lexists(os.path.join(ROOT, "project.json")):
                _load("新建项目").原地开始(ROOT)
            return _run("状态.py", [_project(ROOT, 写入=False)])
        if args.command == "init":
            if not core.is_template(ROOT):
                print("✗ init 只能从母版执行")
                return 2
            return _load("新建项目").main([args.target])
        if args.command == "doctor":
            if args.template:
                return _run("体检.py", [args.project, "--template"])
            return _run("体检.py", [_project(args.project, 写入=False)])
        if args.command in ("brief", "package"):
            project = _project(args.project, 写入=args.write)
            command = [project, args.kid]
            if args.command == "brief":
                command.append("--简报")
            if args.write:
                command.append("--写出")
            command.extend(["--档位", args.profile])
            return _run("读取包.py", command)
        if args.command == "commit":
            project = _project(args.project, 写入=args.apply)
            command = [project, args.kid]
            if args.apply:
                command.append("--落盘")
            if args.approve:
                command.extend(["--批准", args.approve])
            return _run("落盘.py", command)
        if args.command == "revise":
            project = _project(args.project, 写入=args.prepare or args.review or args.apply)
            command = [project]
            for flag in ("prepare", "review", "apply"):
                if getattr(args, flag):
                    command.append("--" + flag)
            for rel in args.file:
                command.extend(["--file", rel])
            if args.approve:
                command.extend(["--approve", args.approve])
            return _load("修订").main(command)
        if args.command == "recover":
            project = core.resolve_project(args.project)
            state = 事务.inspect(project)
            if state is None:
                print("✓ 没有待恢复事务")
                return 0
            if state["state"] == "corrupt":
                print("✗ %s" % state["detail"])
                return 1
            print("待恢复事务 %s（%s），涉及 %d 份文件。%s。"
                  % (state["id"], state["phase"], len(state.get("files") or []),
                     state["detail"]))
            for rel in (state.get("files") or [])[:20]:
                print("    · " + rel)
            事务.recover(project)
            return 0
        if args.command == "rollback":
            project = _project(args.project)
            tx = 事务.rollback_last(project)
            undone = tx.get("_undone", {})
            print("✓ 已撤销 %s（%s）" % (undone.get("id", "最近一笔"), undone.get("label", "")))
            print("  本次撤销自己也是一笔提交：%s" % tx["id"])
            print("  ※ 再运行一次 rollback 是**重做**，不是再退一章——它会撤销这次撤销。")
            print("    要看哪些提交当前生效，运行 python3 novel.py history。")
            return 0
        if args.command == "history":
            project = _project(args.project, 写入=False)
            rows = 事务.history(project, args.limit)
            if not rows:
                print("没有事务历史")
                return 0
            head = 事务.head(project)
            undone = 事务.undone_ids(project)
            print("%-30s %-26s %-10s %s" % ("事务", "内容", "阶段", "现在生效吗"))
            for row in rows:
                txid = row.get("id")
                if txid in undone:
                    mark = "已被撤销"
                elif txid == head:
                    mark = "← HEAD"
                else:
                    mark = ""
                print("%-30s %-26s %-10s %s" %
                      (txid, row.get("label", "")[:26], row.get("phase", ""), mark))
            print()
            print("※ 标「已被撤销」的那笔内容当前不在项目里。rollback 自己也是一笔提交。")
            return 0
        if args.command == "status":
            return _load("状态").main([_project(args.project, 写入=False)])
        if args.command == "feedback":
            project = _project(args.project, 写入=bool(args.record))
            command = [project]
            if args.record:
                command.extend(["--record", args.record])
            if args.issue:
                command.extend(["--issue", args.issue])
            if args.prompt:
                command.append("--prompt")
            return _load("运行反馈").main(command)
        if args.command == "outline":
            project = _project(args.project, 写入=bool(args.prepare or args.refresh))
            command = [project]
            for flag in ("prompt", "prepare", "refresh", "reading", "interview"):
                if getattr(args, flag):
                    command.append("--" + flag)
            command.extend(["--scope", args.scope])
            command.extend(["--offset", str(args.offset), "--limit", str(args.limit)])
            return _load("结构复盘").main(command)
        if args.command == "discover":
            project = _project(args.project, 写入=bool(args.prepare or args.source or args.stage))
            command = [project]
            for flag in ("prepare", "stage", "prompt"):
                if getattr(args, flag):
                    command.append("--" + flag)
            if args.source:
                command += ["--import", args.source]
            return _load("开书探索").main(command)
        if args.command == "voice":
            project = _project(args.project, 写入=bool(args.apply or args.profile))
            command = [project]
            for flag in ("prompt", "check", "foundation", "recommend"):
                if getattr(args, flag):
                    command.append("--" + flag)
            if args.apply:
                command.extend(["--apply", args.apply])
            if args.profile is not None:
                command.extend(["--profile", args.profile] if args.profile else ["--profile"])
            return _load("定声").main(command)
        if args.command == "repeat":
            project = _project(args.project, 写入=False)
            command = [args.kid, project, "--window", str(args.window)]
            if args.card:
                command.append("--card")
            return _load("重复").main(command)
        if args.command == "engine":
            project = _project(args.project, 写入=args.prepare)
            return _load("引擎").main(["engine", project] + (["--prepare"] if args.prepare else []))
        if args.command == "arc":
            project = _project(args.project, 写入=bool(args.new))
            return _load("引擎").main(["arc", project] + (["--new"] + list(args.new) if args.new else []))
        if args.command == "hooks":
            project = _project(args.project, 写入=False)
            return _load("引擎").main(["hooks", project, args.kid])
        if args.command == "guide":
            # 只给一个位置参数且不是插件 ID 时，那是项目路径（同 style 的处理）
            plugin = args.plugin
            if plugin and plugin not in core.SUPPORTED_PLUGINS and args.project == ".":
                args.project, plugin = plugin, None
            project = _project(args.project, 写入=False)
            command = ([plugin] if plugin else []) + [project]
            return _load("题材手册").main(command)
        if args.command == "foundation":
            写 = args.prepare or args.apply
            project = _project(args.project, 写入=写)
            command = [project]
            if args.prepare:
                command.append("--prepare")
            if args.apply:
                command.append("--apply")
            if args.approve:
                command.extend(["--approve", args.approve])
            return _load("开书").main(command)
        if args.command == "style":
            # --baseline / --draft / --suspect 都不需要章节 ID。此时只给一个位置
            # 参数的人给的一定是项目路径，别把它当成章节 ID 报"形如 K0001"。
            kid = args.kid
            if kid and not re.fullmatch(r"K\d{4}", kid) and args.project == ".":
                args.project, kid = kid, None
            # --baseline --apply 才写文件，其余全部只读
            project = _project(args.project, 写入=(args.baseline and args.apply))
            command = []
            if kid:
                command.append(kid)
            command.append(project)
            for flag in ("baseline", "apply", "prompt"):
                if getattr(args, flag):
                    command.append("--" + flag)
            for name in ("draft", "suspect"):
                if getattr(args, name):
                    command.extend(["--" + name, getattr(args, name)])
            return _load("文风").main(command)
        if args.command == "seal":
            project = _project(args.project, 写入=args.apply)
            command = [args.start, args.end, project]
            if args.apply:
                command.append("--apply")
            return _load("封段").main(command)
        if args.command == "backup":
            project = _project(args.project, 写入=False, 允许待恢复=True)
            if 事务.inspect(project) is not None:
                print("△ 项目存在未完成事务，这份备份保存的是**中断时的混合状态**。")
                print("   它可以用来保住现场，但不要当作一个自洽的项目版本。")
            return _load("备份").main(["create", project, "--note", args.note])
        if args.command == "restore":
            return _load("备份").main(["restore", args.archive, args.target])
        if args.command == "migrate":
            if not core.is_template(ROOT):
                print("✗ migrate 只能从新版母版执行")
                return 2
            command = [args.project]
            if args.apply:
                command.append("--apply")
            return _load("迁移项目").main(command)
        if args.command == "sync":
            if not core.is_template(ROOT):
                print("✗ sync 只能从新版母版执行")
                return 2
            command = [args.project]
            if args.check:
                command.append("--check")
            for rel in args.keep_local:
                command.extend(["--keep-local", rel])
            for rel in args.replace_local:
                command.extend(["--replace-local", rel])
            return _load("同步文件").main(command)
        if args.command == "plugin":
            if not args.plugin_args:
                print("✗ plugin 需要 list、none、install、verify 或 uninstall")
                return 2
            return _load("插件").main(args.plugin_args)
        if args.command == "release-test":
            if not core.is_template(ROOT):
                print("✗ release-test 只能从母版执行")
                return 2
            return _load("发布自测").main()
    except (core.ProjectError, 事务.TransactionError, RuntimeError) as exc:
        print("✗ %s" % exc)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
