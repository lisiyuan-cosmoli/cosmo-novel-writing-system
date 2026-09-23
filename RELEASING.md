# 发布说明

公开署名为 LISIYUAN。首次开源从已核验的干净快照初始化新 Git 仓库，不推送内部开发历史、备份、真实小说、候选或私人验收日志。后续版本在这个公开历史上维护。

## 本地验收与打包

在母版根目录运行：

```sh
python3 novel.py doctor --template
python3 novel.py release-test
python3 scripts/check_public_release.py
python3 scripts/build_release.py --output-dir ../release-output
```

`scripts/public-files.json` 是公开文件白名单。新增发行文件时审阅后更新它；检查器拒绝未知文件、符号链接、运行目录、作品产物及常见凭据模式。维护者可用 `--deny-file /私下保存的词表.txt` 附加原项目专名和原句，每行一项，词表不可放入仓库。工具不能发现所有隐私或判断材料授权，提交前仍须审阅实际差异、署名和示例来源。公开说明不写真实作品进度、精确操作统计、作者答复或私人故障经历；需要说明故障时改用通用机制或明确标注的合成案例。检查提交邮箱、旧分支/标签、Release 附件及 Actions 记录，避免正文清理后仍由元数据泄露身份。

打包生成含单一顶层目录的 ZIP、文件摘要清单和 SHA256SUMS；压缩包不含 .git。打包检查不能替代全量测试，测试仍须单独执行并记录。

修改版本、清单或同步规则时，核对 `system-manifest.json` 与内核版本；兼容基线保留已发布版本的真实文件摘要。修改文档、网站和许可后也要验证相关链接及命令。

## GitHub 首次发布

1. 在 `lisiyuan-cosmoli` 下创建公开仓库 `cosmo-novel-writing-system`，推送已核验的干净历史。提交作者使用 LISIYUAN 和 GitHub noreply 地址。
2. About 简介可用：“面向作者与 AI 代理协作的本地长篇小说创作系统：设定管理、读取包、候选审阅与可恢复提交。”主题可选 `creative-writing`、`novel-writing`、`python`、`local-first`。
3. 等待 CI 的 macOS / Ubuntu、Python 3.9 / 3.14 矩阵实际完成。配置了工作流不代表测试通过；失败先修复，不展示通过徽章。
4. 审阅变更并创建 `v6.0` 标签与 Release。发行说明写清功能、使用入口、实测环境和限制，附 ZIP、清单及 SHA256SUMS。GitHub 自动生成的源码归档与维护者打包文件分别标明。
5. Settings → Pages 选择 GitHub Actions，再手动运行 Publish website。只部署 `docs/`。部署成功后核验页面与下载链接，再把 About 网站设为 `https://lisiyuan-cosmoli.github.io/cosmo-novel-writing-system/`。
6. 如启用 GitHub 私有漏洞报告，先核验入口可用，再更新 SECURITY 中的联系说明。

网站工作流默认只手动运行，并限制为主分支。README 和网站中的 GitHub / Pages 地址是固定发布目标，仓库与部署建立前可能尚不可访问。

## 网站预览与介绍

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory docs
```

浏览器打开 `http://127.0.0.1:8000/`，英文版在 `/en/`；两种语言的首页和系统图解可以相互切换。网站是介绍与流程演示，没有在线写作后台。英文页面和 README.en.md 提供项目入门，核心模板、路径与检查规则仍以中文为主。

发布前核对中英文的功能、限制与下载入口一致，说明作者的个人项目背景、先用副本试用的建议、外部 AI 服务的用量差异，以及下载文件夹后发送一句提示词的用法。不要把网站双语写成系统已完成多语言适配。

发布介绍可用网站截图配具体场景：“写到中段后，设定改过几次，候选稿和正式稿开始混在一起。COSMO 把这些状态放回可检查的本地文件，再让每次正式修改经过同一份候选与摘要。”随后放仓库、入门和版本链接，说明适用人群与边界；不把测试数量、AI 评论或演示数据宣传成真人读者评价。
