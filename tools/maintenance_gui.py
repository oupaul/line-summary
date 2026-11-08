#!/usr/bin/env python3
"""維護記錄單 本機 GUI：在瀏覽器選聊天室與日期，按鈕產出 Excel。

只監聽 127.0.0.1（本機），不對外。執行後會自動開瀏覽器。
    python3 tools/maintenance_gui.py [--port 8765]
"""
import argparse
import datetime as dt
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import maintenance_report as mr

JOB = {"state": "idle", "log": [], "result": None}
LOCK = threading.Lock()

PAGE = """<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>維護記錄單產生器</title>
<style>
:root{--navy:#1F4E78;--bg:#f4f6f9;--card:#fff;--line:#d9dee5;--txt:#1d2733;--mut:#5f6b7a;--ok:#1b7f4b;--warn:#b26a00;--err:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#10151c;--card:#19212b;--line:#2c3744;--txt:#e6ebf2;--mut:#9aa7b8;--navy:#5b9bd5}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 -apple-system,"PingFang TC",Arial,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:20px;margin:0 0 4px;color:var(--navy)}p.sub{margin:0 0 20px;color:var(--mut);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}
label.t{display:block;font-weight:600;margin-bottom:6px;font-size:13px}
input[type=text],input[type=date]{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--txt);font:inherit}
.row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:160px}
.files{max-height:210px;overflow:auto;border:1px solid var(--line);border-radius:6px;margin-top:8px}
.files label{display:flex;gap:8px;padding:7px 10px;border-bottom:1px solid var(--line);cursor:pointer;align-items:flex-start}
.files label:last-child{border:0}.files small{color:var(--mut);display:block}
button{background:var(--navy);color:#fff;border:0;border-radius:8px;padding:11px 22px;font:inherit;font-weight:600;cursor:pointer}
button:disabled{opacity:.5;cursor:default}.presets button{background:transparent;color:var(--navy);border:1px solid var(--line);padding:4px 10px;font-weight:400;font-size:13px;margin-right:6px}
#log{white-space:pre-wrap;font:12.5px/1.6 ui-monospace,Menlo,monospace;color:var(--mut);max-height:220px;overflow:auto}
.res{display:none}.res.on{display:block}.kpi{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0}
.kpi div{flex:1;min-width:100px;background:var(--bg);border-radius:8px;padding:10px 12px}.kpi b{display:block;font-size:22px}
a.dl{display:inline-block;margin-top:6px;color:#fff;background:var(--ok);padding:9px 18px;border-radius:8px;text-decoration:none;font-weight:600}
.err{color:var(--err)}
</style></head><body><main>
<h1>維護記錄單產生器</h1><p class="sub">選擇聊天記錄與日期範圍，產出「需求提出時間／提出者／處理完成者／處理內容」維護記錄單 Excel。內容由 Claude 判讀，請人工覆核。</p>
<div class="card"><div class="row">
<div><label class="t">客戶名稱（標題與檔名）</label><input type="text" id="cust" value=""></div>
<div><label class="t">篩選聊天室（關鍵字，逗號分隔）</label><input type="text" id="kw" placeholder="例如：客戶A,窗口名"></div></div>
<div class="files" id="files">載入中…</div></div>
<div class="card"><label class="t">日期範圍</label><div class="row"><div><input type="date" id="since"></div><div><input type="date" id="until"></div></div>
<div class="presets" style="margin-top:10px"><button data-p="last">上個月</button><button data-p="this">本月</button><button data-p="two">最近兩個月</button></div></div>
<button id="go">產生維護記錄單</button>
<div class="card" style="margin-top:14px"><label class="t">進度</label><div id="log">尚未執行</div></div>
<div class="card res" id="res"><label class="t">完成</label><div class="kpi" id="kpi"></div><div id="eng" style="color:var(--mut);font-size:13px"></div><a class="dl" id="dl" href="#">下載 Excel</a></div>
</main><script>
const $=id=>document.getElementById(id);let chats=[];
const fmt=d=>d.toISOString().slice(0,10),loc=d=>new Date(d.getTime()-d.getTimezoneOffset()*6e4);
function preset(p){const n=new Date(),y=n.getFullYear(),m=n.getMonth();let a,b;
 if(p=='last'){a=new Date(y,m-1,1);b=new Date(y,m,0)}else if(p=='this'){a=new Date(y,m,1);b=n}else{a=new Date(y,m-1,1);b=n}
 $('since').value=fmt(loc(a));$('until').value=fmt(loc(b))}
document.querySelectorAll('[data-p]').forEach(b=>b.onclick=()=>preset(b.dataset.p));preset('last');
function render(){const k=$('kw').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean);
 $('files').innerHTML=chats.map((c,i)=>`<label><input type="checkbox" value="${c.name}" ${k.length&&k.some(x=>c.name.includes(x))?'checked':''}><span>${c.name}<small>${c.span} · ${c.kb} KB</small></span></label>`).join('')||'chats/ 內沒有 .txt 檔'}
Promise.all([fetch('/api/chats').then(r=>r.json()),fetch('/api/config').then(r=>r.json())]).then(([j,cfg])=>{chats=j;const s=localStorage.getItem('mr_kw');$('kw').value=s??cfg.chat_keywords.join(',');const c=localStorage.getItem('mr_cust');$('cust').value=c||cfg.customer;render()});
$('kw').oninput=render;
async function poll(){const j=await (await fetch('/api/job')).json();$('log').textContent=j.log.join('\\n')||'…';$('log').scrollTop=1e9;
 if(j.state=='running'){setTimeout(poll,1500);return}$('go').disabled=false;
 if(j.state=='done'){const r=j.result,s=r.stats;$('res').classList.add('on');
  $('kpi').innerHTML=`<div><b>${s.total}</b>案件總數</div><div><b>${s.done}</b>已解決/完成</div><div><b>${s.open}</b>進行中/待處理</div><div><b>${s.tech}/${s.routine}</b>技術/例行</div>`;
  $('eng').textContent='工程師：'+Object.entries(s.engineers).sort((a,b)=>b[1]-a[1]).map(([n,c])=>n+' '+c).join('、');
  $('dl').href='/download?f='+encodeURIComponent(r.file);$('dl').textContent='下載 '+r.file}
 else if(j.state=='error'){$('log').innerHTML+='\\n<span class="err">失敗：'+j.error+'</span>'}}
$('go').onclick=async()=>{const files=[...document.querySelectorAll('#files input:checked')].map(i=>i.value);
 if(!files.length){alert('請至少勾選一個聊天室');return}
 localStorage.setItem('mr_kw',$('kw').value);localStorage.setItem('mr_cust',$('cust').value);
 $('res').classList.remove('on');$('go').disabled=true;$('log').textContent='啟動中…';
 const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer:$('cust').value.trim(),files,since:$('since').value,until:$('until').value})});
 if(!r.ok){$('go').disabled=false;$('log').textContent=await r.text();return}poll()};
fetch('/api/job').then(r=>r.json()).then(j=>{if(j.state=='running'){$('go').disabled=true;poll()}});
</script></body></html>"""


