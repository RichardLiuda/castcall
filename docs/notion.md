# 接 Notion（可选）

**先说清楚 Notion 在这里管什么、不管什么：**

- 本地数据库永远是主数据。网站不依赖 Notion，Notion 挂了、token 过期了，网页照常报名、留言、保存。
- 接上以后：
  - 报名会多一份到 Notion，你可以**在 Notion 里改「状态」来审核**。
  - 留言也会多一份，**在 Notion 里改成「已隐藏」或删掉就下架**。
  - 名册改动每 15 分钟推一份到 Notion，方便在表格里筛选、统计。
- **名册是单向的**：在 Notion 里改名册表格**不会**改到网站上。改名册请用网站后台。
- 三个库互相独立，只想用 Notion 审报名，就只接报名库。

整个过程大约 10 分钟。

## 1. 建一个 integration，拿 token

1. 打开 <https://www.notion.so/profile/integrations>，点 **New integration**（新建集成）。
2. 名字随便起（比如 castcall），Workspace 选你放表格的那个，类型选 **Internal**。
3. 保存后进入它的设置页：
   - **Capabilities** 里勾上 Read content、Update content、Insert content。
   - 复制 **Internal Integration Secret**，以 `ntn_` 开头。这就是 token，**不要发给别人，也不要提交进 git**。

## 2. 建表

在 Notion 里新建一个页面，在里面建下面的数据库（`/database` → Table）。**列名要一字不差**，列的类型照着选。不想用中文列名，见文末[列名对不上](#列名对不上)。

### 报名库

| 列名 | 类型 | 说明 |
|---|---|---|
| CN | 标题（Title） | 新建表格自带的「名称」列，改名成 CN |
| 联系方式 | 文本（Text） | |
| 团 | 文本 | |
| 角色 | 文本 | |
| 记录ID | 文本 | 席位 ID，别改它 |
| 状态 | 单选（Select） | 选项：`待审`、`已通过`、`已拒绝` |

### 留言库

| 列名 | 类型 | 说明 |
|---|---|---|
| CN | 标题 | |
| 内容 | 文本 | |
| 状态 | 单选 | 选项：`已通过`、`已隐藏`、`待审` |
| 时刻 | 文本 | 提交时间 |

### 名册库

| 列名 | 类型 | 说明 |
|---|---|---|
| 角色 | 标题 | |
| 成员 | 文本 | |
| 团 | 单选或文本 | 单选的话可以按团分组看 |
| 排序 | 数字（Number） | |
| 状态 | 单选 | `空缺` / `待配图` / `已定`，网站自动填 |
| 记录ID | 文本 | |

单选的选项不用提前建全，网站第一次写进去的时候 Notion 会自动加上。「状态」列也可以用 Notion 的「状态（Status）」类型，但那种类型的选项必须提前建好。

## 3. 把每个库共享给 integration

**最容易漏的一步。** 对每个库：

1. 点进库（整页打开）。
2. 点右上角 `···` → **连接**（Connections）→ 搜你在第 1 步起的名字 → 确认。

没做这一步，后面的检查会报 `object_not_found`。

## 4. 把 token 和库 ID 写进 .env

在仓库根目录复制 `.env.example` 为 `.env`，填上：

```ini
NOTION_TOKEN=ntn_你的token
NOTION_SIGNUP_DB=https://www.notion.so/你的workspace/1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d?v=...
NOTION_GUESTBOOK_DB=...
NOTION_ROSTER_DB=...
```

库 ID 的拿法：整页打开库，复制浏览器地址栏的链接，直接粘贴整条就行。程序会取出 `?v=` 前面那串 32 位字符（`?v=` 后面的是视图 ID，不是库 ID）。

用不到的库那一行留空或删掉。

## 5. 检查

```bash
python3 server/notion.py check
```

全部 ✓ 才算接好。常见的 ✗ 见下面的[常见报错](#常见报错)。

## 6. 第一次推名册

接名册库时，先把现有的每个席位都推过去一次：

```bash
python3 server/notion.py push --all
```

之后就不用管了：服务器每 15 分钟自动推一次改动（`site.json` 的 `notion.rosterEvery` 可以改，单位秒）。想立刻推：`python3 server/notion.py push`。

## 7. 重启服务器

```bash
python3 server/server.py
```

启动时会显示「Notion 已启用」。

## 怎么审核

**报名：**

1. 有人报名，报名库里出现一行，状态是「待审」。
2. 把状态改成 **已通过**，20 秒内（`notion.syncEvery`）名册上那个席位就写上了这个人的 CN。
3. 改成 **已拒绝**，报名作废。如果之前通过过，席位会空出来。
4. 已通过的改回 **待审**，席位也会空出来。但只对在 Notion 里通过的报名生效：在网站后台点过「通过」的，Notion 里的旧状态推翻不了。
5. 在网站后台审核也行，结果会同步回 Notion 的「状态」列。两边用哪个都可以。
6. 席位已经被别人占了的话，「已通过」不会覆盖原来的人，网站后台的审核面板里会显示原因。

**留言：** 状态改成 **已隐藏**，或者直接删掉那一行，20 秒内网页上就看不到了。改回「已通过」又会出现。

## 常见报错

| 报错 | 原因 | 怎么办 |
|---|---|---|
| `HTTP 401 unauthorized` | token 不对或被重置了 | 回 integration 页面重新复制 |
| `HTTP 404 object_not_found` | 库没共享给 integration，或者 ID 填错了 | 做第 3 步；确认粘贴的是库的链接，不是库所在页面的链接 |
| `缺少列：xxx` | 列名不一样（多了空格、全角半角不同…） | 改列名，或者看下面的列名映射 |
| `列类型写不进去` | 比如把「排序」建成了公式列 | 换成表里写的类型 |
| `「状态」应该是选择（select）类型` | 状态列建成了文本 | 改成单选 |
| `HTTP 400 validation_error` | 用了 Status 类型，但没建对应选项 | 在列设置里把选项建好，或者换成单选 |
| `HTTP 429 rate_limited` | 一次推太多 | 不用管，下一轮会继续推 |

推送失败的报名和留言会自动重试，不会丢。名册推送只有全部成功才算完成，失败的那批下一轮会重推。服务器日志在 `instance/logs/server.log`。

## 列名对不上

列名映射在 `site.json` 的 `notion.columns` 里。比如想用英文列名：

```json
{"notion":{
  "columns":{
    "signup":{"name":"Name","contact":"Contact","group":"Group","character":"Role","id":"Seat ID","status":"Status"},
    "guestbook":{"name":"Name","text":"Message","status":"Status","time":"Time"},
    "roster":{"character":"Role","member":"Member","group":"Group","order":"Order","status":"Status","id":"Seat ID"}
  },
  "status":{"pending":"Pending","approved":"Approved","rejected":"Rejected","hidden":"Hidden"}
}}
```

改完再跑一次 `check`。

## 断开 Notion

把 `.env` 里的 `NOTION_TOKEN` 删掉，重启服务器。本地数据一点不少，Notion 里的表格也原样保留。
