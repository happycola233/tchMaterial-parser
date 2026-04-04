# 国家中小学智慧教育平台 电子课本 下载工具

![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

本工具可以帮助您从[**国家中小学智慧教育平台**](https://basic.smartedu.cn/)获取电子课本的 PDF 文件并进行下载。

## 🌐 在线使用（推荐）

**纯前端版本**，无需安装，直接访问：

👉 **https://coffeeeeffoc.github.io/tchMaterial-parser/**

> 支持复制 curl 命令下载（带 Auth 认证头），需配合浏览器 CORS 扩展使用。

---

## 📦 下载到本地使用

本项目提供 **3 个版本**，请根据需求选择：

| 版本 | 目录 | 说明 | 需要后端 |
|------|------|------|----------|
| **Flask** | `web-flask/` | Python Flask Web 版本 | ❌ 独立运行 |
| **React+Server** | `web-react-server/` | React 前端 + Express 后端 | ❌ 独立运行 |
| **Pure HTML** | `web-pure-html/` | 纯前端版本，无后端 | ⚠️ 需 CORS 代理或扩展 |

### 快速启动

```bash
# Flask 版本
cd web-flask
pip install -r requirements.txt
python app.py
# 访问 http://localhost:5000

# React + Server 版本
cd web-react-server
npm install
npm run server &   # 启动后端 (端口 3001)
npm run dev         # 启动前端 (端口 5173)

# 纯前端版本
cd web-pure-html
npm install
npm run dev
# 需配合 CORS 浏览器扩展使用
```

---

## 🖥️ 桌面端下载工具

原版 Python tkinter 桌面应用，下载发布版请访问 [GitHub Releases](https://github.com/happycola233/tchMaterial-parser/releases)。

---

## 🔑 Access Token 设置

> **重要提示**：部分资源需要 Access Token 才能下载

**获取方法**：
1. 打开浏览器，访问[国家中小学智慧教育平台](https://auth.smartedu.cn/uias/login)并**登录账号**。
2. 按下 **F12** 打开开发者工具，选择**控制台（Console）**。
3. 粘贴以下代码并回车：

```javascript
JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith("ND_UC_AUTH")))).access_token
```

4. 复制输出的 Token，粘贴到工具中保存。

---

## ❓ 常见问题

**Q: 下载失败？**
- 检查是否需要设置 Access Token
- 纯前端版本需配合 CORS 扩展（如 Allow CORS）
- 或复制 curl 命令到终端执行下载

**Q: 纯前端版本如何使用？**
1. 安装 CORS 浏览器扩展
2. 或复制 curl 命令到终端执行下载

---

## ⭐Star History

[![Star History Chart](https://api.star-history.com/svg?repos=happycola233/tchMaterial-parser&type=Date)](https://star-history.com/#happycola233/tchMaterial-parser&Date)

---

## 📜 许可证

[MIT License](LICENSE)
