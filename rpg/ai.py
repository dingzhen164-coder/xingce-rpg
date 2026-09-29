"""
调用大模型（默认 DeepSeek；任何 OpenAI 兼容的 /chat/completions 接口都行）。

本机设置（~/.xingce-rpg/settings.json，网页“设置”页填写）：
    api_key   必填；也可以用环境变量 DEEPSEEK_API_KEY
    base_url  默认 https://api.deepseek.com
    model     默认 deepseek-chat

只用 urllib，不依赖第三方库。所有调用失败都抛 AIError，由 api 层转成网页上的提示。
"""
import json
import os
import re
import urllib.error
import urllib.request

from .paths import load_settings

DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class AIError(Exception):
    pass


def settings():
    s = load_settings()
    return {
        "api_key": s.get("api_key") or os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": (s.get("base_url") or DEFAULT_BASE).rstrip("/"),
        "model": s.get("model") or DEFAULT_MODEL,
    }


def available():
    return bool(settings()["api_key"])


def chat(messages, json_mode=False, temperature=0.3, max_tokens=1500, timeout=120):
    """发一次对话，返回模型回复的文字"""
    s = settings()
    if not s["api_key"]:
        raise AIError("还没有填写 API key（网页右上角“设置”）")
    body = {"model": s["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        s["base_url"] + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + s["api_key"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise AIError(f"AI 接口返回错误 {e.code}：{detail}")
    except Exception as e:
        raise AIError(f"连不上 AI 接口：{e}")
    try:
        return data["choices"][0]["message"]["content"] or ""
    except Exception:
        raise AIError(f"AI 返回格式不对：{str(data)[:300]}")


def chat_json(messages, **kw):
    """要求模型返回 JSON 对象；解析失败时尝试从文字里抠出第一个 {...}"""
    text = chat(messages, json_mode=True, **kw)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    raise AIError(f"AI 没有按要求返回 JSON：{text[:200]}")
