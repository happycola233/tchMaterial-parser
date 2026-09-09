# -*- coding: utf-8 -*-
# 下载面板：解析并复制直链、下载资源文件与进度反馈
# 本模块持有与下载相关的几个控件句柄，因此这些控件的读写不必跨模块

import os, re, threading, time, traceback
import tkinter as tk
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk, messagebox, filedialog
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree

from requests import RequestException

from .runtime import thread_it, ui_call
from .. import config
from ..api import ResourceInfo, parse
from ..bookmarks import add_bookmarks
from ..network import REQUEST_TIMEOUT, request_headers, session
from ..platform_utils import print_error

download_states: list[dict] = [] # 初始化下载状态
PRIVATE_DOWNLOAD_HOSTS = tuple(f"r{index}-ndr-private.ykt.cbern.com.cn" for index in range(1, 4))
# 私有 CDN 在短时间连打时会回 400（有时带 InvalidArgument，有时几乎空包）。
# 立刻换 r2/r3 只会把限流打得更死；同地址稍等再签一次即可。
_400_RETRY_DELAYS = (1.0, 3.0)
_MIN_REQUEST_INTERVAL = 0.2
# 批量下载时限制同时占用私有 CDN 的任务数，避免 GUI 一开十几个线程又打出 400。
_download_slots = threading.BoundedSemaphore(3)
_rate_lock = threading.Lock()
_last_request_at = 0.0

def redact_access_token(text: str) -> str:
    """隐藏查询串里可能残留的 accessToken。本工具不再主动拼接该参数，但异常或用户粘贴的 URL 仍可能带上。"""
    return re.sub(r"([?&]accessToken=)[^&\s'\"]+", r"\1<已隐藏>", text, flags=re.IGNORECASE)

def download_mirror_urls(url: str) -> list[str]:
    """按原地址优先的顺序生成私有 CDN 镜像，普通下载地址保持不变。"""
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    if hostname not in PRIVATE_DOWNLOAD_HOSTS:
        return [url]

    ordered_hosts = [hostname, *(host for host in PRIVATE_DOWNLOAD_HOSTS if host != hostname)]
    return [urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment)) for host in ordered_hosts]

def _pace_request() -> None:
    """避免批量任务在同一瞬间打出一串私有 CDN 请求。"""
    global _last_request_at
    interval = _MIN_REQUEST_INTERVAL
    if interval <= 0:
        return
    with _rate_lock:
        wait = interval - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()

def request_download(url: str):
    """请求资源并在镜像出错时自动切换，返回最终响应和已尝试的无凭据地址。

    鉴权只放在 request_headers 生成的 X-ND-AUTH 里，URL 保持原样。
    官网谁拼 ?accessToken=：不是 UC SDK，是阅读器。普通教材用站点 pdf.js，不拼；
    专题课用 x-edu-microapp-detail 的 docplayer，会拼，但头里仍有按完整 URL
    现算的 MAC。我们的抉择是永远不拼，避免 2efcd89 那种无效 Token 进查询串
    导致的 400 InvalidArgument（#81）。有真实 MAC 时，#76 和专题课都不需要它。

    400 也按鉴权/限流处理：同地址用新 nonce 退避重试，不要立刻改打 r2/r3。
    """
    attempted_urls: list[str] = []
    last_response = None
    last_exception: RequestException | None = None

    for candidate_url in download_mirror_urls(url):
        attempted_urls.append(candidate_url)
        retry = 0
        while True:
            try:
                _pace_request()
                response = session.get(
                    candidate_url,
                    headers=request_headers(candidate_url),
                    stream=True,
                    timeout=REQUEST_TIMEOUT,
                )
            except RequestException as e:
                last_exception = e
                break

            if last_response is not None:
                last_response.close()
            last_response = response

            if response.ok:
                return response, attempted_urls

            # 401/403 换镜像也过不了。400 多半是突发限流，连打镜像会更糟。
            if response.status_code in (401, 403):
                return last_response, attempted_urls
            if response.status_code == 400:
                if retry < len(_400_RETRY_DELAYS):
                    time.sleep(_400_RETRY_DELAYS[retry])
                    retry += 1
                    continue
                return last_response, attempted_urls
            break

    if last_response is not None:
        return last_response, attempted_urls
    if last_exception is not None:
        # requests 的异常文字通常包含完整请求 URL，此处重新包装以清除查询参数中的 Token。
        raise RuntimeError(redact_access_token(str(last_exception))) from None
    raise RuntimeError("没有可用的下载地址")

