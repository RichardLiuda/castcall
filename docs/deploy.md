# 部署

下面以一台 Linux 服务器 + systemd + nginx 为例。用 Caddy、Cloudflare Tunnel 也一样：castcall 只监听本机端口，外面套一层负责 HTTPS 的反向代理。

## 1. 放代码、初始化

```bash
sudo useradd --system --create-home --home-dir /srv/castcall castcall
sudo -u castcall git clone https://github.com/RichardLiuda/castcall.git /srv/castcall/app
cd /srv/castcall/app
sudo -u castcall python3 init.py --title "活动名" --import 名单.txt --fields "身高,样片*" --yes   # 服务器上没浏览器，用命令行；选项见 quickstart.md 第 2 步
```

也可以先在自己电脑上用网页向导建好（`server.py --prefill`），再把整个 `instance/` 传上来。`init.py` 建完会自动配图、生成一图流。服务器上没装一图流依赖时这步会跳过，见下面第 6 节。

## 2. systemd

`/etc/systemd/system/castcall.service`：

```ini
[Unit]
Description=castcall
After=network.target

[Service]
User=castcall
WorkingDirectory=/srv/castcall/app
ExecStart=/usr/bin/python3 server/server.py
# 想把数据放在代码目录外面：
# Environment=CASTCALL_INSTANCE=/srv/castcall/instance
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now castcall
journalctl -u castcall -f
```

## 3. 反向代理

nginx：

```nginx
server {
  server_name roster.example.com;
  client_max_body_size 10m;          # 上传封面 / 立绘
  location / {
    proxy_pass http://127.0.0.1:5510;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
  # listen 443 ssl; ...（用 certbot 配）
}
```

### 客户端 IP

频率限制按 IP 计数。在代理后面，castcall 看到的 IP 都是 `127.0.0.1`，所以要告诉它读哪个请求头：

```ini
# .env
CASTCALL_TRUST_PROXY=X-Forwarded-For
```

| 代理 | 填 |
|---|---|
| nginx（上面的配置） | `X-Forwarded-For` |
| Caddy | `X-Forwarded-For` |
| Cloudflare Tunnel | `CF-Connecting-IP` |

**服务直接暴露在公网（没有代理）时，一定不要设这一项。** 否则别人在请求里伪造这个头，就能绕过所有频率限制，包括登录密码的试错次数。

设了这一项、并且代理传来 `X-Forwarded-Proto: https` 时，登录 cookie 会带上 `Secure`。

## 4. 更新代码

运行时数据都在 `instance/`，不在 git 里，所以更新就是：

```bash
cd /srv/castcall/app
sudo -u castcall git pull
sudo systemctl restart castcall
```

## 5. 备份

`instance/` 是全部数据，定时打包它就行：

```bash
# crontab -e（castcall 用户）
20 4 * * * tar czf /srv/castcall/backup-$(date +\%F).tgz -C /srv/castcall/app instance && find /srv/castcall -name 'backup-*.tgz' -mtime +30 -delete
```

每次网页保存前，名册还会在 `instance/backups/` 留一份快照（默认最近 300 份，环境变量 `CASTCALL_KEEP_BACKUPS` 可改）。改坏了可以从这里拷回 `roster.json`。

## 6. 一图流

要在服务器上生成海报，得装 Chrome 和中文字体，见 [poster.md](poster.md)。装不了的话，在自己电脑上生成，再把 `instance/poster/` 传上来。
