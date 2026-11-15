# 搭建时容易卡住的地方

按「从零到能发链接」的顺序排，每条写：会看到什么 → 为什么 → 怎么办。
这份是从一次真实的本地搭建（Kanon 团片站 + 四个团的示例站）里记下来的，不是设想。

---

## 1. 环境

### 1.1 Bangumi 打不开 → 配图一片报错

**先分清是网络还是名单。** 这两件事的补救办法完全不同，混在一起就会以为「配图时好时坏」：

```bash
python3 server/artsearch.py names 名单.txt
```

- 逐个列出名字，带 `✓` / `⚠` / `✗` → **名单有结论了**。`✓` 能配（`→` 后面是库里的写法，和名单不一样就是中文名 / 日文名写法不同，正常）；`⚠` 只差一个字（多半名单写错了，后面直接给了正确写法）；`✗` 作品角色表里没这个名字（后面列出这部作品实际有哪些角色，点一个就换）。
- 「Bangumi 和 AniList 都连不上，名字没法核对」→ **网络的锅**。只有两个库都不通才会这样：先探一次（8 秒），不通就尽快收尾，不会让每个团各等一次超时。名字既没通过也没否定。
- 摘要里如果写「按 AniList 的角色表核对」，那是**部分确认**、不是全过：写法和库里一致的名字能对上（包括只是简体 / 日文写法不同的，如 泽渡真琴 → 沢渡真琴），汉字被改写成假名的（月宫亚由 → 月宮あゆ）对不上。这时 `✗` 后面会注明「这是 AniList 的表，只有日文名」，意思是**没法确认**，不是让你去改名字——同一份名单 Bangumi 通的时候它是能对上的。

这条命令只查不下载、不建站，几秒到十几秒。**名单一确定就该跑它**——等建完站发现少了几张立绘，成本高得多。

核对过的名字写进 `instance/uploads/art_bind.json`（`团名|角色名 → 角色 id`）。之后一键配图命中绑定就直接按 id 取图，不再搜索：搜索结果会随排序和同名角色漂，id 不会。

这次核对本身的结论写进 `instance/uploads/art_bind_run.json`（时间、`bangumi` 通没通、`ok` / `bound` 几个、`sources` 是哪个库）。它存在的意义是把「**没跑核对**」和「**跑了但两个库都不通**」分开——这两种情况以前在文件层面长得一模一样，排查时只能猜。

**看到**

```
出错 月宫亚由：URLError(OSError('Tunnel connection failed: 502 Bad Gateway'))
...
（--dry）封面 0 张、立绘 0 张。
```

**为什么** 这台机器开着 `HTTP_PROXY`，`api.bgm.tv` 走代理被拒。AniList（`graphql.anilist.co`）通常还能通。

**现在会怎样** 两件事已经改掉：

- **会自己重试**：超时 / 502 / 429 这类抖动最多试 3 次（间隔 0.7s、1.4s），一两次抖动不再变成「一张都没配」。404 这种「真没有」不重试。整条线路连续失败会熔断——断网时不会逐个角色重试到几分钟才收尾。
- **中文名有兜底**：`api.bgm.tv` 的角色搜索只匹配日文 `name`，「月宫亚由」搜不到「月宮あゆ」、「泽渡真琴」搜不到「沢渡真琴」，所以以前同样的团里川澄舞、天野美汐配得上、另外两个配不上。现在搜索落空时会拿**作品自己的角色表**（`subjects/{id}/characters`）建一张「中文名 → 立绘」的表，按「简体中文名 / 别名」再对一次；名单里有错字（美坂栎 / 美坂栞）且只差一个字、候选唯一时也会认，并在汇报里写「按近似名对上（名单里可能有错字）」。这张表缓存在 `instance/uploads/art_index.json`。

Bangumi **完全不通**时不用放弃，但结果会打折，而且两件事打折的方式不同：

