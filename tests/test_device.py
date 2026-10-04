"""局域网模式（口令、cookie、只能本机改的设置）、版本号比较、版本接口。运行：python -m unittest discover -s tests -v"""
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rpg import api, lan, paths, update  # noqa: E402
import server  # noqa: E402


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p = [patch.object(paths, "SETTINGS_DIR", self.tmp), patch.object(paths, "SETTINGS_FILE", self.tmp / "settings.json")]
        for x in self.p:
            x.start()
        self.srv, _ = server.start_server(18931, lan_mode=False)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        for x in self.p:
            x.stop()

    def req(self, method, path, body=None, headers=None, remote=False):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body)
            h["Content-Type"] = "application/json"
        with patch.object(lan, "is_local", lambda a: not remote):
            c.request(method, path, body=body, headers=h)
            r = c.getresponse()
            data = r.read()
        c.close()
        return r, data

    def test_settings_and_code(self):
        st = lan.settings()
        self.assertFalse(st["enabled"])
        self.assertRegex(st["code"], r"^\d{6}$")
        self.assertEqual(lan.settings()["code"], st["code"])          # 不会每次都换
        st2 = lan.update(enabled=True, new_code=True)
        self.assertTrue(st2["enabled"])
        self.assertTrue(lan.status(8765, False)["restart"])           # 开了但还没按局域网方式启动

    def test_local_needs_no_code(self):
        r, _ = self.req("GET", "/api/version")
        self.assertEqual(r.status, 200)
        r, data = self.req("GET", "/api/lan")
        self.assertEqual(r.status, 200)
        self.assertIn("code", json.loads(data))

    def test_remote_gate(self):
        code = lan.settings()["code"]
        r, data = self.req("GET", "/", remote=True)
        self.assertEqual(r.status, 200)
        self.assertIn("入山门", data.decode("utf-8"))
        r, _ = self.req("GET", "/api/version", remote=True)
        self.assertEqual(r.status, 401)
        r, data = self.req("POST", "/lan/login", "code=000000x", {"Content-Type": "application/x-www-form-urlencoded"}, remote=True)
        self.assertIn("口令不对", data.decode("utf-8"))
        r, _ = self.req("POST", "/lan/login", "code=" + code, {"Content-Type": "application/x-www-form-urlencoded"}, remote=True)
        self.assertEqual(r.status, 303)
        cookie = r.getheader("Set-Cookie").split(";")[0]
        r, _ = self.req("GET", "/api/version", headers={"Cookie": cookie}, remote=True)
        self.assertEqual(r.status, 200)
        r, _ = self.req("POST", "/api/lan", {"enabled": False}, headers={"Cookie": cookie}, remote=True)
        self.assertEqual(r.status, 403)                               # 平板上关不掉、改不了
        lan.update(new_code=True)                                     # 换了口令，旧 cookie 作废
        r, _ = self.req("GET", "/api/version", headers={"Cookie": cookie}, remote=True)
        self.assertEqual(r.status, 401)

    def test_ping_without_code(self):
        r, data = self.req("GET", "/lan/ping", remote=True)                 # 平板 App 找电脑：不用口令
        self.assertEqual(r.status, 200)
        d = json.loads(data)
        self.assertEqual(d["app"], "xingce-rpg")
        self.assertNotIn("code", d)

    def test_lan_toggle_local(self):
        r, data = self.req("POST", "/api/lan", {"enabled": True})
        self.assertEqual(r.status, 200)
        d = json.loads(data)
        self.assertTrue(d["enabled"])
        self.assertTrue(d["restart"])

    def test_guess_vault(self):
        home = self.tmp / "home"
        v = home / "Nutstore Files" / "我的坚果云" / "行测obsidian" / "行测"
        (v / "copilot" / "skills").mkdir(parents=True)
        (home / "Library" / "x" / "copilot" / "skills").mkdir(parents=True)     # 系统文件夹不去翻
        self.assertEqual(paths.guess_vault(home), v.resolve())
        self.assertIsNone(paths.guess_vault(self.tmp / "nothing"))

    def test_version_compare(self):
        self.assertGreater(update._ver("v1.0.10"), update._ver("1.0.9"))
        self.assertEqual(update._ver("v1.2.0"), (1, 2, 0))
        self.assertEqual(update._ver(""), (0,))

    def test_apply_refuses_source_version(self):
        with self.assertRaises(update.UpdateError):
            update.apply()

    def test_web_files(self):
        r, data = self.req("GET", "/manifest.webmanifest")
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(data)["short_name"], "修仙传")
        r, _ = self.req("GET", "/device.js")
        self.assertEqual(r.status, 200)


if __name__ == "__main__":
    unittest.main()
