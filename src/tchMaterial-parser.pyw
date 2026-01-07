# -*- coding: utf-8 -*-
# 国家中小学智慧教育平台 资源下载工具 v3.3.0
# 项目地址：https://github.com/happycola233/tchMaterial-parser
# 作者：肥宅水水呀（https://space.bilibili.com/324042405）以及其他为本工具作出贡献的用户

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import os, sys, platform
from functools import partial
import threading, psutil, tempfile, pyperclip
import base64, json, re, requests
from pypdf import PdfReader, PdfWriter
import traceback

os_name = platform.system() # 获取操作系统类型

try: # 在 Windows 操作系统下，导入 Windows 相关库，这样的写法是为了避免 Pylance “reportPossiblyUnboundVariable”
    import win32print, win32gui, win32con, win32api, ctypes, winreg
except Exception:
    win32print = win32gui = win32con = win32api = ctypes = winreg = None


def parse(url: str) -> tuple[str, str, str, list] | tuple[None, None, None, None]: 
    try:
        content_id: str | None = None
        content_type: str | None = None
        resource_url: str | None = None

        # 简单提取 URL 中的 contentId 与 contentType（为了减少导入的库，使用了不严谨的方法）
        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentId":
                content_id = q.split("=")[1]
                break
        if not content_id:
            return None, None, None, None

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

        if re.search(r"^https?://([^/]+)/syncClassroom/basicWork/detail", url): # 对基础性作业的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
        else: # 对课本的解析
            if content_type == "thematic_course": # 对专题课程（含电子课本、视频等）的解析
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
            else: # 对普通电子课本的解析
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{content_id}.json")
        
        data = response.json()
        title = data.get("title", "未知教材")
        
        # 3. 获取章节目录 (核心修改部分)
        chapters = data.get("chapters", [])
        
        # 如果主接口没目录，尝试通过 ebook_mapping + tree 接口组合获取
        if not chapters:
            mapping_url = None
            for item in data.get("ti_items", []):
                if item.get("ti_file_flag") == "ebook_mapping":
                    # 形如 https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/*.pkg/ebook_mapping_*.txt
                    mapping_url = item["ti_storages"][0]
                    break
            
            if mapping_url:
                try:
                    # A. 下载 mapping 文件获取页码和 ebook_id
                    # 直接请求原始 mapping 地址（不带请求头）
                    map_data = None
                    map_resp = session.get(mapping_url)
                    if map_resp.status_code == 200:
                        map_resp.encoding = 'utf-8'
                        try:
                            map_data = map_resp.json()
                        except Exception:
                            # 响应不是 JSON（可能是 XML/错误页）
                            map_data = None
                    # 无法解析时直接报错
                    if not map_data:
                        raise RuntimeError("mapping 文件无法访问或不是有效的 JSON")

                    ebook_id = map_data.get("ebook_id")
                    
                    # 构建 nodeId 到 pageNumber 的映射字典
                    # 格式: { "node_id_1": 5, "node_id_2": 10 }
                    page_map = {}
                    if "mappings" in map_data:
                        for m in map_data["mappings"]:
                            page_map[m["node_id"]] = m.get("page_number", 1)

                    # B. 如果有 ebook_id，去下载完整的目录树 (Tree API)
                    if ebook_id:
                        tree_url = f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/{ebook_id}.json"
                        tree_resp = session.get(tree_url, headers=headers if access_token else None)
                        
                        if tree_resp.status_code == 200:
                            tree_data = tree_resp.json()
                            
                            # 递归函数：合并 Tree的标题 和 Mapping的页码
                            def process_tree_nodes(nodes):
                                result = []
                                for node in nodes:
                                    # 从 page_map 中找页码，找不到为none
                                    page_num = page_map.get(node["id"], None)
                                    
                                    chapter_item = {
                                        "title": node["title"],
                                        "page_index": page_num 
                                    }
                                    
                                    # 如果有子节点，递归处理
                                    if node.get("child_nodes"):
                                        chapter_item["children"] = process_tree_nodes(node["child_nodes"])
                                    
                                    result.append(chapter_item)
                                return result

                            # 开始解析
                            if isinstance(tree_data, list):
                                chapters = process_tree_nodes(tree_data)
                            elif isinstance(tree_data, dict) and "child_nodes" in tree_data:
                                chapters = process_tree_nodes(tree_data["child_nodes"])
                                
                            # print(f"成功获取完整目录: {len(chapters)} 个顶级章节")

                    # C. 兜底方案：如果获取 Tree 失败，仅使用 mapping 生成纯页码索引
                    if not chapters and "mappings" in map_data:
                        temp_chapters = []
                        mappings = map_data["mappings"]
                        mappings.sort(key=lambda x: x["page_number"])
                        for i, m in enumerate(mappings):
                            temp_chapters.append({
                                "title": f"第 {i+1} 节 (P{m['page_number']})",
                                "page_index": m['page_number']
                            })
                        chapters = temp_chapters
                        
                except Exception as e:
                    print(f"目录解析异常: {e}")
                    traceback.print_exc()

        # 4. 获取 PDF 下载链接 (保持不变)
        
        for item in list(data["ti_items"]):
            if item["lc_ti_format"] == "pdf": # 寻找存有 PDF 链接列表的项
                resource_url = item["ti_storages"][0] # 获取并构造 PDF 的 URL
                if resource_url is None:
                    continue
                if not access_token: # 未登录时，通过一个不可靠的方法构造可直接下载的 URL
                    resource_url = re.sub(r"^https?://(?:.+).ykt.cbern.com.cn/(.+)/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}).pkg/(.+)\.pdf$", r"https://c1.ykt.cbern.com.cn/\1/\2.pkg/\3.pdf", resource_url)
                break

        if not resource_url:
            if content_type == "thematic_course": # 专题课程
                resources_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/thematic_course/{content_id}/resources/list.json")
                resources_data = resources_resp.json()
                for resource in list(resources_data):
                    if resource["resource_type_code"] == "assets_document":
                        for item in list(resource["ti_items"]):
                            if item["lc_ti_format"] == "pdf":
                                resource_url = item["ti_storages"][0]
                                if resource_url is None:
                                    continue
                                if not access_token:
                                    resource_url = re.sub(r"^https?://(?:.+).ykt.cbern.com.cn/(.+)/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}).pkg/(.+)\.pdf$", r"https://c1.ykt.cbern.com.cn/\1/\2.pkg/\3.pdf", resource_url)
                                break
                if not resource_url:
                    return None, None, None, None
            else:
                return None, None, None, None

        return resource_url, content_id, title, chapters
    except Exception: 
        return None, None, None, None
    
