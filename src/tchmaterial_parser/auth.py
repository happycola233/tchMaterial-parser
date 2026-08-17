# -*- coding: utf-8 -*-
# 官网 UC SDK 的 X-ND-AUTH 生成，以及用户粘贴登录凭据时的 JSON 校验
#
# 官网在登录后把凭据写入 localStorage 的 ND_UC_AUTH-* ，页面里的 getAuthHeader /
# getAuthHeaderAsync 每次请求都会现算签名，而不是复用抓包里的一整段头。
# 对应实现大致是：
#   Fe(diff)  -> nonce = (Date.now() + diff) + ":" + Ze(8)
#   ze(url)   -> HMAC-SHA256(mac_key, 签名原文) 再 Base64
#   He(...)   -> MAC id="{access_token}",nonce="...",mac="..."
#
# 签名原文（末尾必须有空行，四段都以 \n 分隔）：
#   {nonce}\n{METHOD}\n{解码后的 path}{?query}\n{hostname}\n
#
# 维护时注意：
# - 中文文件名必须先 unquote 再签名。HAR 里编码路径对不上，解码后才能对上官网 mac。
# - query 要保留在 path 后面；hostname 不含端口。不要改成 netloc，也不要签 fragment。
# - diff 只是本地时钟相对 UC 服务器的毫秒差，加进 nonce 时间戳，不单独放进请求头。
# - 私有 CDN 下载只需要 X-ND-AUTH。UC SDK 的 getAuthHeader 只生成这个头，从不改 URL。
#   官网若出现 ?accessToken=，是详情页阅读器自己拼的，不是登录 SDK：
#   普通电子教材（assets_document）走站点 pdfjs/2.15，HAR 里不带该参数；
#   专题课（thematic_course，如部分体育教师用书）走 x-edu-microapp-detail 的
#   docplayer，会拼上 Token，同时仍按「已带查询串的完整 URL」现算 MAC。
#   本工具的抉择：下载时不拼接 accessToken，只对解析出的原地址签名。有真实 MAC
#   时专题课也能过；2efcd89 无条件拼接会在 Token 无效/过期时变成 #81 的
#   400 InvalidArgument。#76 那批较严的资源在只有占位头时会 400，用本模块
#   生成的真实 MAC、URL 不带 Token 即可通过。
# - 没有 mac_key 时退回旧占位头 nonce="0",mac="0"，兼容只保存了 Access Token 的用户。
#   此时部分私有资源仍可能 400，需要用户重新粘贴含 mac_key 的 JSON。

import base64, hashlib, hmac, json, math, random, time
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

# 官网 Ze() 的字符表。下标用 Math.ceil(35 * Math.random())，0 几乎抽不到，1–35 对应 1-9A-Z。
NONCE_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

class TokenCredentials(NamedTuple):
    """从用户粘贴内容解析出的登录凭据。mac_key 为空时只能生成占位 X-ND-AUTH。"""
    access_token: str
    mac_key: str | None = None
    diff: int = 0 # 毫秒；与官网 Fe(diff) 的 parseInt(diff, 10) 一致

def generate_nonce(diff: int = 0) -> str:
    """按官网 Fe(diff) 生成 nonce：用服务器时间近似值，避免本地时钟偏差导致签名被拒。"""
    suffix = "".join(NONCE_ALPHABET[math.ceil(35 * random.random())] for _ in range(8))
    return f"{int(time.time() * 1000) + int(diff)}:{suffix}"

def signature_string(url: str, method: str, nonce: str) -> str:
    """构造官网 ze() 的 HMAC 原文。path 先解码，query 原样保留，host 不含端口。"""
    parts = urlsplit(url)
    relative = unquote(parts.path) + (f"?{parts.query}" if parts.query else "")
    return f"{nonce}\n{method.upper()}\n{relative}\n{parts.hostname or ''}\n"

def sign_mac(text: str, mac_key: str) -> str:
    """HMAC-SHA256(mac_key, 原文) 的 Base64，对应官网 CryptoJS.HmacSHA256(...).toString(Base64)。"""
    digest = hmac.new(mac_key.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")

def build_nd_auth(
    url: str,
    method: str = "GET",
    access_token: str | None = None,
    mac_key: str | None = None,
    diff: int = 0,
    nonce: str | None = None,
) -> str:
    """生成当前 URL 的 X-ND-AUTH。nonce 可传入以便单测对照；生产路径应让它现算。"""
    token_id = access_token or "0"
    if not mac_key:
        # 旧版匿名/仅 Token 格式。CDN 有时只看 id，#76 里较严的对象存储会因此 400。
        return f'MAC id="{token_id}",nonce="0",mac="0"'

    nonce = nonce or generate_nonce(diff)
    mac = sign_mac(signature_string(url, method, nonce), mac_key)
    return f'MAC id="{token_id}",nonce="{nonce}",mac="{mac}"'

TOKEN_JSON_FIELDS = ("access_token", "mac_key", "diff")

class TokenInputError(ValueError):
    """粘贴的登录凭据不是含 access_token、mac_key、diff 的 JSON。"""

def format_token_json(access_token: str, mac_key: str | None = None, diff: int = 0) -> str:
    """把已保存的字段格式化成设置窗口用的三项 JSON。旧版只有 Access Token 时 mac_key 为空串。"""
    return json.dumps({
        "access_token": access_token,
        "mac_key": mac_key or "",
        "diff": int(diff),
    }, ensure_ascii=False, indent=2)

def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise TokenInputError(f"{field} 必须是整数。")
    try:
        return int(value) # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise TokenInputError(f"{field} 必须是整数。") from None

def _credentials_from_mapping(data: dict) -> TokenCredentials:
    missing = [field for field in TOKEN_JSON_FIELDS if field not in data]
    if missing:
        raise TokenInputError(
            f"登录凭据缺少字段：{', '.join(missing)}。必须包含 access_token、mac_key、diff 三项。"
        )

    token = data.get("access_token")
    mac_key = data.get("mac_key")
    if not isinstance(token, str) or not token.strip():
        raise TokenInputError("access_token 必须是非空字符串。")
    if not isinstance(mac_key, str) or not mac_key.strip():
        raise TokenInputError("mac_key 必须是非空字符串。")
    return TokenCredentials(token.strip(), mac_key, _require_int(data.get("diff"), "diff"))

def parse_token_input(raw: str) -> TokenCredentials:
    """解析设置 Token 窗口的粘贴内容：必须是含 access_token、mac_key、diff 的 JSON；空内容表示清除。"""
    text = raw.strip()
    if not text:
        return TokenCredentials("")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise TokenInputError("登录凭据必须是 JSON，且包含 access_token、mac_key、diff 三项。") from None

    # 控制台复制 JSON.stringify 结果时，有时会带上一层引号。
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise TokenInputError("登录凭据必须是 JSON，且包含 access_token、mac_key、diff 三项。") from None

    if not isinstance(data, dict):
        raise TokenInputError("登录凭据必须是包含 access_token、mac_key、diff 的 JSON 对象。")
    return _credentials_from_mapping(data)
