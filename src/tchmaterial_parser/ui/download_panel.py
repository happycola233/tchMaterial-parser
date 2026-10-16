# -*- coding: utf-8 -*-
# 下载面板：解析并复制直链、下载资源文件与进度反馈
# 本模块持有与下载相关的几个控件句柄，因此这些控件的读写不必跨模块

import os, re, threading, time, traceback
import unicodedata
import tkinter as tk
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk, messagebox, filedialog
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree

from requests import RequestException

from . import runtime
from .runtime import thread_it, ui_call
from .. import config
from ..api import AUDIO_FORMATS, ResourceInfo, parse
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
# 用户请求停止当前批次：正在传输的任务尽快收尾，排队中的任务不再发起请求。
_stop_requested = threading.Event()
_batch_running = False
_parsing_download = False
_parsing_copy = False
_manager_window = None


class DownloadStopped(Exception):
    """用户主动停止，不作为下载错误展示。"""

def redact_access_token(text: str) -> str:
    """隐藏查询串里可能残留的 accessToken。本工具不再主动拼接该参数，但异常或用户粘贴的 URL 仍可能带上。"""
    text = re.sub(r"([?&]accessToken=)[^&\s'\"]+", r"\1<已隐藏>", text, flags=re.IGNORECASE)
    for secret in (config.access_token, config.mac_key):
        if secret:
            text = text.replace(secret, "<已隐藏>")
    return text

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

def request_download(url: str, cancel: threading.Event | None = None):
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
            if _stop_requested.is_set() or (cancel is not None and cancel.is_set()):
                if last_response is not None:
                    last_response.close()
                raise DownloadStopped()
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
                    response.close()
                    (cancel or _stop_requested).wait(_400_RETRY_DELAYS[retry])
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
    return unicodedata.normalize("NFC", os.path.normcase(filename)).casefold()

def _allocate_download_paths(resources: list[ResourceInfo], directory: str) -> list[str]:
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

        # 已完整下载的同名文件保留原路径，由批次跳过；“最终文件.tmp” 可能属于另一个仍在运行的程序实例，必须避开。
        while (
            filename_key(candidate) in reserved_paths
            or os.path.exists(f"{candidate}.tmp")
            or os.path.isdir(candidate)
        ):
            candidate = f"{stem} ({sequence}){extension}"
            sequence += 1

        reserved_paths.add(filename_key(candidate))
        allocated_paths.append(candidate)
    return allocated_paths

def audio_download_title(resource: ResourceInfo) -> str:
    title = resource.audio_title or resource.title
    if resource.textbook_title and resource.audio_title:
        # 只移除已知父标题及明确的组合分隔符，教材和单元标题本身都可能含连字符。
        prefix = r"\s+".join(re.escape(part) for part in resource.textbook_title.split())
        match = re.match(rf"^{prefix}\s+-\s+(.+)$", title, flags=re.DOTALL)
        if match:
            return match[1]
    return title


def _audio_directory(parent: str, name: str) -> str:
    """已有同名普通文件时另选目录，不移动或覆盖用户文件。"""
    candidate = os.path.join(parent, sanitize_filename(name))
    stem = candidate
    sequence = 2
    while os.path.lexists(candidate) and not os.path.isdir(candidate):
        candidate = f"{stem} ({sequence})"
        sequence += 1
    return candidate


