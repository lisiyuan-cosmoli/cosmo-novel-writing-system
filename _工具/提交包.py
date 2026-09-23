#!/usr/bin/env python3
# 章节提交闸门。体检负责报告，闸门遇到错误会拒绝提交。
# 机器只能核对文件、状态与交叉记录，正文内容仍需用户完整阅读。
import io,os,re,sys,glob,subprocess,importlib.util
P  = sys.argv[1] if len(sys.argv)>1 else '.'
KID= sys.argv[2] if len(sys.argv)>2 else None
# 4.0 批次提交：落盘.py 对批内每章各跑一次，并用 --批末 告知批次最后一章。
# 状态快照只在批末推进一次，所以批内前几章的快照抬头按批末核对。
批末=None
if '--批末' in sys.argv[3:]:
    _i=sys.argv.index('--批末')
    批末=sys.argv[_i+1] if _i+1<len(sys.argv) and re.fullmatch(r'K\d{4}', sys.argv[_i+1]) else None
受信工具=os.environ.get('NOVEL_TRUSTED_TOOL_DIR') or os.path.join(P,'_工具')
if 受信工具 not in sys.path: sys.path.insert(0,受信工具)
import 章节卡
import v2_core as core
_ex=importlib.util.spec_from_file_location('ex', os.path.join(受信工具,'排除表.py'))
_EX=importlib.util.module_from_spec(_ex); _ex.loader.exec_module(_EX)
跳过=_EX.跳过
def rd(rel):
    p=os.path.join(P,rel)
    return io.open(p,encoding='utf-8').read() if os.path.exists(p) else ''

# ── 编号扫描：不限两位 ────────────────────────────────────
# v2 写死 C\d{2} / F\d{2}。到 F100 时正则会从 "F100" 里截出 "F10" 去查表，
# 查不到就静默放过；更糟的是一次 findall 会把同一行后面的 F07 一起吞掉。
# 这里先定位编号，再各自看它前后同一行内有没有关键词，编号位数不再有上限。
def 编号位置(文本, 前缀):
    return [(m.start(), m.group(1)) for m in
            re.finditer(r'(?<![A-Za-z0-9])(%s\d{2,})(?![0-9])' % 前缀, 文本 or '')]


def 同行窗口(文本, 位置, 长度, 后看, 前看):
    行首 = 文本.rfind('\n', 0, 位置) + 1
    行尾 = 文本.find('\n', 位置)
    行尾 = len(文本) if 行尾 < 0 else 行尾
    后 = 文本[位置:min(行尾, 位置 + 长度 + 后看)]
    前 = 文本[max(行首, 位置 - 前看):位置]
    return 前, 后


def 找账本行(账本, 编号):
    pat = re.compile(r'^\|\s*%s\s*\|' % re.escape(编号))
    return [l for l in 账本.split('\n') if pat.match(l.strip())]


# ── 世界规则的跨章提醒 ───────────────────────────────
# 不做规则版本子系统。规则本来就写在 固定设定 C 的「特殊规则」栏里，
# 这里只做一件机器做得到的事：本章正文命中了某条规则的关键词，
# 章节卡却没声明触碰它 —— 提醒人去看一眼，不替人判断冲突。
def 解析规则(设定文):
    """从 固定设定 C 的特殊规则栏抽出 [(编号, 摘要, 关键词)]。"""
    行 = [l for l in (设定文 or '').split('\n')
          if l.strip().startswith('|') and '特殊规则' in l]
    if not 行:
        return []
    格 = [x.strip() for x in 行[0].strip().strip('|').split('|')]
    正文 = 格[1] if len(格) > 1 else ''
    out = []
    for m in re.finditer(r'[①②③④⑤⑥⑦⑧⑨]|\bR\d{2}\b', 正文):
        起 = m.start()
        尾 = re.search(r'[①②③④⑤⑥⑦⑧⑨]|\bR\d{2}\b', 正文[起 + 1:])
        段 = 正文[起:起 + 1 + (尾.start() if 尾 else len(正文))]
        名 = re.search(r'\*\*([^*]{2,12})\*\*', 段)
        词 = [名.group(1)] if 名 else []
        词 += re.findall(r'「([^」]{3,12})」', 段)      # 规则里引号括起来的说法
        out.append((m.group(0), 段[:60], [w for w in 词 if w]))
    return out


