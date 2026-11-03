---
name: castcall-setup
description: Deploy or update a castcall cos 团建 / 团片 recruiting site — ask whether the user supplies the name list (text, CSV, spreadsheet, chat screenshot) or wants one drafted from the works' Bangumi character lists, import it, auto-fetch covers and portraits, generate the 一图流 poster, start and check the site. Use when the user asks to build a recruiting / roster page with castcall, add or change roles, or fill in artwork.
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

3. **建站**：问清活动名称（日期、开场时间、地点、联系方式有就填）；密码不要自己编。
   `python3 init.py --title … --import 名单.txt … --yes`：建完会自动配图、再生成一图流，把最后两行总结转告用户。
   已经初始化过的实例改用 `python3 tools/import.py 名单.txt --dry` → 去掉 `--dry`。

4. **启动并验收**：`python3 server/server.py`，按 `AGENTS.md` 第 3 步逐项核对。

5. **补漏**：被跳过的角色用 `artsearch.py search 角色名 --group 团名` 找候选给用户挑，或请用户在后台「找立绘」；
   图改过后重新「生成一图流」。

6. **交付**：一两句话汇报几个团、几个角色、几个空缺、配好几张图、哪些没配上、一图流有没有生成；
   告诉用户网址 `http://127.0.0.1:5510/`、右下角的锁是后台、密码是什么、报名在「审核」里通过；要公开访问见 `docs/deploy.md`。
