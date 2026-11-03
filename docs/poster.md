# 一图流（可选）

把名册排成一张大海报：网站上 `/poster/` 可以直接看（手机竖版、电脑宽版），也能导出 JPG 发群。

## 安装

核心服务只用标准库。海报要额外装：

```bash
python3 -m venv .venv-poster
.venv-poster/bin/pip install -r requirements-poster.txt
.venv-poster/bin/playwright install chromium
```

另外要有中文字体（海报用 Noto Sans / Serif CJK）：

- Debian / Ubuntu：`sudo apt install fonts-noto-cjk`
- Fedora：`sudo dnf install google-noto-sans-cjk-fonts google-noto-serif-cjk-fonts`
- macOS：系统自带的字体能显示，但要和设计稿一致，最好装 Noto CJK

然后在 `.env` 里告诉服务器用哪个 Python：

```ini
CASTCALL_POSTER_PYTHON=/path/to/castcall/.venv-poster/bin/python
```

按上面的命令把 venv 建在仓库根目录的 `.venv-poster/` 时，这一行可以不写，会自动使用。

## 生成

- **建站时**：`init.py` 和网页向导建完站、配完图会自动生成一次（`init.py --no-poster` 关掉）。
- **后台**：工具条点「生成一图流」，一两分钟后提示完成。抬头会出现「一图流」入口。名册或图片改过之后要再点一次。
- **命令行**：

```bash
.venv-poster/bin/python poster/build.py                 # 多团：master + wide；单团：master + social
.venv-poster/bin/python poster/build.py social --group "示例作品 A"
```

产物在 `instance/poster/`：

| 文件 | 尺寸 | 用途 |
|---|---|---|
| `master.html` / `master.jpg` | 宽 2400，长度随人数 | 竖版，手机看、发群 |
| `wide.html` / `wide.jpg` | 宽 3840，8 列 | 宽版，电脑、投屏（只有多团） |
| `social.jpg` | 1080×1350 | 单团卡片，社交平台配图 |

名册改了不会自动重建，要再点一次。成员是空、`待定`、`TBD` 的席位不上海报。

## 让封面裁得好看

每个团的标题条会铺这个团的封面。条很扁，程序要知道封面上哪块区域必须完整露出（通常是人物从眉毛到下巴）。在名册里给团加：

```json
"cover_focus":[0.1,0.3,0.9,0.5]
```

四个数依次是左、上、右、下，都是占封面宽或高的比例（0–1）。上面这个例子的意思是：横向 10%–90%、纵向 30%–50% 的区域要完整露出。没写就用 `[0.1,0.1,0.9,0.5]`。

调法：生成一次，看 `/poster/` 上这个团的标题条，脸被切了就调这四个数，再生成。

## 其他素材

- **立绘**：在后台上传。海报会自动裁成 4:5 半身卡，没有立绘的显示相机图标。
- **标题大图**：放一张图到 `instance/uploads/brand/`，在 `site.json` 写 `"poster":{"hero":"文件名"}`。
- **logo**：`brand.logo`，同上。

## 服务器上跑不了 Chrome？

在自己电脑上生成，再把 `instance/poster/` 整个目录传到服务器同样的位置。网页版引用的是相对网站的地址，换台机器也能看。
