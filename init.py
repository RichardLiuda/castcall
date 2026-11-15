#!/usr/bin/env python3
"""第一次用：生成实例目录（默认 ./instance）。也可以直接启动服务器，在浏览器里走初始化向导。

  python3 init.py                    # 一问一答
  python3 init.py --mode single --title "XX 团片" --yes      # 不问，其余用默认值，密码随机生成并打印一次
  python3 init.py --import 名单.txt --title "XX 团片" --yes  # 名册直接用一份名单（格式见 server/importer.py）
  python3 init.py --example key-demo --yes                   # 用 examples/roster.key-demo.json 当初始名册（13 个团的大样例），
                                                             # 顺带生成占位封面、几条留言和几条待审报名（--no-seed 不要）

会写出 site.json（活动信息）、roster.json（名册）、auth.json（管理密码），然后自动配图（导入了名单时）、生成一图流
（缺依赖就跳过并提示；--no-art / --no-poster 关掉）。已经初始化过的目录不会被覆盖，
除非加 --force（只重写 site.json 和 auth.json，名册永远不覆盖）。"""
import argparse,getpass,json,os,secrets,sys
ROOT=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,os.path.join(ROOT,'server'))
import config,setup
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
  ap.add_argument('--import',dest='imp',help='初始名册用这份名单（文本或 CSV，- 表示标准输入）')
  ap.add_argument('--blank',action='store_true',help='不要示例名册，从一个空团开始')
  ap.add_argument('--no-seed',action='store_true',help='用 --example 时不生成占位封面、留言和待审报名')
  ap.add_argument('--fields',help='报名额外要填的，逗号分隔，* 结尾 = 必填，其余选填："身高,样片*,年龄,性别"；'
                  '预设有 身高 / 年龄 / 性别 / 样片 / 所在城市 / 出过的角色 / 想说的话，别的字当作自定义文字题。不给 = 只填 CN 和联系方式')
  ap.add_argument('--no-art',action='store_true',help='建完不自动配图（默认：导入了名单就从 Bangumi / AniList 找封面和立绘）')
  ap.add_argument('--no-poster',action='store_true',help='建完不生成一图流（默认生成；缺依赖时会跳过并提示怎么装）')
  ap.add_argument('--yes',action='store_true',help='不提问，没给的都用默认值');ap.add_argument('--force',action='store_true')
  a=ap.parse_args(argv);C=config.use(a.instance);y=a.yes
  if a.example:
    ex=setup.example_path(a.example)
    if not ex:print('没有这个样例：'+a.example);return 1
    if not a.mode:
      with open(ex,encoding='utf-8') as f:a.mode='single' if len(json.load(f)['groups'])==1 else 'multi'
  if os.path.exists(C.ROSTER) and not a.force:
    print(f'{C.INSTANCE} 已经初始化过了（有 roster.json）。要重设活动信息和密码，加 --force；名册不会被覆盖。');return 1
  print('castcall 初始化 → '+C.INSTANCE+'\n')
  roster=None
  if a.imp:
    import importer
    if a.imp=='-':text=sys.stdin.read()
    else:
      with open(a.imp,encoding='utf-8-sig') as f:text=f.read()
    try:roster=importer.parse(text,a.title or '我们的团')
    except ValueError as e:print(e);return 1
    print('名单：'+importer.summary(roster))
    # 名单刚定下来就核对「这些名字配不配得上图」：配不上的现在就告诉你，别等建完站少了几张立绘才发现。
    # 核对过的名字会绑到确定的角色 id，配图时直接按 id 取图，不再靠搜索（搜索结果会漂）。
    if not a.no_art:
      import artsearch
      print('核对每个名字能不能配上图…')
      try:
        # log 回调要能吃多个参数：bind() 现在只用单参数，但把 tuple 拼进字符串迟早出事
        # （`'  '+x` 里 x 是 tuple → TypeError，然后被下面的 except 吞成「没核对成」）。
        rep=artsearch.bind(roster,log=lambda *x:print('  '+' '.join(str(i) for i in x)))
        print('  '+artsearch.bind_line(rep))
        for x in rep['near']:print('  像写错了  '+x)
        for x in rep['missing']:print('  找不到    '+x)
        if rep['near'] or rep['missing']:print('  改好名字重新导入更省事；不改也行，建站后在后台「找立绘」手选。')
      except Exception as e:print(f'  没核对成（{e}），不影响建站；网络好了在后台点「一键配图」')
    a.mode=a.mode or ('single' if len(roster['groups'])==1 else 'multi')
  mode=a.mode or ('single' if ask('单团还是多团？输入 1 = 单团（一个团的团片），2 = 多团（多个团同时招募）','2',y)=='1' else 'multi')
  title=a.title or ask('活动名称','示例 cos 团建' if mode=='multi' else '示例团片',y)
  date=a.date if a.date is not None else ask('日期（页面上显示的文字，可留空）','',y)
  start=a.start if a.start is not None else ask('开场时间，用于倒计时（如 2026-12-12T11:00:00+08:00，可留空）','',y)
  loc=a.location if a.location is not None else ask('地点（可留空）','',y)
  contact=a.contact if a.contact is not None else ask('联系方式，显示在缺人看板底部（如「微信 abc123」，可留空）','',y)
  clabel=ask('报名表里要填的联系方式叫什么（微信 / QQ / 邮箱）','微信',y)
  import fields as FL
  spec=a.fields if a.fields is not None else ask('报名还要填什么？逗号分隔，* 结尾 = 必填，比如「身高,样片*,年龄,性别」（直接回车 = 只填 CN 和联系方式）','',y)
  try:fl=FL.parse_spec(spec)
  except ValueError as e:print(e);return 1
  print('报名表：CN、'+clabel+('、'+FL.summary(fl) if fl else ''))
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
  example=None if roster is not None or a.blank else (a.example or f'{mode}.example')
  try:C,seeded=setup.create(C.INSTANCE,title=title,password=pw,date=date,start=start,location=loc,contact=contact,
                            contact_label=clabel,roster=roster,example=example,seed=bool(a.example) and not a.no_seed,force=a.force,fields=fl)
  except ValueError as e:print(e);return 1
  if seeded:print(f'样例：{seeded["covers"]} 张占位封面、{seeded["notes"]} 条留言、{seeded["signups"]} 条待审报名（后台「审核」里能看到）')
  # 首次收尾：导入的名单先自动配图，再生成一图流。两步失败都不影响建站，只打印补救办法
  import firstrun
  done=firstrun.run(do_art=roster is not None and not a.no_art,do_poster=not a.no_poster)
  if done:print('\n'+'\n'.join('  '+x for x in done))
  print(f'\n完成。登录后台（右下角的锁）就能改名册。')
  if shown:print(f'\n  管理密码：{shown}\n  只显示这一次，请现在记下来。忘了就再跑一次 python3 init.py --force。')
  site=config.C.site
  default=os.path.abspath(os.path.join(ROOT,'instance'))==C.INSTANCE
  env='' if default else f'CASTCALL_INSTANCE={os.path.relpath(C.INSTANCE) if C.INSTANCE.startswith(os.getcwd()) else C.INSTANCE} '
  print(f'\n启动：{env}python3 server/server.py\n然后打开 http://127.0.0.1:{site["server"]["port"]}/'+('' if default else '（同时开多个实例时，再加 CASTCALL_PORT=其他端口）'))
  return 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