def add_bookmarks(pdf_path: str, chapters: list) -> None:
    """给 PDF 添加书签"""
    try:
        if not chapters:
            return
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)

        # 递归添加书签的内部函数
        def _add_chapter(chapter_list, parent=None):
            for chapter in chapter_list:
                title = chapter.get("title", "未知章节")
                # 1. 获取原始值
                p_index = chapter.get("page_index")
                # print(f"处理章节“{title}”，页码索引：{p_index}")
                # 2. 如果值为 None (JSON里的null) 或者不存在，跳过这个书签（因为未使用）
                if p_index is None:
                    sys.stderr.write(f"[!!]跳过章节“{title}”的书签，原因：未指定页码\n")
                    continue
                # 3. 尝试将其转为整数并减 1 (pypdf 页码从 0 开始)
                try:
                    page_num = int(p_index) - 1
                except (ValueError, TypeError):
                    page_num = 0 # 如果转换失败，默认指向第1页
                # page_num = chapter.get("page_index", 1) - 1
                if page_num < 0: page_num = 0
                
                if page_num >= len(writer.pages):
                    page_num = len(writer.pages) - 1

                # 添加书签
                # parent 是父级书签对象，用于处理多级目录
                bookmark = writer.add_outline_item(title, page_num, parent=parent)

                # 如果有子章节（children），递归添加
                if "children" in chapter and chapter["children"]:
                    _add_chapter(chapter["children"], parent=bookmark)
        
        # 开始处理章节数据
        _add_chapter(chapters)

        # 保存修改后的文件
        with open(pdf_path, "wb") as f:
            writer.write(f)
            
    except Exception as e:
        sys.stderr.write(f"添加书签失败: {e}\n")
        traceback.print_exc()

def ui_call(func, *args, **kwargs) -> None:
    """在主线程执行 Tk UI 更新"""
    root.after(0, lambda: func(*args, **kwargs))

