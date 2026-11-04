# AGENTS.md：给 AI 编码助手（Claude Code、Cursor、Codex……）

用户多半是 cos 团建 / 团片的组织者，不一定会写代码。典型的请求是「这是我们的名单，帮我把招募页搭起来」。
**优先调现成的命令，不要手改 JSON。**

## 标准部署流程（和 docs/quickstart.md 第 1 节一一对应，按顺序做，别跳步）

**第 0 步：环境。** `python3 --version` ≥ 3.9。一图流默认会生成，依赖没装时先问用户要不要装：

```bash
python3 -m venv .venv-poster && .venv-poster/bin/pip install -r requirements-poster.txt && .venv-poster/bin/playwright install chromium
```

（仓库里有 `.venv-poster/` 会被自动使用。用户不想装就跳过，建站照常，一图流那步会提示。）

**第 1 步：名单来源——先问用户，别自己决定。** 用户没直接给名单时，原话问：

> 名单你来提供（文字、表格、截图都行），还是我按作品的角色表先整理一版？我整理的那版只有角色、全部空缺，CN 需要你补。

- 用户给：整理成下面的格式（截图逐行识别，看不清的 CN 留空，别猜）。
- 用户让你整理：`python3 server/artsearch.py roster 作品A 作品B -o 名单.txt`（Bangumi 主角 + 配角，简体中文名；
  `--main` 只要主角，`--limit` 控制人数）。Bangumi 连不上时会退到 AniList，名字是日文，要改成中文。
  摄影 / 后勤这类工作组不会自动生成，问用户要不要加。
- **两种都要把整理好的名单给用户过目、确认后再导入。**

**第 2 步：在网页向导里建站——选项交给团长在网页上选，不要在对话里逐项问。** 名单确认后存成 `名单.txt`，在后台启动：

```bash
python3 server/server.py --prefill 名单.txt --title "活动名"     # 活动名用户说过就带上，没说就不带
```

它会打印 `http://127.0.0.1:5510/setup?t=…`。**把这个完整链接原样给用户**（口令只出现在终端里），告诉用户：

> 打开这个链接，名单已经填好了。在网页上核对名单，选单团还是多团、活动日期地点、报名的人除了 CN 和联系方式还要填什么（身高、年龄、性别、样片……都能设成选填或必填），再设一个管理密码，点「建好它」。完成页会显示自动配图和一图流的进度，好了告诉我。

**等用户填向导时，必须把这一轮对话卡住。** 很多 AI 助手的环境在一轮对话结束时会杀掉后台进程（服务器收到 SIGTERM），
向导就没了。所以「启动服务器 → 发链接 → 等用户填完」要在**同一轮**里完成：

1. 在后台启动 `server.py --prefill …`，读到它打印的链接；
2. 把链接和上面那段话发给用户，**紧接着调用你的「向用户提问并等待回答」工具**（Claude Code 是 `AskUserQuestion`），
   问「向导填好、完成页的配图和一图流都亮了吗？」，选项比如「建好了」/「遇到问题」。这一轮在等回答，服务器就一直活着；
3. 用户回答「建好了」以后，在这一轮里接着做第 3 步验收。

没有提问工具的话：改成前台运行 `python3 server/server.py --prefill 名单.txt --exit-after-setup`（命令超时设到最长）。
它在向导提交、配图和一图流都跑完后自己退出，并打印结果。

万一服务器还是被杀了：**用同一条命令重启就行**。向导链接不变（口令存在 `instance/.setup-token`），用户已经打开的页面可以直接接着提交；
建站后配图 / 一图流没跑完的话，重启时会自动补跑（`instance/firstrun.pending`）。别删这两个文件。

验收和交付做完以后，告诉用户：这一轮结束后本地服务器会停，想一直开着就在自己的终端里运行 `python3 server/server.py`，或按 `docs/deploy.md` 部署。

- 名单格式不对时 `server.py` 会在启动时报错退出：改好名单再启动。
- 已经初始化过（存在 `instance/roster.json`）时 `--prefill` 不生效：改名单走 `python3 tools/import.py 名单.txt --dry`，看过再去掉 `--dry`。
- **用户明确说不想用网页**、或者环境里没有浏览器（只能 ssh 的服务器），才用命令行一次做完；这时才在对话里问报名字段和密码：

  ```bash
  python3 init.py --title "活动名" --import 名单.txt [--fields "身高,样片*,性别"] [--password "至少8位"] --yes
  ```

  `--fields` 逗号分隔、`*` 结尾必填；密码不要编，不给就让它随机生成并把打印的密码原样转告用户。它同样会自动配图、生成一图流，把最后两行总结转告用户。

**第 3 步：验收。** 打开 `http://127.0.0.1:5510/` 核对（服务器已经在跑；用 `init.py` 建的话先 `python3 server/server.py`）：团 / 角色 / CN 和名单一致，
封面立绘配上了，抬头有「一图流」，空缺能点「报名 →」，右下角的锁能用密码进后台。

