---
name: castcall-publish
description: Publish a castcall roster site that is already built locally to a hosting platform that takes a directory and returns a link (Docker, PaaS, or an assistant's own "publish as app" tool such as WorkBuddy), republish it, or take it offline. Covers the data-overwrite decision, bundling with tools/bundle.py, platform settings, post-publish checks and the proxy / rate-limit fix. Use when the user asks to publish / deploy / 上线 / share a castcall site, update the live link, or take it down.
---

# castcall：发布到托管平台

完整说明在 `docs/hosting.md`，先读它。这里是你和用户之间的顺序。站点还没建好的话，先走 `castcall-setup`。

**发布是对外的、覆盖式的动作：只有用户在这一轮明确说了发布 / 上线 / 要分享链接才做；否则先问，然后停。**

1. **体检**：`python3 tools/bundle.py --check`，把 `✗` / `!` 的条目原样告诉用户。
   - `✗` 没建站：先建站。
   - 没有一图流：问用户要不要先在本地生成（`docs/poster.md`）；平台上一般生成不了。
   - 自动配图没跑完：先在本地启动一次 `python3 server/server.py`，等它跑完。

2. **数据怎么处理——必须问用户**（`docs/hosting.md` 第 1 节）：
   > 发布会把本地的 instance/ 整个传上去。以后再发布的话，线上的报名、留言会被本地这份覆盖。你想：① 接 Notion 保底（推荐）② 只在开募前发布这一次 ③ 演示用，接受覆盖？

   选 ① 就先按 `docs/notion.md` 配好 `.env`（token 不要你自己编，问用户要）。

3. **打包**：`python3 tools/bundle.py --out <固定目录>`。目录选在仓库外，并且**以后每次都用同一个**（平台按目录认应用，换了目录链接就变了）。
   第一次发布时把这个目录告诉用户，记进项目的说明里。

4. **发布**：用平台或你自己的发布工具，参数照 `docs/hosting.md` 第 3 节：安装命令留空，启动命令 `python3 server/server.py`，Python 运行时。
   - 应用名取活动名。
   - 平台返回「不支持」时，把原因原样转告用户并停下：**不要**换成静态托管硬发（页面会是空的），也不要改 `server/` / `web/` 去迁就。
   - WorkBuddy：工具是 `workbuddy_sites_deploy`，`language: "python"`，`installCmd: ""`，`startCmd: "python3 server/server.py"`，用户明确要求时才带 `userAskedToPublish: true`；不传 `appId`，按 `directory` 认应用。

5. **验收**：按 `docs/hosting.md` 第 4 节跑那三条 `curl`，再在浏览器里走一遍报名和后台登录（报名要在**线上**后台的「审核」里看）。

6. **修频率限制**：请用户登录线上后台，打开 `<链接>/api/admin/whoami`，把结果给你。根据 `headers` 里平台传真实 IP 的那个头，在 `.env` 写 `CASTCALL_TRUST_PROXY=<头名>`，重新打包、发布，再看一次 `whoami`，确认 `ip` 是用户自己的公网 IP。
   这一步不做，全站所有访客共用一份频率限制，开募时报名会被误拦。

7. **交付**：告诉用户链接、后台密码就是本地建站时设的、哪些事线上做不了（重新生成一图流；配图看平台网络），以及重新发布会覆盖线上数据（除非接了 Notion）。

**下线**：用户明确说下线才做，用同一个发布目录调用平台的下线操作；做之前再确认一次，链接会立刻失效。
