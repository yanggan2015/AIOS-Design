#!/usr/bin/env python3
"""luminOS AI Control Center — real local operator UI (stdlib HTTP + RPC)."""
from __future__ import annotations

import argparse
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from aios_common.ipc import call as rpc_call

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>luminOS 控制中心</title>
<style>
:root { --bg:#0f1419; --fg:#e7ecf1; --accent:#3d9bfd; --panel:#1a222c; --ok:#3dd68c; --bad:#f07178; }
*{box-sizing:border-box} body{margin:0;font:15px/1.5 "IBM Plex Sans","Noto Sans SC",sans-serif;background:radial-gradient(1200px 600px at 10% -10%,#1b3a57,transparent),var(--bg);color:var(--fg);min-height:100vh}
header{padding:28px 32px 8px} header h1{margin:0;font:600 28px/1.2 "IBM Plex Serif",serif;letter-spacing:.02em}
header p{margin:8px 0 0;opacity:.75;max-width:40rem}
main{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 32px 40px}
@media(max-width:900px){main{grid-template-columns:1fr}}
section{background:var(--panel);border:1px solid #2a3542;border-radius:10px;padding:16px}
h2{margin:0 0 12px;font-size:16px;opacity:.9}
button,input,textarea{font:inherit} input,textarea{width:100%;background:#0c1117;border:1px solid #334155;color:var(--fg);border-radius:8px;padding:10px}
button{background:var(--accent);color:#041018;border:0;border-radius:8px;padding:10px 14px;font-weight:600;cursor:pointer}
button.secondary{background:#243041;color:var(--fg)}
pre{background:#0c1117;border-radius:8px;padding:12px;overflow:auto;max-height:280px;font-size:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.status{display:inline-block;padding:2px 8px;border-radius:999px;background:#243041;font-size:12px}
.status.ok{background:#143528;color:var(--ok)} .status.bad{background:#3a1a1e;color:var(--bad)}
</style>
</head>
<body>
<header>
  <h1>luminOS</h1>
  <p>系统控制中心 — 服务状态、DCP 夹具、Agent 任务、RCP 配对。不是演示壳，直接打本机守护进程。</p>
</header>
<main>
  <section>
    <h2>服务</h2>
    <div id="svcs"></div>
    <div class="row"><button onclick="refresh()">刷新</button></div>
  </section>
  <section>
    <h2>DCP · fixture:hello</h2>
    <div class="row">
      <input id="text" placeholder="输入文本" value="你好 luminOS"/>
      <button onclick="typeOk()">写入并点 OK</button>
      <button class="secondary" onclick="snap()">快照</button>
    </div>
    <pre id="dcp"></pre>
  </section>
  <section>
    <h2>Agent</h2>
    <textarea id="goal" rows="3">在夹具里输入「控制中心」并点 OK</textarea>
    <div class="row"><button onclick="runAgent()">执行</button><button class="secondary" onclick="abortAgent()">急停</button></div>
    <pre id="agent"></pre>
  </section>
  <section>
    <h2>RCP 配对</h2>
    <div class="row"><button onclick="pair()">生成配对码</button></div>
    <pre id="pair"></pre>
  </section>
</main>
<script>
async function api(path, body){
  const r = await fetch(path, {method: body?'POST':'GET', headers:{'Content-Type':'application/json'}, body: body?JSON.stringify(body):undefined});
  return r.json();
}
function show(id, obj){ document.getElementById(id).textContent = JSON.stringify(obj, null, 2); }
async function refresh(){
  const d = await api('/api/ping');
  const el = document.getElementById('svcs');
  el.innerHTML = Object.entries(d).map(([k,v])=>`<span class="status ${v.ok?'ok':'bad'}">${k}: ${v.ok?'OK':v.error}</span>`).join(' ');
}
async function typeOk(){
  const text = document.getElementById('text').value;
  show('dcp', await api('/api/dcp/hello', {text}));
}
async function snap(){ show('dcp', await api('/api/dcp/snapshot')); }
async function runAgent(){ show('agent', await api('/api/agent/run', {goal: document.getElementById('goal').value})); }
async function abortAgent(){ show('agent', await api('/api/agent/abort', {})); }
async function pair(){ show('pair', await api('/api/rcp/pair', {})); }
refresh();
</script>
</body>
</html>
"""


def _run(coro):
    return asyncio.run(coro)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code: int, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            data = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/ping":
            out = {}
            for s in ["policy", "dcpd", "agentd", "ai-engined", "rcpd", "gateway", "store", "scheduler"]:
                try:
                    r = _run(rpc_call(s, "ping", {}, timeout=1.5))
                    out[s] = {"ok": True, "result": r}
                except Exception as e:  # noqa: BLE001
                    out[s] = {"ok": False, "error": str(e)}
            return self._json(200, out)
        if path == "/api/dcp/snapshot":
            try:
                r = _run(rpc_call("dcpd", "snapshot", {"target": "fixture:hello"}))
                return self._json(200, r)
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"error": str(e)})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/dcp/hello":
                text = body.get("text", "")
                _run(rpc_call("dcpd", "act", {"target": "fixture:hello", "action": "ime_commit", "args": {"node": "w_entry", "text": text}}))
                r = _run(rpc_call("dcpd", "act", {"target": "fixture:hello", "action": "click", "args": {"node": "w_btn_ok"}}))
                snap = _run(rpc_call("dcpd", "snapshot", {"target": "fixture:hello"}))
                return self._json(200, {"act": r, "snapshot": snap})
            if path == "/api/agent/run":
                r = _run(rpc_call("agentd", "run", {"goal": body.get("goal", ""), "opts": {"max_steps": 16}}, timeout=60))
                return self._json(200, r)
            if path == "/api/agent/abort":
                r = _run(rpc_call("agentd", "abort", {}))
                return self._json(200, r)
            if path == "/api/rcp/pair":
                r = _run(rpc_call("rcpd", "issue_pairing", {}))
                return self._json(200, r)
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": str(e)})
        self._json(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser(prog="aios-control-center")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"luminOS control center http://{args.host}:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