def storage_error_code(response) -> str | None:
    """读取对象存储返回的 XML 错误码；非 XML 响应保持原有通用提示。"""
    try:
        root = ElementTree.fromstring(response.content)
        return root.findtext("Code")
    except (AttributeError, ElementTree.ParseError, TypeError):
        return None

def download_failure_reason(response, attempted_urls: list[str]) -> str:
    status_code = response.status_code
    error_code = storage_error_code(response)
    reason = f"服务器返回 HTTP 状态码 {status_code}"
    if error_code:
        reason += f"（{error_code}）"

    if status_code in (401, 403):
        if config.access_token:
            reason += "，Access Token 可能已过期或无效，请重新设置"
        else:
            reason += "，该资源需要有效的 Access Token，请先设置"
    elif status_code == 400 and error_code == "InvalidArgument":
        # 占位头、过期 Token、或短时间连打私有 CDN 都会回这个码。前面已经同地址重试过。
        if config.access_token:
            reason += "，私有资源暂时无法访问。请稍后重试；若持续失败，请重新设置 Access Token"
        else:
            reason += "，该私有资源需要有效的 Access Token，请先设置"

    if len(attempted_urls) > 1:
        reason += f"，已尝试 {len(attempted_urls)} 个下载镜像"
    return reason

# Windows 禁止在文件名中使用半角 ? * : / 等；改为对应全角字符，尽量保留原标题读法（#86）。
_INVALID_FILENAME_REPLACEMENTS = str.maketrans({
    "<": "＜",
    ">": "＞",
    ":": "：",
    '"': "＂",
    "/": "／",
    "\\": "＼",
    "|": "｜",
    "?": "？",
    "*": "＊",
})
_CONTROL_FILENAME_CHARS = re.compile(r"[\x00-\x1f]")
_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(10)),
    *(f"LPT{i}" for i in range(10)),
})

def sanitize_filename(filename: str) -> str:
    """将非法文件名字符换成全角对应字符，并避开 Windows 保留设备名。"""
    filename = _CONTROL_FILENAME_CHARS.sub("_", filename.translate(_INVALID_FILENAME_REPLACEMENTS))
    filename = filename.rstrip(" .")
    if not filename:
        return "download"

    stem, extension = os.path.splitext(filename)
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        return f"_{stem}{extension}"
    return filename

def download_filename(resource: ResourceInfo) -> str:
    return sanitize_filename(f"{resource.title or 'download'}.{resource.file_format}")

def filename_key(filename: str) -> str:
    """以跨平台保守方式比较文件名，提前避开 Windows/macOS 上的大小写冲突。"""
    return os.path.normcase(filename).casefold()

def allocate_download_paths(resources: list[ResourceInfo], directory: str) -> list[str]:
    """在线程启动前为批量任务分配唯一目标路径，防止多个线程共用同一个 .tmp 文件。"""
    base_filenames = [download_filename(resource) for resource in resources]
    base_counts = Counter(filename_key(filename) for filename in base_filenames)

    edition_filenames: list[str] = []
    for resource, filename in zip(resources, base_filenames):
        # 例如人教版与北师大版的 “普通高中教科书·英语必修 第三册” 同名时，优先使用易读的版别前缀区分。
        if base_counts[filename_key(filename)] > 1 and resource.edition:
            filename = sanitize_filename(f"[{resource.edition}] {filename}")
        edition_filenames.append(filename)

    reserved_paths: set[str] = set()
    allocated_paths: list[str] = []
    for resource, filename in zip(resources, edition_filenames):
        # 按资源的分类层级（学段/学科/版本）归入子目录，段名中的非法字符换为全角
        subdirectory = os.path.join(directory, *(sanitize_filename(part) for part in resource.relative_dir))
        candidate = os.path.join(subdirectory, filename)
        stem, extension = os.path.splitext(candidate)
        sequence = 2

        # 同时检查最终文件和可辨识的 “最终文件.tmp”；后者可能属于另一个仍在运行的程序实例。
        while (
            filename_key(candidate) in reserved_paths
            or os.path.exists(candidate)
            or os.path.exists(f"{candidate}.tmp")
        ):
            candidate = f"{stem} ({sequence}){extension}"
            sequence += 1

        reserved_paths.add(filename_key(candidate))
        allocated_paths.append(candidate)
    return allocated_paths

