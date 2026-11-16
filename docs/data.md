# 数据：在哪、怎么备份、换机器怎么办

**你的全部东西都在一个目录里：`instance/`。** 代码可以随时删、随时 `git pull`，数据不会被动到。

```
instance/
  site.json       活动信息、报名开关、报名字段、招募须知、主题色
  roster.json     名册（网页保存会改它）
  castcall.db     报名、留言、成员照片记录（sqlite）
  auth.json       管理密码的哈希（不是明文）
  uploads/        封面、立绘、logo；还有 map.json（角色 → 立绘）和 art_bind.json（核对过的名字）
  poster/         一图流的网页和 JPG
  backups/        每次保存名册前的快照（默认留最近 300 份）
  cache/thumbs/   后台找图面板的缩略图缓存，删了会自己重建
  logs/           server.log（含 firstrun 的结论那一行）、poster.log（一图流的构建输出）
  .setup-token    向导验证码（建完站就删）
```

`instance/` 已在 `.gitignore` 里，不会被提交；除了你自己，没有脚本会清它。

---

## 备份

**整个目录拷走就是完整备份**，包括密码和图片：

```bash
tar czf castcall-$(date +%Y%m%d).tar.gz instance/
```

想定时备份，交给系统的 `launchd` / `cron` 跑上面这一行即可。恢复到另一台机器上时解压回同一位置，`python3 server/server.py` 就能接着用。

单条数据的撤销不用整目录：名册改坏了去 `instance/backups/` 找上一份（每次保存前自动存，默认留 300 份）。

---

## 换机器 / 迁移

```bash
# 新机器
git clone https://github.com/RichardLiuda/castcall.git && cd castcall
# 把旧机器的 instance/ 整个拷到仓库根目录下（同名覆盖）
python3 server/server.py
```

管理密码、名册、报名记录、图片全跟着回来。**海报建议在新的机器上重新生成一次**（`instance/poster/` 里的 HTML 引用了本机的图片路径和字体）。

---

## 线上和本地是两份数据

发布到托管平台时，`tools/bundle.py` 会把**当时的** `instance/` 打包上去。之后：

- 本地收到的新报名，线上看不到；
- 线上收到的新报名，本地也看不到（除非把线上的 `instance/` 拉回来）。

所以发布是单行道，选一种做法：

| 做法 | 适合 |
|---|---|
| **只在开募前发布一次**，之后不再动 | 短周期、报名量小的团片 |
| 接 [Notion](notion.md) 同步，两边都往同一个库里写 | 需要随时看报名、又不想反复发布 |
| 定期把线上 `instance/` 拉回来（或反过来） | 能接受手动，但要留全量数据 |

**重新发布会整个覆盖线上的 `instance/`**——线上已收到的报名、留言、审核记录都会没。开募以后再发布，先把线上的 `instance/` 备份下来。

---

## 不要做的事

- **不要手改 `instance/roster.json` 再让服务器读**：走后台或 `tools/import.py`，它们会备份、补 id、记变更。非要手改，先停服务器，改完跑一次校验（见 [AGENTS.md](../AGENTS.md) 的「不要做」）。
- **不要删 `instance/` 或 `instance/castcall.db`**：那是全部数据。
- **不要把 `instance/` 提交进 git**：里面有管理密码哈希和真实报名信息。

---

## 配置和数据的区别

想改「活动日期、报名开关、报名字段、招募须知」这类**配置**，去改 `instance/site.json` 或在后台点（字段说明见 [config.md](config.md)）；
`roster.json` / `castcall.db` 是**数据**，走后台或导入工具。两者的分界是：删掉还能重建的是配置，删掉就没了的是数据。
