"""局域网模式：让同一个 Wi-Fi 下的手机、平板用浏览器打开修仙传（电脑当主机，数据只有电脑上这一份）。

- 设置在本机设置（~/.xingce-rpg/settings.json）里：lan = true / false，lan_code = 6 位访问口令；
- 开了局域网模式，程序监听 0.0.0.0（重启生效）；本机（127.0.0.1）访问不用口令，别的设备第一次要输口令，
  对了发一个 cookie，之后不用再输；
- 只有本机能改局域网设置（平板上看不到口令、也关不掉）；
- 二维码用 segno（纯 Python，exe 里带着）；源码版没装 segno 就只显示地址。
"""
import hashlib
import secrets
import socket

from .paths import load_settings, save_settings

COOKIE = "xrpg_lan"


def settings():
    s = load_settings()
    if not s.get("lan_code"):
        s["lan_code"] = "%06d" % secrets.randbelow(10 ** 6)
        save_settings(s)
    return {"enabled": bool(s.get("lan")), "code": s["lan_code"]}


def update(enabled=None, new_code=False):
    s = load_settings()
    if enabled is not None:
        s["lan"] = bool(enabled)
    if new_code or not s.get("lan_code"):
        s["lan_code"] = "%06d" % secrets.randbelow(10 ** 6)
    save_settings(s)
    return settings()


def token(code):
    return hashlib.sha256(("xingce-rpg:" + str(code)).encode("utf-8")).hexdigest()[:32]


def is_local(addr):
    return addr in ("127.0.0.1", "::1", "::ffff:127.0.0.1") or str(addr).startswith("127.")


def authorized(addr, cookie_header):
    """这个请求能不能用：本机总能用；别的设备要带对的 cookie"""
    if is_local(addr):
        return True
    want = token(settings()["code"])
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE and v == want:
            return True
    return False


def ping():
    from .version import VERSION
    return {"app": "xingce-rpg", "name": socket.gethostname()[:40], "version": VERSION}


def local_ips():
    """电脑在局域网里的地址（192.168.x.x / 10.x.x.x 之类），手机要输这个"""
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))          # 不会真的发包，只是让系统选一块网卡
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return [ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254.")]


def qr_svg(text):
    try:
        import segno
    except ImportError:
        return ""
    import io
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, dark="#1b150d", light="#fffaf0", xmldecl=False)
    return buf.getvalue().decode("utf-8")


def status(port, listening_lan):
    st = settings()
    urls = ["http://%s:%d/" % (ip, port) for ip in local_ips()]
    return {"enabled": st["enabled"], "code": st["code"], "port": port, "listening": listening_lan, "urls": urls,
            "qr": qr_svg(urls[0]) if urls and listening_lan else "", "restart": st["enabled"] != listening_lan}


LOGIN_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>行测修仙传 · 入山门</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(ellipse at 50% 30%,#14302b,#050a09 70%);
    font-family:"STKaiti","KaiTi","楷体",serif;color:#e8dcc0}
  .box{text-align:center;padding:32px 28px;border:1px solid rgba(111,211,192,.35);border-radius:16px;background:rgba(20,58,58,.6);width:min(340px,86vw)}
  h1{margin:0 0 6px;font-size:32px;letter-spacing:.3em;color:#ffd98a} p{color:#c9b88e;font-size:15px}
  input{width:100%;box-sizing:border-box;font-size:28px;letter-spacing:.4em;text-align:center;padding:10px;border-radius:10px;border:1px solid #6fd3c0;
    background:#0b1d1b;color:#fff8ec;margin:10px 0}
  button{width:100%;padding:12px;font-size:20px;letter-spacing:.4em;border:none;border-radius:10px;color:#fff8ec;
    background:linear-gradient(180deg,#f6b766,#c9652a);font-family:inherit}
  .err{color:#ff9a8a;min-height:1.4em}
</style></head><body><form class="box" method="post" action="/lan/login">
<h1>入山门</h1><p>输入电脑上「设置 → 📱 手机 / 平板」里的访问口令</p>
<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" autofocus placeholder="······">
<div class="err">{ERR}</div><button>进 入</button></form></body></html>"""


def login_page(err=""):
    return LOGIN_PAGE.replace("{ERR}", err).encode("utf-8")