- **核对名字**（`names` / 向导第 3 步）：会自动改用 AniList 的作品角色表。写法和库里一致的能确认（含简体 / 日文写法差异，如 泽渡真琴 → 沢渡真琴），汉字被改写成假名的对不上，会列出该作品实际的角色名让你点。
- **配图**（`auto`）：核对过的名字按绑定直接取图，不受影响；没绑上的那些退到 AniList 按名字直搜，写法对不上的仍然配不上。所以不会整站「立绘 0 张」，但会少几张——实测五人的团，4 张有绑定、直接出来，剩下 1 张要给用户手选。

这两种情况下少的那几张都是**网络的锅，不是名单的锅**，等网络好了在后台点「一键配图」即可（已有的不重下）。`artsearch.py names` 会直接告诉你现在走的是哪个库，不用猜。

AniList 自己也会抖：同一条命令第一次跑可能封面 `TimeoutError`、第二次就配上了。

**怎么办**

- 能直连就别给 `api.bgm.tv` 挂代理；挂了也通不了的话，等网络好了在后台「一键配图」重试，剩下的手选。
- `artsearch.py auto --dry` 先看会配哪张，再去掉 `--dry`。
- 想知道某张图是「搜来的」还是「按中文名对上的」，看 `instance/uploads/art_index.json`：里面按角色 id 记了候选名和 url。

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

**怎么办** 单测是真依赖最小的验证：`python3 -m unittest discover -s tests`（约 40 秒）。想看真实渲染就用系统 Chrome 手动过一遍，或者装好 playwright 后 `python3 tests/e2e_browser.py --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`。
如果只想验「从零部署能不能成」，不用浏览器：`python3 tools/lab.py smoke`（约 1 秒，见 AGENTS.md 的调试部署流程）。

### 1.4 让 AI 助手部署时，服务器在向导填到一半时被杀

**看到** AI 发了向导链接，你还没填完，页面就打不开了；`instance/` 里只有日志。

**为什么** 不少 AI 助手的环境在一轮对话结束时会杀掉它启动的后台进程（服务器收到 SIGTERM）。

**现在会怎样**

- AGENTS.md / skill 要求 AI 发完链接就用提问框（比如 Claude Code 的 `AskUserQuestion`）把这一轮卡住，等你在网页上填完、点「建好了」再往下走。
- 没有提问框的 AI 用 `server.py --prefill 名单.txt --exit-after-setup` 前台运行：建完、配完图、生成完一图流自己退出。
- 真被杀了：用同一条命令重启。**向导链接不变**（口令存在 `instance/.setup-token`），已经打开的页面直接接着提交；建站后配图 / 一图流没跑完，重启时自动补跑（`instance/firstrun.pending`）。

**怎么办** 让 AI 重启服务器，或者自己在终端里运行它打印过的那条命令。建好后想一直开着：自己的终端里 `python3 server/server.py`，或按 `docs/deploy.md` 部署。

### 1.5 向导里点「检查这些名字配不配得上图」，回「名单是空的」

**看到** 名单明明填在框里，点按钮却提示「没核对成：名单是空的」；浏览器控制台里能看到 `POST /api/setup/names` 返回 400。

**为什么** 老版本的一个 bug：向导的核对只发名单和活动名，没带「这份名单是从哪儿来的」，服务端就当成「先空着」直接拦了。11-14 已修（`server/server.py`：有名字就按粘贴处理）。

**现在会怎样** 两个库都能连的话，几秒到十几秒出结果；Bangumi 连不上时按 AniList 的角色表部分确认（写法和库里一致的名字能对上，汉字改写成假名的对不上，会列出来让你点）。
**不会**因为这次没核对成就不让你建站——只是建完以后自动配图得靠搜索，同一个作品里有同名角色时可能配错，最好在后台「找立绘」里自己看一眼。

**怎么办** 升级到最新代码；已经在用的站不影响，用命令行跑同一条检查也行：`python3 server/artsearch.py names 名单.txt`。

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
- **改完代码、也重建了海报，网页看着还是一样**：先确认浏览器连的是哪个进程。`tools/lab.py sandbox` 建的沙盒是**当时工作区的一份拷贝**（`/var/folders/.../castcall-lab-XXXX`），里面的 `server/server.py` 是拷贝那天的代码；你在仓库里改的选择器、新加的版式它一无所知。重建海报只会换掉图片文件，换不掉「单团一律跳 master」这条老逻辑。用 `lsof -nP -p <pid> | grep cwd` 看进程的工作目录，或者干脆在仓库根目录重开一个端口。

