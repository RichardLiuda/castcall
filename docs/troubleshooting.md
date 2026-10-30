# 搭建时容易卡住的地方

按「从零到能发链接」的顺序排，每条写：会看到什么 → 为什么 → 怎么办。
这份是从一次真实的本地搭建（Kanon 团片站 + 四个团的示例站）里记下来的，不是设想。

---

## 1. 环境

### 1.1 Bangumi 打不开 → 配图一片报错

**看到**

```
出错 月宫亚由：URLError(OSError('Tunnel connection failed: 502 Bad Gateway'))
...
（--dry）封面 0 张、立绘 0 张。
```

**为什么** 这台机器开着 `HTTP_PROXY`，`api.bgm.tv` 走代理被拒。AniList（`graphql.anilist.co`）通常还能通。

**现在会怎样** `server/artsearch.py` 在 Bangumi 失败时会退到 AniList，所以不会再 0 张：一次实测配到 1 张封面 + 3 张立绘。但 AniList 只有日文 / 罗马字名，中文角色名大多对不上，会显示「没有可靠的匹配」。

AniList 本身也会抖：同一条命令第一次跑可能封面 `TimeoutError`、第二次就配上了。结果不稳的时候重跑一遍比调参数有用。

**怎么办**

- 能直连就别给 `api.bgm.tv` 挂代理；挂了也通不了的话，接受 AniList 的结果，剩下的在后台「找立绘」手选。
- `artsearch.py auto --dry` 先看会配哪张，再去掉 `--dry`。

### 1.2 一图流跑不了

**看到** 后台点「生成一图流」没反应；命令行 `ModuleNotFoundError: No module named 'PIL'`。

**为什么** 一图流是可选功能，要 Pillow + Playwright + 中文字体，核心服务不需要。

**怎么办**

```bash
pip install -r requirements-poster.txt
playwright install chromium
# Linux 还要中文字体：fonts-noto-cjk / google-noto-sans-cjk-fonts
```

后台接口在缺依赖时会返回 501 和上面这几行安装指引；命令行版（`poster/build.py`）没有兜住，会直接抛 traceback。

### 1.3 浏览器端测试（`tests/e2e_browser.py`）跑不了

**为什么** 要 Python 的 playwright 包。系统 python 里没有，`pip install playwright` 在受限网络下也可能装不完整。

**怎么办** 单测是真依赖最小的验证：`python3 -m unittest discover -s tests`（67 个，约 25 秒）。想看真实渲染就用系统 Chrome 手动过一遍，或者装好 playwright 后 `python3 tests/e2e_browser.py --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`。

---

## 2. 多个实例：最容易配错对象的地方

`init.py --instance 别处/xxx` 建了实例之后，**其他工具默认还是读写 `./instance/`**：

| 工具 | 认哪个实例 |
|---|---|
| `init.py` | `--instance`，或 `CASTCALL_INSTANCE`，默认 `./instance` |
| `server/server.py` | `CASTCALL_INSTANCE`，默认 `./instance` |
| `server/artsearch.py` | `--instance` / `CASTCALL_INSTANCE`，默认 `./instance` |
| `tools/import.py` | `--instance` / `CASTCALL_INSTANCE`，默认 `./instance` |
| `poster/build.py` | `--instance` / `CASTCALL_INSTANCE`，默认 `./instance` |

忘了带就会**给别的站配图 / 改别的站的名册**（真踩过：给 Kanon 配图时跑到了示例站上）。养成习惯：

```bash
CASTCALL_INSTANCE=instance-kanon python3 server/server.py
CASTCALL_INSTANCE=instance-kanon python3 server/artsearch.py auto --dry
```

同一台机器开两个站要同时指定端口，否则第二个会停在「端口 5510 已被占用」：

```bash
CASTCALL_INSTANCE=instance-kanon CASTCALL_PORT=5511 python3 server/server.py
```

---

## 3. 页面形态：单团还是多团

`site.json` 的 `mode` 有三档，见 `docs/config.md`。这里只记踩过的坑：

- **工作组不算团**。`kind: "crew"` 的摄影 / 后勤 / 妆娘组以前会被当成第二个团，于是「一部作品 + 摄影后勤」这种最常见的团片名单，页面变成了两张封面卡。现在 `mode: "auto"` 会把它们算作同一个单团。
- **单团页要把工作组人也列出来**。以前单团页只渲染第一个团，摄影组整组消失；现在列在「已定阵容」下面，缺的席位同样能点「报名 →」。
- 想强行保持封面卡墙（哪怕只有一个作品），`site.json` 里写 `"mode": "multi"`。

