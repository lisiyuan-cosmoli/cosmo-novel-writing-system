#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取包自测 —— 持久化的必报警样本集。

规矩：**改过的检查，绿灯不算数。** 必须先喂一个明知该报警的样本，看它真的报了，才算测过。
所以这些样本不住在会话里，住在这里。

**本脚本自行生成最小夹具**，不读取任何具体项目的书名、人名、正文原句、真实章卡或真实活项——
上一版直接复制某个项目，于是它在那个项目里十二项通过，在母版直接崩溃。
**一个只能在一处跑通的自测，测的是那一处，不是这个工具。**

每个用例读**真实生成物**：控制台上写着「识别到两个片段」不能代替打开成品文件确认两段都在。
所有沙盘用 try/finally 清理，成功、失败、被中断都不留目录。

用法：  python3 _工具/读取包自测.py [<提供工具的目录>]
"""
import contextlib, io, os, re, shutil, subprocess, sys, tempfile, uuid

工具源 = os.path.dirname(os.path.abspath(__file__))
母版根 = os.path.dirname(工具源)
结果 = []


# 本轮运行的顶层沙盘，见 新书自测.py 里同名说明。
本轮沙盘 = tempfile.mkdtemp(prefix='读取包自测-运行-%s-' % uuid.uuid4().hex[:8])


def 断(名, 条件, 详=''):
    结果.append((名, bool(条件), 详))


def 写(p, t):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, 'w', encoding='utf-8').write(t)


def 章卡文本(kid, display, old='无'):
    samples = 'K0001 K0002' if display <= 3 else 'K0002 K0003 K0004'
    return f'''# 章节卡 {kid}（夹具）

## 基本信息

| 项 | 内容 |
|---|---|
| 永久 ID | {kid} |
| 展示章号 | {display} |
| 工作模式 | 完整 |
| 视角人物 | 甲 |
| 时间与上一章间隔 | 次日清晨 |
| 主要地点 | 乙街旧屋 |

## 本章变化

| 项 | 内容 |
|---|---|
| 章首状态 | 甲站在旧屋门外 |
| 本章主要行动 | 甲进屋寻找铜钥匙 |
| 阻力来自哪里 | 门锁生锈且丙正在靠近 |
| 越过阻力要付出的具体代价 | 甲必须砸锁并留下痕迹 |
| 章末不可逆变化 | 门锁被砸坏，丙看见甲进屋 |
| 结束时谁获得了什么 | 甲得到钥匙，丙得到目击事实 |
| 读者带走的问题或期待 | 钥匙能打开什么 |

## 必须出现的具体信息 🔒

1. 门槛下的铜钥匙
2. 生锈的门锁
3. 丙留在窗外的影子

## 硬锚点 🔒

| 项 | 内容 |
|---|---|
| 最后落在哪个动作或事实 | 甲把铜钥匙装进口袋 |
| 哪件事本章不能解释 | 钥匙对应哪扇门 |
| 哪个承诺必须兑现 | 后文说明丙为何跟来 |

## 知情范围

| 人物或读者 | 章首知道什么 | 本章新知道什么 | 仍然不知道或误解什么 |
|---|---|---|---|
| 甲 | 知道旧屋可能有钥匙 | 知道钥匙藏在门槛下 | 不知道钥匙用途 |

## 连续性约束

| 项 | 内容 |
|---|---|
| 需要照应的伏笔 ID | F01 铜钥匙 |
| 已启用插件需要推进的记录 | 无，夹具未启用插件 |
| 需要调阅的旧章 | {old} |
| 本章不能出现的人物、信息或地点 | 丁不能出场 |
| 伤势、物件、位置与时间限制 | 铜钥匙原在门槛下，时间为清晨 |

## 重复动作清单

| 项 | 记录 |
|---|---|
| 重复证据状态 | 已完成 |
| 取样章 | {samples} |
| 命中总行数 | 0 行 |
| 检索方式 | novel.py repeat --window 3（工具执行，非手抄） |
| 本章处理 | 无跨章重复，无需处理 |

## 场景清单

| 序号 | 地点与在场者 | 谁想得到什么 | 阻力与代价 | 场景结束时的变化 |
|---|---|---|---|---|
| 1 | 乙街旧屋，甲与窗外的丙 | 甲要拿到钥匙 | 砸锁会留下痕迹 | 甲拿到钥匙且被丙看见 |

## 走向选择

### 走向 A

| 项 | 内容 |
|---|---|
| 核心行动 | 甲砸锁进屋 |
| 所得 | 找到钥匙 |
| 代价 | 留下痕迹 |
| 章末状态 | 丙看见甲 |

### 走向 B

| 项 | 内容 |
|---|---|
| 核心行动 | 甲从窗户进入 |
| 所得 | 没有砸锁 |
| 代价 | 手臂受伤 |
| 章末状态 | 窗框留下血迹 |

### 走向 C

| 项 | 内容 |
|---|---|
| 核心行动 | 甲引开丙再返回 |
| 所得 | 无人目击进屋 |
| 代价 | 错过约定时间 |
| 章末状态 | 同伴开始怀疑甲 |

## 用户选择

| 项 | 内容 |
|---|---|
| 选择 | A |
| 选择理由 | 让所得与代价同时落到可见事实 |
| 是否含 AI 代拟内容 | 否 |

## 提交前核对

- [x] 两栏 🔒 已由用户提供或明确授权代拟
- [x] 阻力的代价足以影响人物选择
- [x] 知情范围与状态快照一致
- [x] 旧章调阅只使用必要片段
- [x] 重复动作清单由 novel.py repeat 实际生成，取样章、命中数与本章处理已经记录
- [x] 已启用插件需要更新的表已经列出
- [x] 章末变化能够写进大纲、快照或事实记录
'''


def 声音表文本(填好):
    """取母版的声音表模板；填好=True 时按模板原位补上一个人的四行。"""
    模板 = io.open(os.path.join(母版根, '00_设定层', '05_人物声音.md'), encoding='utf-8').read()
    if not 填好:
        return 模板
    块 = ['### 人物：甲',
          '- **句子倾向**：短句为主，急了反而更慢',
          '- **语言习惯**：把对方的话拆开再还回去',
          '- **绝不会说**：解释自己为什么知道',
          '- **变化线与锚**：A01 话少 → A02 更少。**锚：语气词密度不低于 0.12**',
          '']
    头 = 模板.split('## 人物表', 1)[0]
    尾 = '## 全书底噪' + 模板.split('## 全书底噪', 1)[1]
    return 头 + '## 人物表\n\n' + '\n'.join(块) + '\n' + 尾


def 夹具(目标=58000, 硬线=62000, 口径='成品包字符', 活项=None, 大纲章=None, 章卡=True,
         卡旧章='—', 卡ID='K0003', 声音表=None):
    """生成一个最小项目。**全部是编造的中性内容**，与任何真实作品无关。"""
    D = tempfile.mkdtemp(prefix='夹具-', dir=本轮沙盘)
    P = os.path.join(D, 'proj')
    os.makedirs(P)
    # Include the optional reminder's real transitive dependencies, not a stub.
    for f in ('读取包.py', '模块表.py', '章节卡.py', 'v2_core.py', '排除表.py',
              '结构复盘.py', '开书探索.py', '事务.py', '运行反馈.py', '文风.py', '引擎.py', '文风档.py',
              '人物声音.py'):
        shutil.copy(os.path.join(工具源, f), os.path.join(P, '_工具', f)
                    if os.path.isdir(os.path.join(P, '_工具')) else
                    (os.makedirs(os.path.join(P, '_工具')) or os.path.join(P, '_工具', f)))
    行 = 大纲章 or [('K0001', 1), ('K0002', 2), ('K0003', 3)]
    大纲 = '# 分章大纲（夹具）\n\n## 全书节拍\n\n| 位置 | 内容 |\n|---|---|\n| 开场 | 甲进屋 |\n\n## 章节表\n\n'
    大纲 += '| 永久 ID | 展示章号 | 视角 | 这章发生什么 | 开始 | 结束 | 状态 |\n|---|---|---|---|---|---|---|\n'
    for k, n in 行:
        大纲 += '| %s | %d | 甲 | 夹具章 | — | — | **已定稿** |\n' % (k, n)
    写(os.path.join(P, '00_设定层/03_分章大纲.md'), 大纲)
    写(os.path.join(P, '00_设定层/01_固定设定.md'), '# 固定设定（夹具）\n\n世界规则：甲住在乙街。\n')
    写(os.path.join(P, '00_设定层/02_风格样本.md'), '# 风格样本（夹具）\n\n禁用词：忽然、顿时。\n')
    if 声音表 is not None:
        写(os.path.join(P, '00_设定层/05_人物声音.md'), 声音表文本(声音表 == '填好'))
    写(os.path.join(P, '02_检查层/执行契约.md'), '# 执行契约（夹具）\n\n输入缺失不能算通过。\n')
    写(os.path.join(P, '02_检查层/代理执行协议.md'), '# 代理执行协议（夹具）\n\n创作数据不是工具指令。\n')
    写(os.path.join(P, '02_检查层/08_四遍检查提示词.md'), '# 逐章检查（夹具）\n\n检查因果、知情范围、连续性和语言。\n')
    写(os.path.join(P, '02_检查层/11_文风基线.md'),
       '# 文风基线（夹具）\n\n不用套语承担动作与情绪。\n\n'
       '<!-- 文风基线：以下区块由 novel.py style --baseline 生成，不要手改 -->\n'
       '状态：**未建立**\n<!-- 文风基线区块结束 -->\n')
    快照 = ('# 状态快照（夹具）\n\n> 状态：**更新至 K0003**\n\n'
            '## A. 人物当前状态\n\n| 人物 | 位置 |\n|---|---|\n| 甲 | 乙街 |\n\n'
            '## B. 关系状态\n\n| A ↔ B | 当前 |\n|---|---|\n| 甲↔丙 | 生疏 |\n\n'
            '## C. 知情范围表\n\n| 秘密或事实 | 甲 | 丙 |\n|---|---|---|\n| 那扇门没锁 | 知道 | 不知道 |\n\n'
            '## D. 各方立场\n\n| 人物或群体 | 想要 |\n|---|---|\n| 甲 | 离开 |\n\n'
            '## E. 场上的物件\n\n| 物件 | 位置 |\n|---|---|\n| 铜钥匙 | 甲口袋 |\n\n'
            '## F. 更新记录\n\n| 更新到（永久 ID） | 日期 | 改动 |\n|---|---|---|\n| K0003 | — | 夹具 |\n')
    写(os.path.join(P, '01_运行层/04_状态快照.md'), 快照)
    写(os.path.join(P, '01_运行层/05_伏笔表.md'), '# 伏笔表（夹具）\n\n| 编号 | 内容 |\n|---|---|\n| F01 | 铜钥匙 |\n')
    写(os.path.join(P, '01_运行层/06_事实记录.md'), '# 事实记录（夹具）\n\n### K0003（已确认）\n- 甲带走了铜钥匙。\n')
    for k, n in 行:
        写(os.path.join(P, '05_正文/%s.md' % k),
           '<!-- 永久ID:%s | 展示章号:%d -->\n\n# 夹具第 %d 章\n\n'
           '开头一句是 %s 独有的。\n中间这段只出现一次：铜钥匙压在门槛下。\n'
           '重复的句子。重复的句子。\n结尾一句是 %s 收束。\n' % (k, n, n, k, k))
    默认活项 = ('| # | 事项 | 阻塞 | 状态 |\n|---|---|---|---|\n'
                '| 1 | 夹具事项甲 | 🅿️提示 | 等着 |\n')
    八 = 活项 if 活项 is not None else 默认活项
    配 = ['# 项目配置（夹具）\n', '## 一、基本信息\n\n书名：夹具\n']
    if 目标 is not None:
        配.append('\n> 读取包目标：%d' % 目标)
    if 硬线 is not None:
        配.append('　读取包硬上限：%d' % 硬线)
    if 口径 is not None:
        配.append('　计量口径：%s\n' % 口径)
    配.append('\n## 三、每章生成时读取的文件\n\n- [ ] `01_运行层/05b_线索兑现表.md`（悬疑）\n')
    配.append('\n## 六、改稿\n\n无。\n')
    配.append('\n## 八、当前仍未了结的事\n\n' + 八)
    配.append('\n## 九、进度\n\n无。\n')
    写(os.path.join(P, '项目配置.md'), ''.join(配))
    if 章卡:
        展示 = dict(行).get(卡ID, 1)
        写(os.path.join(P, '06_归档/章节卡_%s.md' % 卡ID),
           章卡文本(卡ID, 展示, 卡旧章))
    return D, P


def 跑(P, *a):
    r = subprocess.run([sys.executable, os.path.join(P, '_工具', '读取包.py')] + list(a),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def 包目录(P):
    d = os.path.join(P, '_读取包')
    return sorted(f for f in os.listdir(d) if f.endswith('.md')) if os.path.isdir(d) else []


def 临时残留(P):
    d = os.path.join(P, '_读取包')
    return [f for f in os.listdir(d) if f.startswith('.tmp-')] if os.path.isdir(d) else []


def 路径行(o):
    return [l for l in o.split('\n') if l.startswith('READ_PACKAGE=')]


@contextlib.contextmanager
def 场(**kw):
    D, P = 夹具(**kw)
    try:
        yield P
    finally:
        shutil.rmtree(D, ignore_errors=True)


def main():
    # ① 无章卡简报成功写出
    with 场(章卡=False) as P:
        c, o = 跑(P, P, 'K0003', '--简报', '--写出')
        断('① 无章卡 · 简报成功并写出', c == 0 and len(包目录(P)) == 1 and 路径行(o),
           '退出码 %s，包 %d 份，路径行 %d' % (c, len(包目录(P)), len(路径行(o))))

    # ②③ 有章卡时，简报仍不含章卡、也不含定向旧章
    # ⚠️ 测试修准：第一版拿 K0001 当「定向旧章」，而它同时是 K0003 的**最近两章**之一，
    #    本来就该在包里。**测试自己写错了断言，不是工具漏了。**
    #    改用五章夹具：当前 K0005，最近两章是 K0003/K0004，定向旧章取 K0001。
    五章 = [('K0001', 1), ('K0002', 2), ('K0003', 3), ('K0004', 4), ('K0005', 5)]
    with 场(大纲章=五章, 卡ID='K0005', 卡旧章='K0001') as P:
        c, o = 跑(P, P, 'K0005', '--简报', '--写出')
        f = 包目录(P)
        t = io.open(os.path.join(P, '_读取包', f[0]), encoding='utf-8').read() if f else ''
        断('② 有章卡 · 简报成品里没有章卡', c == 0 and '章节卡_K0005' not in t, '退出码 %s' % c)
        # 3.6 契约变更：简报不再带任何旧章**正文**（此前带最近两章全文，
        # 与"简报不含旧章"的说法对不上，也占了简报 11.9%）。改带最近一章梗概。
        断('③ 有章卡 · 简报里一份旧章正文都没有（3.6 起改带梗概）',
           c == 0 and '05_正文/' not in t,
           '退出码 %s，仍含正文=%s' % (c, '05_正文/' in t))

    # ④ 无章卡正式失败，但仍报告基础项
    with 场(章卡=False) as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        断('④ 无章卡 · 正式失败但仍报基础项',
           c == 2 and '无法完成测量' in o and '01_固定设定.md' in o and not 包目录(P),
           '退出码 %s，含基础项=%s' % (c, '01_固定设定.md' in o))

    # ⑤⑥⑦ 参数与 ID 校验
    with 场() as P:
        c1, _ = 跑(P, P, 'K0003', '--简报', '--不存在的参数')
        c2, o2 = 跑(P, P, 'ch003', '--简报')
        c3, o3 = 跑(P, P, 'K0099', '--简报')
        断('⑤ 未知参数被拒绝', c1 == 2, '退出码 %s' % c1)
        断('⑥ 非法永久 ID 被拒绝', c2 == 2 and '四位数字' in o2, '退出码 %s' % c2)
        断('⑦ 永久 ID 不在大纲被拒绝', c3 == 2 and '不在分章大纲' in o3, '退出码 %s' % c3)

    # ⑧ K0100：大纲 / 图谱解析器 / 体检 / 读取包 四处都是第 100 章
    章 = [('K0001', 1), ('K0002', 2), ('K0100', 100)]
    with 场(大纲章=章, 章卡=False) as P:
        # ⚠️ 测试修准：体检还要 import 排除表.py，第一版没给夹具复制，于是体检直接崩溃，
        #    而测试把「崩溃」读成了「没打印那句话」。**先怀疑测试。**
        for f in ('图谱_解析.py', '体检.py', '排除表.py'):
            src = os.path.join(工具源, f)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(P, '_工具', f))
        import importlib.util as il
        ok图 = None
        gp = os.path.join(P, '_工具', '图谱_解析.py')
        if os.path.exists(gp):
            try:
                sp = il.spec_from_file_location('_g', gp)
                mg = il.module_from_spec(sp); sp.loader.exec_module(mg); mg.解析(P)
                ok图 = mg.KMAP.get('K0100')
            except Exception as e:
                ok图 = '解析异常 %r' % e
        ok检 = None
        bp = os.path.join(P, '_工具', '体检.py')
        if os.path.exists(bp):
            r = subprocess.run([sys.executable, bp, P], capture_output=True, text=True)
            _out = r.stdout + r.stderr
            ok检 = '全书 100 章' in _out          # 崩溃也算不通过，不容错
            if 'Traceback' in _out: ok检 = '体检崩溃：' + _out.strip().split(chr(10))[-1][:60]
        c, o = 跑(P, P, 'K0100', '--简报')
        断('⑧ K0100 · 大纲/图谱/体检/读取包都是第 100 章',
           ok图 == 100 and ok检 is True and c == 0,
           '图谱=%s 体检=%s 读取包退出=%s' % (ok图, ok检, c))

    # ⑨⑩ 配置字段
    with 场(目标=None) as P:
        c, o = 跑(P, P, 'K0003', '--简报', '--写出')
        断('⑨ 配置缺目标线 · 失败且不写出',
           c == 2 and '缺字段' in o and not 包目录(P), '退出码 %s' % c)
    with 场(目标=62000, 硬线=62000) as P:
        c, o = 跑(P, P, 'K0003', '--简报', '--写出')
        断('⑩ 目标线不小于硬线 · 失败', c == 2 and '必须小于硬上限' in o, '退出码 %s' % c)

    # ⑪⑫⑬ 三档容量
    with 场(目标=500000, 硬线=600000) as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        断('⑪ 软线以内 · 成功且报 ✓', c == 0 and '在目标' in o and len(包目录(P)) == 1, '退出码 %s' % c)
    with 场(目标=100, 硬线=600000) as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        断('⑫ 软硬线之间 · 成功并报告超出来源',
           c == 0 and '超目标' in o and '超出来自' in o and len(包目录(P)) == 1, '退出码 %s' % c)
    with 场(目标=100, 硬线=200) as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        断('⑬ 超硬线 · 失败、不建目录、不写文件、不报路径',
           c == 1 and not os.path.isdir(os.path.join(P, '_读取包')) and not 路径行(o),
           '退出码 %s，目录存在=%s，路径行=%d' % (c, os.path.isdir(os.path.join(P, '_读取包')), len(路径行(o))))

    # ⑭ 成品包字符 == 写出文件 len()
    with 场() as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        f = 包目录(P)
        t = io.open(os.path.join(P, '_读取包', f[0]), encoding='utf-8').read() if f else ''
        m = re.search(r'成品包字符：(\d+)', t)
        断('⑭ 文件头成品包字符 == 文件 len()',
           bool(m) and int(m.group(1)) == len(t),
           '头 %s ／ len %d' % (m.group(1) if m else '无', len(t)))

    # ⑭b—⑭e 5.0 声音层：三条路都要实测，模块级单测不能代替进包
    with 场(声音表='填好') as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        f = 包目录(P)
        t = io.open(os.path.join(P, '_读取包', f[0]), encoding='utf-8').read() if f else ''
        断('⑭b 声音表填好 · 正式包里有该条目',
           c == 0 and '05_人物声音.md' in t, '退出码 %s，包 %d 份' % (c, len(f)))
        断('⑭c 声音表填好 · 进包只带填好的人，不带模板说明与占位',
           '### 人物：甲' in t and '____' not in t and '## 怎么定' not in t,
           '含占位=%s，含说明=%s' % ('____' in t, '## 怎么定' in t))
        c2, o2 = 跑(P, P, 'K0003', '--简报', '--写出')
        f2 = [x for x in 包目录(P) if x not in f]
        t2 = io.open(os.path.join(P, '_读取包', f2[0]), encoding='utf-8').read() if f2 else ''
        断('⑭d 声音表填好 · 简报不带（与风格样本同口径）',
           c2 == 0 and '05_人物声音.md' not in t2, '退出码 %s' % c2)

    with 场(声音表='空') as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        f = 包目录(P)
        t = io.open(os.path.join(P, '_读取包', f[0]), encoding='utf-8').read() if f else ''
        断('⑭e 空模板 · 不进包但出提醒，且照常出包',
           c == 0 and '05_人物声音.md' not in t and '声音层未启用' in o,
           '退出码 %s，包里有声音表=%s，有提醒=%s'
           % (c, '05_人物声音.md' in t, '声音层未启用' in o))

    with 场() as P:          # 完全没有这个文件（同步不全的旧项目）
        c, o = 跑(P, P, 'K0003', '--写出')
        断('⑭f 没有声音表文件 · 照常出包，不报错也不提醒',
           c == 0 and len(包目录(P)) == 1 and '声音层未启用' not in o,
           '退出码 %s，包 %d 份' % (c, len(包目录(P))))

    # ⑮ 相同输入两次 → 文件名、摘要、内容完全一致
    with 场() as P:
        c1, _ = 跑(P, P, 'K0003', '--写出'); f1 = 包目录(P)
        t1 = io.open(os.path.join(P, '_读取包', f1[0]), encoding='utf-8').read()
        c2, _ = 跑(P, P, 'K0003', '--写出'); f2 = 包目录(P)
        t2 = io.open(os.path.join(P, '_读取包', f2[0]), encoding='utf-8').read()
        断('⑮ 相同输入两次 · 文件名/摘要/内容完全一致',
           c1 == c2 == 0 and f1 == f2 and len(f1) == 1 and t1 == t2,
           '文件 %s → %s，内容一致=%s' % (f1, f2, t1 == t2))

    # ⑯ 缺必需文件 · 一次报告全部
    with 场() as P:
        for r in ('00_设定层/02_风格样本.md', '01_运行层/05_伏笔表.md', '01_运行层/06_事实记录.md'):
            os.rename(os.path.join(P, r), os.path.join(P, r + '.bak'))
        c, o = 跑(P, P, 'K0003', '--写出')
        n = sum(1 for x in ('02_风格样本.md', '05_伏笔表.md', '06_事实记录.md') if x in o)
        断('⑯ 缺三份必需文件 · 一次全报（不是只报第一条）',
           c == 2 and n == 3 and not 包目录(P), '报出 %d / 3' % n)

    # ⑰⑱ 锚点
    with 场(卡旧章='K0001§「原文里没有这句话」→「也没有」') as P:
        c1, o1 = 跑(P, P, 'K0003')
    with 场(卡旧章='K0001§「重复的句子。」→「结尾一句」') as P:
        c2, o2 = 跑(P, P, 'K0003')
    断('⑰ 首锚缺失 / 首锚重复 · 都失败',
       c1 == 2 and '首锚' in o1 and '找不到' in o1 and c2 == 2 and '出现 2 次' in o2,
       '缺失 %s ／ 重复 %s' % (c1, c2))
    with 场(卡旧章='K0001§「开头一句」→「原文里没有的尾锚」') as P:
        d1, p1 = 跑(P, P, 'K0003')
    with 场(卡旧章='K0001§「中间这段只出现一次」→「重复的句子。」') as P:
        d2, p2 = 跑(P, P, 'K0003')
    with 场(卡旧章='K0001§「结尾一句」→「开头一句」') as P:
        d3, p3 = 跑(P, P, 'K0003')
    断('⑱ 尾锚缺失 / 重复 / 在首锚之前 · 都失败',
       d1 == 2 and '尾锚' in p1 and d2 == 2 and '出现 2 次' in p2 and d3 == 2 and '之前' in p3,
       '缺失 %s ／ 重复 %s ／ 倒置 %s' % (d1, d2, d3))

    # ⑲ 同章多片段 · 全部真的写进成品文件
    with 场(卡旧章='K0001§「开头一句」→「独有的。」、K0001§「中间这段只出现一次」→「门槛下。」') as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        f = 包目录(P)
        t = io.open(os.path.join(P, '_读取包', f[0]), encoding='utf-8').read() if f else ''
        断('⑲ 同章多片段 · 两段都真的在成品文件里',
           c == 0 and t.count('片段 1') == 2 and t.count('片段 2') == 2
           and '开头一句是 K0001 独有的。' in t and '中间这段只出现一次：铜钥匙压在门槛下。' in t,
           '退出码 %s，片段1×%d 片段2×%d' % (c, t.count('片段 1'), t.count('片段 2')))

    # ⑳ 阻塞行的状态说明含无关 ✅ 时仍阻塞
    表 = ('| # | 事项 | 阻塞 | 状态 |\n|---|---|---|---|\n'
          '| 1 | 夹具冲突 | 🔴阻塞 | 甲项已 ✅ 完成，但本条未裁定 |\n')
    with 场(活项=表) as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        断('⑳ 状态列含无关 ✅ · 仍然阻塞',
           c == 2 and '内容阻塞' in o and not 包目录(P), '退出码 %s' % c)

    # ㉑ 🔴阻塞 拦正式，不拦简报
    with 场(活项=表) as P:
        c1, _ = 跑(P, P, 'K0003', '--写出')
        c2, o2 = 跑(P, P, 'K0003', '--简报', '--写出')
        断('㉑ 🔴阻塞 · 正式退出 2、简报不受影响', c1 == 2 and c2 == 0 and 路径行(o2),
           '正式 %s ／ 简报 %s' % (c1, c2))

    # ㉒ §八 表头损坏 / 编号重复 / 未知标记
    坏 = [('表头损坏', '| 编号 | 事项 | 阻塞 | 状态 |\n|---|---|---|---|\n| 1 | 甲 | 🅿️提示 | — |\n', '表头'),
          ('编号重复', '| # | 事项 | 阻塞 | 状态 |\n|---|---|---|---|\n| 1 | 甲 | 🅿️提示 | — |\n| 1 | 乙 | 🅿️提示 | — |\n', '重复'),
          ('未知标记', '| # | 事项 | 阻塞 | 状态 |\n|---|---|---|---|\n| 1 | 甲 | 待定 | — |\n', '整格'),
          ('混合标记', '| # | 事项 | 阻塞 | 状态 |\n|---|---|---|---|\n| 1 | 甲 | 🔴阻塞 ✅ | — |\n', '混合标记不允许')]
    好 = True; 详 = []
    for 名, 表x, 关键 in 坏:
        with 场(活项=表x) as P:
            c, o = 跑(P, P, 'K0003', '--写出')
            通 = (c == 2 and 关键 in o and not 包目录(P))
            好 = 好 and 通; 详.append('%s=%s' % (名, '✓' if 通 else 'c%s' % c))
    断('㉒ §八 表头损坏/编号重复/未知标记/混合标记 · 都失败', 好, '／'.join(详))

    # ㉓ 写出阶段异常 · 不留临时文件、不留半份包
    with 场() as P:
        io.open(os.path.join(P, '_读取包'), 'w', encoding='utf-8').write('这是一个文件，不是目录')
        c, o = 跑(P, P, 'K0003', '--写出')
        残 = [f for f in os.listdir(P) if f.startswith('.tmp-')]
        断('㉓ 写出异常 · 退出 3、不留临时文件、不报路径',
           c == 3 and not 路径行(o) and not 残, '退出码 %s，残留 %s' % (c, 残))

    # ㉔ 多项错误同时存在 · 一次全报
    多 = ('| # | 事项 | 阻塞 | 状态 |\n|---|---|---|---|\n| 1 | 夹具冲突 | 🔴阻塞 | 未裁定 |\n')
    with 场(活项=多, 卡旧章='K0001§「原文里没有这句话」→「也没有」') as P:
        os.rename(os.path.join(P, '00_设定层/02_风格样本.md'),
                  os.path.join(P, '00_设定层/02_风格样本.bak'))
        c, o = 跑(P, P, 'K0003', '--写出')
        断('㉔ 多项错误并存 · 一次全报（缺文件＋锚点＋阻塞）',
           c == 2 and '02_风格样本.md' in o and '首锚' in o and '内容阻塞' in o and not 包目录(P),
           '缺件=%s 锚点=%s 阻塞=%s' % ('02_风格样本.md' in o, '首锚' in o, '内容阻塞' in o))

    # ㉕–㉚ 章节卡必须结构完整，不能只靠“文件非空”。
    def 改卡(P, transform):
        path = os.path.join(P, '06_归档/章节卡_K0003.md')
        text = io.open(path, encoding='utf-8').read()
        写(path, transform(text))
        return 跑(P, P, 'K0003', '--写出')

    with 场() as P:
        path = os.path.join(P, '06_归档/章节卡_K0003.md')
        写(path, '# 缩略章节卡\n\n| 需要调阅的旧章 | 无 |\n')
        c, o = 跑(P, P, 'K0003', '--写出')
        断('㉕ 缩略章节卡 · 正式包拒绝', c == 2 and '章节卡' in o and not 包目录(P), '退出码 %s' % c)
    with 场() as P:
        c, o = 改卡(P, lambda t: t.replace('| 永久 ID | K0003 |', '| 永久 ID | K0099 |'))
        断('㉖ 章节卡永久 ID 错配 · 拒绝', c == 2 and '不是当前章节' in o, '退出码 %s' % c)
    with 场() as P:
        c, o = 改卡(P, lambda t: t.replace('| 展示章号 | 3 |', '| 展示章号 | 30 |'))
        断('㉗ 章节卡展示章号错配 · 拒绝', c == 2 and '分章大纲' in o, '退出码 %s' % c)
    with 场() as P:
        c, o = 改卡(P, lambda t: t.replace('| 视角人物 | 甲 |', '| 视角人物 | （填写） |'))
        断('㉘ 章节卡占位符冒充填写 · 拒绝', c == 2 and '视角人物' in o, '退出码 %s' % c)
    with 场() as P:
        c, o = 改卡(P, lambda t: t.replace('| 选择 | A |', '| 选择 | |'))
        断('㉙ 章节卡没有用户选择 · 拒绝', c == 2 and '用户选择' in o, '退出码 %s' % c)
    with 场() as P:
        c, o = 改卡(P, lambda t: t.replace('| 章末状态 | 同伴开始怀疑甲 |',
                                             '| 章末状态 | |'))
        断('㉚ 完整模式缺一个走向 · 拒绝', c == 2 and 'A、B、C' in o, '退出码 %s' % c)

    # ㉛ 最近章节只取有效、已定稿且正文存在的前序章节。
    七章 = [('K0001', 1), ('K0002', 2), ('K0003', 3), ('K0004', 4),
            ('K0005', 5), ('K0006', 6), ('K0007', 7)]
    with 场(大纲章=七章, 卡ID='K0007', 卡旧章='无') as P:
        path = os.path.join(P, '00_设定层/03_分章大纲.md')
        text = io.open(path, encoding='utf-8').read()
        replacements = {'K0004': '未写', 'K0005': '待返工', 'K0006': '已废弃'}
        lines = []
        for line in text.splitlines():
            for kid, status in replacements.items():
                if line.startswith('| %s |' % kid):
                    cells = line.strip().strip('|').split('|')
                    cells[-1] = ' %s ' % status
                    line = '|' + '|'.join(cells) + '|'
            lines.append(line)
        写(path, '\n'.join(lines))
        c, o = 跑(P, P, 'K0007', '--写出')
        files = 包目录(P)
        package = io.open(os.path.join(P, '_读取包', files[0]), encoding='utf-8').read() if files else ''
        source = lambda kid: 'DATA ｜ 05_正文/%s.md ／ 全文' % kid
        valid = all(source(kid) in package for kid in ('K0002', 'K0003'))
        invalid = any(source(kid) in package for kid in ('K0001', 'K0004', 'K0005', 'K0006'))
        断('㉛ 废弃/返工/未写跳过，但最近已定稿正文完整进入',
           c == 0 and valid and not invalid, '退出码 %s，有效=%s，混入=%s' % (c, valid, invalid))
        os.unlink(os.path.join(P, '05_正文/K0003.md'))
        c, o = 跑(P, P, 'K0007', '--写出')
        断('㉛b 最近已定稿正文缺失必须停止，不能回退挑更早章',
           c != 0 and '05_正文/K0003.md' in o and 'READ_PACKAGE=' not in o, o[-400:])

    # ㉜ 展示章号是唯一顺序来源，插入与 ID 大小都不改变选择。
    重排 = [('K0090', 4), ('K0002', 1), ('K0010', 3), ('K0007', 2), ('K0050', 5)]
    with 场(大纲章=重排, 卡ID='K0050', 卡旧章='无') as P:
        c, o = 跑(P, P, 'K0050', '--写出')
        files = 包目录(P)
        package = io.open(os.path.join(P, '_读取包', files[0]), encoding='utf-8').read() if files else ''
        source = lambda kid: 'DATA ｜ 05_正文/%s.md ／ 全文' % kid
        selected = all(source(kid) in package for kid in ('K0010', 'K0090'))
        wrong = any(source(kid) in package for kid in ('K0002', 'K0007'))
        断('㉜ 插入与重排 · 按展示章号取最近两章', c == 0 and selected and not wrong,
           '退出码 %s，正确=%s，混入=%s' % (c, selected, wrong))

    # ㉝㉞ 直接拿**现行母版模板**跑开书初始化检查。
    #     v2 的这组样本全部用自造夹具，而夹具表头停在 v1 的名字，
    #     于是「模板改名 → 排除名单失效 → C/D/E 三节空转」这一整类问题
    #     在 43/43 全绿的情况下活了整整一个版本。凡是拿名单匹配模板的检查，
    #     都必须有一条样本咬住真模板本身。
    import importlib.util as _il
    _rp = _il.spec_from_file_location('_readpkg', os.path.join(工具源, '读取包.py'))
    _RP = _il.module_from_spec(_rp); _rp.loader.exec_module(_RP)
    母版根 = os.path.dirname(工具源)
    _tmp = tempfile.mkdtemp(prefix='真模板-', dir=本轮沙盘)
    try:
        for rel in ('项目配置.md', '00_设定层/01_固定设定.md', '00_设定层/02_风格样本.md',
                    '00_设定层/03_分章大纲.md', '01_运行层/04_状态快照.md'):
            dst = os.path.join(_tmp, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(os.path.join(母版根, rel), dst)
        os.makedirs(os.path.join(_tmp, '_工具'), exist_ok=True)
        写(os.path.join(_tmp, '_工具/专名表.txt'), '')
        空缺 = _RP.初始化缺项(_tmp, 'K0001')
        节点 = ['状态快照 %s 节还没有初始化' % x for x in ('A', 'B', 'C', 'D', 'E')]
        漏报 = [n for n in 节点 if not any(n in x for x in 空缺)]
        断('㉝ 真模板 · 空白状态快照 A–E 五节全部报缺', not 漏报,
           '漏报：' + '、'.join(漏报))

        快照p = os.path.join(_tmp, '01_运行层/04_状态快照.md')
        文 = io.open(快照p, encoding='utf-8').read()
        填 = {'## A.': '| 甲 | 乙街 | 清醒 | 离开 | 被认出 | K0001 |',
              '## B.': '| 甲 ↔ 丙 | 生疏 | 客气 | 上月起 | 一笔旧账 |',
              '## C.': '| 那扇门没锁 | 知道 | 不知道 | 不知道 | 不知道 |',
              '## D.': '| 甲 | 离开乙街 | 一把铜钥匙 | 等夜里 |',
              '## E.': '| 铜钥匙 | K0001 | 甲口袋 | 开后门 |'}
        for 头, 行 in 填.items():
            段 = re.split(r'\n## ', 文.split(头, 1)[1])[0]
            文 = 文.replace(头 + 段, 头 + 段.rstrip() + '\n' + 行 + '\n', 1)
        写(快照p, 文)
        补后 = _RP.初始化缺项(_tmp, 'K0001')
        误报 = [n for n in 节点 if any(n in x for x in 补后)]
        断('㉞ 真模板 · 五节填好之后一节都不再报', not 误报,
           '仍在报：' + '、'.join(误报))
    finally:
        shutil.rmtree(_tmp, ignore_errors=True)

    # ㉟㊱ 文风基线：必须作为 CONTROL 进包；缺它要停，不能"没有所以跳过"
    with 场() as P:
        c, o = 跑(P, P, 'K0003', '--写出')
        f = 包目录(P)
        包文 = io.open(os.path.join(P, '_读取包', f[0]), encoding='utf-8').read() if f else ''
        断('㉟ 文风基线作为 CONTROL 进正式包',
           c == 0 and 'CONTROL ｜ 02_检查层/11_文风基线.md' in 包文,
           '退出码 %s' % c)
    with 场() as P:
        os.unlink(os.path.join(P, '02_检查层/11_文风基线.md'))
        c, o = 跑(P, P, 'K0003', '--写出')
        断('㊱ 文风基线取不到时停止，不出包',
           c == 2 and '11_文风基线.md' in o and not 包目录(P),
           '退出码 %s' % c)

    shutil.rmtree(本轮沙盘, ignore_errors=True)

    W = 76
    print('=' * W); print('读取包自测（自生成最小夹具，不读取任何真实作品内容）'); print('=' * W)
    坏数 = 0
    for 名, 过, 详 in 结果:
        print('%s  %-44s %s' % ('✓' if 过 else '✗ 失败', 名, '' if 过 else 详))
        坏数 += 0 if 过 else 1
    print('=' * W)
    print('%d / %d 通过' % (len(结果) - 坏数, len(结果)))
    if 坏数:
        print('※ 有样本没按预期报警。**先怀疑测试，再怀疑被测对象**——')
        print('  一个「应该报却显示通过」的样本，和一个真的通过，长得一模一样。')
    return 1 if 坏数 else 0


if __name__ == '__main__':
    sys.exit(main())