def allocate_download_paths(resources: list[ResourceInfo], directory: str) -> list[str]:
    """音频放入 mp3/教材目录；同时识别旧规则的完整文件，供批次跳过。"""
    legacy_paths = _allocate_download_paths(resources, directory)
    organized = []
    for resource in resources:
        if resource.file_format.lower() not in AUDIO_FORMATS:
            organized.append(resource)
            continue
        category = os.path.join(directory, *(sanitize_filename(part) for part in resource.relative_dir))
        audio_dir = _audio_directory(category, "mp3")
        if resource.textbook_title:
            audio_dir = _audio_directory(audio_dir, resource.textbook_title)
        organized.append(resource._replace(
            title=audio_download_title(resource),
            edition=None, # 教材目录已隔离版别；避免批次内其他教材改变音频文件名
            relative_dir=tuple(os.path.relpath(audio_dir, directory).split(os.sep)),
        ))

    paths = _allocate_download_paths(organized, directory)
    reserved = {filename_key(path) for path in paths}
    legacy_counts = Counter(filename_key(os.path.join(*resource.relative_dir, download_filename(resource)))
                            for resource in resources)
    for index, (resource, old_path, new_path) in enumerate(zip(resources, legacy_paths, paths)):
        if resource.file_format.lower() not in AUDIO_FORMATS or old_path == new_path:
            continue
        # 新位置优先；旧位置只用于跳过完整文件，不迁移，也不把 .tmp 当作已下载。
        if os.path.isfile(new_path):
            continue
        candidates = [old_path]
        legacy_key = filename_key(os.path.join(*resource.relative_dir, download_filename(resource)))
        if resource.edition and legacy_counts[legacy_key] == 1:
            # 旧批次可能因其他版别的同名标题加过前缀；单独补下载时也要识别。
            category = os.path.join(directory, *(sanitize_filename(part) for part in resource.relative_dir))
            candidates.append(os.path.join(category, sanitize_filename(f"[{resource.edition}] {download_filename(resource)}")))
        for candidate in candidates:
            if (os.path.isfile(candidate) and not os.path.exists(f"{candidate}.tmp")
                    and filename_key(candidate) not in reserved):
                reserved.add(filename_key(candidate))
                paths[index] = candidate
                break
    return paths

def bind_widgets(text: tk.Text, bookmark: tk.BooleanVar, button: ttk.Button, copy_button: ttk.Button, progress_bar: ttk.Progressbar, label: ttk.Label) -> None: # 由 app.py 在创建控件后写入
    global url_text, bookmark_var, download_btn, copy_btn, download_progress_bar, progress_label
    url_text, bookmark_var, download_btn, copy_btn, download_progress_bar, progress_label = text, bookmark, button, copy_button, progress_bar, label

def downloads_active() -> bool: # 是否存在尚未完成的下载任务
    return _batch_running or _parsing_download or any(not state["finished"] for state in download_states)


def show_download_manager() -> None:
    global _manager_window
    from .download_manager import DownloadManager

    if _manager_window is None or not _manager_window.window.winfo_exists():
        _manager_window = DownloadManager(runtime.root)
    _manager_window.show()


def monitor_downloads() -> None:
    """主线程定时读取进度，避免每个数据块都向 Tk 事件队列投递更新。"""
    if runtime.app_closing:
        return
    if download_states and (_batch_running or not (_parsing_download or _parsing_copy)):
        refresh_download_progress()
    if _manager_window is not None and _manager_window.window.winfo_exists() and _manager_window.window.winfo_viewable():
        _manager_window.refresh()
    runtime.root.after(200, monitor_downloads)


def task_status(state: dict) -> str:
    if state.get("kind") == "parse":
        return "解析失败"
    if state["finished"]:
        if state["failed_reason"]:
            return "下载失败"
        if state.get("stopped"):
            return "已停止"
        if state.get("skipped"):
            return "已存在"
        return "已完成"
    if state.get("cancel") and state["cancel"].is_set():
        return "正在停止"
    return state.get("phase", "排队中")


def download_summary(states: list[dict]) -> str:
    counts = Counter(task_status(state) for state in states)
    finished = sum(state["finished"] for state in states)
    parts = [f"已结束 {finished}/{len(states)}"]
    for status in ("正在停止", "已完成", "已存在", "下载失败", "解析失败", "已停止"):
        if counts[status]:
            parts.append(f"{status} {counts[status]}")
    return " · ".join(parts)

def show_parse_progress(current: int, total: int) -> None: # 后台解析大量链接时在进度标签上反馈进度；下载进行中则让位给下载进度
    if _batch_running:
        return
    ui_call(progress_label.config, text=f"正在解析链接 {current}/{total}")