def 规则提醒(设定文, 正文, 卡文):
    """返回 [(编号, 关键词)]：正文里出现了这条规则的关键词，章卡没声明。"""
    出 = []
    声明 = 卡文 or ''
    for 编号, 摘, 词表 in 解析规则(设定文):
        命中 = [w for w in 词表 if w and w in (正文 or '')]
        if not 命中:
            continue
        if 编号 in 声明 or any(w in 声明 for w in 命中):
            continue
        出.append((编号, '、'.join(命中)))
    return 出


# ── 事实与推断必须分行 ──────────────────────────────
# 推断与已成立事实分行，避免后续章节把猜测沿用为事实。
推断词 = ('推想', '推断', '判断', '坐实', '应该是', '可能是', '大概是',
          '似乎', '估计', '看来', '想必', '八成', '恐怕是')


def 查事实行(本章事实, kid):
    """返回 (正文事实行里的推断词命中, 行内容)。空表示干净。"""
    for line in (本章事实 or '').split('\n'):
        s = line.strip()
        if not s.startswith('- 正文事实'):
            continue
        命中 = [w for w in 推断词 if w in s]
        if 命中:
            return 命中, s
    return [], ''

拒=[]; 过=[]
def 判(名, 条件, 说明):
    (过 if 条件 else 拒).append((名, 说明))

# ── 0 先跑体检，任何 error 直接拒 ────────────────────────────
# 返回码、错误行与结论行一起核对，防止检查器崩溃后被误判为通过。
_hp=os.path.join(受信工具,'体检.py')
if not os.path.exists(_hp):
    判('体检脚本存在', False, _hp)
else:
    r=subprocess.run([sys.executable, _hp, P], capture_output=True, text=True)
    体检错=[l.strip() for l in r.stdout.split('\n') if l.startswith('✗')]
    有结论=bool(re.search(r'错误 \d+ ／ 注意 \d+ ／ 通过 \d+', r.stdout))
    判('体检跑完并给出结论行', 有结论, (r.stderr.strip().split('\n')[-1] if r.stderr.strip() else '没有结论行'))
    判('体检返回码为 0 或 1（不是崩溃）', r.returncode in (0,1), '返回码 %s'%r.returncode)
    判('体检无 error', 有结论 and not 体检错, 体检错 or '通过')

if not KID:
    print('用法：python3 _工具/提交包.py <项目文件夹> <永久ID>'); sys.exit(2)

大纲=rd('00_设定层/03_分章大纲.md')
快照=rd('01_运行层/04_状态快照.md')
事实=rd('01_运行层/06_事实记录.md')
# 悬疑插件的活动线索与已结清线索分开保存，互证时两份都读。
线索归档=rd('06_归档/线索归档.md')
线索=rd('01_运行层/05b_线索兑现表.md')+'\n'+线索归档
伏笔=rd('01_运行层/05_伏笔表.md')
配置=rd('项目配置.md')
正文p=os.path.join(P,'05_正文','%s.md'%KID)

# ── 1 七件东西必须同时到位 ──────────────────────────────
判('正文文件存在', os.path.exists(正文p), 正文p)
判('大纲已标已定稿', bool(re.search(r'^\|\s*'+KID+r'\s*\|.*已定稿', 大纲, re.M)), '大纲行')
# 封段之后本章条目会被移进 06b，所以两份都要查
事实b=rd('01_运行层/06b_事实记录_已归档段.md')
判('事实记录有本章条目（06 或 06b）', ('### %s（'%KID) in 事实 or ('### %s（'%KID) in 事实b, '06 / 06b 都没有')
# 悬疑插件专属检查只在插件启用时触发。
import importlib.util as _mu
_ms=_mu.spec_from_file_location('_mt', os.path.join(受信工具,'模块表.py'))
_MT=_mu.module_from_spec(_ms); _ms.loader.exec_module(_MT)
判('项目配置可读（模块启用情况能判断）', _MT.配置可读(P),
   '读不到 → **不等于"没启用模块"**，是判断不了')