def bind_widgets(text: tk.Text, bookmark: tk.BooleanVar, button: ttk.Button, copy_button: ttk.Button, progress_bar: ttk.Progressbar, label: ttk.Label) -> None: # 由 app.py 在创建控件后写入
    global url_text, bookmark_var, download_btn, copy_btn, download_progress_bar, progress_label
    url_text, bookmark_var, download_btn, copy_btn, download_progress_bar, progress_label = text, bookmark, button, copy_button, progress_bar, label

def downloads_active() -> bool: # 是否存在尚未完成的下载任务
    return bool(download_states) and not all(state["finished"] for state in download_states)

def show_parse_progress(current: int, total: int) -> None: # 后台解析大量链接时在进度标签上反馈进度；下载进行中则让位给下载进度
    if downloads_active():
        return
    ui_call(progress_label.config, text=f"正在解析链接 {current}/{total}")

def refresh_download_progress() -> None: # 汇总全部任务状态刷新进度条与标签，没有 Content-Length 或出现失败时也能看到进展
    states = list(download_states)
    all_downloaded_size = sum(state["downloaded_size"] for state in states)
    all_total_size = sum(state["total_size"] for state in states)
    finished_number = len([state for state in states if state["finished"]])
    failed_number = len([state for state in states if state["failed_reason"]])
    total_number = len(states)
    if all_total_size > 0: # 防止下面一行代码除以 0 而报错
        download_progress = (all_downloaded_size / all_total_size) * 100
        ui_call(download_progress_bar.config, value=download_progress) # 更新进度条
        progress_text = f"{format_bytes(all_downloaded_size)}/{format_bytes(all_total_size)} ({download_progress:.2f}%) 已下载 {finished_number}/{total_number}"
    else:
        progress_text = f"已下载 {format_bytes(all_downloaded_size)}，已完成 {finished_number}/{total_number} 个文件"
    if failed_number:
        progress_text += f"，{failed_number} 个失败"
    ui_call(progress_label.config, text=progress_text) # 更新标签以显示当前下载进度

def collect_parsed_resources(
    parse_fn: Callable[[str, bool], list[ResourceInfo] | None],
    urls: list[str],
    bookmarks: bool,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[ResourceInfo], set[str]]:
    """逐条解析链接并汇总结果：按资源直链去重，解析失败的链接单独收集。"""
    resources_info_list: list[ResourceInfo] = []
    resource_urls: set[str] = set()
    failed_urls: set[str] = set()
    for index, url in enumerate(urls):
        if on_progress:
            on_progress(index + 1, len(urls))
        resources_info = parse_fn(url, bookmarks)
        if not resources_info:
            failed_urls.add(url)
            continue
        for resource in resources_info:
            if resource.url in resource_urls: # 直接使用 resources_info_list 会报错（list 不可哈希）
                continue
            resources_info_list.append(resource)
            resource_urls.add(resource.url)
    return resources_info_list, failed_urls

def parse_urls_in_background(
    urls: list[str],
    bookmarks: bool,
    on_finished: Callable[[list[ResourceInfo], set[str]], None],
) -> None:
    """在后台线程逐条解析链接，完成后回到主线程执行 on_finished(资源列表, 失败链接集合)。

    批量选择的链接可能多达上百条，逐条解析需多次网络请求，放在主线程会让界面未响应。
    """
    def worker() -> None:
        resources_info_list, failed_urls = collect_parsed_resources(parse, urls, bookmarks, show_parse_progress)
        ui_call(on_finished, resources_info_list, failed_urls)

    thread_it(worker)

