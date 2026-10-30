"""Outbound HTTPS (Notion, Bangumi, AniList) with a CA bundle that actually loads.

python.org's macOS installer ships without root certificates until you run its「Install Certificates」script, so
urllib fails every request with CERTIFICATE_VERIFY_FAILED. Fall back to the system bundle (macOS / most Linux) or
certifi when the default store is empty, instead of making every organiser debug that."""
import json,os,ssl,urllib.error,urllib.request
UA='castcall/1.0 (https://github.com/RichardLiuda/castcall)'
_CTX=None
def ctx():
  global _CTX
  if _CTX is None:
    c=ssl.create_default_context()
    if not c.cert_store_stats().get('x509_ca'):
      for p in ('/etc/ssl/cert.pem','/etc/ssl/certs/ca-certificates.crt','/etc/pki/tls/certs/ca-bundle.crt','/usr/local/etc/openssl/cert.pem','/opt/homebrew/etc/openssl@3/cert.pem'):
        if os.path.isfile(p):
          try:c.load_verify_locations(p);break
          except Exception:pass
      else:
        try:
          import certifi;c.load_verify_locations(certifi.where())
        except Exception:pass
    _CTX=c
  return _CTX
def request(url,body=None,method=None,headers=None,timeout=20,raw=False,limit=None):
  """→ (data, None) or (None, short error). data is parsed JSON unless raw=True (then bytes). Never raises."""
  h={'User-Agent':UA,'Accept':'application/json'};h.update(headers or {})
  data=None
  if body is not None:
    data=json.dumps(body,ensure_ascii=False).encode() if not isinstance(body,(bytes,bytearray)) else bytes(body)
    h.setdefault('Content-Type','application/json')
  req=urllib.request.Request(url,data=data,method=method or ('POST' if data is not None else 'GET'),headers=h)
  try:
    with urllib.request.urlopen(req,timeout=timeout,context=ctx()) as r:
      b=r.read(limit+1 if limit else -1)
      if limit and len(b)>limit:return None,'too large'
      if raw:return b,None
      return json.loads(b.decode('utf-8','replace') or '{}'),None
  except urllib.error.HTTPError as e:
    try:d=json.loads(e.read().decode('utf-8','replace'))
    except Exception:d={}
    return None,f"HTTP {e.code} {d.get('code','') if isinstance(d,dict) else ''}: {str((d.get('message') or d.get('title') or '') if isinstance(d,dict) else '')[:160]}"
  except Exception as e:
    msg=repr(e)[:160]
    if 'CERTIFICATE_VERIFY_FAILED' in msg:msg='HTTPS 证书校验失败：Python 找不到根证书（macOS 上运行 /Applications/Python 3.x/Install Certificates.command，或 pip install certifi）'
    return None,msg
