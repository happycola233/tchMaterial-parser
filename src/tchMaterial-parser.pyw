# -*- coding: utf-8 -*-
# 国家中小学智慧教育平台 资源下载工具 v3.1
# 项目地址：https://github.com/happycola233/tchMaterial-parser
# 作者：肥宅水水呀（https://space.bilibili.com/324042405）以及其他为本工具作出贡献的用户
# 最近更新于：2025-05-18

# 导入相关库
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os, platform
import sys
from functools import partial
import base64, tempfile, pyperclip
import threading, requests, psutil
import json, re

os_name = platform.system() # 获取操作系统类型

if os_name == "Windows": # 如果是 Windows 操作系统，导入 Windows 相关库
    import win32print, win32gui, win32con, win32api, ctypes, winreg

def parse(url: str) -> tuple[str, str, str] | tuple[None, None, None]: # 解析 URL
    try:
        content_id, content_type, resource_url = None, None, None

        # 简单提取 URL 中的 contentId 与 contentType（这种方法不严谨，但为了减少导入的库只能这样了）
        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentId":
                content_id = q.split("=")[1]
                break
        if not content_id:
            return None, None, None

        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentType":
                content_type = q.split("=")[1]
                break
        if not content_type:
            content_type = "assets_document"

        # 获得该 contentId 下资源的信息，返回数据示例：
        """
        {
            "id": "4f64356a-8df7-4579-9400-e32c9a7f6718",
            // ...
            "ti_items": [
                {
                    // ...
                    "ti_storages": [ // 资源文件地址
                        "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/pdf.pdf",
                        "https://r2-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/pdf.pdf",
                        "https://r3-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/pdf.pdf"
                    ],
                    // ...
                },
                {
                    // ...（和上一个元素组成一样）
                }
            ]
        }
        """
        # 其中 $.ti_items 的每一项对应一个资源

        if re.search(r"^https?://([^/]+)/syncClassroom/basicWork/detail", url): # 对于 “基础性作业” 的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
        else: # 对于课本的解析
            if content_type == "thematic_course": # 对专题课程（含电子课本、视频等）的解析
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
            else: # 对普通电子课本的解析
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{content_id}.json")

        data = response.json()
        for item in list(data["ti_items"]):
            if item["lc_ti_format"] == "pdf": # 找到存有 PDF 链接列表的项
                resource_url: str = item["ti_storages"][0] # 获取并构造 PDF 的 URL
                if not access_token: # 未登录时，通过一个不可靠的方法构造可直接下载的 URL
                    resource_url = re.sub(r"^https?://(.+)-private.ykt.cbern.com.cn/(.+)/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}).pkg/(?:.+)\.pdf$", r"https://\1.ykt.cbern.com.cn/\2/\3.pdf", resource_url)
                break

        if not resource_url:
            if content_type == "thematic_course": # 专题课程
                resources_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/thematic_course/{content_id}/resources/list.json")
                resources_data = resources_resp.json()
                for resource in list(resources_data):
                    if resource["resource_type_code"] == "assets_document":
                        for item in list(resource["ti_items"]):
                            if item["lc_ti_format"] == "pdf":
                                resource_url: str = item["ti_storages"][0]
                                if not access_token:
                                    resource_url = re.sub(r"^https?://(.+)-private.ykt.cbern.com.cn/(.+)/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}).pkg/(?:.+)\.pdf$", r"https://\1.ykt.cbern.com.cn/\2/\3.pdf", resource_url)
                                break
                if not resource_url:
                    return None, None, None
            else:
                return None, None, None

        return resource_url, content_id, data["title"]
    except Exception:
        return None, None, None # 如果解析失败，返回 None

