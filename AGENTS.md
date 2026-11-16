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

**第 1.5 步：名单定下来以后，先核对每个名字配不配得上图。** 名字对不上作品里的角色，自动配图就永远配不上——这种问题必须在建站前告诉团长，不能等页面上少了几张立绘才被发现。

```bash
python3 server/artsearch.py names 名单.txt
```

每个名字后面一个标记：`✓` 能配上（`→` 后面是作品里的写法，和名单不一样就是中文名 / 日文名不同，正常）；`⚠` 只差一个字，多半是名单写错了，后面给了正确的写法；`✗` 作品角色表里没有这个名字，下面列出了这部作品实际有哪些角色。

- `⚠` 和 `✗` 都要**告诉用户并等他确认**，不要自己改名单。他确认「对，就是这个」以后，把名单里的字改成输出里的写法。
- 退出码非 0 = 有名字配不上。如实转告，别只报「建好了」。
- Bangumi 连不上会自动改用 AniList 的作品角色表核对（仍能确认一部分：写法相同的、以及只是简体 / 日文写法不同的，如 泽渡真琴 → 沢渡真琴）。只有**两个库都不通**才算没法核对：这时跳过这步直接建站，网络好了在后台点「一键配图」会再对一次。**不要**因此谎称名字都没问题。
- 核对过的名字记在 `instance/uploads/art_bind.json`，配图时直接按它取图，不再搜索（也就不会配上同名的另一个角色）。这次核对的结论记在 `instance/uploads/art_bind_run.json`（时间、两个库通没通、自动绑了几个）——汇报时用它，别用猜的。

**第 2 步：在网页向导里建站——选项交给团长在网页上选，不要在对话里逐项问。** 名单确认后存成 `名单.txt`，在后台启动：

```bash
python3 server/server.py --prefill 名单.txt --title "活动名"     # 活动名用户说过就带上，没说就不带
```

它会打印一行 **6 位验证码**和一个带验证码的链接 `http://127.0.0.1:5510/setup?t=…`。**把这个完整链接原样给用户，并把那 6 位数字也念一遍**（两者都只出现在终端里），告诉用户：

> 打开这个链接，名单已经填好了。在网页上核对名单，选单团还是多团、活动日期地点、报名的人除了 CN 和联系方式还要填什么，再设一个管理密码，点「建好它」。完成页会显示自动配图和一图流的进度，好了告诉我。

**团长没说的，不要替他编。** 日期、开场时间、地点、联系方式，用户没说就留空——页面会自己隐藏这一块，编一个错的日期比空着糟得多。报名表默认只要 CN 和联系方式；身高、样片、性别这些是可选预设，用户没提就别勾（尤其别把样片设成必填，会让不少人直接放弃报名）。

**等用户填向导时，必须把这一轮对话卡住。** 很多 AI 助手的环境在一轮对话结束时会杀掉后台进程（服务器收到 SIGTERM），
向导就没了。所以「启动服务器 → 发链接 → 等用户填完」要在**同一轮**里完成：

1. 在后台启动 `server.py --prefill …`，读到它打印的链接；
2. 把链接和上面那段话发给用户，**紧接着调用你的「向用户提问并等待回答」工具**（Claude Code 是 `AskUserQuestion`），
   问「向导填好、完成页的配图和一图流都亮了吗？」，选项比如「建好了」/「遇到问题」。这一轮在等回答，服务器就一直活着；
3. 用户回答「建好了」以后，在这一轮里接着做第 3 步验收。

没有提问工具的话：改成前台运行 `python3 server/server.py --prefill 名单.txt --exit-after-setup`（命令超时设到最长）。
这时你得自己把向导提交掉：**只用用户明确说过的信息**，日期 / 地点 / 报名字段一律留空，别按「一般团片会要什么」去补。
它在向导提交、配图和一图流都跑完后自己退出，并打印结果。

万一服务器还是被杀了：**用同一条命令重启就行**。向导和验证码都不变（存在 `instance/.setup-token`），用户已经打开的页面可以直接接着提交；
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