---

## 4. 配图的实际表现

- **中文名在 AniList 经常对不上**：它返回 `月宮あゆ` 这类日文名，搜中文「月宫亚由」没有结果。能配上的是恰好有简体中文别名的（实测「美坂栞」「川澄舞」「天野美汐」配上了）。这类漏配是正常的，后台手选更快。
- **AniList 的横幅是超宽图**（约 1900×400）：以前铺满整屏 banner（`background-size: cover`）时会被放大成中间一条糊掉的局部。现在一键配图在 AniList 上优先拿竖版封面；后台手选了横幅（宽:高 > 2）时，单团页拆成两层：页顶一条清晰带（到团名下沿，不超过原图高，不放大），往下是同一张图的模糊铺底，照旧一路铺到留言区。桌面上基本是完整构图；手机竖屏只能看到横幅中间一段，手机为主的站还是换竖版或方图。
- **一键配图是串行的**：每个角色至少一次请求 + 0.35 秒间隔，一百多个角色要跑几分钟。后台跑的时候没有进度条（接口只回 `running: true`），不要以为卡死；跑完 `GET /api/admin/art/auto` 能拿到 `report`。
- 配图只下载 Bangumi / AniList 图床上的图，别处的 URL 会被拒绝（不是通用下载器）。

### 用接口手换封面要两步

`POST /api/admin/upload?kind=cover&group=Kanon` 只把文件存进 `uploads/covers/`，返回 `{"ok":true,"file":"xxxx.png"}`，**不会**改名册里的 `cover`。后台是上传完再 `PUT /api/data` 把文件名写回去。只有 `kind=portrait` 会顺带把这一席指到新图（内部调 `set_portrait`）。

所以脚本换封面得：

```bash
curl -b cookie -X POST -H 'Content-Type: image/png' --data-binary @cover.png \
  'http://127.0.0.1:5510/api/admin/upload?kind=cover&group=Kanon'
# → file: xxxx.png
curl -b cookie http://127.0.0.1:5510/api/data > d.json   # 改 cover 后 PUT 回去
```

只传第一步的话，页面上看不到任何变化，容易以为上传失败。

---

## 5. 还没修的

这些不影响上线，但会被人问到：

- **活动日期过了以后，倒计时整块消失**，页面上没有任何「已结束 / 回顾中」的状态。
- **单团页没配封面时**，首屏是一大片纯渐变（`--solo-h` 至少 240px），信息密度很低。配一张封面就好。
- **`poster/build.py` 缺依赖直接抛 traceback**，不像后台接口那样给安装指引。
- **`artsearch.py` 的网络错误分类**：现在 Bangumi 挂了但 AniList 也没结果时会显示「没有可靠的匹配」，比之前统一报「出错」准确，但仍然不告诉用户「是 Bangumi 连不上，所以只剩一个源」。

---

## 6. 验收清单

从零到能发链接，按这个顺序走一遍，每步都有可观察的结果：

```bash
# 1 建站（不给 --password 就会随机生成并打印一次，务必抄下来）
python3 init.py --instance instance-kanon --title "Kanon 团建" \
  --import 名单.txt --yes
# 期望：打印「N 个团、M 个席位（X 已定、Y 空缺)」+ 管理密码

# 2 配图（先预览）
CASTCALL_INSTANCE=instance-kanon python3 server/artsearch.py auto --dry
CASTCALL_INSTANCE=instance-kanon python3 server/artsearch.py auto

# 3 单测
python3 -m unittest discover -s tests
# 期望：Ran 67 tests ... OK

# 4 起服务
CASTCALL_INSTANCE=instance-kanon python3 server/server.py
# 期望：castcall: http://127.0.0.1:5510/  （实例目录 …，Notion 未启用）
```

打开页面后确认四件事：

1. 一部作品 + 摄影后勤 → **单团页**（页首是封面和「N 个角色」），不是两张卡。
2. 招募中的角色有「报名 →」，点进去是报名表（提交后提示「等审核」，不会直接占位）。
3. 页面拉到下方有「已定阵容」和「摄影 / 后勤」，工作组的空缺也能报名。
4. 右下角的锁 → 输密码 → 工具条出现「审核」，能通过刚才那条报名。

对外的最后一步见 `docs/deploy.md`（systemd + nginx）。