def download_file(url: str, save_path: str) -> None: # 下载文件
    global download_states
    current_state = { "download_url": url, "save_path": save_path, "downloaded_size": 0, "total_size": 0, "finished": False, "failed_reason": None }
    download_states.append(current_state)

    response = session.get(url, headers=headers, stream=True)

    # 服务器返回 401 或 403 状态码
    if response.status_code == 401 or response.status_code == 403:
        current_state["finished"] = True
        current_state["failed_reason"] = "授权失败，Access Token 可能已过期或无效，请重新设置"
    elif response.status_code >= 400:
        current_state["finished"] = True
        current_state["failed_reason"] = f"服务器返回状态码 {response.status_code}"
    else:
        current_state["total_size"] = int(response.headers.get("Content-Length", 0))

        try:
            with open(save_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=131072): # 分块下载，每次下载 131072 字节（128 KB）
                    file.write(chunk)
                    current_state["downloaded_size"] += len(chunk)
                    all_downloaded_size = sum(state["downloaded_size"] for state in download_states)
                    all_total_size = sum(state["total_size"] for state in download_states)
                    downloaded_number = len([state for state in download_states if state["finished"]])
                    total_number = len(download_states)

                    if all_total_size > 0: # 防止下面一行代码除以 0 而报错
                        download_progress = (all_downloaded_size / all_total_size) * 100
                        # 更新进度条
                        download_progress_bar["value"] = download_progress
                        # 更新标签以显示当前下载进度
                        progress_label.config(text=f"{format_bytes(all_downloaded_size)}/{format_bytes(all_total_size)} ({download_progress:.2f}%) 已下载 {downloaded_number}/{total_number}")

            current_state["downloaded_size"] = current_state["total_size"]
            current_state["finished"] = True
        except Exception as e:
            current_state["downloaded_size"], current_state["total_size"] = 0, 0
            current_state["finished"] = True
            current_state["failed_reason"] = str(e)

    if all(state["finished"] for state in download_states):
        download_progress_bar["value"] = 0 # 重置进度条
        progress_label.config(text="等待下载") # 清空进度标签
        download_btn.config(state="normal") # 设置下载按钮为启用状态

        failed_states = [state for state in download_states if state["failed_reason"]]
        if len(failed_states) > 0:
            messagebox.showwarning(
                "下载完成",
                f"文件已下载到：{os.path.dirname(save_path)}\n以下链接下载失败：\n"
                + "\n".join(f'{state["download_url"]}，原因：{state["failed_reason"]}' for state in failed_states)
            )
        else:
            messagebox.showinfo("下载完成", f"文件已下载到：{os.path.dirname(save_path)}") # 显示完成对话框

def format_bytes(size: float) -> str: # 将数据单位进行格式化，返回以 KB、MB、GB、TB 为单位的数据大小
    for x in ["字节", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:3.1f} {x}"
        size /= 1024.0
    return f"{size:3.1f} PB"

def parse_and_copy() -> None: # 解析并复制链接
    urls = [line.strip() for line in url_text.get("1.0", tk.END).splitlines() if line.strip()] # 获取所有非空行
    resource_links = []
    failed_links = []

    for url in urls:
        resource_url = parse(url)[0]
        if not resource_url:
            failed_links.append(url) # 添加到失败链接
            continue
        resource_links.append(resource_url)

    if failed_links:
        messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_links)) # 显示警告对话框

    if resource_links:
        pyperclip.copy("\n".join(resource_links)) # 将链接复制到剪贴板
        messagebox.showinfo("提示", "资源链接已复制到剪贴板")