def download_file(url: str, save_path: str, chapters: list | None = None) -> None: # 下载文件
    global download_states
    current_state = { "download_url": url, "save_path": save_path, "downloaded_size": 0, "total_size": 0, "finished": False, "failed_reason": None }
    download_states.append(current_state)

    try:
        response = session.get(url, headers=headers, stream=True)

        if response.status_code >= 400: # 服务器返回表示错误的 HTTP 状态码
            current_state["finished"] = True
            current_state["failed_reason"] = f"服务器返回 HTTP 状态码 {response.status_code}" + "，Access Token 可能已过期或无效，请重新设置" if response.status_code == 401 or response.status_code == 403 else ""
        else:
            current_state["total_size"] = int(response.headers.get("Content-Length", 0))

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
                        ui_call(download_progress_bar.config, value=download_progress) # 更新进度条
                        ui_call(progress_label.config, text=f"{format_bytes(all_downloaded_size)}/{format_bytes(all_total_size)} ({download_progress:.2f}%) 已下载 {downloaded_number}/{total_number}") # 更新标签以显示当前下载进度
            if chapters:
                ui_call(progress_label.config, text="添加书签")
                add_bookmarks(save_path, chapters)
            current_state["downloaded_size"] = current_state["total_size"]
            current_state["finished"] = True

    except Exception as e:
        current_state["downloaded_size"], current_state["total_size"] = 0, 0
        current_state["finished"] = True
        current_state["failed_reason"] = str(e)

    if all(state["finished"] for state in download_states): # 所有文件下载完成
        ui_call(download_progress_bar.config, value=0) # 重置进度条
        ui_call(progress_label.config, text="等待下载") # 清空进度标签
        ui_call(download_btn.config, state="normal") # 设置下载按钮为启用状态

        failed_states = [state for state in download_states if state["failed_reason"]]
        if len(failed_states) > 0: # 存在下载失败的文件
            ui_call(messagebox.showwarning, "下载完成", f"文件已下载到：{os.path.dirname(save_path)}\n以下文件下载失败：\n{"\n".join(f"{state["download_url"]}，原因：{state["failed_reason"]}" for state in failed_states)}")
        else:
            ui_call(messagebox.showinfo, "下载完成", f"文件已下载到：{os.path.dirname(save_path)}")

def format_bytes(size: float) -> str: # 将数据单位进行格式化，返回以 KB、MB、GB、TB、PB 为单位的数据大小
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
        messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_links))

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
        if not dir_path: # 用户取消/关闭对话框
            download_btn.config(state="normal") # 恢复下载按钮为启用状态
            return
        dir_path = os.path.normpath(dir_path)
    else:
        dir_path = None

    for url in urls:
        resource_url, content_id, title ,chapters = parse(url)
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
                download_btn.config(state="normal") # 恢复下载按钮为启用状态
                return
            save_path = os.path.normpath(save_path)

        thread_it(download_file, (resource_url, save_path, chapters)) # 开始下载（多线程，防止窗口卡死）

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

    # 设置一个 Frame 用于留白，使布局更美观
    frame = ttk.Frame(token_window, padding=20)
    frame.pack(fill="both", expand=True)

    # 提示文本
    label = ttk.Label(frame, text="请粘贴从浏览器获取的 Access Token：", font=(ui_font_family, 10))
    label.pack(pady=5)

    # 创建多行 Text
    token_text = tk.Text(frame, width=50, height=4, wrap="word", font=(ui_font_family, 9))
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
    if os_name == "Darwin":
        token_text.bind("<Control-Button-1>", show_token_menu)
        token_text.bind("<Button-2>", show_token_menu)

    # 按下 Enter 键，保存 Access Token，并屏蔽换行事件
    def return_save_token(event):
        save_token()
        return "break"

    token_text.bind("<Return>", return_save_token)
    token_text.bind("<Shift-Return>", lambda e: "break") # 按下 Shift＋Enter 也不换行，直接屏蔽

    # 保存按钮
    def save_token():
        user_token = token_text.get("1.0", tk.END).strip()
        tip_info = set_access_token(user_token)
        download_btn.config(state="normal") # 重新启用下载按钮
        messagebox.showinfo("保存成功", tip_info)

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
国家中小学智慧教育平台需要登录后才可获取教材，因此要使用本程序下载教材，您需要在平台内登录账号（如没有需注册），然后获得登录凭据（Access Token）。本程序仅保存该凭据至本地。

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
        txt = tk.Text(help_frame, wrap="word", font=(ui_font_family, 9))
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
        if os_name == "Darwin":
            txt.bind("<Control-Button-1>", show_help_menu)
            txt.bind("<Button-2>", show_help_menu)

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
    def parse_hierarchy(self, hierarchy) -> dict: # 解析层级数据
        if not hierarchy: # 如果没有层级数据，返回空字典
            return {}

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

                    book["display_name"] = book["title"] if "title" in book else book["name"] if "name" in book else f"(未知电子课本 {book["id"]})"

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

                    lesson["display_name"] = lesson["title"] if "title" in lesson else lesson["name"] if "name" in lesson else f"(未知课件 {lesson["id"]})"

                    temp_hier["children"][lesson["id"]] = lesson

        return parsed_hier

    def fetch_resource_list(self): # 获取资源列表
        book_hier = self.fetch_book_list()
        # lesson_hier = self.fetch_lesson_list() # 目前此函数代码存在问题
        return { **book_hier }