def run_job(customer, files, since, until):
    def log(msg):
        with LOCK:
            JOB["log"].append(f"[{dt.datetime.now():%H:%M:%S}] {msg}")
    try:
        cfg = mr.load_config()
        out, stats = mr.generate(customer, files, since, until, None, log, team_prefix=cfg["team_prefix"],
                                 extra=tuple(cfg["engineers"]), exclude=tuple(cfg["exclude"]))
        with LOCK:
            JOB.update(state="done", result={"file": out.name, "stats": stats})
    except Exception as e:  # noqa: BLE001 -- 顯示給使用者
        with LOCK:
            JOB.update(state="error", error=str(e))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._local():
            return self._send(403, "forbidden", "text/plain")
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/chats":
            items = [{"name": f.name, "span": " ~ ".join(mr.chat_date_span(f)), "kb": f.stat().st_size // 1024}
                     for f in mr.list_chat_files()]
            return self._send(200, json.dumps(items, ensure_ascii=False))
        if u.path == "/api/config":
            cfg = mr.load_config()
            return self._send(200, json.dumps({"customer": cfg["customer"], "chat_keywords": cfg["chat_keywords"]}, ensure_ascii=False))
        if u.path == "/api/job":
            with LOCK:
                return self._send(200, json.dumps(JOB, ensure_ascii=False))
        if u.path == "/download":
            name = Path(parse_qs(u.query).get("f", [""])[0]).name  # 只允許檔名，擋路徑穿越
            p = mr.OUT / name
            if not name.endswith(".xlsx") or not p.is_file():
                return self._send(404, "not found", "text/plain")
            return self._send(200, p.read_bytes(),
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              {"Content-Disposition": "attachment; filename*=UTF-8''" + __import__("urllib.parse").parse.quote(name)})
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        if not self._local() or self.path != "/api/run":
            return self._send(403, "forbidden", "text/plain")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._send(400, "need json", "text/plain")
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            since, until = mr.parse_date(req["since"]), mr.parse_date(req["until"])
            customer = req["customer"].strip() or "客戶"
            customer = "".join(ch for ch in customer if ch not in '\\/:*?"<>|')
            files = [mr.CHATS / Path(n).name for n in req["files"]]  # basename only
            if since > until or not files or not all(f.is_file() for f in files):
                raise ValueError("日期或聊天室選擇有誤")
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return self._send(400, f"參數錯誤：{e}", "text/plain; charset=utf-8")
        with LOCK:
            if JOB["state"] == "running":
                return self._send(409, "已有工作進行中", "text/plain; charset=utf-8")
            JOB.clear()
            JOB.update(state="running", log=[], result=None)
        threading.Thread(target=run_job, args=(customer, files, since, until), daemon=True).start()
        self._send(200, "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"維護記錄單產生器已啟動：{url}（關閉此視窗或按 Ctrl+C 結束）")
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