def download() -> None: # 下载资源文件
    global download_states
    download_btn.config(state="disabled") # 设置下载按钮为禁用状态
    download_states = [] # 初始化下载状态
    urls = [line.strip() for line in url_text.get("1.0", tk.END).splitlines() if line.strip()] # 获取所有非空行
    failed_links = []

    if len(urls) > 1:
        messagebox.showinfo("提示", "您选择了多个链接，将在选定的文件夹中使用教材名称作为文件名进行下载。")
        dir_path = filedialog.askdirectory() # 选择文件夹
        if os_name == "Windows":
            dir_path = dir_path.replace("/", "\\")
        if not dir_path:
            download_btn.config(state="normal") # 设置下载按钮为启用状态
            return
    else:
        dir_path = None

    for url in urls:
        resource_url, content_id, title = parse(url)
        if not resource_url:
            failed_links.append(url) # 添加到失败链接
            continue

        if dir_path:
            default_filename = title or "download"
            save_path = os.path.join(dir_path, f"{default_filename}.pdf") # 构造完整路径
        else:
            default_filename = title or "download"
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")], initialfile = default_filename) # 选择保存路径
            if not save_path: # 用户取消了文件保存操作
                download_btn.config(state="normal") # 设置下载按钮为启用状态
                return
            if os_name == "Windows":
                save_path = save_path.replace("/", "\\")

        thread_it(download_file, (resource_url, save_path)) # 开始下载（多线程，防止窗口卡死）

    if failed_links:
        messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_links)) # 显示警告对话框
        download_btn.config(state="normal") # 设置下载按钮为启用状态

    if not urls and not failed_links:
        download_btn.config(state="normal") # 设置下载按钮为启用状态