def thread_it(func, args: tuple = ()) -> None: # 打包函数到线程
    t = threading.Thread(target=func, args=args)
    # t.daemon = True
    t.start()

session = requests.Session() # 初始化请求
download_states = [] # 初始化下载状态
access_token = None
headers = { "X-ND-AUTH": 'MAC id="0",nonce="0",mac="0"' } # 设置请求头部，包含认证信息，其中 “MAC id” 即为 Access Token，“nonce” 和 “mac” 不可缺省但可为任意非空值
session.proxies = {} # 全局忽略代理

def load_access_token() -> None: # 读取本地存储的 Access Token
    global access_token
    try:
        if os_name == "Windows": # 在 Windows 上，从注册表读取
            if winreg is None:
                return
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
        elif os_name == "Darwin": # 在 macOS 上，从 ~/Library/Application Support/tchMaterial-parser/data.json 文件读取
            target_file = os.path.join(
                os.path.expanduser("~"),
                "Library",
                "Application Support",
                "tchMaterial-parser",
                "data.json"
            )
            if not os.path.exists(target_file):
                return

            with open(target_file, "r") as f:
                data = json.load(f)
            access_token = data["access_token"]

    except Exception:
        pass # 读取失败则不做处理

def set_access_token(token: str) -> str: # 设置并更新 Access Token
    global access_token
    access_token = token
    headers["X-ND-AUTH"] = f'MAC id="{access_token}",nonce="0",mac="0"'

    try:
        if os_name == "Windows": # 在 Windows 上，将 Access Token 写入注册表
            if winreg is None:
                return "Access Token 已保存！"
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
        elif os_name == "Darwin": # 在 macOS 上，将 Access Token 保存至 ~/Library/Application Support/tchMaterial-parser/data.json 文件中
            target_dir = os.path.join(
                os.path.expanduser("~"),
                "Library",
                "Application Support",
                "tchMaterial-parser"
            )
            target_file = os.path.join(target_dir, "data.json")
            os.makedirs(target_dir, exist_ok=True)

            data = { "access_token": token }
            with open(target_file, "w") as f:
                json.dump(data, f, indent=4)

            return "Access Token 已保存！\n已写入文件：~/Library/Application Support/tchMaterial-parser/data.json"
        else:
            return "Access Token 已保存！"
    except Exception:
        return "Access Token 已保存！"

# 尝试加载已保存的 Access Token
load_access_token()

# 获取资源列表
try:
    resource_list = resource_helper().fetch_resource_list()
except Exception:
    resource_list = {}
    messagebox.showwarning("警告", "获取资源列表失败，请手动填写资源链接，或重新打开本程序") # 弹出警告窗口

# GUI
root = tk.Tk()

def pick_ui_font_family() -> str:
    try:
        available = set(tkfont.families(root))
    except Exception:
        return "TkDefaultFont"

    for name in ("微软雅黑", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "Arial Unicode MS"):
        if name in available:
            return name

    try:
        return tkfont.nametofont("TkDefaultFont").actual("family")
    except Exception:
        return "TkDefaultFont"

