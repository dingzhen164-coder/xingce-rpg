"""
假 AI 服务器（OpenAI 兼容的 /chat/completions），用于不花钱地手动测试网页：

    python tests/fake_ai_server.py            # 监听 127.0.0.1:8799
    然后在网页“设置”里：接口地址填 http://127.0.0.1:8799，API key 随便填

回复内容和 tests/test_flow.py 里的 fake_chat 一样（全部判通过）。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_flow import fake_chat  # noqa: E402


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = fake_chat(body["messages"], json_mode=bool(body.get("response_format")))
        data = json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"fake AI on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