def refresh_download_progress() -> None:
    states = list(download_states)
    finished = sum(state["finished"] for state in states)
    # 服务器可能不提供文件大小，且失败、停止不等于下载完成；总条只表示任务处理数量。
    download_progress_bar.config(value=100 * finished / len(states) if states else 0)
    progress_label.config(text=download_summary(states) if states else "等待下载")


def record_parse_results(urls: list[str], failed_urls: set[str], show: bool = True) -> None:
    """解析错误也进入同一列表；再次解析成功后移除对应的旧错误。"""
    download_states[:] = [
        state for state in download_states
        if not (state.get("kind") == "parse" and state["download_url"] in urls)
    ]
    for url in urls:
        if url in failed_urls:
            state = create_download_state(url, "")
            state.update(kind="parse", title="资源页面解析失败", finished=True,
                         failed_reason="未能获取可下载的资源。请检查页面链接、网络连接与 Access Token，再重新解析。")
            download_states.append(state)
    if failed_urls and show:
        show_download_manager()

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
        try:
            resources_info = parse_fn(url, bookmarks)
        except Exception as error:
            print_error(RuntimeError(redact_access_token(str(error))))
            resources_info = None
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
    global _parsing_copy
    urls = {line.strip() for line in url_text.get("1.0", "end").splitlines() if line.strip()} # 获取所有非空行并去重
    if not urls:
        return

    copy_btn.config(state="disabled") # 解析期间禁用按钮，避免重复触发
    _parsing_copy = True

    def copy_urls(resources_info_list: list[ResourceInfo], failed_urls: set[str]) -> None: # 解析完成后在主线程复制链接
        global _parsing_copy
        _parsing_copy = False
        copy_btn.config(state="normal") # 恢复按钮为启用状态
        if not _parsing_download:
            refresh_download_progress()

        resource_urls = {resource.url for resource in resources_info_list}
        record_parse_results(list(urls), failed_urls)

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

def stop_downloads() -> None: # 请求停止当前批次；已下载完成的文件保留，未完成的临时文件删除
    _stop_requested.set()
    stop_tasks(download_states)
    progress_label.config(text="正在停止下载")
    download_btn.config(state="disabled") # 避免重复触发，批次结束后统一恢复

def stop_tasks(states: list[dict]) -> None:
    for state in states:
        if not state["finished"]:
            state["cancel"].set()


def download(urls: list[str] | None = None) -> None: # 下载资源文件
    global _parsing_download
    if downloads_active(): # 下载进行中时，同一个按钮用于停止
        if not _parsing_download:
            stop_downloads()
        return

    download_btn.config(state="disabled") # 设置下载按钮为禁用状态
    download_progress_bar.config(value=0) # 重置上一批任务可能残留的进度
    if urls is None:
        urls = list(dict.fromkeys(line.strip() for line in url_text.get("1.0", "end").splitlines() if line.strip()))

    if config.access_token and not config.access_token.isascii(): # 判断 Access Token 中是否包含非 ASCII 字符
        messagebox.showwarning("警告", "Access Token 不正确（包含非 ASCII 字符），请点击“设置 Token”按钮重新填写。")
        download_btn.config(state="normal") # 恢复下载按钮为启用状态
        return

    if not urls:
        download_btn.config(state="normal") # 恢复下载按钮为启用状态
        return

    _parsing_download = True
    download_btn.config(text="正在解析")

    def start_downloads(resources_info_list: list[ResourceInfo], failed_urls: set[str]) -> None: # 解析完成后在主线程选择保存位置并开始下载
        global _parsing_download
        record_parse_results(urls, failed_urls, show=False)

        def restore_download_btn() -> None: # 未产生下载任务时恢复界面状态
            global _parsing_download
            _parsing_download = False
            refresh_download_progress()
            download_btn.config(state="normal", text="下载")
            if failed_urls:
                show_download_manager()

        if len(resources_info_list) > 1:
            dir_path = filedialog.askdirectory(parent=runtime.root, title=f"保存 {len(resources_info_list)} 个文件（自动按教材分类创建子文件夹）")
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
                    parent=runtime.root,
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
            return

        progress_label.config(text=f"正在下载 {len(download_targets)} 个文件")
        batch_download = len(resources_info_list) > 1
        _parsing_download = False
        directory = dir_path if batch_download else os.path.dirname(download_targets[0][1])
        start_download_batch(download_targets, directory, skip_existing=batch_download)
        show_download_manager()

    parse_urls_in_background(list(urls), bookmark_var.get(), start_downloads)

