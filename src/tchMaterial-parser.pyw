# -*- coding: utf-8 -*-
# 国家中小学智慧教育平台 资源下载工具 v2.3
#   https://github.com/happycola233/tchMaterial-parser
# 最近更新于：2024-10-03
# 作者：肥宅水水呀（https://space.bilibili.com/324042405）以及其他为本工具作出贡献的用户

# 导入相关库
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os, platform
from functools import partial
import base64, tempfile
import threading, requests, pyperclip, psutil

os_name = platform.system() # 获取操作系统类型
if os_name == "Windows": # 如果是 Windows 操作系统，导入 Windows 相关库
    import win32print, win32gui, win32con, win32api, ctypes

    # 高 DPI 适配
    scale: float = round(win32print.GetDeviceCaps(win32gui.GetDC(0), win32con.DESKTOPHORZRES) / win32api.GetSystemMetrics(0), 2) # 获取当前的缩放因子

    # 调用 API 设置成由应用程序缩放
    try: # Windows 8.1 或更新
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except: # Windows 8 或更老
        ctypes.windll.user32.SetProcessDPIAware()
else:
    scale = 1.0


# 在导入库的部分后添加
root = tk.Tk()  # 创建主窗口
root.title("国家中小学智慧教育平台 资源下载工具")
root.minsize(int(800 * scale), int(600 * scale))  # 设置最小窗口大小
root.withdraw()  # 暂时隐藏主窗口，直到完全加载完成
session = requests.Session()  # 创建会话
download_states = []  # 存储下载状态





def parse(url: str) -> tuple[str, str, str] | tuple[str, str, str, list] | tuple[None, None, None]: # 解析 URL
    try:
        content_id, content_type, resource_url = None, None, None

        # 简单提取 URL 中的 contentId 与 contentType（这种方法不严谨，但为了减少导入的库只能这样了）
        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentId":
                content_id = q.split("=")[1]
                break

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

        if "syncClassroom/basicWork/detail" in url: # 对于"基础性作业"的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
        else: # 对于课本的解析
            if content_type == "thematic_course": # 对专题课程（含电子课本、视频等）的解析
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
            elif content_type == "assets_document":  # 添加对教材资源的音频解析
                # 获取教材主体信息
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{content_id}.json")
                # 获取教材关联的音频资源
                audio_response = session.get(f"https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/{content_id}/relation_audios.json")
                audio_data = audio_response.json()
                
                # 构建音频资源列表，包含URL和标题
                audio_info = []
                processed_titles = set()  # 用于去重的标题集合
                
                for audio in audio_data:
                    audio_title = audio.get("title", f"音频_{len(audio_info)+1}")
                    if audio_title in processed_titles:
                        continue
                        
                    for item in audio["ti_items"]:
                        if item["lc_ti_format"] == "audio/mp3":
                            for storage_url in item["ti_storages"]:
                                audio_url = storage_url.replace("-private", "")
                                # 过滤掉不可下载的URL
                                if "clip-" in audio_url or ".pkg/" in audio_url:
                                    continue
                                audio_info.append({"url": audio_url, "title": f"{len(audio_info)+1:03d}_{audio_title}"})
                                processed_titles.add(audio_title)
                                break  # 找到第一个有效URL后就跳出
            else: # 对普通电子课本的解析
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{content_id}.json")
        
        data = response.json()
        for item in list(data["ti_items"]):
            if item["lc_ti_format"] == "pdf": # 找到存有 PDF 链接列表的项
                resource_url: str = item["ti_storages"][0].replace("-private", "") # 获取并构建 PDF 的 URL
                break

        if not resource_url:
            if content_type == "thematic_course": # 专题课程
                resources_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/thematic_course/{content_id}/resources/list.json")
                resources_data = resources_resp.json()
                for resource in list(resources_data):
                    if resource["resource_type_code"] == "assets_document":
                        for item in list(resource["ti_items"]):
                            if item["lc_ti_format"] == "pdf":
                                resource_url: str = item["ti_storages"][0].replace("-private", "")
                                break
                if not resource_url:
                    return None, None, None
            else:
                return None, None, None

        # 如果是教材资源且有音频，返回音频信息
        if content_type == "assets_document" and "audio_info" in locals() and audio_info:
            return resource_url, content_id, data["title"], audio_info
        else:
            return resource_url, content_id, data["title"]
    except:
        return None, None, None # 如果解析失败，返回 None

def download_file(url: str, save_path: str) -> None: # 下载文件
    global download_states
    try:
        response = session.get(url, stream=True)
        response.raise_for_status()  # 检查响应状态
        
        total_size = int(response.headers.get("Content-Length", 0))
        current_state = {
            "download_url": url,
            "save_path": save_path,
            "downloaded_size": 0,
            "total_size": total_size,
            "finished": False,
            "failed": False
        }
        download_states.append(current_state)

        # 确保目标目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=131072): # 分块下载，每次下载 128 KB
                if chunk: # 过滤掉keep-alive新chunk
                    file.write(chunk)
                    file.flush() # 确保数据写入磁盘
                    current_state["downloaded_size"] += len(chunk)
                    all_downloaded_size = sum(state["downloaded_size"] for state in download_states)
                    all_total_size = sum(state["total_size"] for state in download_states)
                    downloaded_number = len([state for state in download_states if state["finished"]])
                    total_number = len(download_states)

                    if all_total_size > 0:
                        download_progress = (all_downloaded_size / all_total_size) * 100
                        download_progress_bar["value"] = download_progress
                        progress_label.config(text=f"{format_bytes(all_downloaded_size)}/{format_bytes(all_total_size)} ({download_progress:.2f}%) 已下载 {downloaded_number}/{total_number}")

        current_state["downloaded_size"] = current_state["total_size"]
        current_state["finished"] = True
        
    except Exception as e:
        log_text.insert(tk.END, f"下载失败 {url}: {str(e)}\n")
        log_text.see(tk.END)
        current_state["downloaded_size"], current_state["total_size"] = 0, 0
        current_state["finished"], current_state["failed"] = True, True

    if all(state["finished"] for state in download_states):
        download_progress_bar["value"] = 0
        progress_label.config(text="等待下载")
        download_btn.config(state="normal")

        failed_urls = [state["download_url"] for state in download_states if state["failed"]]
        if len(failed_urls) > 0:
            failed_str = '\n'.join(failed_urls)
            log_text.insert("end", f"文件已下载到：{os.path.dirname(save_path)}/{os.path.basename(save_path)}\n")
            log_text.insert("end", f"以下链接下载失败：\n{failed_str}\n")
            log_text.see("end")
        else:
            log_text.insert("end", f"文件已下载到：{os.path.dirname(save_path)}\n")
            log_text.see("end")

