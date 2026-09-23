# COSMO 小说创作系统 v6.0

**让长篇小说的设定、正文和修改，有据可查。** 作者：**LISIYUAN**。

面向作者与 AI 代理协作的本地创作系统。保存已经确认的故事状态，组织每章读取材料，核对跨章记录，并以候选、摘要批准和可恢复事务保护正式稿。核心只用 Python 标准库，不需要 API 密钥；它提供工作流与工具，写作和内容判断由作者与所用代理完成。

[项目介绍与交互示意](https://lisiyuan-cosmoli.github.io/cosmo-novel-writing-system/) · [下载版本](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/releases) · [使用说明](使用说明_给你自己看.md) · [English introduction](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/blob/main/README.en.md) · [参与贡献](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/blob/main/CONTRIBUTING.md)

网站是系统介绍和工作流演示，实际小说保存在你的本地项目中。适合需要连续性记录、候选审阅和可追溯修改的长篇创作；如果只需记几段随笔，可以先从自己的简单文档开始。

系统检查文件和记录，不能证明一章好看，也不能证明作者或代理已经认真读完。小说内容与创作决定由作者掌握。

## 开始使用

1. 从 [GitHub 下载完整系统](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/releases)，解压。
2. 把整个文件夹拖进 ChatGPT Codex、Claude Code 或 WorkBuddy 等 AI 代理的工作区。
3. 发送下面这句话，跟着 AI 的引导一步一步开始。

> 请先阅读这个文件夹里的 AGENTS.md 和 START_HERE.md，按其中的流程引导我开始创作一本小说。

作品会保存在当前文件夹，下次打开它就能继续写。

如果不想每次下载，可以在开始写作前备份一份空白模板。以后开新书时，复制这份模板即可；也可以从 GitHub 重新下载。

AI 需要能够读写文件并运行命令。普通聊天附件模式不够；拖入后如果工具尚未打开项目，选择该文件夹作为工作目录再发送提示词。Python 环境检查与首次初始化由代理按入口说明处理，不需要用户复制模板、运行脚本或填写终端命令。

### 运行环境

目前仅在 macOS 上完成验证，需要 Python 3.9 或以上。Windows、Linux 与 WSL 等其他环境尚未验证；如需使用，请自行适配并测试，确认文件保存、备份和恢复正常后再用于正式作品。AI 服务和工作区的具体权限取决于所用工具。使用云端工作区时，确认作品可以保存、导出或同步回来。

<details>
<summary>其他 AI 工具参考</summary>

你正在使用的 Codex 可以继续使用。下面补充几种同类工具，链接均为官方说明；按常见入口列举，同一工具可能有不止一种使用方式。选择一个自己熟悉的即可，不必全部安装。

这些是截至 2026-09-23 根据官方资料整理的候选工具，**不是 COSMO 的逐项兼容认证，也不是写作质量排名**。先在独立的新书副本中，让代理读取入口文件，运行 `python3 novel.py status` 和 `python3 novel.py doctor`，并确认能保存和重新读取修改。本版仅在 macOS 上完成验证，其他环境需自行适配与测试；工具本身能在 Windows 上运行，不代表本系统已支持原生 Windows。

| 工具与官方说明 | 常见入口 | 使用时确认 |
| --- | --- | --- |
| [Codex CLI](https://developers.openai.com/codex/cli/) | 终端中的项目代理 | 在新书目录启动，允许本次任务所需的文件与命令操作。 |
| [Claude Code](https://code.claude.com/docs/en/overview) | 终端、编辑器或桌面入口 | 选择新书目录；明确让它先读本项目入口文件。 |
| [WorkBuddy](https://www.workbuddy.ai/docs/workbuddy/Quickstart) | 桌面工作区 | 选择并授权新书文件夹，再确认当前环境可运行所需 Python 命令。 |
| [Cursor Agent](https://cursor.com/docs/agent/overview) | 编辑器内代理 | 打开新书文件夹，使用能编辑文件和运行终端命令的 Agent。 |
| [GitHub Copilot（VS Code 代理）](https://code.visualstudio.com/learn/agents/1-using-tools-with-agents) | 编辑器内代理 | 打开新书文件夹，确认代理的文件与终端工具可用。 |
| [Cline](https://docs.cline.bot/cline-overview) | 编辑器或终端 | 在新书工作区使用，核对文件修改和命令执行的权限。 |
| [Gemini CLI](https://geminicli.com/docs/reference/tools/) | 终端中的项目代理 | 在新书目录启动，确认文件工具与 shell 工具可用。 |

这里的 Claude Code 指项目代理。如果使用 Claude 的其他文件工作方式（部分官方资料仍称 [Cowork](https://support.claude.com/en/articles/14116274-organize-your-tasks-with-projects-in-claude-cowork)），按当前版本核对文件夹访问、Python 命令执行与项目保存能力。普通聊天中上传附件不等于接入了可操作的项目。工具、模型和订阅是不同选择，费用及 token 用量也需分别核对。


</details>

## 先了解项目边界

我是 LISIYUAN，不是职业小说作家，也不是专业开发者。我围绕自己的中文小说写作需求，通过 Vibe Coding 逐步搭建了这套系统，主要借助 ChatGPT 6 Astra 和 Claude Opus 5 完成开发与修改。项目仍在持续调整。现有测试用于核对列明的软件行为，不能当作专业软件质量保证或文学质量保证。

请先备份已有作品，在独立副本上用一章或一小段流程试用，确认能理解候选、批准与恢复的边界，再决定是否用于长期创作。需要保留完整工作现场时，另存整个项目副本；工具的常规备份不包含候选、候选存根和事务历史。

系统以中文为主。全球用户可以按许可使用和改造；英文网站与英文入门只翻译介绍，不代表内核已完成多语言适配。完整本地化需要一并核对：

- 中文目录与文件名、表头、章节状态和解析器使用的固定字段，不能只把显示文字翻译后就改名。
- 中文提示词、词表和正则，以及人物声音、重复片段和字数统计的适用口径；现有“字数”并非英文单词数。
- 改动后的读取包、提交批准、修订、同步与旧项目兼容，用合成项目重新验证。

## AI 服务、上下文与费用

本地核心没有内置付费 API，也不要求 API 密钥。你另外使用的 AI 助手、模型服务或订阅可能收费，费用与额度按所选服务处理。

`项目配置.md` 的初始读取包目标为 **58,000 字符**，硬上限为 **62,000 字符**，按包含包头和来源说明的成品文本计数。它限制的是单份读取包的字符数，不是 token 上限，也不保证能装进任意模型的上下文窗口。

同样的材料在不同模型、语言和分词方式下会产生不同 token 数；平台额外携带的系统提示、会话历史和工具信息也会占用上下文，AI 生成、重复交互和重试可能增加用量。先用小范围任务实测，为输出预留空间，按所选服务的计数、实际用量和账单核对，不用固定字符换算比例推算整本书的消耗。计量说明可参阅 [OpenAI 的 token 说明](https://help.openai.com/en/articles/4936856-understanding-and-counting-tokens) 与 [Anthropic 的 token 计数说明](https://platform.claude.com/docs/en/build-with-claude/token-counting)；预先计数也可能与实际用量略有差异。

## 6.0 的变化

- 修复提交后清理候选时丢失新保存内容的问题；成功提交的候选保留到可定位的存根目录。
- 备份拒绝静默跳过不可读目录，并在事务锁内核验采集前后的文件集合和内容；已有中断事务的现场备份单独标明。
- 插件安装、不启用和卸载使用锁内计划；多次回退后的历史状态重新按完整撤销关系计算。
- 正式读取包缺少必需前章时停止；状态与体检识别单章及批次候选；规划范围按展示章号解析。
- 文风导入与检查衔接 INIT／REVISE 候选，正式样本按既有摘要批准流程提交。
- 新书的读者引擎可选“通用”或“升级对抗”。通用模式围绕读者期待和阶段发展；对手、升级与爽感兑现只在选定相应模式时要求。旧引擎卡保持既有解释，不自动改变旧书路线。
- 统一榜单正文研究为可选，保留三章／十二章审查与作者交流，不新增批准层。

结构版本仍为 schema 2。升级内容及证据边界见 [交付验收报告](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/blob/main/交付验收报告.md)、[已知限制](已知限制.md)；历史变化见 [CHANGELOG](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/blob/main/CHANGELOG.md)。

## 给执行代理的流程说明

首次开书由代理运行 `python3 novel.py start`，在当前下载文件夹建立项目身份；再次运行只读取已有项目状态。软件审查或源码维护不执行此步骤，仍使用 `doctor --template`。原 `init <新目录>` 保留为可选维护命令，不是用户的开书步骤。

新书初始状态为 `draft`。讨论合作方式、已有材料、故事与结构、文风及读者引擎后，在 INIT 候选中整理十一项决定。

```text
python3 novel.py status
python3 novel.py foundation --prepare
python3 novel.py voice --profile literary
python3 novel.py voice --apply "/已选定的原创样本.md"
python3 novel.py voice --check --foundation
python3 novel.py foundation
python3 novel.py foundation --apply --approve <本轮完整摘要>
```

文风档可以选 literary、webnovel、romance 或 genre；档名不等于题材或创作模式。探索、研究与参考作品推荐按需开展，工具本身不联网，也不生成文学或市场结论。

旧书补做或重做开书时，文风命令加 `--foundation`，明确使用 INIT。仅有一份 INIT／REVISE 候选时默认接续它；两者并存时默认拒绝混用，需要先明确本轮处理的候选。

插件选择独立于文风与创作模式。可以不装，也可以组合安装。

```text
python3 novel.py plugin none
python3 novel.py plugin install suspense
python3 novel.py plugin install romance
python3 novel.py plugin install speculative
python3 novel.py plugin install serial
python3 novel.py guide serial
```

插件的逐章检查进入读取包，完整题材手册按需调阅。

## 日常写作

```text
python3 novel.py status
python3 novel.py doctor
python3 novel.py brief K0008-K0010 --write
python3 novel.py package K0008-K0010 --write --profile standard
python3 novel.py repeat K0008 --card
python3 novel.py style K0008 --prompt
python3 novel.py commit K0008-K0010
python3 novel.py commit K0008-K0010 --apply --approve <CANDIDATE_SHA256>
```

先确认阶段方向、准备章卡与正式读取包，再连续写成候选；执行两遍检查和独立审稿，回填相关记录。正式提交前完整展示正文、候选清单及同一摘要，取得明确批准。

默认每批三章，`batch_max` 最多五章；也可一章一批。永久 ID 负责内部引用，展示章号决定阅读与规划顺序。读取档位 fast／standard／full 只调整历史材料量，不降低提交与摘要保护。

每三章回看近期阅读体验，每十二章或弧末复盘阶段结构。先阅读正文，再与作者交流。榜单正文研究可选；不做说明理由，受限记录实际范围，不能把没有开展写成完成。

`style` 与 `repeat` 只定位可计算现象，不评分、不自动改稿。文风基线来自本书正样本和明确认可的章节；正式定稿不自动等于文风认可。

## 改稿、备份与恢复

修改旧章、设定或路线，先建立修订候选并做关联核对。

```text
python3 novel.py revise --prepare --file 00_设定层/01_固定设定.md --file 05_正文/K0001.md
python3 novel.py revise --review
python3 novel.py revise
python3 novel.py revise --apply --approve <REVISION_SHA256>
python3 novel.py backup --note "阶段完成"
python3 novel.py history
```

正常备份保存当前有效内容，候选、读取包、候选存根、事务历史和旧备份不重复收取。候选存根的位置会在提交结果中给出；正式稿与存根是不同用途，不把存根当待提交批准。

`rollback` 撤销最近一笔提交，它本身也成为一笔提交；再次运行会重做。未完成事务需要先核对现场，再显式 `recover`；系统不会自行恢复。损坏日志的现场备份只用于保住中断状态，不保证作品自洽。

事实记录可按需要用 `seal` 封段；先写阶段摘要并确认，再搬运，工具不自动提炼故事事实。

## 从旧版升级

schema 2 项目使用 `sync`，不重新开书，也不需要 `migrate`。从新版母版先查看差异，按项目范围授权执行。

```text
python3 novel.py sync "/项目路径" --check
python3 novel.py sync "/项目路径"
```

共享工具与规则会更新；正文、已填设定、候选和识别到的定制插件保留。共享文件存在本地修改时先报告冲突，不自动替换。6.0 保留原 5.0 的真实安装基线，升级后重新生成读取包与变更后的候选批准依据。细节见 [迁移说明](迁移说明.md)。

## 维护与验证

维护者先读 [贡献指南](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/blob/main/CONTRIBUTING.md) 和 [技术文档](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/blob/main/技术文档.md)，在副本中开发和测试。发布步骤见 [RELEASING](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/blob/main/RELEASING.md)。

```text
python3 novel.py doctor --template
python3 novel.py release-test
python3 scripts/check_public_release.py
```

发布自测覆盖新书、读取包、插件、提交、回退、恢复、备份、并发、同步及兼容路径。新增反例与现有测试一起运行；具体结果以本版验收报告为准，不用测试数量替代覆盖范围。

## 许可证

软件（Python、Shell、macOS `.command`、CSS、JavaScript、JSON、YAML 和仓库配置）使用 [Apache-2.0](LICENSE)；文档、空白模板、网站 HTML 与原创示意图使用 [CC BY-SA 4.0](LICENSE-docs)。具体范围见 [NOTICE](NOTICE)。公开署名统一为 **LISIYUAN**。

系统许可不要求你公开自己写的小说、填入的设定与账本，也不对这些用户内容提出权利要求。系统核心工具在本地运行，不自行上传作品；你主动交给 AI 服务、代码托管或其他工具的材料，按对应服务与操作处理。网页不加载第三方运行资源或统计脚本；点击外部链接会访问相应网站。