def create_download_state(url: str, save_path: str) -> dict:
    return {
        "download_url": url, "save_path": save_path, "title": os.path.basename(save_path),
        "downloaded_size": 0, "total_size": 0, "finished": False, "failed_reason": None,
        "skipped": False, "stopped": False, "phase": "排队中", "cancel": threading.Event(),
        "chapters": None, "speed": 0, "attempt": 1, "error_details": None,
    }

def start_download_batch(targets: list[tuple[ResourceInfo, str]], directory: str, skip_existing: bool = False) -> None:
    if downloads_active():
        return
    # 所有排队任务先登记，快速失败或完成的线程也不会漏算尚未启动的任务。
    states = [create_download_state(resource.url, save_path) for resource, save_path in targets]
    for (resource, _), state in zip(targets, states):
        state["chapters"] = resource.chapters
    download_states.extend(states)

    if skip_existing: # 临时文件重命名是下载的最后一步，目标文件存在即说明上一轮已完整下载
        for (_, save_path), state in zip(targets, states):
            if os.path.isfile(save_path):
                state["skipped"], state["finished"] = True, True

    run_download_tasks(states, directory)


def retry_tasks(states: list[dict]) -> None:
    if downloads_active():
        return
    pending = [state for state in states if state.get("kind") != "parse" and state["finished"]
               and (state["failed_reason"] or state.get("stopped"))]
    reserved_paths = set()
    for state in pending:
        path_key = filename_key(os.path.abspath(state["save_path"]))
        if path_key in reserved_paths:
            state["failed_reason"] = "同一保存位置的另一条任务已加入重试，请查看该任务的结果。"
            continue
        # 已有目标文件可能是之前选择覆盖的原文件；只有第一次保存对话框可以授权覆盖。
        if os.path.exists(state["save_path"]):
            state["failed_reason"] = "目标位置已有文件。请从主界面重新下载并选择保存位置，以免覆盖已有内容。"
            continue
        reserved_paths.add(path_key)
        state.update(downloaded_size=0, total_size=0, finished=False, failed_reason=None,
                     error_details=None, stopped=False, phase="排队中", speed=0, attempt=state["attempt"] + 1)
        state["cancel"].clear()
    pending = [state for state in pending if not state["finished"]]
    if pending:
        run_download_tasks(pending, "")


def run_download_tasks(states: list[dict], directory: str) -> None:
    global _batch_running
    _stop_requested.clear()
    _batch_running = True
    download_btn.config(state="normal", text="停止下载")
    pending = [state for state in states if not state["finished"]]
    refresh_download_progress()
    if not pending: # 整批文件都已下载过，无需启动线程
        finish_download_batch(states, directory)
        return

    def worker() -> None:
        # 批量勾选可能产生数千个文件，仅保留少量工作线程，其余任务排队。
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(download_file, state["download_url"], state["save_path"], state["chapters"], state)
                for state in pending
            ]
            for future, state in zip(futures, pending):
                try:
                    future.result()
                except Exception as error:
                    state.update(finished=True, failed_reason=redact_access_token(str(error)))
        ui_call(finish_download_batch, states, directory) # 全部线程退出后，仅由批次通知一次

    thread_it(worker)