ui_font_family = pick_ui_font_family()

# 高 DPI 适配
if os_name == "Windows" and win32print is not None and win32gui is not None and win32con is not None and win32api is not None and ctypes is not None:
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

root.title("国家中小学智慧教育平台 资源下载工具 v3.2") # 设置窗口标题
# root.geometry("900x600") # 设置窗口大小

def set_icon() -> None: # 设置窗口图标
    icon = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAN8AAADfCAYAAAEB/ja6AAAACXBIWXMAAAsTAAALEwEAmpwYAAAE7mlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQiPz4gPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iQWRvYmUgWE1QIENvcmUgOS4xLWMwMDIgNzkuYTZhNjM5NiwgMjAyNC8wMy8xMi0wNzo0ODoyMyAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iIHhtbG5zOnBob3Rvc2hvcD0iaHR0cDovL25zLmFkb2JlLmNvbS9waG90b3Nob3AvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0RXZ0PSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VFdmVudCMiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIDI1LjkgKFdpbmRvd3MpIiB4bXA6Q3JlYXRlRGF0ZT0iMjAyNC0wOC0xOVQxNDozNzo1MyswODowMCIgeG1wOk1vZGlmeURhdGU9IjIwMjQtMDgtMTlUMTQ6Mzg6MjQrMDg6MDAiIHhtcDpNZXRhZGF0YURhdGU9IjIwMjQtMDgtMTlUMTQ6Mzg6MjQrMDg6MDAiIGRjOmZvcm1hdD0iaW1hZ2UvcG5nIiBwaG90b3Nob3A6Q29sb3JNb2RlPSIzIiB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOmRjMWFiMTUxLTkzYzUtMGI0MS1hYWNiLTYxYzFhMmIyNTczOSIgeG1wTU06RG9jdW1lbnRJRD0i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")
    icon_path = os.path.join(tempfile.gettempdir(), "icon.png")
    with open(icon_path, "wb") as f:
        f.write(icon)

    icon = tk.PhotoImage(file=icon_path)
    root.iconphoto(True, icon)
    setattr(root, "_icon_ref", icon) # 为防止图片被垃圾回收，保存引用

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
container_frame.pack(anchor="center", expand=True, padx=int(40 * scale), pady=int(20 * scale)) # 在容器的中心位置放置，允许组件在容器中扩展，水平外边距 40，垂直外边距 40

title_label = ttk.Label(container_frame, text="国家中小学智慧教育平台 资源下载工具", font=(ui_font_family, 16, "bold")) # 添加标题标签
title_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

description = """\
📌 请在下面的文本框中输入一个或多个资源页面的网址（每个网址一行）。
🔗 资源页面网址示例：
      https://basic.smartedu.cn/tchMaterial/detail?
      contentType=assets_document&contentId=...
📝 您也可以直接在下方的选项卡中选择教材。
📥 点击 “下载” 按钮后，程序会解析并下载资源。
❗️ 注：为了更可靠地下载，建议点击 “设置 Token” 按钮，参照里面的说明完成设置。"""
description_label = ttk.Label(container_frame, text=description, justify="left", font=(ui_font_family, 9)) # 添加描述标签
description_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

url_text = tk.Text(container_frame, width=70, height=12, font=(ui_font_family, 9)) # 添加 URL 输入框，长度和宽度不使用缩放！！！
url_text.pack(padx=int(15 * scale), pady=int(15 * scale)) # 设置水平外边距、垂直外边距（跟随缩放）

# 创建右键菜单
context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="剪切 (Ctrl＋X)", command=lambda: url_text.event_generate("<<Cut>>"))
context_menu.add_command(label="复制 (Ctrl＋C)", command=lambda: url_text.event_generate("<<Copy>>"))
context_menu.add_command(label="粘贴 (Ctrl＋V)", command=lambda: url_text.event_generate("<<Paste>>"))

def show_context_menu(event):
    context_menu.post(event.x_root, event.y_root)
    context_menu.bind("<FocusOut>", lambda e: context_menu.unpost()) # 绑定失焦事件，失焦时自动关闭菜单
    root.bind("<Button-1>", lambda e: context_menu.unpost(), add="+") # 绑定左键点击事件，点击其他地方也关闭菜单

