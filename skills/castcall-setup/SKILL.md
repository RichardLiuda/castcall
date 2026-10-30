---
name: castcall-setup
description: Set up or update a castcall cos 团建 / 团片 recruiting site from a name list (text, CSV, spreadsheet, or chat screenshot) — initialise the instance, import roles and CNs, fetch portraits and covers, start the server. Use when the user asks to build a recruiting / roster page with castcall, add or change roles, or fill in artwork.
---

# castcall：从名单到招募页

先读仓库根目录的 `AGENTS.md`（命令、格式、禁区都在那里）。下面是做事的顺序。

1. **弄清三件事，缺了就问用户**：活动名称；单团还是多团（看名单里有没有多个作品）；管理密码（不要自己编，
   用户不给就让 `init.py` 随机生成并把打印出来的密码原样告诉用户）。日期、开场时间、地点、联系方式有就填，没有可以空着。

2. **整理名单**成 `AGENTS.md` 里的文本格式，存到一个临时文件（比如 `名单.txt`）。
   - 截图 / 群聊：逐行识别「角色 + CN」，看不清的 CN 宁可留空（变成空缺），别猜。
   - 多部作品：每部前面加 `## 作品名`。
   - 把整理结果给用户过目一遍，再导入。

3. **初始化或导入**
   - 还没有 `instance/roster.json`：`python3 init.py --title … --import 名单.txt … --yes`
   - 已经有了：`python3 tools/import.py 名单.txt --dry`，看过输出再去掉 `--dry`。整份换掉才用 `--replace`。

4. **配图**：`python3 server/artsearch.py auto --dry` 看会配哪些，再去掉 `--dry` 执行。
   被跳过的角色：用 `python3 server/artsearch.py search 角色名 --group 团名` 找候选，或者请用户在后台点「找立绘」自己挑。

5. **启动并交付**：`python3 server/server.py`。告诉用户：
   - 网址 `http://127.0.0.1:5510/`，右下角的锁是后台，密码是什么；
   - 有人报名后在后台「审核」里点通过；
   - 要让别人访问得放到服务器上，见 `docs/deploy.md`。

做完用一两句话汇报：几个团、几个角色、几个空缺、配好几张图、哪些没配上。
