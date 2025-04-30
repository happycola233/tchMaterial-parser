# [国家中小学智慧教育平台](https://basic.smartedu.cn/tchMaterial/) 电子课本下载工具

![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Made With Love❤️](https://img.shields.io/badge/Made_With-%E2%9D%A4-red.svg)

> [!TIP]
> 🚀最新版本 v3.0 现已发布，欢迎体验！

本工具可以帮助您从[**国家中小学智慧教育平台**](https://basic.smartedu.cn/tchMaterial/)获取电子课本的 PDF 文件网址并进行下载，让您更方便地获取课本内容。

> [!NOTE]
>
> 自**2025 年 2 月**起，国家中小学智慧教育平台**需要登录**才能访问电子课本资源，用户需提供 **Access Token**（即登录凭据）才可正常使用本工具的下载功能。
>
> **👉请先按照[下方指南](#2-设置-access-token)设置 Access Token，否则程序将无法解析资源！**

## ✨工具特点

- **支持 Access Token 登录**🔑：支持用户手动输入 Access Token，在 Windows 操作系统下会存入注册表，下次启动可自动加载。
- **支持批量下载**📚：一次输入多个电子课本预览页面网址，即可批量下载 PDF 课本文件。
- **自动文件命名**📂：程序会自动使用教材名称作为文件名，方便管理下载的课本文件。
- **高 DPI 适配**🖥️：优化 UI 以适配高分辨率屏幕，避免界面模糊问题。
- **下载进度可视化**📊：实时显示下载进度，支持暂停/恢复操作。
- **跨平台支持**💻：支持 Windows、Linux、macOS 等操作系统（需要图形界面）。

![程序截图](./res/PixPin_2025-03-14_23-44-26.png)

## ⬇️下载与安装方法

### GitHub Releases 页面

由于我们的精力有限，本项目的 [GitHub Releases 页面](https://github.com/happycola233/tchMaterial-parser/releases)**仅会发布适用于 Windows 与 Linux 操作系统的 x64 架构**的程序。

在下载完成之后，即可运行本程序，不需要额外的安装步骤。

### Arch 用户软件仓库（AUR）

对于 **Arch Linux** 操作系统，本程序已发布至[Arch 用户软件仓库](https://aur.archlinux.org/packages/tchmaterial-parser)，因此您还可以通过在终端中输入以下命令安装：

```sh
yay -S tchmaterial-parser
```

感谢 [@iamzhz](https://github.com/iamzhz) 制作了本工具的发行包（[#26](../../issues/26)）！

## 🛠️使用方法

### 1. 输入教材链接📥

将电子课本的**预览页面网址**粘贴到程序文本框中，支持多个 URL（每行一个）。

**示例网址**：

```text
https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=XXXXXX&catalogType=tchMaterial&subCatalog=tchMaterial
```

### 2. 设置 Access Token🔑

若您第一次使用本程序，需点击 “**设置 Token**” 按钮，粘贴 Access Token 并保存。

1. **打开浏览器**，访问[国家中小学智慧教育平台](https://auth.smartedu.cn/uias/login)并**登录账号**。
2. 按下 **F12** 或 **Ctrl+Shift+I**，或右键——检查（审查元素）打开**开发者工具**，选择**控制台（Console）**。
3. 在控制台粘贴以下代码后回车（Enter）：

   ```js
   (function() {
     const authKey = Object.keys(localStorage).find(key => key.startsWith("ND_UC_AUTH"));
     if (!authKey) {
       console.error("未找到 Access Token，请确保已登录！");
       return;
     }
     const tokenData = JSON.parse(localStorage.getItem(authKey));
     const accessToken = JSON.parse(tokenData.value).access_token;
     console.log("%cAccess Token: ", "color: green; font-weight: bold", accessToken);
   })();
   ```
  
4. 复制控制台输出的 **Access Token**，然后在本程序中点击 “**设置 Token**” 按钮，粘贴并保存 Token。

> [!NOTE]
> Access Token 可能会过期，若下载失败提示 **401 Unauthorized**，请重新获取并设置新的 Token。

### 3. 开始下载🚀

点击 “**下载**” 按钮，程序将自动解析并下载 PDF 课本。

本工具支持**批量下载**，所有 PDF 文件会自动按课本名称命名并保存在选定目录中。

## ❓常见问题

### 1. 为什么下载失败？⚠️

- 检查是否已[**正确设置 Access Token**](#2-设置-access-token)🔑，且没有过期。
- **确认网络连接是否正常**🌐，有时网络不稳定可能导致下载失败。
- **确保输入的网址有效**🔗，部分旧资源可能已被移除。

### 2. Access Token 保存在哪里？💾

- **Windows 操作系统**：Token 会存储在**注册表** `HKEY_CURRENT_USER\Software\tchMaterial-parser` 项中的 `AccessToken` 值。
- **Linux 操作系统**: Token 会存储在 `~/.config/tchMaterial-parser/data.json` 的文件中。
- **macOS 等操作系统**：Token 仅在运行时临时存储于内存，不会自动保存，程序重启后需重新输入，目前我们正在努力改进该功能。

### 3. Token 会不会泄露？🔐

- 本程序**不会上传** Token，也不会存储在云端，仅用于本地请求授权。
- **请勿在公开场合分享 Token**，以免您的账号被他人使用，造成严重后果。

## ⭐Star History

[![Star History Chart](https://api.star-history.com/svg?repos=happycola233/tchMaterial-parser&type=Date)](https://star-history.com/#happycola233/tchMaterial-parser&Date)

## 🤝贡献指南

如果您发现 Bug 或有改进建议，欢迎提交 **Issue** 或 **Pull Request**，让我们一起完善本工具！

## 📜许可证

本项目基于 [MIT 许可证](LICENSE)，欢迎自由使用和二次开发。

## 💌友情链接

- 📚您也可以在 [ChinaTextbook](https://github.com/TapXWorld/ChinaTextbook) 项目中下载归档的教材 PDF。
