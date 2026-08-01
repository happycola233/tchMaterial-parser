# -*- coding: utf-8 -*-
# 下载面板：解析并复制直链、下载资源文件与进度反馈
# 本模块持有与下载相关的几个控件句柄，因此这些控件的读写不必跨模块

import os, traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pyperclip

from .runtime import thread_it, ui_call
from .. import config
from ..api import parse
from ..bookmarks import add_bookmarks
from ..network import headers, session
from ..platform_utils import print_error

download_states: list[dict] = [] # 初始化下载状态

def bind_widgets(text: tk.Text, bookmark: tk.BooleanVar, button: ttk.Button, progress_bar: ttk.Progressbar, label: ttk.Label) -> None: # 由 app.py 在创建控件后写入
    global url_text, bookmark_var, download_btn, download_progress_bar, progress_label
    url_text, bookmark_var, download_btn, download_progress_bar, progress_label = text, bookmark, button, progress_bar, label

def parse_and_copy() -> None: # 解析并复制链接
    urls = {line.strip() for line in url_text.get("1.0", "end").splitlines() if line.strip()} # 获取所有非空行并去重
    resource_urls: set[str] = set()
    failed_urls: set[str] = set()

    for url in urls:
        resources_info = parse(url, False)
        if not resources_info:
            failed_urls.add(url) # 添加到失败链接
            continue
        for resource in resources_info:
            resource_urls.add(resource[1])

    if failed_urls:
        messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_urls))

    if resource_urls:
        pyperclip.copy("\n".join(resource_urls)) # 将链接复制到剪贴板
        messagebox.showinfo("提示", f'资源链接已复制到剪贴板。\n注意：链接可能无法直接下载，需要加上以下 HTTP 标头才能下载{"（以下标头含有隐私信息，请勿分享给别人）" if config.access_token else ""}：\n\nAuthorization: Bearer {config.access_token or "0"}\nX-ND-AUTH: MAC id="{config.access_token or "0"}",nonce="0",mac="0"')

def download() -> None: # 下载资源文件
    global download_states
    download_btn.config(state="disabled") # 设置下载按钮为禁用状态
    download_states = [] # 初始化下载状态
    urls = {line.strip() for line in url_text.get("1.0", "end").splitlines() if line.strip()} # 获取所有非空行并去重
    resources_info_list: list[tuple[str, str, str, list[dict]]] = []
    resource_urls: set[str] = set()
    failed_urls: set[str] = set()

    for url in urls:
        resources_info = parse(url, bookmark_var.get())
        if not resources_info:
            failed_urls.add(url)
            continue
        for resource in resources_info:
            resource_url = resource[1]
            if resource_url in resource_urls: # 直接使用 resources_info_list 会报错（list 不可哈希）
                continue
            resources_info_list.append(resource)
            resource_urls.add(resource_url)

    if len(resources_info_list) > 1:
        messagebox.showinfo("提示", "您将下载多个文件，请选择要下载文件的位置，本程序将在选定的文件夹中使用教材名称作为文件名进行下载。")
        dir_path = filedialog.askdirectory() # 选择文件夹
        if not dir_path: # 用户取消或关闭对话框
            download_btn.config(state="normal") # 恢复下载按钮为启用状态
            return
        dir_path = os.path.normpath(dir_path)
    else:
        dir_path = None

    for resource in resources_info_list:
        title, resource_url, resource_format, chapters = resource
        default_filename = title or "download"
        if dir_path:
            save_path = os.path.join(dir_path, f"{default_filename}.{resource_format}") # 构造完整路径
        else:
            save_path = filedialog.asksaveasfilename(defaultextension=f".{resource_format}", filetypes=[(f"{resource_format.upper()} 文件", f"*.{resource_format}"), ("所有文件", "*.*")], initialfile=default_filename) # 选择保存路径
            if not save_path: # 用户取消了文件保存操作
                download_btn.config(state="normal") # 恢复下载按钮为启用状态
                return
            save_path = os.path.normpath(save_path)
        thread_it(download_file, resource_url, save_path, chapters) # 开始下载（多线程，防止窗口卡死）

    if failed_urls:
        messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_urls)) # 显示警告对话框

    if not resources_info_list:
        download_btn.config(state="normal") # 设置下载按钮为启用状态

def download_file(url: str, save_path: str, chapters: list[dict] | None = None) -> None: # 下载文件
    current_state = { "download_url": url, "save_path": save_path, "downloaded_size": 0, "total_size": 0, "finished": False, "failed_reason": None }
    download_states.append(current_state)
    temp_path = f"{save_path}.tmp"

    try:
        response = session.get(url, headers=headers, stream=True)

        if not response.ok: # 服务器返回表示错误的 HTTP 状态码
            current_state["finished"] = True
            current_state["failed_reason"] = f"服务器返回 HTTP 状态码 {response.status_code}" + ("，Access Token 可能已过期或无效，请重新设置" if response.status_code in (401, 403) else "")
        else:
            current_state["total_size"] = int(response.headers.get("Content-Length", 0))

            with open(temp_path, "wb") as file:
                for chunk in response.iter_content( # 分块下载
                    chunk_size=131072 if current_state["total_size"] < 20971520 else 262144 if current_state["total_size"] < 52428800 else 524288
                ):
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

            current_state["downloaded_size"] = current_state["total_size"]

            if chapters: # 添加书签
                ui_call(progress_label.config, text="添加书签")
                add_bookmarks(temp_path, chapters)

            os.replace(temp_path, save_path) # 重命名临时文件为目标文件
            current_state["finished"] = True

    except Exception as e:
        print_error(e)
        current_state["downloaded_size"], current_state["total_size"] = 0, 0
        current_state["finished"] = True
        current_state["failed_reason"] = traceback.format_exc().rstrip()
        try:
            os.remove(temp_path)
        except Exception:
            pass

    if all(state["finished"] for state in download_states): # 所有文件下载完成
        ui_call(download_progress_bar.config, value=0) # 重置进度条
        ui_call(progress_label.config, text="等待下载") # 清空进度标签
        ui_call(download_btn.config, state="normal") # 设置下载按钮为启用状态

        failed_states = [state for state in download_states if state["failed_reason"]]
        if failed_states: # 存在下载失败的文件
            failed_message = "\n\n".join(
                f"{state['download_url']}\n{state['failed_reason']}"
                for state in failed_states
            )
            ui_call(
                messagebox.showwarning,
                "下载完成",
                f"文件已下载到：{os.path.dirname(save_path)}\n以下文件下载失败：\n{failed_message}",
            )
        else:
            ui_call(messagebox.showinfo, "下载完成", f"文件已下载到：{os.path.dirname(save_path)}")

def format_bytes(size: float) -> str: # 将数据单位进行格式化，返回以 KB、MB、GB、TB、PB 为单位的数据大小
    for x in ["字节", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:3.1f} {x}"
        size /= 1024.0
    return f"{size:3.1f} PB"