def show_access_token_window() -> None: # 打开输入 Access Token 的窗口
    token_window = tk.Toplevel(root)
    token_window.title("设置 Access Token")
    # 让窗口自动根据控件自适应尺寸；如需最小尺寸可用 token_window.minsize(...)

    token_window.focus_force() # 自动获得焦点
    token_window.grab_set() # 阻止主窗口操作
    token_window.bind("<Escape>", lambda event: token_window.destroy()) # 绑定 Esc 键关闭窗口

    # 设置一个 Frame 用于留白、布局更美观
    frame = ttk.Frame(token_window, padding=20)
    frame.pack(fill="both", expand=True)

    # 提示文本
    label = ttk.Label(frame, text="请粘贴从浏览器获取的 Access Token：", font=("微软雅黑", 10))
    label.pack(pady=5)

    # 多行 Text 替代原先 Entry，并绑定右键菜单
    token_text = tk.Text(frame, width=50, height=4, wrap="word", font=("微软雅黑", 9))
    token_text.pack(pady=5)

    # 若已存在全局 token，则填入
    if access_token:
        token_text.insert("1.0", access_token)

    # 创建右键菜单，支持剪切、复制、粘贴
    token_context_menu = tk.Menu(token_text, tearoff=0)
    token_context_menu.add_command(label="剪切 (Ctrl＋X)", command=lambda: token_text.event_generate("<<Cut>>"))
    token_context_menu.add_command(label="复制 (Ctrl＋C)", command=lambda: token_text.event_generate("<<Copy>>"))
    token_context_menu.add_command(label="粘贴 (Ctrl＋V)", command=lambda: token_text.event_generate("<<Paste>>"))

    # 绑定右键点击事件
    def show_token_menu(event):
        token_context_menu.post(event.x_root, event.y_root)
        token_context_menu.bind("<FocusOut>", lambda e: token_context_menu.unpost())
        root.bind("<Button-1>", lambda e: token_context_menu.unpost(), add="+")

    token_text.bind("<Button-3>", show_token_menu)

    # 按下 Enter 键即可保存 token，并屏蔽换行事件
    def return_save_token(event):
        save_token()
        return "break"

    token_text.bind("<Return>", return_save_token) # 按下 Enter 键，保存 Access Token
    token_text.bind("<Shift-Return>", lambda e: "break") # 按下 Shift＋Enter 也不换行，直接屏蔽

    # 保存按钮
    def save_token():
        user_token = token_text.get("1.0", tk.END).strip()
        tip_info = set_access_token(user_token)
        # 重新启用下载按钮，并提示用户
        download_btn.config(state="normal")
        # 显示提示
        messagebox.showinfo("提示", tip_info)

        token_window.destroy()

    save_btn = ttk.Button(frame, text="保存", command=save_token)
    save_btn.pack(pady=5)

    # 帮助按钮
    def show_token_help():
        help_win = tk.Toplevel(token_window)
        help_win.title("获取 Access Token 方法")

        help_win.focus_force() # 自动获得焦点
        help_win.grab_set() # 阻止主窗口操作
        help_win.bind("<Escape>", lambda event: help_win.destroy()) # 绑定 Esc 键关闭窗口

        help_frame = ttk.Frame(help_win, padding=20)
        help_frame.pack(fill="both", expand=True)

        help_text = """\
国家中小学智慧教育平台需要登录后才可获取教材，因此要使用本程序下载教材，您需要在平台内登录账号（如没有需注册），然后获得登录凭据（[...]
获取方法如下：
1. 打开浏览器，访问国家中小学智慧教育平台（https://auth.smartedu.cn/uias/login）并登录账号。
2. 按下 F12 或 Ctrl+Shift+I，或右键——检查（审查元素）打开开发者工具，选择控制台（Console）。
3. 在控制台粘贴以下代码后回车（Enter）：
---------------------------------------------------------
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
---------------------------------------------------------
然后在控制台输出中即可看到 Access Token。将其复制后粘贴到本程序中。"""

        # 只读文本区，支持选择复制
        txt = tk.Text(help_frame, wrap="word", font=("微软雅黑", 9))
        txt.insert("1.0", help_text)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)

        # 同样可给帮助文本区绑定右键菜单
        help_menu = tk.Menu(txt, tearoff=0)
        help_menu.add_command(label="复制 (Ctrl＋C)", command=lambda: txt.event_generate("<<Copy>>"))
        def show_help_menu(event):
            help_menu.post(event.x_root, event.y_root)
            help_menu.bind("<FocusOut>", lambda e: help_menu.unpost())
            root.bind("<Button-1>", lambda e: help_menu.unpost(), add="+")

        txt.bind("<Button-3>", show_help_menu)

    help_btn = ttk.Button(frame, text="如何获取？", command=show_token_help)
    help_btn.pack(pady=5)

    # 让弹窗居中
    token_window.update_idletasks()
    w = token_window.winfo_width()
    h = token_window.winfo_height()
    ws = token_window.winfo_screenwidth()
    hs = token_window.winfo_screenheight()
    x = (ws // 2) - (w // 2)
    y = (hs // 2) - (h // 2)
    token_window.geometry(f"{w}x{h}+{x}+{y}")
    token_window.lift() # 置顶可见

class resource_helper: # 获取网站上资源的数据
    def parse_hierarchy(self, hierarchy): # 解析层级数据
        if not hierarchy: # 如果没有层级数据，返回空
            return None

        parsed = {}
        for h in hierarchy:
            for ch in h["children"]:
                parsed[ch["tag_id"]] = { "display_name": ch["tag_name"], "children": self.parse_hierarchy(ch["hierarchies"]) }
        return parsed

    def fetch_book_list(self): # 获取课本列表
        # 获取电子课本层级数据
        tags_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json")
        tags_data = tags_resp.json()
        parsed_hier = self.parse_hierarchy(tags_data["hierarchies"])

        # 获取电子课本 URL 列表
        list_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json")
        list_data: list[str] = list_resp.json()["urls"].split(",")

        # 获取电子课本列表
        for url in list_data:
            book_resp = session.get(url)
            book_data: list[dict] = book_resp.json()
            for book in book_data:
                if len(book["tag_paths"]) > 0: # 某些非课本资料的 tag_paths 属性为空数组
                    # 解析课本层级数据
                    tag_paths: list[str] = book["tag_paths"][0].split("/")[2:] # 电子课本 tag_paths 的前两项为“教材”、“电子教材”

                    # 如果课本层级数据不在层级数据中，跳过
                    temp_hier = parsed_hier[book["tag_paths"][0].split("/")[1]]
                    if not tag_paths[0] in temp_hier["children"]:
                        continue

                    # 分别解析课本层级
                    for p in tag_paths:
                        if temp_hier["children"] and temp_hier["children"].get(p):
                            temp_hier = temp_hier["children"].get(p)
                    if not temp_hier["children"]:
                        temp_hier["children"] = {}

                    book["display_name"] = book["title"] if "title" in book else book["name"] if "name" in book else f"(未知电子课本 {book['id']})"

                    temp_hier["children"][book["id"]] = book

        return parsed_hier

    def fetch_lesson_list(self): # 获取课件列表
        # 获取课件层级数据
        tags_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/national_lesson_tag.json")
        tags_data = tags_resp.json()
        parsed_hier = self.parse_hierarchy([{ "children": [{ "tag_id": "__internal_national_lesson", "hierarchies": tags_data["hierarchies"], "tag_name": "课件资源" }] }])

        # 获取课件 URL 列表
        list_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson/teachingmaterials/version/data_version.json")
        list_data: list[str] = list_resp.json()["urls"]

        # 获取课件列表
        for url in list_data:
            lesson_resp = session.get(url)
            lesson_data: list[dict] = lesson_resp.json()
            for lesson in lesson_data:
                if len(lesson["tag_list"]) > 0:
                    # 解析课件层级数据
                    tag_paths: list[str] = [tag["tag_id"] for tag in sorted(lesson["tag_list"], key=lambda tag: tag["order_num"])]

                    # 分别解析课件层级
                    temp_hier = parsed_hier["__internal_national_lesson"]
                    for p in tag_paths:
                        if temp_hier["children"] and temp_hier["children"].get(p):
                            temp_hier = temp_hier["children"].get(p)
                    if not temp_hier["children"]:
                        temp_hier["children"] = {}

                    lesson["display_name"] = lesson["title"] if "title" in lesson else lesson["name"] if "name" in lesson else f"(未知课件 {lesson['id']})"

                    temp_hier["children"][lesson["id"]] = lesson

        return parsed_hier

    def fetch_resource_list(self): # 获取资源列表
        book_hier = self.fetch_book_list()
        # lesson_hier = self.fetch_lesson_list() # 目前此函数代码存在问题
        return { **book_hier }

def thread_it(func, args: tuple = ()) -> None: # args 为元组，且默认值是空元组
    # 打包函数到线程
    t = threading.Thread(target=func, args=args)
    # t.daemon = True
    t.start()

# 初始化请求
session = requests.Session()
# 初始化下载状态
download_states = []
# 设置请求头部，包含认证信息
access_token = None
headers = { "X-ND-AUTH": 'MAC id="0",nonce="0",mac="0"' } # “MAC id”等同于“access_token”，“nonce”和“mac”不可缺省但无需有效
session.proxies = { "http": None, "https": None } # 全局忽略代理

def load_access_token() -> None: # 读取本地存储的 Access Token
    global access_token
    try:
        if os_name == "Windows": # 在 Windows 上，从注册表读取
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\tchMaterial-parser", 0, winreg.KEY_READ) as key:
                token, _ = winreg.QueryValueEx(key, "AccessToken")
                if token:
                    access_token = token
                    # 更新请求头
                    headers["X-ND-AUTH"] = f'MAC id="{access_token}",nonce="0",mac="0"'
        elif os_name == "Linux": # 在 Linux 上，从 ~/.config/tchMaterial-parser/data.json 文件读取
            # 构建文件路径
            target_file = os.path.join(
                os.path.expanduser("~"), # 获取当前用户主目录
                ".config",
                "tchMaterial-parser",
                "data.json"
            )
            if not os.path.exists(target_file): # 文件不存在则不做处理
                return

            # 读取 JSON 文件
            with open(target_file, "r") as f:
                data = json.load(f)
            # 提取 access_token 字段
            access_token = data["access_token"]

    except Exception:
        pass # 读取失败则不做处理

def set_access_token(token: str) -> str: # 设置并更新 Access Token
    global access_token
    access_token = token
    headers["X-ND-AUTH"] = f'MAC id="{access_token}",nonce="0",mac="0"'

    try:
        if os_name == "Windows": # 在 Windows 上，将 Access Token 写入注册表
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\tchMaterial-parser") as key:
                winreg.SetValueEx(key, "AccessToken", 0, winreg.REG_SZ, token)
            return "Access Token 已保存！\n已写入注册表：HKEY_CURRENT_USER\\Software\\tchMaterial-parser\\AccessToken"
        elif os_name == "Linux": # 在 Linux 上，将 Access Token 保存至 ~/.config/tchMaterial-parser/data.json 文件中
            # 构建目标目录和文件路径
            target_dir = os.path.join(
                os.path.expanduser("~"),
                ".config",
                "tchMaterial-parser"
            )
            target_file = os.path.join(target_dir, "data.json")
            # 创建目录（如果不存在）
            os.makedirs(target_dir, exist_ok=True)

            # 构建要保存的数据字典
            data = { "access_token": token }
            # 写入 JSON 文件
            with open(target_file, "w") as f:
                json.dump(data, f, indent=4)

            return "Access Token 已保存！\n已写入文件：~/.config/tchMaterial-parser/data.json"
        else:
            return "Access Token 已保存！"
    except Exception:
        return "Access Token 已保存！"

# 立即尝试加载已存的 Access Token（如果有的话）
load_access_token()

# 获取资源列表
try:
    resource_list = resource_helper().fetch_resource_list()
except Exception:
    resource_list = {}
    messagebox.showwarning("警告", "获取资源列表失败，请手动填写资源链接，或重新打开本程序") # 弹出警告窗口

# GUI
root = tk.Tk()

# 高 DPI 适配
if os_name == "Windows":
    scale: float = round(win32print.GetDeviceCaps(win32gui.GetDC(0), win32con.DESKTOPHORZRES) / win32api.GetSystemMetrics(0), 2) # 获取当前的缩放因子

    # 调用 API 设置成由应用程序缩放
    try: # Windows 8.1 或更新
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: # Windows 8 或更老
        ctypes.windll.user32.SetProcessDPIAware()
else: # 在非 Windows 操作系统上，通过 Tkinter 估算缩放因子
    try:
        scale: float = round(root.winfo_fpixels("1i") / 96.0, 2)
    except Exception:
        scale = 1.0

root.tk.call("tk", "scaling", scale / 0.75) # 设置缩放因子

root.title("国家中小学智慧教育平台 资源下载工具 v3.1") # 设置窗口标题
# root.geometry("900x600") # 设置窗口大小

def set_icon() -> None: # 设置窗口图标
    icon = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAN8AAADfCAYAAAEB/ja6AAAACXBIWXMAAAsTAAALEwEAmpwYAAAE7mlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0wTXBDZWhpSHpyZV[...]")
    with open(tempfile.gettempdir() + "/icon.png", "wb") as f:
        f.write(icon)

    icon = tk.PhotoImage(file=tempfile.gettempdir() + "/icon.png")
    root.iconphoto(True, icon)
    root._icon_ref = icon # 为防止图片被垃圾回收，保存引用

set_icon() # 设置窗口图标

def on_closing() -> None: # 处理窗口关闭事件
    if not all(state["finished"] for state in download_states): # 当正在下载时，询问用户
        if not messagebox.askokcancel("提示", "下载任务未完成，是否退出？"):
            return

    current_process = psutil.Process(os.getpid()) # 获取自身的进程 ID
    child_processes = current_process.children(recursive=True) # 获取自身的所有子进程

    for child in child_processes: # 结束所有子进程
        try:
            child.terminate() # 结束进程
        except Exception: # 进程可能已经结束
            pass

    # 结束自身进程
    sys.exit(0)

root.protocol("WM_DELETE_WINDOW", on_closing) # 注册窗口关闭事件的处理函数

# 创建一个容器框架
container_frame = ttk.Frame(root)
container_frame.pack(anchor="center", expand="yes", padx=int(40 * scale), pady=int(20 * scale)) # 在容器的中心位置放置，允许组件在容器中扩展，水平外边距 40，垂直外[...]

title_label = ttk.Label(container_frame, text="国家中小学智慧教育平台 资源下载工具", font=("微软雅黑", 16, "bold")) # 添加标题标签
title_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

description = """\
📌 请在下面的文本框中输入一个或多个资源页面的网址（每个网址一行）。
🔗 资源页面网址示例：
    https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=...
📝 您也可以直接在下方的选项卡中选择教材。
📥 点击 “下载” 按钮后，程序会解析并下载资源。
⚠️ 注：为了更可靠地下载，建议点击 “设置 Token” 按钮，参照里面的说明完成设置。"""
description_label = ttk.Label(container_frame, text=description, justify="left", font=("微软雅黑", 9)) # 添加描述标签
description_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

url_text = tk.Text(container_frame, width=70, height=12, font=("微软雅黑", 9)) # 添加 URL 输入框，长度和宽度不使用缩放！！！
url_text.pack(padx=int(15 * scale), pady=int(15 * scale)) # 设置水平外边距、垂直外边距（跟随缩放）

# 创建右键菜单
context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="剪切 (Ctrl＋X)", command=lambda: url_text.event_generate("<<Cut>>"))
context_menu.add_command(label="复制 (Ctrl＋C)", command=lambda: url_text.event_generate("<<Copy>>"))
context_menu.add_command(label="粘贴 (Ctrl＋V)", command=lambda: url_text.event_generate("<<Paste>>"))

def show_context_menu(event):
    context_menu.post(event.x_root, event.y_root)
    # 绑定失焦事件，失焦时自动关闭菜单
    context_menu.bind("<FocusOut>", lambda e: context_menu.unpost())
    # 绑定左键点击事件，点击其他地方也关闭菜单
    root.bind("<Button-1>", lambda e: context_menu.unpost(), add="+")

# 绑定右键菜单到文本框（3 代表鼠标的右键按钮）
url_text.bind("<Button-3>", show_context_menu)

options = [["---"] + [resource_list[k]["display_name"] for k in resource_list], ["---"], ["---"], ["---"], ["---"], ["---"], ["---"], ["---"]] # 构建选择项

variables = [tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root)]

