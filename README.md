# castcall

**cos 团建 / 团片招募用的名册站。** 一个页面看清「哪个团、哪个角色、谁来出」，空着的角色可以在线报名，组织者在后台审核通过后自动落座。

- **多团同时招募**（一次团建好几部作品）和**单团招募**（一个团的团片）都支持，同一份代码按团数自动切换。
- **只依赖 Python 标准库**：`python3 server/server.py` 就能跑，前端没有构建步骤。
- **数据在本地**：名册是一个 JSON 文件，报名和留言在 sqlite 里。
- **Notion 可选**：想在 Notion 里看表、审核，接上就行；不接也什么都不缺。
- **一图流海报**：建站时自动生成，把名册排成长图，网页版和 JPG 都有（要装可选依赖）。

## 部署

不管用哪种方式，都是同一套**标准流程**（详细步骤见 [docs/quickstart.md](docs/quickstart.md)）：

| 步骤 | 做什么 | 结果 |
|---|---|---|
| 0 装环境 | Python 3.9+；一图流依赖建议装进 `.venv-poster/`（见下） | — |
| 1 准备名单 | 用自己的名单，或按作品角色表先出一版（全部空缺） | `名单.txt` |
| 2 建站 | 带着名单启动 → 在**网页向导**里核对名单、选单团 / 多团、活动信息、报名要填什么、设密码 → 自动配图 → 生成一图流 | 有封面、立绘、海报的名册站 |
| 3 验收 | 核对名册、配图、报名、后台 | `http://127.0.0.1:5510/` |
| 4 上线 | systemd + 反向代理 | [docs/deploy.md](docs/deploy.md) |

```bash
git clone https://github.com/RichardLiuda/castcall.git && cd castcall
# 一图流依赖（可选但推荐；不装也能建站，只是跳过海报）
python3 -m venv .venv-poster && .venv-poster/bin/pip install -r requirements-poster.txt && .venv-poster/bin/playwright install chromium
```

所有选项都在**网页向导**里选：单团 / 多团、活动日期地点、报名的人要填什么（身高、年龄、性别、样片……每项可选填或必填）、管理密码。完成页会显示自动配图和一图流的进度。

### 方式一：交给 AI 助手（推荐）

把名单（文本、表格、截图都行）给它，或者只告诉它作品名，说「用 castcall 帮我搭招募页」。它会：

1. **先问你名单是自己提供，还是由它按作品的角色表整理一版**，整理好给你过目；
2. 带着名单启动服务器，给你一个向导链接——打开后名单已经填好，你在网页上选其余选项、设密码；
3. 等你建好，核对页面，汇报配图和一图流的结果。

- **Codex、Cursor 等**：会自动读仓库根目录的 [AGENTS.md](AGENTS.md)，不用额外设置。
- **Claude Code**：除了 AGENTS.md，还可以装上 [castcall-setup](skills/castcall-setup/SKILL.md) 这个 skill（一份写给 AI 的操作手册，
  遇到「搭招募页 / 导名单 / 配图」这类请求会自动按它做）：

  ```bash
  mkdir -p .claude/skills && cp -r skills/castcall-setup .claude/skills/     # 只在这个仓库里生效
  # 或者：mkdir -p ~/.claude/skills && cp -r skills/castcall-setup ~/.claude/skills/   # 所有项目都能用
  ```

  装好后在 Claude Code 里说「用 castcall 帮我搭招募页」，或者直接输入 `/castcall-setup`。

### 方式二：自己动手

```bash
python3 server/artsearch.py roster CLANNAD -o 名单.txt          # 没有名单时：按作品角色表出一版（全部空缺），改好再用
python3 server/server.py --prefill 名单.txt --title "活动名"     # 打开终端里打印的 /setup?t=… 链接，名单已经填好
```

没有名单就直接 `python3 server/server.py`，在向导里粘贴名单或者选「先空着」。

### 没有浏览器时：命令行

只能 ssh 的服务器、脚本批量建站，用 `init.py` 一次做完（效果和向导相同）：

```bash
python3 init.py --title "活动名" --import 名单.txt --fields "身高,样片*,性别" --yes   # * = 必填；密码随机生成，只打印一次
python3 server/server.py
```

`init.py` 不带参数就是一问一答。不想自动配图 / 生成一图流：加 `--no-art` / `--no-poster`。

### 之后

- 没配上的立绘：后台编辑角色 → 「找立绘」；批量重试：工具条「一键配图」。
- 名册或图片改过之后：工具条「生成一图流」重新生成。
- logo、标签页图标、一图流大图：工具条「站点素材」。

需要 Python 3.9 以上，macOS / Linux / Windows 都行。

## 页面上有什么

| | 说明 |
|---|---|
| 名册 | 多团：封面卡墙，点开看席位；单团：一整页，招募中的角色在最前面，点一下就报名 |
| 搜索 | 按角色名或 CN 找人 |
| 缺人看板 | 所有空缺 / 角色未定 / 还没立绘的席位，按团列出 |
| 报名 | 空缺席位上点「报名」，填 CN 和联系方式，以及团长选的身高 / 年龄 / 性别 / 样片 / 自定义题（可选填）；**不会直接占座**，后台通过才写进名册 |
| 倒计时 | 填了开场时间就显示，活动结束后自动消失 |
| 留言区 | 默认先显示、后台可隐藏；也可以改成先审后发 |
| 一图流 | 建站时自动生成（装了依赖的话），抬头有入口；改了名册在后台重新生成 |
| 成员照片 | 可选：已定的成员上传本人照片，审核后显示在角色卡上 |

## 文档

- [docs/quickstart.md](docs/quickstart.md)：标准部署流程（从零到上线）
- [AGENTS.md](AGENTS.md) / [skills/castcall-setup](skills/castcall-setup/SKILL.md)：给 AI 助手的部署说明
- [docs/config.md](docs/config.md)：`site.json` 每个字段、名册格式、单团 / 多团怎么切
- [docs/notion.md](docs/notion.md)：接 Notion 的手把手教程
- [docs/poster.md](docs/poster.md)：一图流（要装 Pillow + Playwright）
- [docs/troubleshooting.md](docs/troubleshooting.md)：搭建时容易卡住的地方
- [docs/deploy.md](docs/deploy.md)：放到服务器上（systemd + 反向代理）

## 目录

```
server/    HTTP 服务、名册保存链路、sqlite、Notion 适配器
web/       前端（原生 HTML/CSS/JS）
poster/    一图流生成脚本
examples/  示例配置和名册
tests/     python3 -m unittest discover -s tests
instance/  ← 你的数据（init.py 生成，已在 .gitignore 里，不要提交）
```

## 许可证

代码以 [MIT](LICENSE) 发布。**许可证不覆盖任何图片和素材**：你上传的封面、立绘、logo 版权归各自的权利人，仓库里也不附带任何第三方素材。

castcall 从一个真实活动的名册站（keyroster）里抽出来，去掉了活动专属的内容和数据。