配图先看数字对不对：`instance/logs/server.log` 里 `firstrun` 那一行的「立绘 N 张」应该等于可配图的角色数（工作组不算）。
少了就是有名字没配上，回到第 4 步；**不要**看着页面「差不多」就报完工。

**第 4 步：补漏。** 被跳过的角色：`python3 server/artsearch.py search 角色名 --group 团名` 列候选给用户挑，或者让用户在后台点「找立绘」。
图改过以后要重新生成一图流（后台「生成一图流」或 `POST /api/admin/poster`）。

**第 5 步：交付。** 一两句话汇报：几个团、几个角色、几个空缺、配好几张图、哪些没配上、一图流有没有生成。配图和一图流的结果在 `instance/logs/server.log` 里 `firstrun` 开头那一行，一图流生成好了会有 `instance/poster/master.html`。密码是用户自己在向导里设的，不用转告。

**第 6 步：上线（用户要求时才做）。** 用户说要发布 / 上线 / 分享链接：
- 托管平台（上传一个目录、平台给链接；包括你自己带的「发布为应用」工具）：按 `docs/hosting.md`，或 skill `castcall-publish`。
  核心是 `python3 tools/bundle.py --check` → 问用户数据怎么处理（重新发布会覆盖线上的报名）→ `tools/bundle.py --out <固定目录>` →
  发布（安装命令留空、启动 `python3 server/server.py`）→ 验收 → 用 `/api/admin/whoami` 补上 `CASTCALL_TRUST_PROXY`。
- 自己的服务器：`docs/deploy.md`（systemd + 反向代理）。

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

- 先核对名字（不下载、不建站）：`python3 server/artsearch.py names 名单.txt`。`✓` 能配、`⚠` 像写错了、`✗` 作品里没这个名。
  退出码非 0 就是有名字配不上——**这个要在建站前给用户看**，建完站再说就晚了。
- 自动：`python3 server/artsearch.py auto`（`--dry` 预览，`--redo` 重找已有的，`--covers-only` / `--portraits-only`）。工作组不配。
- 绑定：`instance/uploads/art_bind.json` 记着「团名|角色名 → 角色 id」，`names` 和建站时自动生成。配图优先用它，
  命中就按 id 取图、不再搜索。名单改了名字，旧绑定不会自动失效（它是按名字查的），重跑一次 `names` 覆盖即可。
- 中日写法不同会自己转：泽→沢、宫→宮、亚→亜…… 这一层在 `artsearch.py` 的 `VAR` 表里。**不要**为了配图去改用户名单里的字；
  核对已经处理了写法差异，改字只会让名单和团长手上的不一致。
- 这次核对的结论在 `instance/uploads/art_bind_run.json`（`bangumi` 通没通、`ok` / `bound` 几个、`sources` 是哪个库）。
  汇报「名字都核对过了」之前先看它，别凭印象。
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
| `GET /api/admin/whoami` | 托管后自检：服务器看到的来源 IP 和转发头（用来设 `CASTCALL_TRUST_PROXY`） |
| `GET/POST /api/admin/signup-fields {"fields":[…]}` | 报名额外要填的（格式见 docs/config.md） |
| `GET /api/admin/brand`，`POST /api/admin/brand?slot=logo|favicon|hero[&clear=1]`（body 是图片） | 站点素材 |
| `GET /api/admin/photos`，`POST /api/admin/photos/<id> {"action":"approve|reject|reopen"}`，`POST /api/admin/photos/config {"enabled","moderation"}` | 成员本人照片 |

## 调试部署流程（改完细节怎么验）

改一个细节要跑三层，从快到慢，前一层过不了就别进下一层：

```bash
python3 -m unittest discover -s tests        # 代码层，约 40 秒，不联网不占端口
python3 tools/lab.py smoke                   # 流程层，约 1 秒：干净沙盒里 init.py 从零建站 + 十几条断言（不配图）
python3 tools/lab.py smoke --via wizard      # 走网页向导那条路（会真去配图并断言立绘 / 封面配齐，约 80 秒）
python3 tools/lab.py blind                   # AI 层：dsh 扮演不知情的团长助手，看它能否按本文档走通（5-15 分钟）
python3 tools/lab.py list                    # 历次结果 + 通过率
```

