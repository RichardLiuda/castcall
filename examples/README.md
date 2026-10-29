# 示例数据

| 文件 | 内容 | 用法 |
|---|---|---|
| `site.example.json` | 完整的 `site.json` 示例 | `init.py` 以它为模板 |
| `roster.multi.example.json` | 4 个团的小名册，作品和角色都是虚构的 | `init.py`（选多团）默认用它 |
| `roster.single.example.json` | 1 个团的小名册，虚构 | `init.py`（选单团）默认用它 |
| `roster.key-demo.json` | 13 个团、150 个席位的大样例 | `init.py --example key-demo` |
| `roster.key-single.json` | 上面其中一个团，20 个席位 | `init.py --example key-single` |

## ⚠️ 待通用化：key-demo / key-single

这两份是从一次真实的 Key 作品团建（keyroster）里照搬结构做的，用来测试大名册的排版和性能：

- **作品名、角色名、团的配色是 Key 作品里真实的名字**（CLANNAD、Kanon、AIR……）。
- **CN 全部是随机生成的假昵称**，和真实参与者对不上，也没有任何联系方式。
- **不含任何图片。** 封面是 `init.py` 现场画的条纹占位图，立绘为空。

**公开发布前要换掉**：生成一份结构相同（团数、人数、空缺分布不变）但作品名、角色名都是虚构的版本，替换这两个文件，再把 `init.py --example` 的说明、`docs/quickstart.md` 里对应的段落一起改掉。
