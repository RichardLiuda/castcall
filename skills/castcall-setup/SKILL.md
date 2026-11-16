---
name: castcall-setup
description: Deploy or update a castcall cos 团建 / 团片 recruiting site — ask whether the user supplies the name list (text, CSV, spreadsheet, chat screenshot) or wants one drafted from the works' Bangumi character lists, then start the server with the list pre-filled and hand the user the web setup wizard link (they pick single / multi, event info, signup fields such as height / age / gender / sample photo, and the password); the wizard then auto-fetches covers and portraits and builds the 一图流 poster. Check the site and report. Use when the user asks to build a recruiting / roster page with castcall, add or change roles, or fill in artwork.
---

# castcall：从名单到招募页

标准流程在仓库根目录的 `AGENTS.md`「标准部署流程」（命令、名单格式、禁区都在那里），先读它。下面是你和用户之间的顺序：

1. **环境**：Python ≥ 3.9。一图流默认会生成；没有 `.venv-poster/` 时问用户「要不要装一图流依赖（约几百 MB，含 Chromium）？」，
   要就照 `AGENTS.md` 第 0 步装，不要就跳过。

2. **名单从哪来——必须先问**，用户已经给了名单就不用问：
   > 名单你来提供（文字、表格、截图都行），还是我按作品的角色表先整理一版？我整理的那版只有角色、全部空缺，CN 需要你补。
   - 用户提供：整理成 `AGENTS.md` 的文本格式。截图逐行识别「角色 + CN」，看不清的 CN 留空，别猜。
   - 你来整理：`python3 server/artsearch.py roster 作品A 作品B -o 名单.txt`；再问要不要加摄影 / 后勤等工作组。
   - **整理结果给用户过目，确认后才导入。**

2.5. **核对名字——建站之前**：`python3 server/artsearch.py names 名单.txt`。`✓` 能配（`→` 后是库里的写法）、`⚠` 像写错了、`✗` 作品里没这个名（后面列出实际角色，点一个就换）。
   `⚠` / `✗` 要**告诉用户并等他确认，不要自己改名单**；退出码非 0 = 有名字配不上。核对结果会绑定成角色 id 写进 `instance/uploads/art_bind.json`，后面配图按 id 取图、不再靠搜索。Bangumi 连不上会自动改用 AniList 核对，只有两个库都不通才算没法核对。详见 `AGENTS.md` 第 1.5 步。

3. **建站——走网页向导**：`python3 server/server.py --prefill 名单.txt --title "活动名"` 放后台跑，
   把它打印的 **6 位验证码**和 `http://127.0.0.1:5510/setup?t=…` 完整链接一起给用户（话术见 `AGENTS.md` 第 2 步；链接末尾带着验证码，念一遍是给人手输用的）。
   单团 / 多团、日期地点、**报名要填的信息**（身高 / 年龄 / 性别 / 样片 / 自定义题，选填或必填）、密码，都让用户在网页上选，不要在对话里逐项问。
   **发完链接立刻用 `AskUserQuestion` 卡住这一轮**（「向导填好、完成页都亮了吗？」）：环境会在一轮结束时杀掉后台的服务器，
   必须在同一轮里等用户回答、再做验收。服务器万一被杀，用同一条命令重启，链接和验证码都不变、没跑完的配图会自动补跑。详见 `AGENTS.md` 第 2 步。用户明确不要网页、或者没有浏览器时，才用 `init.py --import … --fields … --yes`。
   已经初始化过的实例改用 `python3 tools/import.py 名单.txt --dry` → 去掉 `--dry`。

4. **验收**：服务器已经在跑，按 `AGENTS.md` 第 3 步逐项核对。

5. **补漏**：被跳过的角色用 `artsearch.py search 角色名 --group 团名` 找候选给用户挑，或请用户在后台「找立绘」；
   图改过后重新「生成一图流」。

6. **交付**：一两句话汇报几个团、几个角色、几个空缺、配好几张图、哪些没配上、一图流有没有生成；
   配图和一图流的结果看 `instance/logs/server.log` 里 `firstrun` 那一行。告诉用户网址 `http://127.0.0.1:5510/`、右下角的锁是后台（密码是用户自己设的）、报名在「审核」里通过、报名表在后台「报名表」里改；要公开访问见 `docs/deploy.md`。
