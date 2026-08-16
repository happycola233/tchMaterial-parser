# -*- coding: utf-8 -*-
# 全局共享的 HTTP 会话与认证头部（两者都只被原地修改，因此可以直接导入使用）

import requests

session = requests.Session() # 初始化请求
session.proxies = {} # 全局忽略代理

headers = { # 设置请求头部，包含认证信息
    "Authorization": "Bearer 0",
    "Origin": "https://basic.smartedu.cn",
    "Referer": "https://basic.smartedu.cn/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    # 保留旧版匿名请求格式；设置 Token 后，私有 CDN 的主要鉴权入口由下载 URL 的 accessToken 参数提供。
    "X-ND-AUTH": 'MAC id="0",nonce="0",mac="0"',
}