def parse_and_copy() -> None: # 解析并复制链接
    urls = {line.strip() for line in url_text.get("1.0", "end").splitlines() if line.strip()} # 获取所有非空行并去重
    if not urls:
        return

    copy_btn.config(state="disabled") # 解析期间禁用按钮，避免重复触发

    def copy_urls(resources_info_list: list[ResourceInfo], failed_urls: set[str]) -> None: # 解析完成后在主线程复制链接
        copy_btn.config(state="normal") # 恢复按钮为启用状态
        if not downloads_active():
            progress_label.config(text="等待下载") # 解析进度已无用，恢复默认文案

        resource_urls = {resource.url for resource in resources_info_list}
        if failed_urls:
            messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_urls))

        if resource_urls:
            try:
                resource_urls_str = "\n".join(resource_urls)
                url_text.clipboard_clear()
                url_text.clipboard_append(resource_urls_str) # 将链接复制到剪贴板
                if url_text.clipboard_get() == resource_urls_str: # 检查剪贴板内容是否正确
                    # 真实 X-ND-AUTH 必须按每条 URL 现算，不能把某一次的 nonce/mac 当作通用头复制出去。
                    messagebox.showinfo(
                        "提示",
                        f'资源链接已复制到剪贴板。\n注意：链接可能无法直接下载。官网私有资源使用按地址单独计算的 X-ND-AUTH，请优先用本工具下载。{"若需手动请求，至少带上以下标头（含隐私信息，请勿分享）：" if config.access_token else "未登录时可以尝试："}\n\nAuthorization: Bearer {config.access_token or "0"}\nX-ND-AUTH: MAC id="{config.access_token or "0"}",nonce="0",mac="0"',
                    )
                else:
                    messagebox.showerror("错误", "无法将链接复制到剪贴板，请手动复制。")
            except Exception as e:
                print_error(e)
                messagebox.showerror("错误", "无法将链接复制到剪贴板，请手动复制。")

    parse_urls_in_background(list(urls), False, copy_urls)

def download() -> None: # 下载资源文件
    global download_states
    download_btn.config(state="disabled") # 设置下载按钮为禁用状态
    download_progress_bar.config(value=0) # 重置上一批任务可能残留的进度
    download_states = [] # 初始化下载状态
    urls = {line.strip() for line in url_text.get("1.0", "end").splitlines() if line.strip()} # 获取所有非空行并去重

    if config.access_token and not config.access_token.isascii(): # 判断 Access Token 中是否包含非 ASCII 字符
        messagebox.showwarning("警告", "Access Token 不正确（包含非 ASCII 字符），请点击“设置 Token”按钮重新填写。")
        download_btn.config(state="normal") # 恢复下载按钮为启用状态
        return

    if not urls:
        download_btn.config(state="normal") # 恢复下载按钮为启用状态
        return

    def start_downloads(resources_info_list: list[ResourceInfo], failed_urls: set[str]) -> None: # 解析完成后在主线程选择保存位置并开始下载
        def restore_download_btn() -> None: # 未产生下载任务时恢复界面状态
            if not downloads_active():
                progress_label.config(text="等待下载")
            download_btn.config(state="normal") # 设置下载按钮为启用状态

        if len(resources_info_list) > 1:
            messagebox.showinfo("提示", "您将下载多个文件，请选择要下载文件的位置。本程序将在该文件夹中按教材分类创建子文件夹，并以资源名称命名文件。")
            dir_path = filedialog.askdirectory() # 选择文件夹
            if not dir_path: # 用户取消或关闭对话框
                restore_download_btn()
                return
            dir_path = os.path.normpath(dir_path)
            # 路径必须在任何线程启动前统一预留，否则同名资源仍可能同时打开同一个 .tmp 文件。
            download_targets = list(zip(resources_info_list, allocate_download_paths(resources_info_list, dir_path)))
        elif resources_info_list:
            download_targets: list[tuple[ResourceInfo, str]] = []
            for resource in resources_info_list:
                save_path = filedialog.asksaveasfilename( # 选择保存路径
                    defaultextension=f".{resource.file_format}",
                    filetypes=[(f"{resource.file_format.upper()} 文件", f"*.{resource.file_format}"), ("所有文件", "*.*")],
                    initialfile=sanitize_filename(resource.title or "download"),
                )
                if not save_path: # 用户取消了文件保存操作
                    restore_download_btn()
                    return
                save_path = os.path.normpath(save_path)
                download_targets.append((resource, save_path))
        else: # 没有可下载的资源
            restore_download_btn()
            if failed_urls:
                messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_urls)) # 显示警告对话框
            return

        progress_label.config(text=f"正在下载 {len(download_targets)} 个文件")
        directory = dir_path if len(resources_info_list) > 1 else os.path.dirname(download_targets[0][1])
        start_download_batch(download_targets, directory)

        if failed_urls:
            messagebox.showwarning("警告", "以下 “行” 无法解析：\n" + "\n".join(failed_urls)) # 显示警告对话框

    parse_urls_in_background(list(urls), bookmark_var.get(), start_downloads)