# 绑定右键菜单到文本框（3 代表鼠标的右键按钮）
url_text.bind("<Button-3>", show_context_menu)
if os_name == "Darwin":
    url_text.bind("<Control-Button-1>", show_context_menu)
    url_text.bind("<Button-2>", show_context_menu)

options = [[resource_list[k]["display_name"] for k in resource_list], [], [], [], [], [], [], []] # 构建选择项

variables = [tk.StringVar(root, "资源类型"), tk.StringVar(root, "分类 1"), tk.StringVar(root, "分类 2"), tk.StringVar(root, "分类 3"), tk.StringVar(root, "分类 4"), tk.StringVar(root, "分类 5"), tk.StringVar(root, "分类 6"), tk.StringVar(root, "分类 7")]

# 处理用户选择事件
event_flag = False # 防止事件循环调用
def selection_handler(index: int, *args) -> None:
    global event_flag
    if event_flag: # 检测到循环调用
        return
    event_flag = True

    current_hier = resource_list
    end_flag = False # 是否到达最终目标
    for i in range(index + 1): # 获取当前层级
        try:
            current_id = next(k for k, v in current_hier.items() if v["display_name"] == variables[i].get())
            current_hier = current_hier[current_id]["children"]
        except (StopIteration, KeyError): # 无法继续向下选择，说明已经到达最终目标
            end_flag = True
            break

    if index < len(drops) - 1 and not end_flag: # 更新选择项
        current_drop = drops[index + 1]
        variables[index + 1].set(f"分类 {index + 1}")
        current_drop["menu"].delete(0, "end") # 删除当前菜单中的所有选项

        current_options = [current_hier[k]["display_name"] for k in current_hier.keys()]
        for choice in current_options:
            current_drop["menu"].add_command(label=choice, command=partial(lambda index, choice: variables[index + 1].set(choice), index, choice)) # 添加当前菜单的选项

        current_drop.configure(state="active") # 恢复当前菜单

        for i in range(index + 2, len(drops)): # 重置后面的选择项
            drops[i].configure(state="disabled") # 禁用后面的菜单
            variables[i].set(f"分类 {i}")
            drops[i]["menu"].delete(0, "end")

    if end_flag: # 到达目标，显示 URL
        current_id = next(k for k, v in current_hier.items() if v["display_name"] == variables[index].get())
        resource_type = current_hier[current_id]["resource_type_code"] or "assets_document"
        if url_text.get("1.0", tk.END) == "\n": # URL 输入框为空的时候，插入的内容前面不加换行
            url_text.insert("end", f"https://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={current_id}&catalogType=tchMaterial&subCatalog=tchMaterial")
        else:
            url_text.insert("end", f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={current_id}&catalogType=tchMaterial&subCatalog=tchMaterial")

        for i in range(index + 1, len(drops)): # 重置后面的选择项
            drops[i].configure(state="disabled") # 禁用后面的菜单
            variables[i].set(f"分类 {i}")
            drops[i]["menu"].delete(0, "end")

    event_flag = False

for index in range(8): # 绑定事件
    variables[index].trace_add("write", partial(selection_handler, index))

# 添加 Container
dropdown_frame = ttk.Frame(root)
dropdown_frame.pack(padx=int(10 * scale), pady=int(10 * scale))

drops = []

# 添加菜单栏
for i in range(8):
    drop = ttk.OptionMenu(dropdown_frame, variables[i], None, *options[i])
    drop.configure(state="active" if i == 0 else "disabled") # 配置第一个下拉菜单为始终活跃状态，保证下拉菜单一直有形状
    drop.bind("<Leave>", lambda e: "break") # 绑定鼠标移出事件，当鼠标移出下拉菜单时，执行 lambda 函数，“break” 表示中止事件传递
    drop.grid(row=i // 4, column=i % 4, padx=int(15 * scale), pady=int(15 * scale)) # 设置位置，2 行 4 列（跟随缩放）
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
download_progress_bar.pack(side="bottom", padx=int(40 * scale), pady=int(10 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置进度条高度（跟随缩放）

# 下载进度标签
progress_label = ttk.Label(container_frame, text="等待下载", anchor="center") # 初始时文本为空，居中
progress_label.pack(side="bottom", padx=int(5 * scale), pady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置标签高度（跟随缩放）

root.mainloop() # 开始主循环
