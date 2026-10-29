#!/usr/bin/env python3
"""End-to-end check in a real browser (not part of the unit tests: needs Playwright and Chrome).

  python3 tests/e2e_browser.py [--chrome PATH] [--out DIR] [--no-poster]

Builds two throw-away instances (multi + single), starts a server for each, then drives the page:
roster, cast board, a public signup, admin login → review → approve, the guestbook, single-group layout,
phone width, and (unless --no-poster) the poster build. Screenshots + report.json land in --out."""
import argparse,json,os,shutil,socket,subprocess,sys,tempfile,time,urllib.request
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW='e2e-password-1'
def free_port():
  s=socket.socket();s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
def instance(mode):
  d=tempfile.mkdtemp(prefix=f'castcall-e2e-{mode}-')
  # multi gets every optional field, single gets none (no date / place / countdown / contact): both page variants must work
  full=['--date','2026-12-12','--start','2030-12-12T11:00:00+08:00','--location','某某公园','--contact','微信 example_id'] if mode=='multi' else []
  subprocess.run([sys.executable,os.path.join(ROOT,'init.py'),'--instance',d,'--mode',mode,'--title','示例 cos 团建' if mode=='multi' else '示例团片',
    *full,'--password',PW,'--yes'],check=True,capture_output=True)
  return d
