"""Web ダッシュボード（標準ライブラリのみ）。

python -m zengin_sim serve → http://127.0.0.1:8000/
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .bank import TransferError
from .world import Simulation

STATIC = Path(__file__).parent / "static"


class App:
    def __init__(self):
        self.lock = threading.Lock()
        self.sim = Simulation()

    def reset(self, start: str | None = None) -> None:
        dt = datetime.fromisoformat(start) if start else None
        self.sim = Simulation(dt)

    # 各 API は (status, dict) を返す
    def api(self, method: str, path: str, body: dict) -> tuple[int, dict]:
        s = self.sim
        with self.lock:
            if method == "GET" and path == "/api/state":
                return 200, s.snapshot()
            if method != "POST":
                return 404, {"error": "not found"}
            try:
                if path == "/api/transfer":
                    node = s.node(body["from_bank"])
                    src = node.find(body["from_branch"], int(body["from_type"]), body["from_no"])
                    if src is None:
                        return 400, {"error": "依頼人口座が見つかりません"}
                    dst_node = s.nodes.get(body["to_bank"])
                    bene = body.get("beneficiary") or ""
                    if not bene and dst_node:
                        d = dst_node.find(body["to_branch"], int(body["to_type"]), body["to_no"])
                        bene = d.holder if d else "ﾌﾒｲ"
                    st = node.transfer(src.key, body["to_bank"], body["to_branch"], int(body["to_type"]),
                                       body["to_no"], bene, int(body["amount"]), edi=body.get("edi", ""))
                    rec = s.center.records.get(s.center.tx_id(node.code, st.seq))
                    return 200, {"status": rec.status.value if rec else st.status.value, "note": st.note}
                if path == "/api/advance":
                    if "to" in body:
                        s.run_until(datetime.fromisoformat(body["to"]))
                    else:
                        s.advance(int(body.get("minutes", 60)))
                    return 200, {"now": s.clock.now.isoformat()}
                if path == "/api/random":
                    n = s.random_transfers(int(body.get("count", 50)), large_ratio=float(body.get("large_ratio", 0)))
                    return 200, {"sent": n}
                if path == "/api/rc":
                    s.node(body["bank"]).set_rc(bool(body["up"]))
                    s.center.tick()
                    return 200, {"ok": True}
                if path == "/api/center":
                    if "core_up" in body:
                        s.center.core_up = bool(body["core_up"])
                    if "more_up" in body:
                        s.center.more_up = bool(body["more_up"])
                    return 200, {"ok": True}
                if path == "/api/boj":
                    s.boj.inject(body["bank"], int(body["amount"]), body.get("purpose", "資金調達(模擬)"))
                    s.center.tick()
                    return 200, {"ok": True}
                if path == "/api/recall":
                    s.node(body["bank"]).request_recall(int(body["seq"]))
                    return 200, {"ok": True}
                if path == "/api/reset":
                    self.reset(body.get("start"))
                    return 200, {"ok": True}
            except (TransferError, KeyError, ValueError) as e:
                return 400, {"error": str(e)}
        return 404, {"error": "not found"}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 静かにする
            pass

        def _send(self, code: int, payload: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, (STATIC / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
                return
            code, obj = app.api("GET", self.path.split("?")[0], {})
            self._json(code, obj)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "JSON が不正です"})
                return
            code, obj = app.api("POST", self.path, body)
            self._json(code, obj)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    app = App()
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"全銀システム模擬ダッシュボード: http://{host}:{port}/  （Ctrl+C で終了）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します")
    finally:
        httpd.server_close()
