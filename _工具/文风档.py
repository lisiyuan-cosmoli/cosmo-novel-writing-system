#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""4.1 题材文风档：一类书的默认写法。

文风档和题材插件分开选：一本网文也可以选文学档。题材插件只推荐默认档。
所选档决定三件事：进包的写作约束与第二遍语言检查（CONTROL）、
去 AI 腔词表里哪些类别对本书不算问题、style 是否提醒“正在往克制漂”。

没有记录文风档的旧项目按文学克制处理，行为与 4.0 相同。
"""
from __future__ import print_function

import io
import json
import os
import re
from collections import Counter

REGISTRY_REL = "04_题材插件/文风档/registry.json"
PROFILE_DIR = "04_题材插件/文风档"
DEFAULT = "literary"

# 表现力指标：只做粗略计数，用来发现“往克制漂”，不打分、不拦提交。
情绪词 = re.compile(r"高兴|开心|痛快|爽|委屈|憋屈|生气|火大|心疼|难受|慌了|急了|得意|解气|"
                  r"激动|兴奋|紧张|害怕|感动|想哭|笑出了?声|气得|恼火|烦死|舒坦|踏实")
内心词 = re.compile(r"心想|心里(?:想|说|骂|嘀咕|回|默念|一|直)|在心里|暗想|暗暗|她想|他想|我想")
反应词 = re.compile(r"所有人|众人|全场|围观|弹幕|评论区|群里|回头看|看了过来|愣住|傻眼|倒吸|"
                  r"炸了|惊呆|齐刷刷|目瞪口呆|鸦雀无声|议论")
漂移比例 = 0.5
重复上限 = 1   # 4.1.2：同一个情绪词一章用到第二次就提醒
样本建议字数 = 3000


def _json(P, rel):
    try:
        with io.open(os.path.join(P, rel), encoding="utf-8") as handle:
            return json.load(handle)
    except (IOError, OSError, ValueError):
        return None


def 登记表(P):
    data = _json(P, REGISTRY_REL)
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
        return {}
    return {p["id"]: p for p in data["profiles"] if isinstance(p, dict) and p.get("id")}


def 插件推荐(P, plugin_id):
    data = _json(P, REGISTRY_REL) or {}
    return (data.get("plugin_default") or {}).get(plugin_id)


def 当前档(P):
    """返回 (档 ID, 是否显式选择)。未选择时按文学克制处理。"""
    project = _json(P, "project.json") or {}
    value = project.get("voice_profile")
    if isinstance(value, str) and value:
        return value, True
    return DEFAULT, False


def 档信息(P, pid=None):
    pid = pid or 当前档(P)[0]
    return 登记表(P).get(pid)


def 档正文(P, pid=None):
    info = 档信息(P, pid)
    if not info:
        return None, None
    rel = "%s/%s" % (PROFILE_DIR, info["file"])
    try:
        with io.open(os.path.join(P, rel), encoding="utf-8") as handle:
            return rel, handle.read().replace("\r\n", "\n")
    except (IOError, OSError):
        return rel, None


def 允许类别(P):
    info = 档信息(P) or {}
    return list(info.get("allow_categories") or [])


def 外放档(P):
    return bool((档信息(P) or {}).get("expressive"))


def _正文(text):
    lines = [l for l in (text or "").split("\n") if not l.startswith("<!--") and not l.startswith("#")]
    return "\n".join(lines)


def 表现度量(text):
    body = _正文(text)
    字 = len(re.sub(r"\s", "", body)) or 1
    per = lambda n: n * 1000.0 / 字
    return {"情绪直写": per(len(情绪词.findall(body))),
            "内心独白": per(len(内心词.findall(body))),
            "旁人反应": per(len(反应词.findall(body))),
            "字数": 字}


def 漂移提醒(本章, 样本):
    """外放档：本章某项明显低于样本（不足一半）时提醒；样本本身没有这一项时不提醒。"""
    out = []
    for key in ("情绪直写", "内心独白", "旁人反应"):
        s, c = 样本.get(key, 0), 本章.get(key, 0)
        if s >= 1.0 and c < s * 漂移比例:
            out.append("%s 每千字 %.1f，样本 %.1f——正在往克制漂" % (key, c, s))
    return out


def 情绪词频(text):
    return Counter(情绪词.findall(_正文(text)))


def 重复提醒(本章, 前文=()):
    """外放档：同一个情绪词一章用了不止一次，或连着三章都在用，提醒换说法。

    专门对着“往克制漂”的反作用：那条提醒按固定词计数，补情绪时最省事的做法
    是补同一批计数词，写出来就是“激动得”“高兴得”“痛快”一章接一章。
    两条提醒一起响，才逼得出变化。只提醒，不拦提交。
    """
    out = []
    本 = 情绪词频(本章)
    多 = ['「%s」%d 次' % (w, n) for w, n in 本.most_common() if n > 重复上限]
    if 多:
        out.append('同一个情绪词本章用了不止一次：' + '、'.join(多))
    前 = [set(情绪词频(x)) for x in list(前文)[-2:]]
    if len(前) == 2:
        连 = sorted(w for w in 本 if all(w in s for s in 前))
        if 连:
            out.append('连着三章都在用：' + '、'.join('「%s」' % w for w in 连))
    return out


def 设置(P, pid):
    """写 project.json 的 voice_profile，走可恢复事务。"""
    import v2_core as core
    import 事务
    if pid not in 登记表(P):
        raise core.ProjectError("未知文风档 %s，可选：%s" % (pid, "、".join(sorted(登记表(P)))))
    current = core.load_project(P)
    updated = dict(current)
    updated["voice_profile"] = pid
    updated["updated_at"] = core.utc_now()
    data = (json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return 事务.apply_changes(P, {"project.json": data}, "voice profile %s" % pid)


def 报告(P):
    pid, 显式 = 当前档(P)
    表 = 登记表(P)
    print("文风档：%s（%s）%s" % (pid, (表.get(pid) or {}).get("name", "未知"),
                                  "" if 显式 else "——尚未选择，按文学克制处理"))
    for k in sorted(表):
        print("  %-9s %s%s" % (k, 表[k]["name"], "  ← 当前" if k == pid else ""))
    return 0
