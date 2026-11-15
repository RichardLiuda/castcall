#!/usr/bin/env python3
"""把站点打包成一个「发布目录」：交给托管平台（Docker、PaaS、WorkBuddy 之类的在线应用）整个上传。见 docs/hosting.md。

  python3 tools/bundle.py --out ../castcall-publish            # 代码 + instance/ → ../castcall-publish
  python3 tools/bundle.py --out ../castcall-publish --check    # 只做发布前体检，不写

和直接上传仓库相比：
- 不带 .venv-poster（上百 MB，平台上没 Chromium 也用不上）、.git、tests、docs、本机缓存和日志；
- instance/ 总是放在 <out>/instance，启动命令固定是 python3 server/server.py；
- sqlite 用 backup API 拷一份一致的快照（服务器开着也能打包）；
- .env 只留能上云的（Notion、代理头、备份份数），去掉本机路径（CASTCALL_CHROME 等）；
- 去掉 .setup-token / firstrun.pending：线上不该再进向导、也不该去补跑配图。
<out> 每次整个重建，所以要用固定的目录：很多平台按目录认应用，换目录链接就变了。
已经存在、但不是本工具生成的目录不会被覆盖。"""
import argparse,json,os,shutil,sqlite3,sys
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,os.path.join(ROOT,'server'))
import config
MARK='.castcall-bundle'
CODE=('server','web','poster','tools','examples','init.py','requirements-poster.txt','LICENSE','README.md')
SKIP_NAMES={'__pycache__','.DS_Store','.claude','.workbuddy'}
SKIP_INSTANCE={'logs','.setup-token','firstrun.pending','castcall.db','castcall.db-wal','castcall.db-shm','.env'}
LOCAL_ENV=('CASTCALL_CHROME','CASTCALL_POSTER_PYTHON','CASTCALL_HOST','CASTCALL_PORT','CASTCALL_INSTANCE')
def ignore(_dir,names):return {n for n in names if n in SKIP_NAMES or n.endswith(('.pyc','.log','.tmp'))}
def env_lines(C):
  """仓库根 .env + instance/.env 合并后能上云的部分 → (留下的行, 去掉的 key)"""
  keep,drop=[],[]
  for k,v in C.env.items():
    if k in LOCAL_ENV:drop.append(k)
    else:keep.append(f'{k}={v}')
  return keep,drop
def size(p):
  n=0
  for d,_,fs in os.walk(p):
    for f in fs:
      try:n+=os.path.getsize(os.path.join(d,f))
      except OSError:pass
  return n
def check(C):
  """→ (errors, warnings, facts)：发布前体检"""
  import setup,store
  err,warn,facts=[],[],[]
  if not setup.initialized(C):err.append(f'{C.INSTANCE} 还没建站：先按 docs/quickstart.md 建好、验收过再发布')
  else:
    c=store.counts();su=sum(c['signups'].values());gb=sum(c['guestbook'].values())
    facts.append(f'报名 {su} 条、留言 {gb} 条、成员照片 {sum(c.get("photos",{}).values())} 张会一起上传')
    if su or gb:warn.append('本地已经有报名 / 留言：如果线上已经开募，重新发布会用这份本地数据**整个覆盖**线上的（见 docs/hosting.md「数据」）')
  if not os.path.isfile(os.path.join(C.POSTER,'master.html')):warn.append('还没有一图流（instance/poster/master.html）：线上一般生成不了，先在本地生成再打包，否则线上没有「一图流」入口')
  if os.path.exists(os.path.join(C.INSTANCE,'firstrun.pending')):warn.append('建站后的自动配图 / 一图流还没跑完（firstrun.pending）：先在本地启动一次让它跑完')
  if not config.C.notion_on():facts.append('没接 Notion：线上的报名只存在线上的 instance/ 里，重新发布会被覆盖')
  _,drop=env_lines(C)
  if drop:facts.append('.env 里这些是本机路径，不会带上去：'+'、'.join(drop))
  if not C.getenv('CASTCALL_TRUST_PROXY'):facts.append('没设 CASTCALL_TRUST_PROXY：上线后登录后台打开 /api/admin/whoami 确认平台的真实 IP 请求头，再补上（见 docs/hosting.md「频率限制」）')
  return err,warn,facts
def build(C,out):
  if os.path.exists(out):
    if os.listdir(out) and not os.path.exists(os.path.join(out,MARK)):raise SystemExit(f'{out} 已经有别的东西了（不是 bundle.py 生成的），换个空目录')
    shutil.rmtree(out)
  os.makedirs(out)
  for x in CODE:
    s=os.path.join(ROOT,x)
    if os.path.isdir(s):shutil.copytree(s,os.path.join(out,x),ignore=ignore)
    elif os.path.isfile(s):shutil.copy2(s,out)
  di=os.path.join(out,'instance')
  shutil.copytree(C.INSTANCE,di,ignore=lambda d,ns:ignore(d,ns)|({n for n in ns if n in SKIP_INSTANCE} if os.path.samefile(d,C.INSTANCE) else set()))
  if os.path.isfile(C.DB):
    src=sqlite3.connect(C.DB);dst=sqlite3.connect(os.path.join(di,'castcall.db'))
    with dst:src.backup(dst)
    src.close();dst.close()
  keep,_=env_lines(C)
  if keep:
    with open(os.path.join(out,'.env'),'w',encoding='utf-8') as f:f.write('# tools/bundle.py 生成：只留能上云的配置\n'+'\n'.join(keep)+'\n')
    try:os.chmod(os.path.join(out,'.env'),0o600)
    except OSError:pass
  with open(os.path.join(out,MARK),'w',encoding='utf-8') as f:json.dump({'from':C.INSTANCE},f,ensure_ascii=False)
def main(argv):
  ap=argparse.ArgumentParser(description='打包发布目录（见 docs/hosting.md）')
  ap.add_argument('--out',help='发布目录（固定用同一个，平台按目录认应用）')
  ap.add_argument('--instance',default=os.environ.get('CASTCALL_INSTANCE') or os.path.join(ROOT,'instance'))
  ap.add_argument('--check',action='store_true',help='只体检，不打包')
  a=ap.parse_args(argv);C=config.use(a.instance)
  if not a.check and not a.out:ap.error('要给 --out（或者只体检：--check）')
  if a.out and os.path.abspath(a.out).startswith(os.path.abspath(ROOT)+os.sep):ap.error('--out 要放在仓库外面（不然会把自己打包进去），比如 ../castcall-publish')
  err,warn,facts=check(C)
  for x in err:print('✗',x)
  for x in warn:print('!',x)
  for x in facts:print('·',x)
  if err:return 1
  if a.check:return 0
  build(C,os.path.abspath(a.out))
  print(f'\n打包好了：{os.path.abspath(a.out)}（{size(a.out)/1e6:.1f} MB）\n启动命令：python3 server/server.py    安装命令：不需要（只用标准库）')
  return 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
