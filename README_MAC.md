# macOS 运行指南

## 系统要求

- **操作系统**: macOS 10.9 或更高版本
- **Python**: 3.6 或更高版本
- **图形界面**: 支持GUI的环境（Terminal.app、iTerm2等）

## 安装步骤

### 1. 检查Python环境

```bash
python3 --version
```

如果没有Python 3，请先安装：
```bash
# 使用Homebrew安装（推荐）
brew install python

# 或者从官网下载安装包
# https://www.python.org/downloads/macos/
```

### 2. 安装依赖

```bash
pip3 install -r requirements-mac.txt
```

### 3. 运行程序

```bash
python3 run_mac.py
```

或者直接执行：
```bash
./run_mac.py
```

## macOS 特殊说明

### Token 存储位置

在macOS系统中，Access Token **仅在运行时临时存储于内存**，程序重启后需要重新输入。这是当前版本的限制，未来版本会改进此功能。

### GUI 支持

- 程序使用Tkinter作为GUI框架，macOS原生支持
- 如果遇到GUI问题，可能需要安装XQuartz：
  ```bash
  brew install --cask xquartz
  ```

### 中文字体支持

程序已针对macOS优化中文显示，如果遇到字体问题：

1. 确保系统语言设置为中文
2. 检查终端的字符编码设置为UTF-8

## 使用方法

### 1. 获取 Access Token

1. 打开浏览器，访问 [国家中小学智慧教育平台](https://auth.smartedu.cn/uias/login) 并登录
2. 按 `F12` 或 `Cmd+Option+I` 打开开发者工具
3. 选择 "Console"（控制台）标签
4. 粘贴以下代码并按回车：

```javascript
(function() {
  const authKey = Object.keys(localStorage).find(key => key.startsWith("ND_UC_AUTH"));
  if (!authKey) {
    console.error("未找到 Access Token，请确保已登录！");
    return;
  }
  const tokenData = JSON.parse(localStorage.getItem(authKey));
  const accessToken = JSON.parse(tokenData.value).access_token;
  console.log("%cAccess Token:", "color: green; font-weight: bold", accessToken);
})();
```

5. 复制输出的 Access Token

### 2. 设置 Token

1. 在程序界面点击 "设置 Token" 按钮
2. 粘贴刚才复制的 Access Token
3. 点击 "保存"

### 3. 下载教材

1. 在文本框中输入教材页面网址，或使用下拉菜单选择
2. 点击 "下载" 按钮
3. 选择保存位置

## 常见问题

### Q: 程序无法启动，提示 "No module named 'tkinter'"

A: 安装Python的Tkinter支持：
```bash
brew install python-tk
```

### Q: 下载失败，提示 401 或 403 错误

A: Access Token 可能已过期，请重新获取并设置新的 Token。

### Q: 程序界面显示异常或中文乱码

A: 检查系统语言设置，确保终端支持UTF-8编码。

### Q: 无法保存 Access Token

A: 这是macOS版本的已知限制。Token仅在程序运行期间有效，重启程序需要重新输入。

## 技术支持

如果遇到其他问题，请：

1. 检查是否满足系统要求
2. 确认所有依赖已正确安装
3. 查看终端输出的错误信息
4. 访问项目GitHub页面获取最新信息

## 版本信息

- 程序版本：v3.1
- macOS适配版本：基于原版修改
- 最后更新：2025-05-18 