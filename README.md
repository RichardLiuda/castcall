# castcall

**cos 团建 / 团片招募用的名册站。** 一个页面看清「哪个团、哪个角色、谁来出」，空着的角色可以在线报名，组织者在后台审核通过后自动落座。

- **多团同时招募**（一次团建好几部作品）和**单团招募**（一个团的团片）都支持，同一份代码按团数自动切换。
- **只依赖 Python 标准库**：`python3 server/server.py` 就能跑，前端没有构建步骤。
- **数据在本地**：名册是一个 JSON 文件，报名和留言在 sqlite 里。
- **Notion 可选**：想在 Notion 里看表、审核，接上就行；不接也什么都不缺。
- **一图流海报**（可选）：一键把名册排成长图，网页版和 JPG 都有。

## 三分钟跑起来

```bash
git clone <这个仓库> castcall && cd castcall
python3 init.py              # 问几个问题：单团还是多团、活动名称、管理密码…
python3 server/server.py     # 打开 http://127.0.0.1:5510/
```

右下角的锁是后台入口。示例名册登录后就能改：加团、加角色、上传封面和立绘、审核报名。

需要 Python 3.9 以上，macOS / Linux / Windows 都行。

## 页面上有什么

| | 说明 |
|---|---|
| 名册 | 多团：封面卡墙，点开看席位；单团：直接是这个团的角色表 |
| 搜索 | 按角色名或 CN 找人 |
| 缺人看板 | 所有空缺 / 角色未定 / 还没立绘的席位，按团列出 |
| 报名 | 空缺席位上点「报名」，填 CN 和联系方式；**不会直接占座**，后台通过才写进名册 |
| 倒计时 | 填了开场时间就显示，活动结束后自动消失 |
| 留言区 | 默认先显示、后台可隐藏；也可以改成先审后发 |
| 一图流 | 后台点「生成一图流」后，抬头出现入口 |

## 文档

- [docs/quickstart.md](docs/quickstart.md)：从零到上线的完整步骤
- [docs/config.md](docs/config.md)：`site.json` 每个字段、名册格式、单团 / 多团怎么切
- [docs/notion.md](docs/notion.md)：接 Notion 的手把手教程
- [docs/poster.md](docs/poster.md)：一图流（要装 Pillow + Playwright）
- [docs/deploy.md](docs/deploy.md)：放到服务器上（systemd + 反向代理）

## 目录

```
server/    HTTP 服务、名册保存链路、sqlite、Notion 适配器
web/       前端（原生 HTML/CSS/JS）
poster/    一图流生成脚本
examples/  示例配置和名册
tests/     python3 -m unittest discover -s tests
instance/  ← 你的数据（init.py 生成，已在 .gitignore 里，不要提交）
```

## 许可证

代码以 [MIT](LICENSE) 发布。**许可证不覆盖任何图片和素材**：你上传的封面、立绘、logo 版权归各自的权利人，仓库里也不附带任何第三方素材。

castcall 从一个真实活动的名册站（keyroster）里抽出来，去掉了活动专属的内容和数据。
