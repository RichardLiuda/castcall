# AGENTS.md：给 AI 编码助手（Claude Code、Cursor、Codex……）

用户多半是 cos 团建 / 团片的组织者，不一定会写代码。典型的请求是「这是我们的名单，帮我把招募页搭起来」。
**优先调现成的命令，不要手改 JSON。**

## 快速路线

```bash
# 1. 初始化（不交互）。名单可以是文本或 CSV，格式见下
python3 init.py --title "活动名" --import 名单.txt --date 2026-12-12 --start 2026-12-12T11:00:00+08:00 \
  --location "地点" --contact "微信 abc123" --password "至少8位的密码" --yes
# 2. 自动配图（Bangumi / AniList；只配有把握的，其余跳过）
python3 server/artsearch.py auto
# 3. 启动
python3 server/server.py          # http://127.0.0.1:5510/ ，右下角的锁是后台
```

- 已经初始化过（存在 `instance/roster.json`）时，`init.py` 会拒绝执行；改名单用 `python3 tools/import.py 名单.txt`
  （合并，不会覆盖已有的 CN）或加 `--replace`（整份替换，会先备份）。先加 `--dry` 看会改什么。
- 不知道密码就别编：问用户，或者不传 `--password`、去掉 `--yes`，让 `init.py` 随机生成并打印一次，原样转告用户。
- 只想看效果：`python3 init.py --example key-demo --password ... --yes`（13 个团的大样例，带占位封面、留言和待审报名）。

## 名单格式（server/importer.py）

```
## 团名（通常是作品名）        ← 没有团名行就是单团
> 团的说明（可选）
角色名 CN                      ← 空格 / Tab / 冒号 / 竖线分隔都行
角色名                         ← 没有 CN = 空缺，可以报名
## 摄影 / 后勤                 ← 团名带「摄影 / 后勤 / 妆娘 / staff」会设成工作组（不配立绘）
摄影 阿光
```

CSV：表头里有 `团`（或 `作品` / `group`）、`角色`（`character` / `role`）、`CN`（`成员` / `member` / `coser`）就行。
用户给的是图片或聊天截图：先把内容整理成上面的文本，再导入。

## 改配置

- 活动信息、报名开关和时间窗、联系方式字段、留言审核方式：`instance/site.json`，字段说明在 `docs/config.md`。
  只写想改的字段，保存后刷新页面就生效。**不要把密钥写进 site.json**（它有一部分会发给浏览器）。
- Notion、端口、代理头：`.env`（照 `.env.example`），教程在 `docs/notion.md`、`docs/deploy.md`。
- 单团 / 多团按团数自动切换；`site.json` 里 `"mode":"multi"` 可以强制多团界面。

## 图片

- 自动：`python3 server/artsearch.py auto`（`--dry` 预览，`--redo` 重找已有的，`--covers-only` / `--portraits-only`）。
- 指定某张：`python3 server/artsearch.py search 角色名 --group 团名` 列出候选 URL；用户挑中后，
  在后台用「找立绘」/「在线找封面」点选，或者调接口 `POST /api/admin/art/pick`（需要登录）。
- 用户自己的图：后台编辑角色 / 团时上传。
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

## 改代码时

- 服务端只用标准库，别引入依赖（一图流的 Pillow / Playwright 是例外，且是可选的）。
- 测试：`python3 -m unittest discover -s tests`。浏览器端到端：`python3 tests/e2e_browser.py`（需要 Playwright）。