def serve(d,port):
  env=dict(os.environ,CASTCALL_INSTANCE=d,CASTCALL_PORT=str(port))
  p=subprocess.Popen([sys.executable,os.path.join(ROOT,'server','server.py')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  for _ in range(100):
    try:urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1);return p
    except Exception:time.sleep(.1)
  raise SystemExit('server did not start:\n'+p.stdout.read().decode(errors='replace'))
def main(a):
  from playwright.sync_api import sync_playwright
  out=os.path.abspath(a.out);shutil.rmtree(out,ignore_errors=True);os.makedirs(out)
  rep={'steps':[],'console':[],'ok':True}
  def step(name,ok,detail=''):
    rep['steps'].append({'step':name,'ok':bool(ok),'detail':str(detail)[:300]});rep['ok']&=bool(ok)
    print(('PASS ' if ok else 'FAIL ')+name+(f'  ({detail})' if detail else ''),flush=True)
  dirs={m:instance(m) for m in ('multi','single')};ports={m:free_port() for m in dirs};procs={m:serve(dirs[m],ports[m]) for m in dirs}
  try:
    with sync_playwright() as p:
      kw={'args':['--no-sandbox']}
      if a.chrome:kw['executable_path']=a.chrome
      br=p.chromium.launch(**kw)
      def page(w=1280,h=900,mobile=False):
        ctx=br.new_context(viewport={'width':w,'height':h},device_scale_factor=2 if mobile else 1,is_mobile=mobile,has_touch=mobile)
        pg=ctx.new_page()
        pg.on('console',lambda m:m.type=='error' and rep['console'].append(m.text[:300]))
        pg.on('pageerror',lambda e:rep['console'].append('pageerror: '+str(e)[:300]))
        pg.on('response',lambda r:r.status>=400 and rep['console'].append(f'HTTP {r.status} {r.url}'))
        return pg
      shot=lambda pg,n:pg.screenshot(path=os.path.join(out,n+'.png'))
      # ── multi, desktop ──
      U=f'http://127.0.0.1:{ports["multi"]}/';pg=page();pg.goto(U);pg.wait_for_timeout(800)
      step('multi: covers render',pg.locator('.cv').count()==4,pg.locator('.cv').count())
      step('multi: header from site.json','示例 cos 团建' in pg.locator('.hdr h1').inner_text(),pg.locator('.hdr h1').inner_text())
      step('multi: countdown stub','12.12' in pg.locator('.cd-stub b').inner_text(),pg.locator('.cd-stub').inner_text().replace('\n',' '))
      shot(pg,'01-multi-home')
      pg.locator('.cv header').first.click();pg.wait_for_timeout(700)
      step('multi: card opens',pg.locator('.cv.open').count()==1)
      step('multi: group meta shown',pg.locator('.cv.open .gmeta').count()==1)
      shot(pg,'02-multi-open')
      pg.locator('#castbtn').click();pg.wait_for_timeout(500);shot(pg,'03-cast-board')
      step('cast board: contact footer','example_id' in pg.locator('.cast-note').inner_text())
      vac=pg.locator('.cast-row[data-k=vacant]');step('cast board: vacant rows',vac.count()>=3,vac.count())
      vac.first.click();pg.wait_for_timeout(500)
      join=pg.locator('#sheet [data-signup]');step('sheet: signup button',join.count()==1)
      join.click();pg.wait_for_timeout(400)
      step('signup: contact label from site.json','微信' in pg.locator('#signup .signup-wx').inner_text())
      pg.fill('#signup [name=name]','测试报名');pg.fill('#signup [name=contact]','wx_e2e');shot(pg,'04-signup-form')
      pg.locator('#signup [type=submit]').click();pg.wait_for_timeout(800)
      step('signup: submitted',pg.locator('#signup').is_hidden() and '等审核' in (pg.locator('#toast').inner_text() or ''),pg.locator('#toast').inner_text())
      pg.keyboard.press('Escape');pg.goto(U);pg.wait_for_timeout(600)
      # admin: login → review → approve
      pg.locator('#fab').click();pg.wait_for_timeout(300);pg.fill('#modal input[type=password]',PW);pg.keyboard.press('Enter');pg.wait_for_timeout(800)
      step('admin: logged in',pg.locator('body.editing').count()==1)
      pg.wait_for_timeout(400);badge=pg.locator('#rvn')
      step('admin: pending badge',badge.is_visible() and badge.inner_text()=='1',badge.inner_text() if badge.count() else '')
      shot(pg,'05-admin-toolbar')
      pg.locator('#etb button',has_text='审核').click();pg.wait_for_timeout(700);shot(pg,'06-review-panel')
      step('review: lists signup','测试报名' in pg.locator('.rv').inner_text())
      pg.locator('.rv-it button',has_text='通过').first.click();pg.wait_for_timeout(800);shot(pg,'07-review-approved')
      step('review: approved','已通过' in pg.locator('.rv').inner_text())
      pg.locator('#modal button',has_text='关闭').click();pg.wait_for_timeout(1500)
      d=json.loads(urllib.request.urlopen(U+'api/data').read())
      step('roster: member seated',any(m.get('member')=='测试报名' for g in d['groups'] for m in g['members']))
      pg.locator('#etb button',has_text='新团').click();pg.wait_for_timeout(400);shot(pg,'08-group-form');pg.locator('#modal button',has_text='取消').click()
      # guestbook
      pg.locator('#gb-open').scroll_into_view_if_needed();pg.locator('#gb-open').click();pg.wait_for_timeout(700)
      pg.fill('#gb [name=body]','端到端测试留言');pg.locator('#gb [type=submit]').click();pg.wait_for_timeout(1500)
      step('guestbook: note appears','端到端测试留言' in pg.locator('#gb-list').inner_text())
      shot(pg,'09-guestbook')
      # ── multi, phone ──
      m=page(390,844,True);m.goto(U);m.wait_for_timeout(800);shot(m,'10-multi-phone')
      m.locator('.cv header').nth(1).click();m.wait_for_timeout(900);shot(m,'11-multi-phone-open')
      step('phone: card opens',m.locator('.cv.open').count()==1)
      # ── single ──
      S=f'http://127.0.0.1:{ports["single"]}/';s=page();s.goto(S);s.wait_for_timeout(800)
      step('single: minimal config renders, no countdown',s.locator('#bn').count()==0 and s.locator('#solo').count()==1)
      step('single: no cover wall, no expand-all',s.locator('.cv').count()==0 and not s.locator('#xall').is_visible())
      op=s.locator('.seat-open');step('single: open roles listed first',op.count()>=1 and s.locator('.pills .pill').count()>=1,op.count())
      op.first.click();s.wait_for_timeout(500);step('single: open role → signup form directly',s.locator('#signup').is_visible())
      s.keyboard.press('Escape');s.wait_for_timeout(300)
      shot(s,'12-single-home')
      sm=page(390,844,True);sm.goto(S);sm.wait_for_timeout(800);shot(sm,'13-single-phone')
      # ── poster ──
      if not a.no_poster:
        env=dict(os.environ)
        if a.chrome:env['CASTCALL_CHROME']=a.chrome
        r=subprocess.run([sys.executable,os.path.join(ROOT,'poster','build.py'),'--instance',dirs['multi']],env=env,capture_output=True,text=True,timeout=600)
        step('poster: build',r.returncode==0,(r.stdout+r.stderr)[-300:])
        if r.returncode==0:
          for n in ('master.jpg','wide.jpg'):shutil.copy(os.path.join(dirs['multi'],'poster',n),os.path.join(out,'poster-'+n))
          q=page();q.goto(U+'poster/master.html');q.wait_for_timeout(1200);shot(q,'14-poster-master-web')
          step('poster: web page + chrome',q.locator('.kr-poster-chrome').count()==1)
          pg.goto(U);pg.wait_for_timeout(500);step('poster: header link appears',pg.locator('#posterlink-hdr').count()==1)
        r=subprocess.run([sys.executable,os.path.join(ROOT,'poster','build.py'),'--instance',dirs['single']],env=env,capture_output=True,text=True,timeout=600)
        step('poster: single build (master + social)',r.returncode==0,(r.stdout+r.stderr)[-300:])
        if r.returncode==0:shutil.copy(os.path.join(dirs['single'],'poster','social.jpg'),os.path.join(out,'poster-social.jpg'))
      br.close()
  finally:
    for p in procs.values():p.terminate()
    for d in dirs.values():shutil.rmtree(d,ignore_errors=True)
  step('no console errors',not rep['console'],'; '.join(dict.fromkeys(rep['console']))[:600])
  json.dump(rep,open(os.path.join(out,'report.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
  print('\n'+('ALL PASS' if rep['ok'] else 'SOME FAILED')+' → '+out)
  return 0 if rep['ok'] else 1
if __name__=='__main__':
  ap=argparse.ArgumentParser();ap.add_argument('--chrome',default=os.environ.get('CASTCALL_CHROME'));ap.add_argument('--out',default=os.path.join(ROOT,'.e2e-out'));ap.add_argument('--no-poster',action='store_true')
  sys.exit(main(ap.parse_args()))