def format_bytes(size: float) -> str: # 格式化字节
    # 返回以 KB、MB、GB、TB 为单位的数据大小
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
        result = parse(url)
        if result is None:
            failed_links.append(url)
        else:
            if len(result) == 4:  # 有音频资源
                resource_url, content_id, title, audio_urls = result
                resource_links.append({"url": resource_url, "title": title, "audio_urls": audio_urls})
            else:  # 无音频资源
                resource_url, content_id, title = result
                resource_links.append({"url": resource_url, "title": title})

def download() -> None:
    global download_states
    download_states = []
    
    # 禁用下载按钮，防止重复点击
    download_btn.config(state="disabled")
    
    # 检查是否有URL输入
    urls = [line.strip() for line in url_text.get("1.0", tk.END).splitlines() if line.strip()]
    if not urls:
        messagebox.showwarning("警告", "请输入至少一个网址！")
        download_btn.config(state="normal")
        return
    
    # 使用 root.after 确保在主线程中打开对话框
    def ask_directory():
        save_dir = filedialog.askdirectory()  # 选择保存目录
        if save_dir:  # 用户选择了目录
            log_text.delete(1.0, tk.END)  # 清空日志
            root.after(100, lambda: start_download(save_dir))  # 延迟100ms启动下载
        else:  # 用户取消选择
            download_btn.config(state="normal")
    
    def start_download(save_dir):
        for url in urls:
            try:
                log_text.insert(tk.END, f"正在解析: {url}\n")
                log_text.see(tk.END)
                
                result = parse(url.strip())
                if result[0] is None:
                    log_text.insert(tk.END, "解析失败，请检查URL是否正确\n")
                    continue
                    
                # 处理音频文件的情况
                if len(result) == 4:  # 如果返回了音频信息
                    resource_url, content_id, title, audio_info = result
                    # 下载PDF
                    save_path = os.path.join(save_dir, f"{title}.pdf")
                    download_file(resource_url, save_path)
                    
                    # 创建音频文件夹
                    audio_dir = os.path.join(save_dir, f"{title}_音频")
                    os.makedirs(audio_dir, exist_ok=True)
                    
                    # 下载音频文件
                    for audio in audio_info:
                        audio_path = os.path.join(audio_dir, f"{audio['title']}.mp3")
                        download_file(audio['url'], audio_path)
                else:
                    # 原有的PDF下载逻辑
                    resource_url, content_id, title = result
                    save_path = os.path.join(save_dir, f"{title}.pdf")
                    download_file(resource_url, save_path)
                    
            except Exception as e:
                log_text.insert(tk.END, f"发生错误: {str(e)}\n")
                log_text.see(tk.END)
        
        # 下载完成后恢复下载按钮
        download_btn.config(state="normal")
    
    root.after(0, ask_directory)  # 在主线程中执行对话框

def thread_it(func, *args):
    """将函数打包进线程"""
    t = threading.Thread(target=func, args=args) 
    t.daemon = True  # 守护线程
    t.start()

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
                    tag_paths: list[str] = book["tag_paths"][0].split("/")[2:] # 电子课本 tag_paths 的前两项为"教材"、"电子教材"

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



# 初始化请求
session = requests.Session()
session.proxies = { "http": None, "https": None }

# 获取资源列表
try:
    resource_list = resource_helper().fetch_resource_list()
except:
    resource_list = {}
    messagebox.showwarning("警告", "获取资源列表失败，请手动填写资源链接，或重新打开本程序") # 弹出警告窗口

# GUI
root = tk.Tk()

root.tk.call("tk", "scaling", scale / 0.75) # 设置缩放因子

root.title("国家中小学智慧教育平台 资源下载工具") # 设置窗口标题
# root.geometry("900x600") # 设置窗口大小