_启用模块,_ = _MT.启用(P)
悬疑 = '悬疑' in _启用模块
if 悬疑:
    判('线索归档取到了（06_归档/线索归档.md 非空）', bool(线索归档.strip()),
       '取不到 → 线索互证会漏掉所有已揭晓条目')
if 批末 and 批末!=KID:
    判('快照抬头已推进到本批末章 %s'%批末, ('更新至 %s'%批末) in 快照, '04_状态快照 抬头')
else:
    判('快照抬头已推进到本章', ('更新至 %s'%KID) in 快照, '04_状态快照 抬头')
# 4.0 引擎层：引擎卡填好才启用；本章落在作者批准的弧卡范围内时，
# 必须在悬念账登记一条事实型章末钩子——核对的是弧卡里批准的章节拍有没有兑现。
# 不在任何弧卡里的章节不在这里阻断，由 status、package 与体检提醒先建弧卡。
import 引擎 as _EN
if _EN.启用(P, rd) and _EN.所属弧(P, KID, _EN.大纲序(P, rd)):
    _钩=_EN.钩子问题(P, KID, rd)
    判('悬念账登记了本章的事实型章末钩子', not _钩, '；'.join(_钩) or '通过')
# 流程审计取不到时停止，防止后续检查在零条记录上通过。
审计=rd('06_归档/流程审计.md')
判('流程审计表取到了（06_归档/流程审计.md 非空）', bool(审计.strip()),
   '取不到 → 下面那一项会变成"核零条"假通过')
_审计头=None; _审计行=None
for _line in 审计.splitlines():
    if not _line.strip().startswith('|'): continue
    _cells=[x.strip().replace('**','') for x in _line.strip().strip('|').split('|')]
    if _cells and _cells[0]=='永久 ID': _审计头=_cells
    if _cells and _cells[0]==KID: _审计行=_cells
判('流程审计表有本章步骤审计', bool(_审计头 and _审计行), '06_归档/流程审计.md')
章卡rel='06_归档/章节卡_%s.md'%KID
章卡p=os.path.join(P,章卡rel)
判('归档有章节卡', os.path.exists(章卡p), '06_归档')
if os.path.exists(章卡p):
    _dm=re.search(r'^\|\s*'+KID+r'\s*\|\s*(\d+)\s*\|', 大纲, re.M)
    _display=int(_dm.group(1)) if _dm else None
    _card_errors=章节卡.校验(rd(章卡rel), KID, _display, phase='commit')
    判('章节卡结构与硬证据完整', not _card_errors, _card_errors or '通过')
判('归档有梗概', bool(glob.glob(os.path.join(P,'06_归档','梗概_%s*'%KID))), '06_归档')

