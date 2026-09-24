# COSMO Novel Writing System v6.0

**From the first chapter to the last, help your AI keep track of the past.** By **LISIYUAN**.

[中文说明](README.md) · [English website](https://lisiyuan-cosmoli.github.io/cosmo-novel-writing-system/en/) · [Releases](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/releases)

This is a **concise English introduction**, not a full translation of the Chinese operating instructions. It covers obtaining the system, trying it and understanding its limits. The core operating instructions are still in Chinese.

COSMO is a long-form fiction workflow built for AI agents. Your AI drafts the prose, and you set the direction and make the calls. Characters, foreshadowing, the outline and every revision are recorded and checked by COSMO, and nothing enters the manuscript until you approve it.

It runs locally on the Python standard library, with no API key or account needed. I also hope it helps people without screenwriting or fiction-writing experience develop stories of their own. Passing a software check does not establish literary quality.

## Get started

1. [Download the complete system from GitHub](https://github.com/lisiyuan-cosmoli/cosmo-novel-writing-system/releases) and extract it.
2. Drag the whole folder into an AI agent workspace, such as ChatGPT Codex, Claude Code or WorkBuddy.
3. Send this prompt, then follow the agent’s guidance:

> Please read AGENTS.md and START_HERE.md in this folder, then follow their workflow to guide me through starting a novel.

Your story stays in this folder. Open it again next time to continue writing.

To avoid downloading the system each time, save an unused copy before you start writing. Duplicate that blank template for each new book, or download a fresh copy from GitHub whenever you need one.

The agent needs file access and command execution. A chat attachment alone is insufficient; if dragging the folder does not open a project, select it as the working folder before sending the prompt. The agent handles environment checks and initial setup through the entry instructions. You do not need to copy a template, run shortcut scripts or enter terminal commands yourself.

This release has only been tested on macOS and requires Python 3.9+. Windows, Linux, WSL and other environments have not been verified. To use COSMO there, adapt and test it yourself, including saving, backup and recovery, before using it for your manuscript. For cloud workspaces, confirm how to save, export or synchronize the project.

<details>
<summary>More AI tool options</summary>

You can keep using Codex. These are additional options, linked to official documentation and grouped by common entry point; some tools offer several interfaces. Choose one you are comfortable with. You do not need to install them all.

This list was checked against official documentation on 2026-09-23. **It is not a COSMO compatibility certification or a ranking of writing quality.** In a separate book copy, ask the agent to read the entry files, run `python3 novel.py status` and `python3 novel.py doctor`, and verify that it can save and reread changes. COSMO has only been tested on macOS; other environments require your own adaptation and testing, and a tool supporting Windows does not make COSMO work on native Windows.

| Tool and official documentation | Common entry point | What to check |
| --- | --- | --- |
| [Codex CLI](https://developers.openai.com/codex/cli/) | Project agent in a terminal | Start in the book directory and allow the file and command operations needed for the task. |
| [Claude Code](https://code.claude.com/docs/en/overview) | Terminal, editor or desktop | Select the book directory and explicitly ask it to read this project’s entry files first. |
| [WorkBuddy](https://www.workbuddy.ai/docs/workbuddy/Quickstart) | Desktop workspace | Select and authorize the book folder, then check that the environment can run the required Python commands. |
| [Cursor Agent](https://cursor.com/docs/agent/overview) | Agent in an editor | Open the book folder and use an Agent with file editing and terminal tools. |
| [GitHub Copilot (VS Code agents)](https://code.visualstudio.com/learn/agents/1-using-tools-with-agents) | Agent in an editor | Open the book folder and check that the agent’s file and terminal tools are available. |
| [Cline](https://docs.cline.bot/cline-overview) | Editor or terminal | Use the book workspace and check permissions for file changes and command execution. |
| [Gemini CLI](https://geminicli.com/docs/reference/tools/) | Project agent in a terminal | Start in the book directory and check that file and shell tools are available. |

Claude Code here means the project agent. If you use another file-enabled Claude workflow (still called [Cowork](https://support.claude.com/en/articles/14116274-organize-your-tasks-with-projects-in-claude-cowork) in some documentation), check folder access, Python command execution and project saving in your current version. Uploading chat attachments does not by itself connect an operable project. The tool, model and subscription are separate choices; check their costs and token usage separately.


</details>

For a new book, the agent runs `python3 novel.py start` in the downloaded folder. It registers the folder as a book without changing existing story material. Existing projects resume from their saved state. Software maintenance uses `doctor --template` instead. Review the story decisions and candidate before approving formal changes.

## A personal practice project

I'm **LISIYUAN**, neither a professional novelist nor a professional software developer. I built this system through Vibe Coding to support my own Chinese-language novel writing, using ChatGPT 6 Astra and Claude Opus 5 as my main tools for development and revision. The project is still being refined. Its tests verify specified software behavior; they are not professional assurance of software reliability or writing quality.

Back up existing work before trying the system. Start with a separate copy and a small task, such as one chapter, before relying on it for a long project. Keep a complete project copy when you need to preserve the working state: the normal built-in backup excludes candidates, retained candidate stubs and transaction history.

## Chinese is the primary language

The English website and this guide translate the introduction. The runtime has not been fully localized. Authors worldwide can use and adapt the project under its licenses, but changing the prose language alone does not make its language-specific checks suitable for that language.

A full localization needs coordinated work on:

- Chinese file paths, table headings, chapter states and fixed labels expected by parsers. Renaming them without updating the code can break the workflow.
- Chinese prompts, dictionaries and regular expressions, including character-voice analysis and repeated-text checks. The existing character count is not an English word count.
- Reading packages, approvals, revision and synchronization behavior, with regression tests on synthetic projects and older project formats.

Preserve the expected machine fields while experimenting. Try a synthetic project before adapting a real manuscript.

## AI services, context and cost

The local core has no built-in paid AI API calls and does not require an API key. Your chosen AI agent, subscription or model service may charge separately.

The initial configuration targets a reading package of **58,000 characters**, with a hard limit of **62,000 characters**. The count covers the assembled text, including its header and source notes. These are character limits for one package, not token limits or a guarantee that it fits a model's context window.

Tokenization varies by model, encoding and language. The host may also include system instructions, conversation history and tool information; additional AI generations, repeated interactions and retries can add to usage. Test a small representative task, leave room for output, and check the chosen service's counts and actual usage. There is no fixed character-to-token ratio or reliable universal cost per chapter. See [OpenAI's token explanation](https://help.openai.com/en/articles/4936856-understanding-and-counting-tokens) and [Anthropic's token-counting documentation](https://platform.claude.com/docs/en/build-with-claude/token-counting); estimates can differ from actual usage.

## Privacy and licenses

The core tools run locally and do not upload your manuscript. Material you deliberately send to an AI service or a hosting platform is handled by that service and your actions. Do not attach real manuscripts, credentials or private project records to public issues; use synthetic examples.

Software uses [Apache-2.0](LICENSE). Documentation, blank templates, website HTML and original diagrams use [CC BY-SA 4.0](LICENSE-docs), with the scope defined in [NOTICE](NOTICE). These licenses do not require you to publish your own novel or filled-in project data.

For contribution and release procedures, see [CONTRIBUTING](CONTRIBUTING.md) and [RELEASING](RELEASING.md). Repository and website addresses are the publication targets; the release guide distinguishes local verification from completed GitHub CI and deployment.
