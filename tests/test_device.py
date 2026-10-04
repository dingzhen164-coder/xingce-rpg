"""局域网模式（口令、cookie、只能本机改的设置）、版本号比较、版本接口。运行：python -m unittest discover -s tests -v"""
import http.client
import json
import os
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

    def test_app_apk_from_computer(self):
        """平板 App 更新：电脑替平板去 GitHub 下安装包，平板从局域网拿（不用口令）"""
        from rpg import appapk
        fake = b"PK\x03\x04 fake apk"
        info = {"latest": "9.9.9", "apk_url": "https://example/xingce-xiuxian.apk", "apk_size": len(fake)}

        class Resp:
            def __init__(self): self.left = fake
            def read(self, n=-1):
                out, self.left = self.left, b""
                return out
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with patch.object(update, "check", return_value=info), patch("urllib.request.urlopen", return_value=Resp()):
            r, data = self.req("GET", "/api/app/latest")
        d = json.loads(data)
        self.assertEqual((d["latest"], d["ready"], d["path"]), ("9.9.9", True, "/app/xingce-xiuxian.apk"))
        self.assertTrue((self.tmp / "apk" / "xingce-xiuxian-9.9.9.apk").is_file())
        r, data = self.req("GET", "/app/xingce-xiuxian.apk", remote=True)                 # 平板浏览器下载：没有 cookie 也给
        self.assertEqual((r.status, data), (200, fake))
        self.assertEqual(r.getheader("Content-Type"), "application/vnd.android.package-archive")
        r, _ = self.req("GET", "/api/app/latest", remote=True)                             # 别的接口照样要口令
        self.assertEqual(r.status, 401)
        port = appapk.serve_apk_port("127.0.0.1", 18960)                                 # 旧版 App 用的“只给安装包”端口
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/xingce-xiuxian.apk")
        rr = c.getresponse()
        self.assertEqual((rr.status, rr.read()), (200, fake))
        c.request("GET", "/api/lan")
        rr = c.getresponse(); rr.read()
        self.assertEqual(rr.status, 404)                                                     # 那个端口只给安装包

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

    def test_changelog_matches_version(self):
        from rpg import changelog
        from rpg.version import VERSION
        es = changelog.entries()
        self.assertEqual(es[0]["version"], VERSION)          # 改了版本号就要在更新记录最上面加一节
        self.assertTrue(all(e["items"] for e in es))
        r, data = self.req("GET", "/api/changelog")
        self.assertEqual(json.loads(data)["entries"][0]["version"], VERSION)

    def test_version_compare(self):
        self.assertGreater(update._ver("v1.0.10"), update._ver("1.0.9"))
        self.assertEqual(update._ver("v1.2.0"), (1, 2, 0))
        self.assertEqual(update._ver(""), (0,))

    def test_release_notes_drop_trailers(self):
        body = "默认亮色\r\n\r\n- 灰字加深\r\n\r\nCo-Authored-By: X <a@b>\r\nClaude-Session: https://x"
        self.assertEqual(update._notes(body), "默认亮色\n\n- 灰字加深")

    def test_swap_env_is_clean(self):
        env = update.clean_env({"PATH": "x", "_PYI_APPLICATION_HOME_DIR": "C:\\T\\_MEI1", "_PYI_PARENT_PROCESS_LEVEL": "1",
                                "_MEIPASS2": "C:\\T\\_MEI1"})
        self.assertEqual(env, {"PATH": "x", "PYINSTALLER_RESET_ENVIRONMENT": "1"})

    def test_swap_script_quotes_paths(self):
        ps = update.swap_script(123, r"C:\a b\it's\x.new.exe", r"C:\a b\it's\x.exe")
        self.assertIn("Wait-Process -Id 123", ps)
        self.assertIn("'C:\\a b\\it''s\\x.new.exe'", ps)

    @unittest.skipUnless(os.name == "nt", "只在 Windows 上真跑换文件")
    def test_swap_really_replaces_on_windows(self):
        import shutil, subprocess, time
        d = self.tmp / "换 exe"
        d.mkdir()
        old, new = d / "app.exe", d / "app.new.exe"
        shutil.copy(r"C:\Windows\System32\whoami.exe", old)
        shutil.copy(r"C:\Windows\System32\hostname.exe", new)
        want = new.read_bytes()
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
        update.launch_swap(p.pid, new, old)
        p.wait()
        for _ in range(60):
            if not new.exists() and old.read_bytes() == want:
                break
            time.sleep(0.5)
        self.assertFalse(new.exists())
        self.assertEqual(old.read_bytes(), want)

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
