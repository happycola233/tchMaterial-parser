# -*- coding: utf-8 -*-
# 全局共享的 HTTP 会话与认证头部（两者都只被原地修改，因此可以直接导入使用）
#
# headers 里的 X-ND-AUTH 只是占位，给公开 JSON 解析等不按 URL 签名的请求用。
# 私有 CDN（ndr-private、ebook_mapping 等）必须走 request_headers()，按当前 URL 现算签名。
# 不要把这里的静态头直接拿去下私有文件。accessToken 查询参数也不要在这里拼：
# 官网只有专题课 docplayer 会拼，UC SDK 和普通教材 pdf.js 都不会；本工具统一不拼。

import requests

session = requests.Session() # 初始化请求
session.trust_env = False # 不读取系统或环境变量中的代理配置

headers = { # 设置请求头部，包含认证信息
    "Authorization": "Bearer 0",
    "Origin": "https://basic.smartedu.cn",
    "Referer": "https://basic.smartedu.cn/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "X-ND-AUTH": 'MAC id="0",nonce="0",mac="0"',
}

def request_headers(url: str, method: str = "GET") -> dict[str, str]:
    """复制全局请求头，并用 auth.build_nd_auth 覆盖 X-ND-AUTH。

    有 mac_key 时生成官网真实签名；只有 Access Token 时仍是占位头，但 id 会换成该 Token。
    延迟导入 config/auth，避免与 config 循环引用。
    """
    from . import auth, config

    result = dict(headers)
    result["X-ND-AUTH"] = auth.build_nd_auth(
        url,
        method,
        config.access_token,
        config.mac_key,
        config.token_diff,
    )
    return result