def create_download_state(url: str, save_path: str) -> dict:
    return { "download_url": url, "save_path": save_path, "downloaded_size": 0, "total_size": 0, "finished": False, "failed_reason": None }

def start_download_batch(targets: list[tuple[ResourceInfo, str]], directory: str) -> None:
    global download_states
    # 所有排队任务先登记，快速失败或完成的线程也不会漏算尚未启动的任务。
    states = [create_download_state(resource.url, save_path) for resource, save_path in targets]
    download_states = states

    def worker() -> None:
        # 批量勾选可能产生数千个文件，仅保留少量工作线程，其余任务排队。
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(download_file, resource.url, save_path, resource.chapters, state)
                for (resource, save_path), state in zip(targets, states)
            ]
            for future in futures:
                future.result()
        ui_call(finish_download_batch, states, directory) # 全部线程退出后，仅由批次通知一次

    thread_it(worker)

def finish_download_batch(states: list[dict], directory: str) -> None: # 在主线程统一恢复控件并显示整批结果
    download_progress_bar.config(value=0)
    progress_label.config(text="等待下载")
    download_btn.config(state="normal")

    failed_states = [state for state in states if state["failed_reason"]]
    if failed_states:
        failed_message = "\n\n".join(
            f"{os.path.relpath(state['save_path'], directory)}\n{state['failed_reason']}"
            for state in failed_states
        )
        messagebox.showwarning("下载完成", f"文件已下载到：{directory}\n以下文件下载失败：\n{failed_message}")
    else:
        messagebox.showinfo("下载完成", f"文件已下载到：{directory}")

def download_file(url: str, save_path: str, chapters: list[dict] | None = None, current_state: dict | None = None) -> None: # 下载文件
    if current_state is None: # 保留单独下载文件的调用方式
        current_state = create_download_state(url, save_path)
        download_states.append(current_state)
    temp_path = f"{save_path}.tmp"

    response = None
    try:
        with _download_slots:
            response, attempted_urls = request_download(url)

            if not response.ok: # 服务器返回表示错误的 HTTP 状态码
                current_state["failed_reason"] = download_failure_reason(response, attempted_urls)
            else:
                current_state["total_size"] = int(response.headers.get("Content-Length", 0))

                os.makedirs(os.path.dirname(save_path), exist_ok=True) # 分类下载时子目录可能尚不存在
                with open(temp_path, "wb") as file:
                    for chunk in response.iter_content( # 分块下载
                        chunk_size=131072 if current_state["total_size"] < 20971520 else 262144 if current_state["total_size"] < 52428800 else 524288
                    ):
                        if chunk: # 过滤掉 Keep-Alive 块
                            file.write(chunk)
                            current_state["downloaded_size"] += len(chunk)
                            refresh_download_progress()

                if current_state["total_size"] > 0 and current_state["downloaded_size"] != current_state["total_size"]: # 文件下载不完整
                    current_state["failed_reason"] = f"文件下载不完整，需下载 {current_state['total_size']} 字节，实际下载 {current_state['downloaded_size']} 字节"
                    current_state["downloaded_size"], current_state["total_size"] = 0, 0
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                else:
                    if chapters: # 添加书签
                        ui_call(progress_label.config, text="添加书签")
                        add_bookmarks(temp_path, chapters)

                    os.replace(temp_path, save_path) # 重命名临时文件为目标文件

    except Exception as e:
        print_error(e)
        current_state["downloaded_size"], current_state["total_size"] = 0, 0
        current_state["failed_reason"] = redact_access_token(traceback.format_exc().rstrip())
        try:
            os.remove(temp_path)
        except Exception:
            pass
    finally:
        if response is not None:
            response.close()
        current_state["finished"] = True

    refresh_download_progress() # 每个任务结束时刷新一次，重试等待期间也能看到完成数与失败数

def format_bytes(size: float) -> str: # 将数据单位进行格式化，返回以 KB、MB、GB、TB、PB 为单位的数据大小
    for x in ["字节", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:3.1f} {x}"
        size /= 1024.0
    return f"{size:3.1f} PB"