# 处理用户选择事件
event_flag = False # 防止事件循环调用
def selection_handler(index: int, *args) -> None:
    global event_flag

    if event_flag:
        event_flag = False # 检测到循环调用，重置标志位并返回
        return

    if variables[index].get() == "---": # 重置后面的选择项
        for i in range(index + 1, len(drops)):
            drops[i]["menu"].delete(0, "end")
            drops[i]["menu"].add_command(label="---", command=tk._setit(variables[i], "---"))

            event_flag = True
            variables[i].set("---")
            # drops[i]["menu"].configure(state="disabled")
        return

    if index < len(drops) - 1: # 更新选择项
        current_drop = drops[index + 1]

        current_hier = resource_list
        current_id = [element for element in current_hier if current_hier[element]["display_name"] == variables[0].get()][0]
        current_hier = current_hier[current_id]["children"]

        end_flag = False # 是否到达最终目标
        for i in range(index):
            try:
                current_id = [element for element in current_hier if current_hier[element]["display_name"] == variables[i + 1].get()][0]
                current_hier = current_hier[current_id]["children"]
            except KeyError: # 无法继续向下选择，说明已经到达最终目标
                end_flag = True
                break

        if not current_hier or end_flag:
            current_options = ["---"]
        else:
            current_options = ["---"] + [current_hier[k]["display_name"] for k in current_hier.keys()]

        current_drop["menu"].delete(0, "end")
        for choice in current_options:
            current_drop["menu"].add_command(label=choice, command=tk._setit(variables[index + 1], choice))

        if end_flag: # 到达目标，显示 URL
            current_id = [element for element in current_hier if current_hier[element]["display_name"] == variables[index].get()][0]
            resource_type = current_hier[current_id]["resource_type_code"] or "assets_document"
            if url_text.get("1.0", tk.END) == "\n": # URL 输入框为空的时候，插入的内容前面不加换行
                url_text.insert("end", f"https://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={current_id}&catalogType=tchMaterial&subCatalog=tchMaterial")
            else:
                url_text.insert("end", f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={current_id}&catalogType=tchMaterial&subCatalog=tchMaterial")
            drops[-1]["menu"].delete(0, "end")
            drops[-1]["menu"].add_command(label="---", command=tk._setit(variables[-1], "---"))
            variables[-1].set("---")

        for i in range(index + 2, len(drops)): # 重置后面的选择项
            drops[i]["menu"].delete(0, "end")
            drops[i]["menu"].add_command(label="---", command=tk._setit(variables[i], "---"))
            # drops[i]["menu"].configure(state="disabled")

        for i in range(index + 1, len(drops)):
            event_flag = True
            variables[i].set("---")

    else: # 最后一项，必为最终目标，显示 URL
        if variables[-1].get() == "---":
            return

        current_hier = resource_list
        current_id = [element for element in current_hier if current_hier[element]["display_name"] == variables[0].get()][0]
        current_hier = current_hier[current_id]["children"]
        for i in range(index - 1):
            current_id = [element for element in current_hier if current_hier[element]["display_name"] == variables[i + 1].get()][0]
            current_hier = current_hier[current_id]["children"]

        current_id = [element for element in current_hier if current_hier[element]["display_name"] == variables[index].get()][0]
        resource_type = current_hier[current_id]["resource_type_code"] or "assets_document"
        if url_text.get("1.0", tk.END) == "\n": # URL 输入框为空的时候，插入的内容前面不加换行
            url_text.insert("end", f"https://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={current_id}&catalogType=tchMaterial&subCatalog=tchMaterial")
        else:
            url_text.insert("end", f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={current_id}&catalogType=tchMaterial&subCatalog=tchMaterial")

for index in range(8): # 绑定事件
    variables[index].trace_add("write", partial(selection_handler, index))

# 添加 Container
dropdown_frame = ttk.Frame(root)
dropdown_frame.pack(padx=int(10 * scale), pady=int(10 * scale))

drops = []

# 添加菜单栏
for i in range(8):
    drop = ttk.OptionMenu(dropdown_frame, variables[i], *options[i])
    drop.config(state="active") # 配置下拉菜单为始终活跃状态，保证下拉菜单一直有形状
    drop.bind("<Leave>", lambda e: "break") # 绑定鼠标移出事件，当鼠标移出下拉菜单时，执行 lambda 函数，“break”表示中止事件传递
    drop.grid(row=i // 4, column=i % 4, padx=int(15 * scale), pady=int(15 * scale)) # 设置位置，2 行 4 列（跟随缩放）
    variables[i].set("---")
    drops.append(drop)

# 按钮：设置 Token
token_btn = ttk.Button(container_frame, text="设置 Token", command=show_access_token_window)
token_btn.pack(side="left", padx=int(5 * scale), pady=int(5 * scale), ipady=int(5 * scale))

# 按钮：下载
download_btn = ttk.Button(container_frame, text="下载", command=download)
download_btn.pack(side="right", padx=int(5 * scale), pady=int(5 * scale), ipady=int(5 * scale))

# 按钮：解析并复制
copy_btn = ttk.Button(container_frame, text="解析并复制", command=parse_and_copy)
copy_btn.pack(side="right", padx=int(5 * scale), pady=int(5 * scale), ipady=int(5 * scale))

# 下载进度条
download_progress_bar = ttk.Progressbar(container_frame, length=(125 * scale), mode="determinate") # 添加下载进度条
download_progress_bar.pack(side="bottom", padx=int(40 * scale), pady=int(10 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置进度条高度（[...]

# 下载进度标签
progress_label = ttk.Label(container_frame, text="等待下载", anchor="center") # 初始时文本为空，居中
progress_label.pack(side="bottom", padx=int(5 * scale), pady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置标签高度（跟随缩放）

root.mainloop() # 开始主循环