def set_icon() -> None: # 设置窗口图标
    # 窗口左上角小图标
    if os_name == "Windows":
        icon = base64.b64decode("AAABAAEAMDAAAAEAIACoJQAAFgAAACgAAAAwAAAAYAAAAAEAIAAAAAAAACQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD///////8AAP///////wAA////////AAD///////8AAP///////wAA////////AAD///////8AAP///////wAA//gAf///AAD/4AAP//8AAP/AAAH//wAA/4AAAH//AAD/AAAAD/kAAPwAAAAABwAA8AAPgAAPAADgA///gH8AAMAP/8B//wAAgBf/gB//AACAE/8AD/8AAAAT/wAH/wAAABH/AAf/AAAAFf8AA/8AAAAU/wAD/wAAABT/gAP/AAAAFv/AAf8AAAAWf+AB/wAAgBJ/4AH/AACAEz/AAf8AAMASP4AD/wAA4AAcAAP/AADwAAAAA/8AAPgAAAAH/wAA/gAAAA//AAD+AAAAH/8AAP8AAAA//wAA/wAAAP//AAD/gAB///8AAP/AAP///wAA/+AB////AAD/+Af///8AAP///////wAA////////AAD///////8AAP///////wAA////////AAD///////8AAP///////wAA////////AAA=")
        with open(tempfile.gettempdir() + "/icon.ico", "wb") as f:
            f.write(icon)
        root.iconbitmap(tempfile.gettempdir() + "/icon.ico") # 更改窗口左上角的小图标
    else: # 非 Windows 操作系统可能不支持 .ico 图标
        icon = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAN8AAADfCAYAAAEB/ja6AAAACXBIWXMAAAsTAAALEwEAmpwYAAAE7mlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQiPz4gPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iQWRvYmUgWE1QIENvcmUgOS4xLWMwMDIgNzkuYTZhNjM5NiwgMjAyNC8wMy8xMi0wNzo0ODoyMyAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iIHhtbG5zOnBob3Rvc2hvcD0iaHR0cDovL25zLmFkb2JlLmNvbS9waG90b3Nob3AvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0RXZ0PSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VFdmVudCMiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIDI1LjkgKFdpbmRvd3MpIiB4bXA6Q3JlYXRlRGF0ZT0iMjAyNC0wOC0xOVQxNDozNzo1MyswODowMCIgeG1wOk1vZGlmeURhdGU9IjIwMjQtMDgtMTlUMTQ6Mzg6MjQrMDg6MDAiIHhtcDpNZXRhZGF0YURhdGU9IjIwMjQtMDgtMTlUMTQ6Mzg6MjQrMDg6MDAiIGRjOmZvcm1hdD0iaW1hZ2UvcG5nIiBwaG90b3Nob3A6Q29sb3JNb2RlPSIzIiB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOmRjMWFiMTUxLTkzYzUtMGI0MS1hYWNiLTYxYzFhMmIyNTczOSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDpkYzFhYjE1MS05M2M1LTBiNDEtYWFjYi02MWMxYTJiMjU3MzkiIHhtcE1NOk9yaWdpbmFsRG9jdW1lbnRJRD0ieG1wLmRpZDpkYzFhYjE1MS05M2M1LTBiNDEtYWFjYi02MWMxYTJiMjU3MzkiPiA8eG1wTU06SGlzdG9yeT4gPHJkZjpTZXE+IDxyZGY6bGkgc3RFdnQ6YWN0aW9uPSJjcmVhdGVkIiBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOmRjMWFiMTUxLTkzYzUtMGI0MS1hYWNiLTYxYzFhMmIyNTczOSIgc3RFdnQ6d2hlbj0iMjAyNC0wOC0xOVQxNDozNzo1MyswODowMCIgc3RFdnQ6c29mdHdhcmVBZ2VudD0iQWRvYmUgUGhvdG9zaG9wIDI1LjkgKFdpbmRvd3MpIi8+IDwvcmRmOlNlcT4gPC94bXBNTTpIaXN0b3J5PiA8L3JkZjpEZXNjcmlwdGlvbj4gPC9yZGY6UkRGPiA8L3g6eG1wbWV0YT4gPD94cGFja2V0IGVuZD0iciI/PtZSP9gAACKSSURBVHic7Z1/jFvlme+/z2sHktvJbmCO54Ywdjw0qKkKaqIFFXRT7aCCCipog5aoIEB4PIFyVSpAF0SrgkoEqKxKBdVSLZSMx4hWgMIVQaQiK1IlVYPIqrnqrGBFqqaJczwkke0hs8zszdzEfp/7h+3B9vjHOcfnnNfH837+mbF9zvs8x4+fc94fz/s8xMzwE+GrNC3QC6jTAbFkYcmvykwZHc+zLbCZIDeENj2pk7AqDMwTMFB59YKZijzsqcAWzJop4yLLArsUtkirr7zuV+qWsHYsatFMGBMOEGO0+rpWayvKNbtK0e5kYoyaKYOandjq/U5YcvxYssDd+F6dwNh44TWnJzuxuQDTlnYHRMcKTzW7uvVjhQfaN00Hm74LOLurOL0TdbShkPhq80/oLbvCgC+uMAtg2M6JlfNs39gt+ZWVX2h0bObbRLy30/me3dpaCW6qeXQsf4CI/t5po+0+b/M8zO8D6FsW5Rw2U8bVVg608sRv+oMqCYp+unNw2qJCXwjU/dLAC9Q21AJtY//xc2xwBQ5Q0XWBPTm2cKKA68/DToJd/9F0UthW190ObXttVjtD1e69eWxwhVNFBEY5bEXTOgUOUNHpr1TELps57+TEJUo0EE+cijcV2KnRdgOZdnbPpC/JOBH4o3aKdDi3KZ3s9yyAZx20u6/VB22v0OlVmCnjhpYC2xne/mf8cPdjC6Ypc3Jwc7tGACCaLGTJwoCo7oXX44olArsVLOTcqkx6ZKHV57Fk4azj52Etdu46jmYTAZw2U8YlVoXUCdT90sAL9N2GfuP7N+o3+gKDjitTygAQS+afB9NWEK8F01uC5+5t95jyC0cX2EW/yrUv1Cq2BHq9QOQFlgTFkoUfAvipx7oswY0vomMD8URurRTiVLeCusXV2RIAWJ+ceZ3BtztXyQt4h5mKPGnnDF8WYltNzztkj5kybrF6sKPJGTNlUPV4Jr4jOxF5IzZWuAuE16qfd2qjmy/Szs+17bqvFbITkTcAoHpxrZf86nG6bgy0noZphognjq90IqReYGEjAID55UzaOGL1PKdfbKtpn2aEpRg440RILVLgEwAL5mTkfivH+xEDUUUwi+ecnlzri2bKWGXlHK+nmBsR2cnBJ5wKiyULf3Ei1CmOYz26UHCD3XOdyOrmhtTVzFq3lmslT0i5OZMemqp9L7ItN3DhwIq/KwlkTk1cdMKqjFYzeWcBdH139RtJ8qbpiaG6WIye7mzXIqS8JJMeOt3puNhY/mYQvYtKLJ2tn1g0WThPHSb93cDNm5bjhtx4ljFQzKYMx0tkVtDThkFHX2DQ6fsL1DeZoKMvMOjoCww6+gKDTt9foCvjrvXjn32HJT8N4k0AjjLT49nJwTfdaLtbuhgP5p8H6KHOEnjKnIh0DM/yCtsXGE+cWSNFyf5kMctt5uRQyx07XmFvymKssJ/oi01xdvFjBN+I5ZtMLFl4v5uLAwACwtFkwXFcrEOZnYlsyw2sWi3mXBS6m4Gtje8zUAzJudVuRmdYnTZUMaba1y7a1SoWIpvzT3YrxCHXu/HFeroS6xZWJ32bnuu2Ml7QTZSHK0G/fuFkxrtZlMUuALe5opH7fGymjCvtnFC3zhBNFuawmIGgO6rfdiyZ2wKIP7jRJoAr7J6waMFocuY9At9o5SQh51ZJsfpsq8/b7Cf5I4Cr7CpZSzF8LnLyV+sKVo9fvMlYvTgAqH0Q21l9NVPG1ZVjM1ZlNRIuXpC3c7yjOJl2cSpCznUMRjBTxkg3G6/s4OgxUUQ43uozy92s8v5H27us7SJiyXxLX2oOZUhQHCj3KQEgliy8CwAMjNlpiYE19mTbRwBkay2emTMEjgNAieSjlbdvBoBsykhbbSeanPlf5NIdux22l6OJkCGIrzAY0xNDR2s+mLLaRjRZmCOw5xcHOPJBPsHgxVt9dXxnTnTeNQYA0fH87d1YTpK83M7xti+QQRkAG6qv7QYlENPrdmXWUversYD9C5Scqf5fjVT0Mch81u4Jti8wjGKm+n+73owXtMsh1QrBoKZZWlqxGKtZualYebC7gZAh2xcHACKbGrzJyYnM/AFg48HeFbwjk75o1smZjge8BHyfwZaSyjTQchtzc+Q37Uba12I7KJ0Zh7KTxrVOBdqR5cbNa9GCxfC5iJUTiHBNLFng8jjPGWbKICH4uhYfH2k2QlmXzH/l0uSZr9uV1RAv6mxwyhzamp286B275zUjOlb4ZyJ0SDtWJ73tZhEvUgIqo9lPuvXWnvHCfq5Jzhcg6jal9/LM9hcQ7TQnBu+1cmgsOZMH2GibnKD5ib5fZFdT9/FEbm1J0FYlGyTbIQRfl9kZOeBWe7afM15dZLdpnFrhdA/v+wCu71o4870nJiM7u22nrYxuTo4lC9cDeN/q8cx4JjtpPN6NTLvocMqgoy8w6OgLDDr6AoNO319g3z/o+52+/4X2O9qAAUcbMOBoAwYcbcCAow0YcLQBA442YMDxPY9pLdFk/ioCvQZgo/2zeYGA7SdSkd+4rliA8NWA0bGZp4jYuzUlxXtMVeC5AWPjnz0Glk7KVXSL7a0xQcQzA8aShU/g6NboPipSXvuF6xcWS+YfAuh5t9t1gYyZMkYa31yXzH9FcHgtAJQEMsXPz8/kdw3N+6+eM1w1oPIgL+951kwZLUsmqcDF8gR9b7ylkLjfnLj4ZaUquNHIsjReA2fn5GoVt96uDdjjm7R9x29DOjZgbxZn6A0YmM+mjNV+yLJswOj46SuIwx95qUy/4cfwxUpVzFOxZIF7xngst5kpg4j5XgZ6urvvR9+gXWaVUwDWeq2AHRgY67RrPTqev73bLcFu46UnNskc42oilEUWE62MFT5hwobFfdqEX4tS6AdSlN5Hu5wkzC9brT3SyPpk4e1m+b78g9JmatBWPgjLLde+6DbFXTu+yJRTf1tplghmSXUAoimrGQc64dUPtBNeeeHiMzA6VvjQK+NVGR7PbWh8b4nxxgpPNWRRWHDLeABgpoYOmimDnG5P7zUEAESTuQQRrvFQzgIAEKjxFlm31T6eOL6SCHXLTVarGtmlsv0+7UXbzbBT1MsOAgAIYtKLxhchOgIAxPWrE8R4tPZ1YwYMLx/+lf1xCa/ab8RO0TI7hKPJvKOOgS0YlUQvtL727ROTxovV/yuFCBfxyni9tMzlBmGCeAzwdrjCjCOVv3FqYpbYWO421FSR9CJNi0rDVTOUeUEYlSxhnkL8VwAgonj1x8KMA198LnZV/xUSX3U7DY3qyfYTKeNWr9oWAB30qvEqX6SyqvmxED8K1H+5DIzZKaJpBdXG8zpLoyjJ+o6EF9Sm6qqSTUUOr08W3l58g/llO7kBg4CQc6u8SN9QS9PBtds0G8RLkpcLFn8pa+HeQL0RVR7oVxyOAJznXHMKMz23aDyXB+qqYYlb/QyiEkB5UMsEzx60jRDxI9X/vRqo17Tv05fJD5spg7JpY7c/8srUXVw8kdskhfiT20KqX2J0vPA0MX1JyNKrjUV0vcaLWykDxeyxQc+fc+3wNSlcSdK1n6YHD3nRtlViycIZdJP5mfELc9J4yC19uqXNeqAvs/ZvCTl3tz/pR5sTHS9sJdB3WPIGoJxgGsCfGbwvm4ocbnXe8FjhGwTcRYS7YPMHUR4D07PZycF/7UJ1ABZCKuKJU3EpVhzvVpATGLyXSOwtstx7MhX5s9vtX3rn9LC4YNXXiOS1DHwDoC1+pC1vBQPzoOK12Ym1H1s9x15JrPHC08T4sX3VNE4pz0y1ntzoMuNd7llAPNZNG/0NHWTwREjKvVbKJS1myiTxPTBvWtIa8MCJlPHLhvfcYziRHxWC9rvZZq/DLJ/ITg497Yes9WP57Uz0CgAIeX4kk74k48kYqVwlQt2zxDv4YTMVeUG1FrV4OsgNuCEXJMkr7Rat8BtfZiniiZlrpOAP/ZDlBAaKIGzLTvg7i+IGSjY+Vkov3ey3XAbtlRI7VE8muElP7Vy9NDFzTUjIGwn0dclYU14ABuoXnSkDVEpWETLM/B9ENFUMn5uyU6euX9DpJgOOzhMTcLQBA442YMDRBgw42oABRxsw4GgDBhxtwICjB/IBRntfgNHGCzDaeAFGGy/AaOMFGG28AKONF2C08QKMNl6A0cYLMNp4AUYbL8Bo4wUYbbwAo40XYLTxAow2XoDpmT0N6+44aYT/24V3MvMoMTaBeC1AK8HIMJAhwiGI8FvmzjX/R7WuvYJS48WShZ8C+KHD0/ednZO3Bqk6mNv4brx4IrdWCjoO0Eq32iSIu06kLl52pVN9M148cXylFANn3DRaI1LyddPpyAGv2u81fOmwrE/OvF7OW+2d4QBACNofS+bzXsroJTz3vCV1GnxCkry81/egd4tnxlt330kjXLxArRew3GZODr2lVAcP8eS2GU/k1io3HACQ2FWut9ufuG+8UQ5LIU653q5j6PnYWN73RAd+4EFl6d4skdqsbtK6O04aYuWqr5VflRZKInT61MRFJ1To5wS3q0r/BcCSekW9AoP3EuhGG6ccJhJPnpi4+LeeKdUFblaUvh7A+26113twQcji1V6Vs3GCLgfuACHlZr9TNzfVw41GYsn8k260ExSkEH+qpE9Wiq7j3i0Kx5Jde150vLDVBT2CC4ldlbxrvtP9bZOxq/NBfc/NlapkvtK18VTMW/YoG2PjM67XuWhHV8YbTuTsjJn6H+ZNsWThX/wS56jDEk/kNpWE+KP2uuYwFa+0k6bfKba+/Eu3zwyHJGcleij4pQchDn8EH74iy7fN2PjMn0KSs52P1ABALFnwfLap468jsi03sGq1mPNakX7EPDa4wsvCU209L5rMX9VrhjNTBpUERQH0/CJr7DJve58tn3nlolLkdVEpu9wAAJ/uHJwGsK36Zmys8AIIDyrTqjVXeNl409umyiJS7ehUILEcobb6XQDX+6SSBbwrwNH0tum24Yj5UTNlEBPf4bwN+USnYzLpkQUzZdzQrSx3oee9anmJ8aLJwnm3hUiiAgAQxLfAyNR+ZqYMIsYPOrVxwmatn+xE5A0zZZCQsm9q3TZSZ7zo2MzPvBh4L9ZjZ94OQrzx8xOTxovlL3puFRMONGlij1PZmfTQlJkyCMy3OG2jW+KJ3Fov2q0zXm2BXxVk0iMLoZJccrszU0bXX7w5GdlTeWZOd9uWXWRI3ONFu4vG83JWPIxipsVHS0qEylDovYa3Otats4OZMqIA/rebbXaEyZPotVrP2+iFAAA4H76g6UCVmfY2eXNT7cti+NyVbutjpozbgPpnr7fwFi9aFQAQGy+85kXjVSrjsiUQleqK5w5vz482HuNVHSHz2ODlXrTrJ2XPY9ylQriZGjpY+5okNa5I3+CZcIX10t1CRLbleqagYWNxRTNl7PNKVjxxZo1XbfuFWPk34qeqlQCAxj0FVgbl3SBFSXn0V7cIMO5XrUSZ+pkIu4NyO3gxEdEWoikvmg0rXA1vt3fO8aC8HfFEYaMU8D1QiCU8uf0rS+XBhMVhQmx85pXaz9wYlDcSS+a2qDAcAEDQq54060WjFvnd4n/M22ved3VQDlQ7J0LZ8lZ24mJP4lmUGS9UmtsLlHfQ1r7vxaC8HzonzVBmvEx6ZAEAQucvqBvbuT0oV72PghnPeNW28vRVRLim5qUHg3L6ifttWic7aTzuVdtKjVcOtfgCtwfll26fGXazPQe4/vyuxTfjxROn4l+8osqtUSzeMr0YlIcYSr1OyNBXPW3fy8ZrKYUuXJz6IiyOe9ZU3/NkUM7Y6nqb1slk0hfNeilAeDX6b4RLpcVeJTP/NprM187seDIoB9jofIw3mCljxGsZgsE7vBYCACQo/oVQuY9AixsyvBiUq4RYdozJcQORnTB2+yGolkx6qPZB7tlDndFksdd7pk9MDr3oh6DqM2/BOxGUAQACx6vv1G6D8mJQviiZ5S+9arsVlTALX6gYT3q36NmcxeedVyvlQDnoyKu2m8rrEBTsNqIstH5F202YK2F/oPVNPvb+R+NTh8xvwwE1QwUm3OqJBKIFAOCGXJsMzHu5Ul7FnBj0OOiWCioMB9QYLzth7GbA9bgOAcwCQPbYxXczaC8Yd5vHBldkU8Zqt2W1hHG3Rw3vMFODEW/a7kzdLyaeOLPGixn4kqBoqwgyv3B5J9GseWwwojqIqW6GpTwj4P64LyQ5Gx0vfOh2u3YwJ42HwLSt85FtmRVSXmKmjItUGw5oscWrEj3tSRAuAbtPpAxvnq8WWT9e2M+MUetnyH8yU0OWSghcMn5mfUiW92OUBDIXlmb/M5MemXWgZkdaPmijycJcYyieu/ACi/Dt2Z0XveOdjPbEE2fiJTp/l6DQ1yTzWkF0moHTTPLfFj7nPa1qNkS25QZW/U34TnDpLoBsRUMzME/gn5+d4+e6rQnRtpfkvQFr4ReKZ88/c/J178Z9doneM/tlhIo3AnyzzTydNuCjkvgmJ8nMO3ZxY8mZjwD2dHtuC04z4y0hxN7/+3nx915ULoltn/07KUubCLyFgKvg8TZkC7xkpoz/afVgS+OT9WP5R5joZ8510tjksJkyru50kOXBZWW/9xkAnha20NSxp92Ki+2Zgfj2/KiUtL87nTR2aFUryfG0TiX6+H0AquNEepVZgNIliTc/TQ8esnLCcCI/SiH6RzDub4xkZ2C+cVbKlTm5eCK3SYrQa4o6Nr3CNBM/mp2IvOFWg+UhSej5uqDkmsy6bqfmX27pio8IiVszaeOI14IqfY4/oNwrPmymjKvdnQ0f5XDsshl/d+AogInvcNPD7BIbK7zAhO+7vpQRHf/sCmL5kdvt9gBHhQxd7XVEmB08WYeKjeVuA4m+yD1NhAMnJozrVOvRDM8WEYcT+VEhgjukYOCX2ZTxgGo92uHpCnC5PmwvVfTqjOrnmR18Wb73conJJfaYxwZv7YU1Ojv4WPBXzZbiNuwrCRpTvcLfDf6X2lY0vVZeR8Mz5rHB54LmYa1Ql6R9lMOxL3/2Lw1bmt1kDxMmVESE+0XPZNiPJ86sYSrexkJ8gyVvIMIAQAZqIq2r0dcgzIJ5mpmmQPxXgD/OpiJLktD1O8S83Ga0+gfl25o1ztHGCzDaeAFGGy/AaOMFGG28AKONF2C08QKMNl6A0cYLMNp4AUYbL8Bo4wUYbbwAo40XYLTxAow2XoDRK+kajSL0nVOjUYR2Po1GEdr5NBpFaOfTaBShnU+jUYR2Po1GEdr5NBpFaOfTaBShnU+jUYR2Po1GEdr5NBpFaOfTaBShnU+jUYR2Po1GEdr5NBpFaOfTaBShnU+jUUTPJPRXyfB4bkOIxbcZGEW5JGHcvdZ5gZmmiPgQs9gb4s9/n0mPLLjXviaoLCvniyfOrGFRupOB+wH0QGFcXiCI3STP/yKTXmupmrCmf+hr5xsez20QLH4M8O0ArVStj0WOgvC0OWG8qloRjbf0nfNFxwtbifE8XO06KiVdDJ979OSv1hVUK6Jxl75wvlgytwUQr6F/HK45RDvPfl56OL9raF61KpruCa7zjXI4dtnMKwASqlXxHy4AdIeZMvap1kTjnMA5X6WG+370dglwH+GHzVTkBdVaaOwTGOeLJ86skaL0IbTTNUUyfjA9abyoWg+NdQLhfLHxmVc8rM7eNzAwH5Lym5n00JRqXTSd6WnniybzVwH0IQFh1boECQbtzaYGb6q+vjR55ush4mvApY0MbCSmjSBbk1OnAT4KxhEIOsqSphbmSx/oiZ/u6Fnn00+7oMEFkNgN8BvmXwd/jwNUVK1Rr9N7zleexfwIemzXFxCwm6TcobvCS+kp51t330kjXLzgLwDWqNZF4xlpIeWPMumh06oVUU3POF9lNvM4tOMtG5hxQIbo7k93Dk6r1kUFveF85a5mFsBa1apolPGseWzwieU0VuwJ54slC+8CuFm1Hpqe4LCQ8pbl0C1V7nzrx/LbmegV1Xpoeo4jQsrr+tkJ1TrfKIejl82cIWBAqR6anoUZB7LHB2/ox+6oEucrx2fS/QB9D3qcp7EAMd97YjKyU7UebuKL88UTuU0sxE8Y2OqHPE3f8rF5bHBzvzwFvXG+UQ6vv+yzByX4Sd2l1LgJA0WQ2JyduPhj1bp0i6vOFxv/7HvM8jntcBqvYcKt2Qljt2o9uqFr54sncmtlKPQemDe5oE+/Ur1L90DSpv6BIceyqaG0aj2c4tj5YsncFoZ4Tz/l2rLHTBm3NPsgnji+UorVW0D0XTDfDD3x5JQbgrqj37bzVbb57NdO1wGiKXNicLPt88rRPqMg+i4z366/5/YwUAxJGQ3ieqBl56sEPf8Bvb3b4DRA/wTmOIjuBNhQpYeQcyNuJseNJ87EpTh/PyDugX5KNkAHzdTgN1VrYRdLzhdLFn4I4Kce69I1DIxlU0a68f14orCxJHg7QdzT6JAMzAPYR8CNANzI7blQDJ+L+pHqL749P8qSHtRLOMEc/7V1vsq45CMAG3zSpyuklDdNp4f2Vl/HkoUsgOF25zDLJ7KTQ0/XvlfpWicIuBM2d1kIia9m0sYRO+e4RTyR2ySF+BmA61XIV0zGTBkjqpWwQ0vnC2IKByn5uul05ED1dSxZ4E7nMPjqbCpyuNNxsWThjyjXcWhHzwz+44njK0ti4GmAHgySDbuC+RZzMrJHtRpWaVqlKDaWv5lAfwyc0UK8uC9s3X0nrYz3Zq05Xv4hdHA8BsZ6xfEAIJMeWcimIo9kU8aKYvhcBOAPVOvkNUTiTtU62GGJc0XHC1vBeFuFMt0SLpUWw44uOEcDskMBNALtbX9EebwogefbtsPyCXOyd8cblfHnFoxyODoys4cI31atkxcwcI1qHexQ9/OMJXNbKKCOBwCZ9CWZ6v9FhOMdT2D5u06HSIH327fBL59oGDP2LAeomJ00bmTiO1Sr4g0cjyfOrFGthVUWnS+yLTcAUPsfWp9BzG3HB7HxmVfQfsJmjzkZud9drbwnOxF5g0BvqNbDGxbWqNbAKovdzlWrxdtwZ6pdEZSpeyUo3uH4j9stzEbH87e3TV1YXkRvGr0SDDjAtu4PBFCeYEHfTU+3/3Exo+V4b919Jw0wvdbm9NOi9Pm1jlVTTHRs5mf9uzYYCkzV3/KTT4inwB1n5XsaZs7UvqYOUSDMpZbjvXDxgvfQeqZ3oRg+d+XJXwWvtHMsWbiegbcJ3K8ha7NBCjMLR5P5q/pzRwL991afMFCsXYyvJTpWeAptlhWExOYgFaqMbMsNrFwtXqPKk0550h5PoZ5Z6rFCmED/qFoJNyBCpuGtNt3O5kYqF9nE423E3KAqesUulYKhu7Cc4kAZb6pWwQ5hgLYAwe5yNoMZcWpxmyfIf218L544vlJCvNuyvXLcaM/fWeOJwkYp+A8AqQoqV8WsOTn4lmol7CDQIfYxOPAJy0dSaIkTsVj9OlrEcRLLJ5oFbPca65Mzr0uBT5ah4wHgHao1sEsY4LhqJbyAiOItnujTjfk/1o8VHmg5+xeARfRKqv1PGLx8upj1fBzE6rwCoMBMHrSDG9b50GoTKtWHlA2P5zYw4Z9bNNvzi+g1NS6Wq+NBkrxVtQ5OECjvZws+xA1T/y020krUjfcEi+ZRPURTrVJA9BIyJPdjOReXYdw9PTF0VLUaThAgPqhaCTfgEhbXdy7dPtNyHCtYLI73KuFj8SaHBWIRff1Yfnt/LhNZ5kfmpPFr1Uo4RTD3x1aTMHi2+v+K4rmmC+TMOJRJXzQLVHdvNA0fWyiGz13pZgoIr2Ci76nWQR38sJkynlWtRTeIkJxPM9AHGYBLs9X/Wu9oKK/vrbvvpEHMrzc7ImCL6J029/YlTHxHECdYGhGZ9MgCCC+pVqRb/uu/Qh0dRjJ+CwDh4oVvA9RsET4wi+jLEQbmhTw/kp2I9MWODAEAC5/LHwHo+W5WO/K7hhYnjprtaGBg/tP04KFYMv8kwFuafN5TO9GtsWSGt39hvJNNGatr92wGHQGUf7jE/APVynRBXVlhAq9pPIBAe8shV/STJZ8FZBG9EWYEKqLDCQzMM/hqc9LYqloXt1ncTFsuv0Rphbp0wZKqNWuaHPQBEFq6Sz8Ai+itWJgv7UDAeyzt4YezKWO1lTw7QaQujYSZGhwD0ZQiXRzTuJ0IoPVNjnqsydpfzy+ityO/a2heEgVygbkdzPxzM2VQP0yqtGNJiiFzYnBzEB3QAvURIAFZRO/E9MTgXiYE3gEZKFbG3ZSdjDyiWh8/aJrfy5wY3MyEQ34r45Sl24laBlkvEGivkHKzozoKPUp2wtgt5PkRDmS0Eh0sCYpmU8aKII67u6Ht3srYWOEFEB70S5kuOH12Tl5eO+O5XIklc88C4jHVerSFaEqUSmOZ9NCUalVU0nFjc6UU2P6AJNCdJdAjJ1KDE6oVUU2POeECGC8XV5x7OkABDJ5jLavAKIejI4V9RPT3HuvjKgTsJil3LOc77KXbZ4ZDJX4RhH/wTSjRFFi+KmQ4XQ3n0yzFVkqP8i5p7Edwt698DBIvnv28+Jvl2kWNjn92BbiUINA/oLsCOEcBOsiQ/8bE+7rZWRBPnIpz6MKvSeaNBL6CGXEC4kwYtt7j4gUwnWYgQ8A0BD5mGTpSouKRk6nIn53q5iWO8un0U1VaBuYJ2Evg3ST5d0HKftWrRLblBlb97QVfARevAGMjyuWwr0DzHSS+w0ARjIMg2hOS/FtVIYVdJbNaJkl6joJwCKDDUoqpMM/+eyY9MqtaKT+IJ46vOS/WrBeMOEhuAHOcCHEwNjBhQ0DmAexyGCR2+tE7ciWTXGRbbmDVanoDoO+40V7AmQVTBsTTDBQIOM2MeQKmGaFZBmYBoCTKyyMXls7/PydP20vvnB6WK78UAoAVRIYs8YAQpTBkJScP8QizCIF4mIABZhhEGGbwGlqWOV66Yo+U/PPa8nNu4Hoax3git0mGQpPLfJOnpo9hxgFm3tGtM3qaQzWeOBWXYsVzAPoiN6hG0wgDRRBeCpVCT9id2fU1gXE8MXMNC36sf+sEaFTCQJGADDOmy1FPNAvI/wQAZsyD6pOFlUsK8Epm8SUiNpgRJ0FrmHlDF5OJ+4Q8f6+VrU9qs4ePcnj4y59dLxjfBfhG9PfEjcY5R5iwjyT9XorSlKqESfHE8ZVSfOkqQGxhxrdB2NJh0mlfSdDYpzsHp5t92JOp+yvp8D5C3yT01VjgKDPeBPHuQG4hGuVw7LKZURDuYcbWJk/Ol4Sce7g2N1BPOl+VAMWWaqwzC+Y3BYt0Jj0YmOB9p0ST+auI6EEwbgOwEuACQHeYKWNfTzsfAMQTubVSiD9Bd0kDR2WXxashiRd1bpwy8URubSkkHgDoWz3vfFWGE/lREvR+ny7s9gdEUwzekZ0wdqtWJQgExvmqxMZytzGJ17UTqoeA3RL8TCDHaD1A4JyvSiXI+z30SLzgMuA0gF8IGXpJ71Rwh8A63yKjHI5dVnicQT/WT0O3oAKYfyNYppfzdiyvCb7z1RDZlhtYNSCeZsL3tSNahQ4Sy3eI+dd6R4e/9JXzNRLfnh9lpp8wY1S1LoqZBbAPjHfOzsvdy3UvY6/R187XyPB4bgMx3U+g76KvFvCpAPAhAB+UJB34NHPxYRxYkstU02MsK+drRXT89BXEoesB8T8AvgbqHXMWwFECHWVwhpj/ysRHiuHiEZ0DpX8g5qalkzUajcc0zdup0Wi8RzufRqMI7XwajSK082k0itDOp9EoQjufRqMI7XwajSK082k0itDOp9EoQjufRqMI7XwajSK082k0itDOp9EoQjufRqMI7XwajSK082k0itDOp9Eo4v8DFeIo4yTRE98AAAAASUVORK5CYII=")
        with open(tempfile.gettempdir() + "/icon.png", "wb") as f:
            f.write(icon)

        icon = tk.PhotoImage(file=tempfile.gettempdir() + "/icon.png")
        root.iconphoto(True, icon) # 更改窗口左上角的小图标