# ── 2 正文抬头必须自洽 ────────────────────────────────
if os.path.exists(正文p):
    raw=io.open(正文p,encoding='utf-8').read()
    _outline_rows = [章节卡._rows(line)[0] for line in 大纲.splitlines()
                     if re.match(r'^\|\s*' + KID + r'\s*\|', line)]
    _row = _outline_rows[0] if _outline_rows else []
    _header_errors = core.body_header_errors(raw, KID,
        int(_row[1]) if len(_row)>1 and _row[1].isdigit() else None,
        _row[2] if len(_row)>2 else None, '已定稿')
    判('正文身份与大纲一致', not _header_errors, _header_errors or '通过')
    hdr=raw.split('\n',1)[0]
    body=raw.split('\n',1)[1] if '\n' in raw else ''
    净=len(re.sub(r'[\s#\-*>|]','',body))
    m=re.search(r'字数:(\d+)', hdr)
    判('抬头字数＝实测净字', bool(m) and int(m.group(1))==净,
       '抬头 %s，实测 %d'%(m.group(1) if m else '无', 净))
    判('抬头状态＝已定稿', '状态:已定稿' in hdr, hdr[:70])
    # 审计只能证明记录结构完整，不能证明人真的执行或认真复读。
    if _审计头 and _审计行:
        _audit={name:(_审计行[i] if i<len(_审计行) else '') for i,name in enumerate(_审计头)}
        # 4.2：审计表允许精简。**列不在表头就跳过该项检查；列在表头仍然照旧严格校验。**
        # 旧项目保留 13 列，一项不少地过；新项目可以只留真正记事的那几列。
        _有列=lambda name: name in _审计头
        if _有列('步骤状态（1–7）'):
            _steps=_audit.get('步骤状态（1–7）','')
            _parsed=re.findall(r'([1-7])\s*(按过渡模式完成|完成|未触发|跳过)', _steps)
            _step_map={number:state for number,state in _parsed}
            判('流程审计 1–7 每一步都有合法状态', set(_step_map)==set('1234567'),
               _steps or '步骤状态为空')
            if _有列('跳过理由'):
                _reason=_audit.get('跳过理由','').strip()
                _needs_reason=[n for n,s in _step_map.items() if s in ('跳过','未触发')]
                判('流程审计的跳过或未触发有理由', not _needs_reason or bool(_reason and _reason not in ('—','无')),
                   ('步骤 %s 缺理由'%','.join(_needs_reason)) if _needs_reason else '无')
        _mode=_audit.get('模式','').strip()
        _card_mode=''
        _cm=re.search(r'^\|\s*工作模式\s*\|\s*([^|]+)\|', rd(章卡rel), re.M)
        if _cm: _card_mode=_cm.group(1).strip()
        if _有列('模式'):
            判('流程审计模式与章节卡一致', _mode in ('完整','过渡') and _mode==_card_mode,
               '审计 %s ／ 章卡 %s'%(_mode or '空',_card_mode or '空'))
        if _有列('判断次数'):
            _count=_audit.get('判断次数','').strip()
            判('流程审计判断次数是正整数', bool(re.fullmatch(r'\d+',_count)) and int(_count)>0,
               _count or '空')
        if _有列('本章耗时'):
            判('流程审计记录本章耗时', bool(_audit.get('本章耗时','').strip()), '为空')
        判('流程审计记录问题最先由谁发现', bool(_audit.get('问题最先由谁发现','').strip()), '为空')
        # 3.5 把 生成平台 拆成宿主平台／模型提供方／模型名称。旧项目留着
        # 生成平台 一列也算数——迁移不该把已经写好的审计行判成不合格。
        if _有列('宿主平台') or _有列('生成平台'):
            _平台 = (_audit.get('宿主平台','') or _audit.get('生成平台','')).strip()
            判('流程审计记录了宿主平台（旧项目的生成平台列同样算数）', bool(_平台), '为空')
        _audit_words=_audit.get('净字数','').strip()
        判('流程审计净字数＝正文实测净字', bool(re.fullmatch(r'\d+',_audit_words)) and int(_audit_words)==净,
           '审计 %s，实测 %d'%(_audit_words or '空',净))

# ── 3 跨账互证：一份账查另一份账 ───────────────────────────
# 3a 事实记录说兑现了某条线索，线索表就必须标已揭晓
# 封段之后，本章条目会落在 06b 而不是 06。两边都找。
# 当前段与已归档段都要查，章节可能已经封段。
本章事实=''
for _src in (事实, 事实b):
    mm=re.search(r'^###\s+'+KID+r'\b.*?(?=\n### |\n## |\Z)', _src, re.S | re.M)
    if mm: 本章事实=mm.group(0); break
判('取到了本章的事实记录条目正文（06 或 06b）', bool(本章事实.strip()),
   '两份都取不到 → 下面的互证会变成"核零条"假通过')

_设定 = rd('00_设定层/01_固定设定.md')
_正文全 = raw if os.path.exists(正文p) else ''
_规则待查 = 规则提醒(_设定, _正文全, rd(章卡rel))
if _规则待查:
    print('  △ 规则提醒（不阻断）：正文触到了这些世界规则，章节卡没声明：')
    for _编, _关 in _规则待查:
        print('      %s 关键词「%s」—— 确认本章用法与规则一致，或在章卡「连续性约束」里声明' % (_编, _关))

_推断命中, _推断行 = 查事实行(本章事实, KID)
判('正文事实行里没有推断词（推断归入角色判断）', not _推断命中,
   ('「正文事实」行含 %s。这些是判断不是事实，移到「角色判断」行并写明是谁的判断。'
    '原文：%s' % ('、'.join(_推断命中), _推断行[:110])) if _推断命中 else '干净')
