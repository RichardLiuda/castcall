#!/usr/bin/env python3
"""第一次用：生成实例目录（默认 ./instance）。

  python3 init.py                    # 一问一答
  python3 init.py --mode single --title "XX 团片" --yes      # 不问，其余用默认值，密码随机生成并打印一次
  python3 init.py --example key-demo --yes                   # 用 examples/roster.key-demo.json 当初始名册（13 个团的大样例）

会写出 site.json（活动信息）、roster.json（示例名册）、auth.json（管理密码）。已经初始化过的目录不会被覆盖，
除非加 --force（只重写 site.json 和 auth.json，名册永远不覆盖）。"""
import argparse,getpass,json,os,secrets,shutil,sys
ROOT=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,os.path.join(ROOT,'server'))
import config
def ask(q,default='',yes=False):
  if yes:return default
  a=input(f'{q}' + (f' [{default}]' if default else '') + '：').strip()
  return a or default
def main(argv):
  ap=argparse.ArgumentParser(description='生成 castcall 实例目录')
  ap.add_argument('--instance',default=os.environ.get('CASTCALL_INSTANCE') or os.path.join(ROOT,'instance'))
  ap.add_argument('--mode',choices=('single','multi'));ap.add_argument('--title');ap.add_argument('--date');ap.add_argument('--start')
  ap.add_argument('--location');ap.add_argument('--contact',help='缺人看板上的联系方式，如 "微信 abc123"')
  ap.add_argument('--password',help='管理密码（不给就问；--yes 时随机生成）')
  ap.add_argument('--example',help='初始名册用 examples/roster.<名字>.json（multi / single / key-demo / key-single）；默认按 --mode')
  ap.add_argument('--yes',action='store_true',help='不提问，没给的都用默认值');ap.add_argument('--force',action='store_true')
  a=ap.parse_args(argv);C=config.use(a.instance);y=a.yes
  if a.example:
    ex=os.path.join(ROOT,'examples',f'roster.{a.example}.json')
    if not os.path.isfile(ex):print('没有这个样例：'+ex);return 1
    if not a.mode:
      with open(ex,encoding='utf-8') as f:a.mode='single' if len(json.load(f)['groups'])==1 else 'multi'
  if os.path.exists(C.ROSTER) and not a.force:
    print(f'{C.INSTANCE} 已经初始化过了（有 roster.json）。要重设活动信息和密码，加 --force；名册不会被覆盖。');return 1
  print('castcall 初始化 → '+C.INSTANCE+'\n')
  mode=a.mode or ('single' if ask('单团还是多团？输入 1 = 单团（一个团的团片），2 = 多团（多个团同时招募）','2',y)=='1' else 'multi')
  title=a.title or ask('活动名称','示例 cos 团建' if mode=='multi' else '示例团片',y)
  date=a.date if a.date is not None else ask('日期（页面上显示的文字，可留空）','',y)
  start=a.start if a.start is not None else ask('开场时间，用于倒计时（如 2026-12-12T11:00:00+08:00，可留空）','',y)
  loc=a.location if a.location is not None else ask('地点（可留空）','',y)
  contact=a.contact if a.contact is not None else ask('联系方式，显示在缺人看板底部（如「微信 abc123」，可留空）','',y)
  clabel=ask('报名表里要填的联系方式叫什么（微信 / QQ / 邮箱）','微信',y)
  cl,_,cv=contact.partition(' ') if ' ' in contact else ('',None,contact)
  site=json.load(open(os.path.join(ROOT,'examples','site.example.json'),encoding='utf-8'))
  site['mode']='auto'
  site['event'].update(title=title,date=date,startAt=start,endAt='',location=loc,organizer='',contact={'label':cl,'value':cv})
  site['signup']['contactLabel']=clabel
  pw=a.password
  if not pw and not y:
    while True:
      pw=getpass.getpass('管理密码（直接回车 = 随机生成）：')
      if not pw:break
      if len(pw)<8:print('至少 8 位。');continue
      if getpass.getpass('再输一遍：')==pw:break
      print('两次不一样，再来。')
  shown=None
  if not pw:pw=shown=secrets.token_urlsafe(12)
  os.makedirs(C.INSTANCE,exist_ok=True)
  for d in (C.UPLOADS,C.POSTER,C.BACKUPS,C.LOGS):os.makedirs(d,exist_ok=True)
  with open(C.SITE,'w',encoding='utf-8') as f:json.dump(site,f,ensure_ascii=False,indent=1)
  if not os.path.exists(C.ROSTER):
    shutil.copy(os.path.join(ROOT,'examples',f'roster.{a.example}.json' if a.example else f'roster.{mode}.example.json'),C.ROSTER)
    import roster
    d=roster.load();roster.ensure_ids(d)
    for g in d['groups']:g['count']=len(g['members'])
    with open(C.ROSTER,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=1)
  import server
  server.set_password(pw,C.AUTH)
  print(f'\n完成。名册是示例数据，登录后台（右下角的锁）就能改。')
  if shown:print(f'\n  管理密码：{shown}\n  只显示这一次，请现在记下来。忘了就再跑一次 python3 init.py --force。')
  print(f'\n启动：python3 server/server.py\n然后打开 http://127.0.0.1:{site["server"]["port"]}/')
  return 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