**第 4 步：补漏。** 被跳过的角色：`python3 server/artsearch.py search 角色名 --group 团名` 列候选给用户挑，或者让用户在后台点「找立绘」。
图改过以后要重新生成一图流（后台「生成一图流」或 `POST /api/admin/poster`）。

**第 5 步：交付。** 一两句话汇报：几个团、几个角色、几个空缺、配好几张图、哪些没配上、一图流有没有生成。配图和一图流的结果在 `instance/logs/server.log` 里 `firstrun` 开头那一行，一图流生成好了会有 `instance/poster/master.html`。密码是用户自己在向导里设的，不用转告。
要让别人访问：`docs/deploy.md`。

只想看效果：`python3 init.py --example key-demo --yes`（13 个团的大样例，不配图，只生成一图流）。

## 名单格式（server/importer.py）

```
## 团名（通常是作品名）        ← 只有一部作品也建议写上；没有团名行就用活动名当团名
> 团的说明（可选）
角色名 CN                      ← 空格 / Tab / 冒号 / 竖线分隔都行
角色名                         ← 没有 CN = 空缺，可以报名
## 摄影 / 后勤                 ← 团名带「摄影 / 后勤 / 妆娘 / staff」会设成工作组（不配封面和立绘）
摄影 阿光
```

CSV：表头里有 `团`（或 `作品` / `group`）、`角色`（`character` / `role`）、`CN`（`成员` / `member` / `coser`）就行。

## 改配置

- 活动信息、报名开关和时间窗、联系方式字段、留言审核方式：`instance/site.json`，字段说明在 `docs/config.md`。
  只写想改的字段，保存后刷新页面就生效。**不要把密钥写进 site.json**（它有一部分会发给浏览器）。
- Notion、端口、代理头：`.env`（照 `.env.example`），教程在 `docs/notion.md`、`docs/deploy.md`。
- 单团 / 多团按团数自动切换；`site.json` 里 `"mode":"multi"` 可以强制多团界面。

## 图片

- 自动：`python3 server/artsearch.py auto`（`--dry` 预览，`--redo` 重找已有的，`--covers-only` / `--portraits-only`）。工作组不配。
- 指定某张：`python3 server/artsearch.py search 角色名 --group 团名` 列出候选 URL；用户挑中后，
  在后台用「找立绘」/「在线找封面」点选，或者调接口 `POST /api/admin/art/pick`（需要登录）。
- 用户自己的图：后台编辑角色 / 团时上传。logo、标签页图标、一图流大图：后台「站点素材」（或 `POST /api/admin/brand`）。
- 立绘映射在 `instance/uploads/map.json`：`{"团名|角色名": "portraits/文件名"}`。改了团名、角色名要同步改这里（后台改名会自动搬）。

## 不要做

- 不要直接改 `instance/roster.json` 再让服务器去读：走 `tools/import.py`、后台或 `PUT /api/data`，它们会备份、补 id、记变更。
  实在要手改，先停服务器，改完运行 `python3 -c "import sys;sys.path.insert(0,'server');import roster;roster.validate(roster.load())"` 校验。
- 不要删 `instance/`、`instance/castcall.db`：那是全部数据（报名、留言）。
- 不要把 `instance/`、`.env` 提交进 git（已在 `.gitignore`）。
- 服务器直接暴露在公网时，不要设 `CASTCALL_TRUST_PROXY`（会让人绕过频率限制）。

## 后台接口（需要登录 cookie：先 `POST /api/login {"password":...}`）

| 接口 | 用途 |
|---|---|
| `GET/PUT /api/data` | 读 / 存整份名册 |
| `GET /api/admin/signups`，`POST /api/admin/signups/<id> {"action":"approve|reject|reopen"}` | 报名审核 |
| `GET /api/admin/guestbook`，`POST /api/admin/guestbook/<id> {"action":"hide|show"}` | 留言 |
| `POST /api/admin/upload?kind=cover|portrait|logo[&group=&character=]`（body 是图片） | 上传 |
| `GET /api/admin/art/search?kind=portrait|cover&q=&group=`，`POST /api/admin/art/pick` | 找图 / 选图 |
| `POST /api/admin/art/auto` | 后台跑一键配图 |
| `POST /api/admin/poster` | 生成一图流（需要 Pillow + Playwright） |
| `GET/POST /api/admin/signup-fields {"fields":[…]}` | 报名额外要填的（格式见 docs/config.md） |
| `GET /api/admin/brand`，`POST /api/admin/brand?slot=logo|favicon|hero[&clear=1]`（body 是图片） | 站点素材 |
| `GET /api/admin/photos`，`POST /api/admin/photos/<id> {"action":"approve|reject|reopen"}`，`POST /api/admin/photos/config {"enabled","moderation"}` | 成员本人照片 |

## 改代码时

- 服务端只用标准库，别引入依赖（一图流的 Pillow / Playwright 是例外，且是可选的）。
- 测试：`python3 -m unittest discover -s tests`。浏览器端到端：`python3 tests/e2e_browser.py`（需要 Playwright）。
