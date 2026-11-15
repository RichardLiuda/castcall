# 发布到托管平台

适用于「把一个目录上传上去，平台给你一个链接」的托管方式：Docker、各类 PaaS，或者 WorkBuddy 这类 AI 助手自带的「发布为在线应用」。
有自己的服务器、想用 systemd + nginx 的话，看 [deploy.md](deploy.md)。

前提：本地已经按 [quickstart.md](quickstart.md) 建好站、验收过。

## 0. castcall 和托管平台的约定

| 平台要求 | castcall 怎么满足 |
|---|---|
| 只占一个 HTTP 端口 | 本来就只有一个服务进程 |
| 监听平台给的 `$PORT`、绑 `0.0.0.0` | 有 `PORT` 环境变量时自动这样做（`CASTCALL_PORT` / `CASTCALL_HOST` 显式给了的话以它们为准） |
| 不装依赖也能启动 | 只用 Python 标准库：**安装命令留空**，启动命令 `python3 server/server.py` |
| 数据存在项目目录里 | 全在 `instance/`：`roster.json`、`site.json`、`castcall.db`（sqlite）、`uploads/`、`poster/` |

## 1. 先决定数据怎么处理

多数平台是**整个目录覆盖式上传**：`instance/` 跟着一起上去。

- **第一次发布**：线上直接拿到本地的名册、封面立绘、一图流和管理密码，打开就能用。
- **之后每次重新发布**：线上的 `instance/` 被本地这份**整个覆盖**。开募以后再发布，线上收到的报名、留言、审核记录都会没了。

三种做法，发布前选一种：

1. **接 Notion**（推荐，见 [notion.md](notion.md)）：报名、留言、名册改动都同步进 Notion，线上数据被覆盖了也有原始记录。Notion 的 token 和库 ID 写在 `.env`，打包时会带上去。
2. **只在开募前发布一次**：之后改名单在线上后台改，不再重新发布。
3. **接受覆盖**：纯演示用，要明确知道每次重新发布都会清空线上的报名。

## 2. 打包发布目录

```bash
python3 tools/bundle.py --check                       # 只体检：缺什么、会带上去什么
python3 tools/bundle.py --out ../castcall-publish     # 打包
```

`bundle.py` 做的事：

- 只拷运行需要的代码（`server/ web/ poster/ tools/ examples/ init.py` …）。不带 `.venv-poster`（上百 MB，平台上没有 Chromium 也用不上）、`.git`、`tests`、`docs`、缓存和日志。
- `instance/` 放到 `<out>/instance`；sqlite 用 backup API 拷一份一致的快照，服务器开着也能打包。
- `.env` 只留能上云的配置（Notion、`CASTCALL_TRUST_PROXY`、`CASTCALL_KEEP_BACKUPS`），去掉本机路径（`CASTCALL_CHROME`、`CASTCALL_POSTER_PYTHON`，以及 `CASTCALL_HOST` / `PORT` / `INSTANCE`）。
- 去掉 `.setup-token`、`firstrun.pending`：线上不该再进向导，也不该去补跑配图。

**发布目录要固定用同一个**：很多平台按目录认应用，换一个目录就成了新应用、链接也变了。`bundle.py` 每次把它整个重建；已经存在、但不是它生成的目录不会被覆盖。

体检会提醒：

- **没有一图流**：平台上一般没有 Chromium，生成不了。先在本地生成（后台「生成一图流」或 `poster/build.py`），再打包。
- **本地已经有报名**：见第 1 节，重新发布会覆盖线上。
- **自动配图还没跑完**：先在本地启动一次，让它跑完。

## 3. 发布

把 `<out>` 交给平台：

| 项 | 值 |
|---|---|
| 目录 | `../castcall-publish`（固定） |
| 语言 / 运行时 | Python 3.9+ |
| 安装命令 | 留空 |
| 启动命令 | `python3 server/server.py` |
| 健康检查 | `GET /api/health` → `{"ok": true, "version": "0.1.0-beta"}` |

发布是对外的动作：只在用户明确说要发布 / 上线时才做。平台不支持这种应用（比如只能发静态页）时就停下来，**不要**把它改成静态托管：`/data.js`、`/site.js`、`/chars.js` 是运行时生成的，静态托管出来是一个空页面。

## 4. 发布后验收

```bash
BASE=https://…        # 平台给的链接
curl -s -o /dev/null -w 'health %{http_code}\n' "$BASE/api/health"    # 200
curl -s "$BASE/api/data" | head -c 300                                 # 团名、角色都在
curl -s -o /dev/null -w 'poster %{http_code}\n' "$BASE/poster/"        # 200 = 一图流入口可用
```

再在浏览器里过一遍：

1. 名册、封面、立绘和本地一致；
2. 空缺角色点「报名 →」能提交，**线上**后台「审核」里能看到这条（报名进的是线上的数据库，本地后台里没有）；
3. 右下角的锁能进后台，密码就是本地建站时设的那个（`auth.json` 跟着上去了）。

### 频率限制：一定要做的一步

平台前面有一层代理，所有访客的请求在服务器看来都来自代理的 IP。不处理的话，**全站所有人共用一份频率限制**：10 分钟里全站一共只能报名 8 次、输错密码 5 次。服务器启动时检测到 `PORT`、又没设代理头，会在日志里提示这件事。

1. 登录线上后台，打开 `$BASE/api/admin/whoami`；
2. `headers` 里会列出平台传真实 IP 用的请求头（常见的是 `X-Forwarded-For`），`peer` 是代理的地址；
3. 把这个头写进 `.env`：`CASTCALL_TRUST_PROXY=X-Forwarded-For`，重新打包、发布；
4. 再打开一次 `whoami`，`ip` 应该变成你自己的公网 IP。

castcall 取的是这个头里**最右边**的值，也就是离服务器最近的那层代理写进去的。访客自己伪造的值只会出现在左边，绕不过限制。

## 5. 线上能做什么、不能做什么

- ✅ 报名、留言、审核、改名单、上传图片、改报名表、成员照片：都能用（sqlite 和文件都在可写的目录里）。
- ❌ **重新生成一图流**：平台上一般没有 Chromium，后台点「生成一图流」会提示缺依赖。已有的海报照常能打开。改了名册要更新海报的话，在本地生成后重新打包发布（注意第 1 节的覆盖问题）。
- ❌ **自动配图**看平台能不能访问 Bangumi / AniList，不行就在本地配好再发布。

## 6. 重新发布与下线

- **重新发布**：同一条 `bundle.py --out` 加同一个发布目录，链接不变。发之前确认第 1 节选的是哪种做法。
- **下线**：按平台的方式下线。链接会立刻失效，属于不可逆的对外操作，用户没明说就别做。
- **备份**：线上的 `instance/` 是唯一一份线上数据。没接 Notion 的话，开募期间定期用平台的文件下载功能把 `instance/` 拉回来（平台不支持就强烈建议接 Notion）。