声称兑现=set()
for _pos, _cid in 编号位置(本章事实, 'C'):
    _前, _后 = 同行窗口(本章事实, _pos, len(_cid), 20, 16)
    if re.search(r'兑现|揭晓', _后) or re.search(r'兑现|揭晓', _前):
        声称兑现.add(_cid)
未标=[]
for cid in sorted(声称兑现):
    row=找账本行(线索, cid)
    if not row: 未标.append('%s 线索表里没有这一条'%cid); continue
    if '已揭晓' not in row[0] and '锁死' not in row[0] and '灭失' not in row[0]:
        未标.append('%s 事实记录说兑现了，线索表仍是未揭晓'%cid)
if 悬疑:
    判('事实记录声称的兑现，线索表都标了（核 %d 条）'%len(声称兑现),
       not 未标,
       未标 or '本章没有声称兑现线索，属于合法的零事件')
    # 3a-2 公平推理：揭晓之前，这条线索有没有真的出现在正文里。
    # 这是机器做得到的那一半——比对章号、查一次登记；读者能不能推出来，
    # 仍然只有人判断得了（08 第二遍 + 悬疑插件逐章检查第 7 条）。
    _fs=_mu.spec_from_file_location('_fair', os.path.join(受信工具,'公平性.py'))
    _F=_mu.module_from_spec(_fs); _fs.loader.exec_module(_F)
    _正文号=set()
    for _f in glob.glob(os.path.join(P,'05_正文','K[0-9][0-9][0-9][0-9].md')):
        _m=re.search(r'K(\d{4})', os.path.basename(_f))
        if _m: _正文号.add(int(_m.group(1)))
    _本号=int(KID[1:]) if re.fullmatch(r'K\d{4}', KID) else None
    _公平阻断, _公平提醒 = _F.核对(rd('01_运行层/05b_线索兑现表.md'), 线索归档,
                                  事实, 事实b, _正文号, _本号)
    判('揭晓的线索都在更早的章里铺过（公平推理）', not _公平阻断,
       _公平阻断 or '本章及此前没有不公平的揭晓')
    for _t in _公平提醒:
        print('  △ 公平性提醒（不阻断）：%s' % _t)
else:
    print('  · 线索互证：未触发（本项目未启用悬疑模块）')
    print('  · 公平推理核对：未触发（本项目未启用悬疑模块）')

# 3b 快照更新记录里若写了"转入已兑现"，伏笔表就必须真的移了表
假称=[]
for _pos, fid in 编号位置(快照, 'F'):
    _前, _后 = 同行窗口(快照, _pos, len(fid), 24, 0)
    if not re.search(r'转入已兑现|已兑现', _后):
        continue
    命中=False; 表='待兑现'
    _当前子表='未兑现'
    for l in 伏笔.split('\n'):
        s=l.strip()
        if s.startswith('## '):
            _当前子表=s[3:].strip()
        if re.match(r'^\|\s*%s\s*\|'%re.escape(fid), s):
            命中=True
            表=_当前子表
            if '已兑现' not in _当前子表:
                假称.append('%s 快照说已兑现，伏笔表里它还在「%s」子表'%(fid,表))
    if not 命中:
        假称.append('%s 快照说已兑现，伏笔表里没有这一条'%fid)
判('快照说的伏笔移表，伏笔表真的移了', not 假称, 假称 or '无')

# 3c 图谱必须比所有账本新
g=os.path.join(P,'图谱.html')
_vc=importlib.util.spec_from_file_location('_vc', os.path.join(受信工具,'v2_core.py'))
_VC=importlib.util.module_from_spec(_vc); _vc.loader.exec_module(_VC)
_容差=_VC.GRAPH_STALE_TOLERANCE
旧=[]
if os.path.exists(g):
    gm=os.path.getmtime(g)
    for rel in ['00_设定层/03_分章大纲.md','01_运行层/04_状态快照.md','01_运行层/05b_线索兑现表.md',
                '01_运行层/05_伏笔表.md','01_运行层/06_事实记录.md',正文p]:
        f=rel if os.path.isabs(rel) else os.path.join(P,rel)
        if os.path.exists(f) and os.path.getmtime(f)>gm+_容差: 旧.append(os.path.basename(f))
