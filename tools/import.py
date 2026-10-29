#!/usr/bin/env python3
"""把名单导入名册（格式见 server/importer.py 开头的说明）。

  python3 tools/import.py 名单.txt              # 并进现有名册：新团、新角色加进去，空缺补上 CN，已有的 CN 不改
  python3 tools/import.py 名单.csv --replace    # 整个名册换成这份名单（会先备份）
  python3 tools/import.py 名单.txt --dry        # 只看会导入什么，不写
  pbpaste | python3 tools/import.py -           # 从标准输入读（macOS 剪贴板）

和网页保存走同一条链路（备份 → 原子写 → 变更队列），服务器开着也可以直接跑：页面刷新就能看到。"""
import argparse,json,os,sys,threading
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,os.path.join(ROOT,'server'))
import config,importer
def main(argv):
  ap=argparse.ArgumentParser(description='导入名单');ap.add_argument('file',help='名单文件，- 表示标准输入')
  ap.add_argument('--instance',default=os.environ.get('CASTCALL_INSTANCE') or os.path.join(ROOT,'instance'))
  ap.add_argument('--replace',action='store_true',help='替换整个名册，而不是合并');ap.add_argument('--dry',action='store_true')
  ap.add_argument('--group',default='',help='名单里没有「## 团名」时用的团名（默认：只有一个团时沿用它的名字）')
  a=ap.parse_args(argv);C=config.use(a.instance)
  if not os.path.isfile(C.ROSTER):print('还没初始化：先运行 python3 init.py（或在浏览器里打开网站走向导）',file=sys.stderr);return 1
  if a.file=='-':text=sys.stdin.read()
  else:
    with open(a.file,encoding='utf-8-sig') as f:text=f.read()
  import roster
  cur=roster.load();dg=a.group or (cur['groups'][0]['name'] if len(cur['groups'])==1 else '我们的团')
  try:new=importer.parse(text,dg)
  except ValueError as e:print(e,file=sys.stderr);return 1
  print('读到：'+importer.summary(new))
  if a.replace:out=new;msg='名册已替换'
  else:
    out=json.loads(json.dumps(cur));ag,ar,fl=importer.merge(out,new);msg=f'新增 {ag} 个团、{ar} 个角色，补上 {fl} 个 CN'
  if a.dry:print('（--dry，没有写入）',msg);return 0
  roster.validate(out)
  with threading.Lock():roster.save(out,'导入')
  print(msg+'。现在：'+importer.summary(roster.load()))
  return 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