---

## 4. 配图的实际表现

- **名单先核对，别等配图**：`python3 server/artsearch.py names 名单.txt` 只查不下载。`✓` 能配（`→` 后是作品里的写法）、`⚠` 像写错了（给了正确写法）、`✗` 作品里没这个名（列出实际的角色名，点一个就换）。核对过的名字绑到角色 id 存 `instance/uploads/art_bind.json`，配图直接按 id 取图，不再搜索。
- **中文名大多能搜到，假名化的不行**：实测 `川澄舞`、`沢渡真琴`、`美坂栞` 都搜得到（AniList 的 `name.native` 就是汉字）。难的是两种：一是名单写简体、库里写日文（泽渡真琴 / 沢渡真琴），靠 `artsearch.py` 里的变体表（泽→沢、宫→宮、亚→亜…）自动转，能对上；二是汉字被改写成假名（月宫亚由 / 月宮あゆ），差两个字且不是错字，任何自动相似度都不可靠，只能把该作品的角色列表摆出来让人点。所以 Bangumi 不通时不是全灭，但会漏一部分。
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
- **`auto` 还不吃 AniList 的作品角色表**：核对（`names`）在 Bangumi 不通时会用 AniList 的角色表建索引，但一键配图里的 `index()` 只用 Bangumi 的 `subjects/{id}/characters`。所以 Bangumi 挂掉时，配图只能按名字直搜，比核对能确认的更少——会出现「核对说 4/5 能配，配图只出 3 张」。绑定的那 4 个不受影响（按 id 取图），差的是没绑上的那些。

---

## 6. 验收清单

从零到能发链接，按这个顺序走一遍，每步都有可观察的结果：

```bash
# 0 没有名单时，按作品角色表出一版（全部空缺），改好再用
python3 server/artsearch.py roster Kanon -o 名单.txt

# 1 建站 + 自动配图 + 生成一图流
#   标准做法是网页向导：python3 server/server.py --prefill 名单.txt --title "Kanon 团建"，打开打印的 /setup?t=… 链接，
#   完成页会依次亮起「建站 → 自动配图 → 生成一图流」，结果也记在 logs/server.log 的 firstrun 那一行。
#   没有浏览器时用命令行（不给 --password 就会随机生成并打印一次，务必抄下来）：
python3 init.py --instance instance-kanon --title "Kanon 团建" \
  --import 名单.txt --yes
# 期望：「N 个团、M 个席位（X 已定、Y 空缺)」→ 一行行「封面 / 立绘 … ← …」→
#       「配图：封面 a 张、立绘 b 张」+「一图流：已生成」（没装依赖则是「跳过」和安装命令）+ 管理密码

# 2 补配图（可选，比如断网后重试）
CASTCALL_INSTANCE=instance-kanon python3 server/artsearch.py auto --dry
CASTCALL_INSTANCE=instance-kanon python3 server/artsearch.py auto

# 3 单测
python3 -m unittest discover -s tests
# 期望：Ran 110 tests ... OK

# 4 起服务
CASTCALL_INSTANCE=instance-kanon python3 server/server.py
# 期望：castcall: http://127.0.0.1:5510/  （实例目录 …，Notion 未启用）
```

打开页面后确认四件事：

1. 一部作品 + 摄影后勤 → **单团页**（页首是封面和「N 个角色」），不是两张卡。
2. 招募中的角色有「报名 →」，点进去是报名表（提交后提示「等审核」，不会直接占位）。
3. 页面拉到下方有「已定阵容」和「摄影 / 后勤」，工作组的空缺也能报名。
4. 右下角的锁 → 输密码 → 工具条出现「审核」，能通过刚才那条报名。
5. 抬头有「一图流」入口，打开是海报（第 1 步说跳过的话没有：装好依赖后在后台点「生成一图流」）。
6. 摄影 / 后勤这类工作组没有被配上莫名其妙的封面（以前会拿组名去搜作品，配到《摄影师的复仇》这种）。

对外的最后一步见 `docs/deploy.md`（systemd + nginx）。