`runs/<时间>-<场景>/report.json` 里是逐条断言，哪一步先红就看哪一步；`blind` 还会留下 `events.jsonl`（dsh 原始事件流）和 `transcript.md`（它跑过的命令、最后的答复）。

**断言都在外部做**：AI 说「部署好了」不算数，脚本要看 `instance/` 里的文件和 `/api/` 的返回。

失败按四类归因，归对了才知道改哪儿：

| 归因 | 症状 | 改哪里 |
|---|---|---|
| 文档 | AI 选了不存在的命令 / 漏了前置条件 / 反复读同一个文件 | AGENTS.md、docs/quickstart.md |
| 代码 | 命令本身报错、traceback | 代码 + 往 `tests/test_api.py` 补一条（断言本身判错了就补 `tests/test_lab.py`） |
| 环境 | 缺依赖、断网、端口占用 | 降级与重试，文档写清补救办法 |
| 模型 | 明知该做却没做、自作主张 | 把关键步骤收敛成一条命令，少让它自由发挥 |

`blind` 的「零」有几种，按需要挑：默认（有 AGENTS.md、有网）→ `--no-agents`（拿掉 AGENTS.md，只留 README 和它指向的 `docs/`，测文档自解释性）→ 自定义 `--names` 传一份格式坏的名单（测报错提示够不够清楚）。

### 同时开几个新会话跑（最接近真实交付）

真实场景就是「用户在对话框里说一句帮我建站」，所以要验的是**新会话能不能自己走通**。`dsh` 和 WorkBuddy 会话都行，做法一样：

```bash
python3 tools/lab.py sandbox --label A1 --port 5511      # 打印沙盒路径，名单已经放好
python3 tools/lab.py sandbox --label C1 --port 5513 --no-agents
```

把每个沙盒交给一个新会话，只给它一句团长口吻的需求（工作目录 + 名单在哪），**不要说这是测试**，否则它会为了通过而作弊。
每个沙盒必须给不同端口：`--port` 写进沙盒的 `.env`，不然几个站会全去抢 5510，看到一堆假的「端口被占用」。

跑完回来做外部断言，密码用它汇报的那个：

```bash
python3 tools/lab.py check <沙盒路径> --label A1 --password <它汇报的密码>
```

`check` 默认要求立绘和封面配齐。少了会逐个归因，四种，别混着读：
- `名单里对不上`：作品角色表里确实没有这个名字 → 改名单，或后台手选；
- `没法确认`：判它的是 AniList 的表（Bangumi 不通），那张表只有日文名，写法不同的查不到 → **不是名单写错**，网络好了重跑一次；
- `核对时网络断了`：那次核对没得出结论；
- `没核对过`：这版没跑名单预检，说不清是名单还是下载。

这一版本来就没让它配图，加 `--no-art`。报告里 `cause: env` 表示缺的那些都能用环境解释（下载失败 / 表认不出 / 断网），没有一个名字真的对不上。

建沙盒时会记一份代码指纹（`.lab.json` 的 `fp`）。`check` 开头出现 `⚠` 时先看它：
- **建沙盒之后主仓库改过 N 个文件**：这版跑的是旧代码，结论不代表现在。要验新代码就重新建沙盒。
- **沙盒里有 N 个文件被部署的 AI 改过**：去沙盒里看 diff。修的是真 bug 就搬回主仓库；绕过了断言就是「模型」类失败。

一次开 3 个就够看出问题：同条件两次看一致性（同样一句话会不会产出两个不同的站），`--no-agents` 一次看 README + docs 够不够用。

## 改代码时

- 服务端只用标准库，别引入依赖（一图流的 Pillow / Playwright 是例外，且是可选的）。
- 测试：`python3 -m unittest discover -s tests`。浏览器端到端：`python3 tests/e2e_browser.py`（需要 Playwright）。
- **改完记一笔在 `docs/optimization-log.md`**：看到什么问题、判断的真因、改了什么、怎么验的、还剩什么没解决。
  只写「改了什么」没有价值——`git log` 已经有了；有价值的是为什么这么改，以及哪些边界是特意留着的。