判('图谱不比账本旧', os.path.exists(g) and not 旧, 旧 or '已重跑')

# 3d 已推翻的判断，不许有尸体留在账本里
# 被推翻的当前判断不得继续留在有效账本。
残留=[]
推表=rd('02_检查层/13_已推翻判断表.md')
关键字=[]
for ln in 推表.split('\n'):
    if not ln.strip().startswith('|') or '闸门 grep' in ln or '---' in ln: continue
    cs=[c.strip() for c in ln.strip().strip('|').split('|')]
    if len(cs)<4: continue
    for kw in cs[2].split('／'):
        kw=kw.strip().strip('`').strip()
        if kw: 关键字.append((cs[1][:28], kw))
扫=[]
for f in glob.glob(os.path.join(P,'**','*.md'), recursive=True):
    rel=os.path.relpath(f,P)
    if 跳过(rel) or rel.startswith('06_归档') or '13_已推翻判断表' in rel or '12_系统事故档案' in rel: continue
    扫.append((rel, io.open(f,encoding='utf-8').read()))
for 判断, kw in 关键字:
    try:
        pat=re.compile(kw)
    except re.error as e:
        # 坏正则不许把闸门崩掉。闸门崩溃 = 静默放行，那比不过更危险。
        残留.append('已推翻判断表里这个关键字不是合法正则：「%s」（%s）'%(kw,e)); continue
    for rel, body in 扫:
        for i, ln in enumerate(body.split('\n'), 1):
            if not pat.search(ln): continue
            # 明确标记为勘误历史的行可以引用旧说法。
            if re.search(r'勘误|已改|改记|原记|曾记|推翻|旧说法|外部审计|事故|查出|查实|一直写着', ln): continue
            # 同一表格行并列保存误解与更正时允许保留。
            if ln.lstrip().startswith('|') and re.search(r'❌|🔴|⚠️|不成立|超过证据|正确解读|实际上', ln): continue
            残留.append('%s：「%s」仍出现在 %s 第 %d 行'%(判断, kw, rel, i))
判('已推翻的判断无残留（第 5b 步）', not 残留, 残留 or '扫 %d 个关键字 × %d 份文件'%(len(关键字),len(扫)))

# ── 输出 ────────────────────────────────────────────
W=46
print('='*W); print('提交包闸门 ·', KID); print('='*W)
for n,d in 过: print('  ✓', n)
for n,d in 拒: print('  ✗', n, '：', d)
print('='*W)
if 拒:
    print('【不通过】%d 项。'%len(拒))
    print()
    print('※ 这道闸门能检查账面结果，不能替用户阅读正文。')
    print('   能：**挡住带着烂账进入下一章**。不补完，这一章不算收口。')
    if os.environ.get('LUOPAN_SHADOW'):
        print('   本次由 落盘.py 调用，**跑在影子上，正式文件尚未改动**。不过 ＝ 正式文件不会被替换。')
    else:
        print('   不能：**这样单独跑，它在写入之后**。请通过 novel.py commit 使用候选事务。')
        print('   → 要在写入之前拦，走：python3 _工具/落盘.py <项目> <永久ID> --落盘')
    print('   最近一次成功事务可用 python3 novel.py rollback 回退。')
    print('   阶段备份使用 python3 novel.py backup，不再复制整棵快照目录。')
    sys.exit(1)
print('【通过】%d 项全过。'%len(过))
print('※ 通过＝账目自洽，可以进入下一章。**不等于这一章的账写对了**——'
      '它验的是账面结果，不是写入过程。')
if not os.environ.get('LUOPAN_SHADOW'):
    print('※ 本次是写入后复核。要在写入前拦，走 落盘.py。')
print()
print('※ 提醒：这 %d 项一条都不查内容。'%len(过))
print('※ 阻力代价、人物误判、叙述者判语、文本自己数不对——闸门看不见，只有人读正文能看见。')
sys.exit(0)