thread_it(set_icon) # 设置窗口图标耗时较长，为不影响窗口绘制，采用多线程

def on_closing() -> None: # 处理窗口关闭事件
    current_process = psutil.Process(os.getpid()) # 获取自身的进程 ID
    child_processes = current_process.children(recursive=True) # 获取自身的所有子进程

    for child in child_processes: # 结束所有子进程
        try:
            child.terminate() # 结束进程
        except: # 进程可能已经结束
            pass

    # 结束自身进程
    try:
        current_process.terminate()
    except: # 进程可能已经结束
        pass

root.protocol("WM_DELETE_WINDOW", on_closing) # 注册窗口关闭事件的处理函数

# 创建一个容器框架
container_frame = ttk.Frame(root)
container_frame.pack(anchor="center", expand="yes", padx=int(40 * scale), pady=int(20 * scale)) # 在容器的中心位置放置，允许组件在容器中扩展，水平外边距 40，垂直外边距 40

title_label = ttk.Label(container_frame, text="国家中小学智慧教育平台 资源下载工具", font=("微软雅黑", 16, "bold")) # 添加标题标签
title_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

description = """请在下面的文本框中输入一个或多个资源页面的网址（每个网址一行）。
资源页面网址示例：
https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_
document&contentId=b8e9a3fe-dae7-49c0-86cb-d146f883fd8e
&catalogType=tchMaterial&subCatalog=tchMaterial
点击下面的"下载"按钮后，程序会解析并下载资源。"""
description_label = ttk.Label(container_frame, text=description, justify="left") # 添加描述标签
description_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

