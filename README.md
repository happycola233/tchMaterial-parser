# [国家中小学智慧教育平台](https://basic.smartedu.cn/tchMaterial/) 电子课本下载工具  

![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Made With Love❤️](https://img.shields.io/badge/Made_With-%E2%9D%A4-red.svg)

本工具可以帮助您从 **[国家中小学智慧教育平台](https://basic.smartedu.cn/tchMaterial/)** 获取电子课本的 PDF 文件网址并进行下载，让您更方便地获取课本内容。  

📢 **⚠️ 重要更新（2025年3月）**  
自 **2025 年 02 月** 起，国家中小学智慧教育平台 **需要登录** 才能访问电子课本资源，用户需提供 **Access Token** 才可正常下载。  

👉 **请先按照下方指南设置 Access Token**，否则程序将无法解析资源！  

---

## ✨ 工具特点  

- **支持 Access Token 登录** 🔑：支持用户手动输入 Access Token，并存储在本地（Windows 版存入注册表），下次启动可自动加载。   
- **支持批量下载** 📚：一次输入多个电子课本预览页面网址，即可批量下载 PDF 课本文件。  
- **自动文件命名** 📂：程序会自动使用教材名称作为文件名，方便管理下载的课本文件。  
- **高DPI适配** 🖥️：优化 UI 以适配高分辨率屏幕，避免界面模糊问题。  
- **下载进度可视化** 📊：实时显示下载进度，支持暂停/恢复操作。  
- **跨平台支持** 💻：支持 Windows、Linux、macOS（需图形界面）。  

---

## 🔑 获取 Access Token（必需）  

1. **打开浏览器**，访问 [国家中小学智慧教育平台](https://auth.smartedu.cn/uias/login) 并 **登录账号**。  
2. 按 **F12** 或 **Ctrl+Shift+I** 打开 **开发者工具**，选择 **控制台（Console）**。  
3. 在控制台粘贴以下代码后回车（Enter）：  

   ```javascript
   (function() {
      let authKey = Object.keys(localStorage).find(key => key.includes("ND_UC_AUTH"));
      if (!authKey) {
         console.error("未找到 Access Token，请确保已登录！");
         return;
      }
      let tokenData = JSON.parse(localStorage.getItem(authKey));
      let accessToken = JSON.parse(tokenData.value).access_token;
      console.log("%cAccess Token: ", "color: green; font-weight: bold", accessToken);
   })();
   ```
4. 复制控制台输出的 **Access Token**，然后在本程序中点击 **“设置 Token”** 按钮，粘贴并保存 Token。  

🚨 **注意**：Access Token 可能会过期，若下载失败提示 **401 Unauthorized**，请重新获取并设置新的 Token。  

---

## 🛠️ 使用方法  

1. **输入教材链接** 📥  
   - 将电子课本的 **预览页面网址** 粘贴到程序文本框中，支持多个 URL（每行一个）。  
   - **示例网址**：  
     ```
     https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=XXXXXX&catalogType=tchMaterial&subCatalog=tchMaterial
     ```

2. **设置 Access Token** 🔑  
   - 若是第一次使用，需点击 **“设置 Token”** 按钮，粘贴 Access Token 并保存。  

3. **开始下载** 🚀  
   - 点击 **“下载”** 按钮，程序将自动解析并下载 PDF 课本。  
   - 支持 **批量下载**，所有 PDF 文件会自动按课本名称命名并保存在选定目录中。  

---

## 📸 截图  

![程序截图](./res/PixPin_2025-03-14_23-44-26.png)  

---

## ❓ 常见问题  

### 1. **为什么下载失败？** ⚠️  

- **检查是否已正确设置 Access Token** 🔑。  
- **确认网络连接是否正常** 🌐，有时网络不稳定可能导致下载失败。  
- **确保输入的网址有效** 🔗，部分旧资源可能已被移除。  
- **Token 过期**：点击下载后，若程序提示 Token 过期，请重新获取 Token 并更新。  

### 2. **Access Token 保存在哪里？** 💾  

- **Windows 版**：Token 会存入 **注册表**（`HKEY_CURRENT_USER\Software\tchMaterial-parser`）。  
- **Linux/macOS 版**：Token 仅存于内存，不会自动保存，程序重启后需重新输入。  

### 3. **Token 会不会泄露？** 🔐  

- 本程序 **不会上传** Token，也不会存储在云端，仅用于本地请求授权。  
- **请勿在公开场合分享 Token**，以免账号被他人使用。  

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=happycola233/tchMaterial-parser&type=Date)](https://star-history.com/#happycola233/tchMaterial-parser&Date)

---

## 🤝 贡献指南  

如果您发现 Bug 或有改进建议，欢迎提交 **Issue** 或 **Pull Request**，让我们一起完善本工具！  

---

## 📜 许可证  

本项目基于 [MIT License](LICENSE) 许可证，欢迎自由使用和二次开发。  

---

## 💌 友情链接  

📚 您也可以在 [ChinaTextbook](https://github.com/TapXWorld/ChinaTextbook) 项目中下载归档的教材 PDF。  

---

🚀 **最新版本 v3.0 现已发布，欢迎体验！**