def finish_download_batch(states: list[dict], directory: str) -> None: # 结果保留在管理窗口，不弹出批量错误或完成提示
    global _batch_running
    _batch_running = False
    download_btn.config(state="normal", text="下载")
    _stop_requested.clear() # 停止标志只在一个批次内有效
    refresh_download_progress()

def download_file(url: str, save_path: str, chapters: list[dict] | None = None, current_state: dict | None = None) -> None: # 下载文件
    if current_state is None: # 保留单独下载文件的调用方式
        current_state = create_download_state(url, save_path)
        download_states.append(current_state)
    temp_path = f"{save_path}.tmp"
    temp_created = False

    def check_stopped() -> None:
        if _stop_requested.is_set() or current_state["cancel"].is_set():
            raise DownloadStopped()

    response = None
    try:
        check_stopped()
        with _download_slots:
            check_stopped()
            current_state["phase"] = "正在连接"
            response, attempted_urls = request_download(url, current_state["cancel"])
            check_stopped()

            if not response.ok: # 服务器返回表示错误的 HTTP 状态码
                current_state["failed_reason"] = download_failure_reason(response, attempted_urls)
            else:
                try:
                    total = max(0, int(response.headers.get("Content-Length", 0)))
                except (TypeError, ValueError):
                    total = 0
                # iter_content 会解压内容，Content-Length 此时是压缩后的大小，不能用于校验。
                current_state["total_size"] = 0 if response.headers.get("Content-Encoding") else total
                current_state["phase"] = "下载中"
                sampled_at, sampled_size = time.monotonic(), 0
                current_state["last_received"] = sampled_at

                os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                with open(temp_path, "xb") as file:
                    temp_created = True
                    for chunk in response.iter_content( # 分块下载
                        chunk_size=131072 if current_state["total_size"] < 20971520 else 262144 if current_state["total_size"] < 52428800 else 524288
                    ):
                        check_stopped()
                        if chunk: # 过滤掉 Keep-Alive 块
                            file.write(chunk)
                            current_state["downloaded_size"] += len(chunk)
                            now = time.monotonic()
                            current_state["last_received"] = now
                            if now - sampled_at >= 0.5:
                                current_state["speed"] = (current_state["downloaded_size"] - sampled_size) / (now - sampled_at)
                                sampled_at, sampled_size = now, current_state["downloaded_size"]

                check_stopped()
                if current_state["total_size"] > 0 and current_state["downloaded_size"] != current_state["total_size"]: # 文件下载不完整
                    current_state["failed_reason"] = f"文件下载不完整，需下载 {current_state['total_size']} 字节，实际下载 {current_state['downloaded_size']} 字节"
                else:
                    if chapters: # 添加书签
                        current_state["phase"] = "写入书签"
                        add_bookmarks(temp_path, chapters)

                    check_stopped()
                    os.replace(temp_path, save_path) # 重命名临时文件为目标文件
                    temp_created = False

    except DownloadStopped:
        current_state["stopped"] = True
    except Exception as e:
        if _stop_requested.is_set() or current_state["cancel"].is_set():
            current_state["stopped"] = True
        else:
            print_error(RuntimeError(redact_access_token(str(e))))
            current_state["failed_reason"] = redact_access_token(f"无法完成下载：{e}")
            current_state["error_details"] = redact_access_token(traceback.format_exc().rstrip())
    finally:
        if temp_created:
            try:
                os.remove(temp_path)
            except OSError as error:
                cleanup_error = redact_access_token(f"无法清理临时文件：{error}")
                current_state["failed_reason"] = f"{current_state['failed_reason'] or ''}\n{cleanup_error}".strip()
        if response is not None:
            try:
                response.close()
            except Exception as error:
                print_error(RuntimeError(redact_access_token(str(error))))
        current_state["speed"] = 0
        current_state["finished"] = True

def format_bytes(size: float) -> str: # 将数据单位进行格式化，返回以 KB、MB、GB、TB、PB 为单位的数据大小
    for x in ["字节", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:3.1f} {x}"
        size /= 1024.0
    return f"{size:3.1f} PB"