url_text = tk.Text(container_frame, width=70, height=12) # 添加 URL 输入框，长度和宽度不使用缩放！！！
url_text.pack(padx=int(15 * scale), pady=int(15 * scale)) # 设置水平外边距、垂直外边距（跟随缩放）

# 创建右键菜单
context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="剪切 (Ctrl + X)", command=lambda: url_text.event_generate("<<Cut>>"))
context_menu.add_command(label="复制 (Ctrl + C)", command=lambda: url_text.event_generate("<<Copy>>"))
context_menu.add_command(label="粘贴 (Ctrl + V)", command=lambda: url_text.event_generate("<<Paste>>"))

# 绑定右键菜单到文本框（3 代表鼠标的右键按钮）
url_text.bind("<Button-3>", lambda event: context_menu.post(event.x_root, event.y_root))





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
    drop.bind("<Leave>", lambda e: "break") # 绑定鼠标移出事件，当鼠标移出下拉菜单时，执行 lambda 函数，"break"表示中止事件传递
    drop.grid(row=i // 4, column=i % 4, padx=int(15 * scale), pady=int(15 * scale)) # 设置位置，2 行 4 列（跟随缩放）
    variables[i].set("---")
    drops.append(drop)

download_btn = ttk.Button(container_frame, text="下载", command=lambda: thread_it(download)) # 添加下载按钮
download_btn.pack(side="left", padx=int(5 * scale), pady=int(5 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置按钮高度（跟随缩放）

copy_btn = ttk.Button(container_frame, text="解析并复制", command=parse_and_copy) # 添加"解析并复制"按钮
copy_btn.pack(side="right", padx=int(5 * scale), pady=int(5 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置按钮高度（跟随缩放）

download_progress_bar = ttk.Progressbar(container_frame, length=(125 * scale), mode="determinate") # 添加下载进度条
download_progress_bar.pack(side="bottom", padx=int(40 * scale), pady=int(10 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置进度条高度（跟随缩放）

# 创建一个新标签来显示下载进度
progress_label = ttk.Label(container_frame, text="等待下载", anchor="center")
progress_label.pack(side="bottom", padx=int(5 * scale), pady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置标签高度（跟随缩放）


# 创建日志文本框和滚动条
log_frame = ttk.Frame(container_frame)
log_frame.pack(after=progress_label, fill="both", expand=True)

log_text = tk.Text(log_frame, height=5, width=70)
scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
log_text.configure(yscrollcommand=scrollbar.set)

# 添加默认提示文本
log_text.insert("1.0", "这里会显示下载和解析过程的日志信息...\n")

log_text.pack(side="left", fill="both", expand=True, padx=int(10 * scale), pady=int(10 * scale))
scrollbar.pack(side="right", fill="y")


root.mainloop() # 开始主循环
