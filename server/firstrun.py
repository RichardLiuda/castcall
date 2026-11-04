"""首次部署的收尾：自动配图 → 生成一图流。init.py（前台，打印进度）和网页向导（后台线程）共用。

两步都是「尽力而为」：断网、Bangumi / AniList 没结果、一图流缺依赖，都只记下原因和补救办法，不让建站失败。
  art=True     从 Bangumi / AniList 给缺图的团找封面、给角色找立绘（只配有把握的）
  poster=True  site.json 里 poster.enabled 时生成一图流（要 Pillow + Playwright + 中文字体，见 docs/poster.md）"""
import json,os,subprocess,threading,time
import config
INSTALL='pip install -r requirements-poster.txt && playwright install chromium（详见 docs/poster.md）'
def art(lock=None,log=print):
  import artsearch
  try:rep=artsearch.auto(lock,log=log)
  except Exception as e:return {'covers':0,'portraits':0,'skipped':[],'errors':[repr(e)]}
  return rep
def art_line(rep):
  s=f"配图：封面 {rep.get('covers',0)} 张、立绘 {rep.get('portraits',0)} 张"
  if rep.get('skipped'):s+=f"，{len(rep['skipped'])} 个没把握跳过（后台「找立绘」手选）"
  if rep.get('errors'):s+=f"，{len(rep['errors'])} 个出错（多半是网络，稍后后台点「一键配图」重试）"
  return s
def poster(wait=True,log=print):
  """→ (ok, message). wait=False 时交给 server.poster_build() 在后台跑。"""
  import server
  if not config.C.site['poster']['enabled']:return False,'一图流：site.json 里关掉了，跳过'
  if not server.poster_available():return False,'一图流：这台机器还没装依赖，跳过。装好后在后台点「生成一图流」：'+INSTALL
  if not wait:server.poster_build();return True,'一图流：后台生成中，一两分钟后抬头出现入口'
  args,env=server.poster_cmd();log('生成一图流…（一两分钟）')
  try:r=subprocess.run(args,env=env,capture_output=True,text=True,timeout=900)
  except Exception as e:return False,f'一图流：没生成出来（{e}），稍后在后台点「生成一图流」重试'
  if r.returncode:return False,'一图流：没生成出来，稍后在后台点「生成一图流」重试。最后几行输出：\n'+(r.stdout+r.stderr).strip()[-600:]
  return True,'一图流：已生成（instance/poster/），页面抬头有入口'
def run(*,do_art=True,do_poster=True,log=print):
  """前台：init.py 用。返回要打印给用户的几行总结。"""
  out=[]
  if do_art:log('\n自动配图…（每个角色一两次请求，几十个角色要一两分钟）');out.append(art_line(art(log=log)))
  if do_poster:out.append(poster(wait=True,log=log)[1])
  return out
def pending_path():return os.path.join(config.C.INSTANCE,'firstrun.pending')
def pending():
  """建站后收尾没跑完就被杀了（进程被清理、断电）：留下的标记 {art, poster}，下次启动补跑。"""
  try:
    with open(pending_path(),encoding='utf-8') as f:d=json.load(f)
    return {'art':bool(d.get('art')),'poster':bool(d.get('poster'))}
  except (OSError,ValueError):return None
STATE={'thread':None,'lines':[],'stage':''}   # stage：art → poster → done，向导完成页轮询它显示进度
def run_bg(lock,*,do_art=True,do_poster=True):
  """后台：网页向导完成后调用，配完图再生成一图流（一图流要用到配好的图）。"""
  t=STATE['thread']
  if t and t.is_alive():return False
  # 先记下「还有收尾没做」：配图是幂等的（已有的不重找），中途被杀下次启动从头补跑也不会重复下载
  with open(pending_path(),'w',encoding='utf-8') as f:json.dump({'art':do_art,'poster':do_poster},f)
  def go():
    import artsearch,server
    lines=[];STATE.update(lines=lines,stage='art' if do_art else 'poster')
    try:
      if do_art:
        # 占住「一键配图」的状态：跑的时候后台按钮不会再开一个，跑完能看到报告
        artsearch.AUTO.update(rep=None,at=time.time(),thread=threading.current_thread())
        rep=art(lock,log=lambda *a:None);artsearch.AUTO['rep']=rep;lines.append(art_line(rep))
      STATE['stage']='poster'
      if do_poster:lines.append(poster(wait=False)[1])
    except Exception as e:lines.append('首次收尾出错：'+repr(e))
    STATE.update(lines=lines,stage='done');server.log('firstrun',' | '.join(lines))
    # 一图流是子进程：等它真的跑完才算收尾结束（--exit-after-setup 也等这一步）
    p=server.POSTER['proc']
    while p and p.poll() is None:time.sleep(1)
    if p:server.log('firstrun poster',f'rc={p.returncode}','ready' if server.poster_ready() else 'not ready')
    try:os.remove(pending_path())
    except OSError:pass
    STATE['finished']=True
  STATE['finished']=False;STATE['thread']=threading.Thread(target=go,daemon=True);STATE['thread'].start();return True
