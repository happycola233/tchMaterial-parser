# -*- coding: utf-8 -*-
# 国家中小学智慧教育平台 资源下载工具 v4.0
# 项目地址：https://github.com/happycola233/tchMaterial-parser
# 作者：肥宅水水呀（https://space.bilibili.com/324042405）以及其他为本工具作出贡献的用户

VERSION = "v4.0"

# 导入相关库
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import os, sys, platform, traceback, io, subprocess
import threading, psutil, pyperclip
import json, math, re, requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk
from pypdf import PdfReader, PdfWriter
import sv_ttk # Sun Valley（Windows 11 风格）主题

def print_error(e: Exception) -> None: # 打印错误信息到控制台
    if sys.stderr: # 无控制台运行时 sys.stderr 可能为 None
        traceback.print_exception(e)

def resource_path(*parts: str) -> Path: # 获取源码或 PyInstaller 打包后的只读资源路径
    # 源码入口位于 src/，资源位于项目根目录；PyInstaller 则把 datas 放到 sys._MEIPASS。
    # 因此不能依赖当前工作目录或可执行文件所在目录，后者在单文件模式下并非资源的实际位置
    source_root = Path(__file__).resolve().parent.parent
    bundle_root = Path(getattr(sys, "_MEIPASS", source_root))
    return bundle_root.joinpath(*parts)

os_name = platform.system() # 获取操作系统类型
if os_name == "Windows": # 在 Windows 操作系统下，导入 Windows 相关库
    try:
        import win32print, win32gui, win32con, win32api, ctypes, winreg
    except Exception as e:
        print_error(e)
        win32print = win32gui = win32con = win32api = ctypes = winreg = None
else:
    win32print = win32gui = win32con = win32api = ctypes = winreg = None

def color_emoji_font_paths() -> list[Path]: # 获取当前系统可能存在的彩色 Emoji 字体
    candidates: list[Path] = []

    if os_name == "Windows":
        windows_dir = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows")
        candidates.append(windows_dir / "Fonts" / "seguiemj.ttf") # Segoe UI Emoji
    elif os_name == "Darwin":
        candidates.extend([
            Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
            Path("/System/Library/Fonts/Apple Color Emoji.ttf"),
            Path("/Library/Fonts/Apple Color Emoji.ttc"),
        ])
    elif os_name == "Linux":
        # 各发行版安装 Noto Color Emoji 的目录并不统一，先询问 fontconfig，再检查常见路径
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}\n", "Noto Color Emoji"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                candidates.append(Path(result.stdout.splitlines()[0].strip()))
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        candidates.extend([
            Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
            Path("/usr/share/fonts/noto/NotoColorEmoji.ttf"),
            Path("/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf"),
            Path.home() / ".local" / "share" / "fonts" / "NotoColorEmoji.ttf",
            Path.home() / ".fonts" / "NotoColorEmoji.ttf",
        ])

    # 去重并忽略不存在的候选项；找不到系统 Emoji 字体时由调用方决定如何显示原字符
    unique_paths: list[Path] = []
    for path in candidates:
        if path.is_file() and path not in unique_paths:
            unique_paths.append(path)
    return unique_paths

def render_system_emoji(symbol: str, icon_size: int) -> Image.Image | None: # 将系统 Emoji 字体中的原始字形渲染为透明背景图像
    # 彩色 Emoji 字体可能是可缩放的 COLR，也可能只有固定字号的 CBDT/SBIX 位图，
    # 因此依次尝试当前 DPI 所需字号及常见的位图 strike 尺寸
    font_sizes = list(dict.fromkeys([max(icon_size * 4, 64), 160, 128, 109, 96, 64, 48, 32]))

    for font_path in color_emoji_font_paths():
        for font_size in font_sizes:
            try:
                font = ImageFont.truetype(str(font_path), font_size)
                measuring_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                measuring_draw = ImageDraw.Draw(measuring_image)
                bounds = measuring_draw.textbbox((0, 0), symbol, font=font, embedded_color=True)
                width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
                if width <= 0 or height <= 0:
                    continue

                padding = max(round(font_size * 0.08), 2)
                rendered = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
                draw = ImageDraw.Draw(rendered)
                draw.text(
                    (padding - bounds[0], padding - bounds[1]),
                    symbol,
                    font=font,
                    fill=(128, 128, 128, 255), # 仅供没有嵌入颜色层的字形使用；系统自带的彩色或灰白图层会保留原貌
                    embedded_color=True,
                )
                content_bounds = rendered.getbbox()
                if not content_bounds:
                    continue
                rendered = rendered.crop(content_bounds)

                fit_size = max(icon_size - 2, 1)
                scale = min(fit_size / rendered.width, fit_size / rendered.height)
                resized = rendered.resize(
                    (max(round(rendered.width * scale), 1), max(round(rendered.height * scale), 1)),
                    Image.Resampling.LANCZOS,
                )
                icon = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
                icon.alpha_composite(resized, ((icon_size - resized.width) // 2, (icon_size - resized.height) // 2))
                return icon
            except (OSError, ValueError):
                continue
    return None

def draw_theme_icon_fallback(target_theme: str, icon_size: int) -> Image.Image: # 绘制无须系统字体的月亮或太阳图标
    # 先以 4 倍尺寸绘制再缩小，使曲线和斜线在高 DPI 与普通屏幕上都保持平滑
    draw_scale = icon_size / 4
    icon = Image.new("RGBA", (icon_size * 4, icon_size * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)

    if target_theme == "dark": # 蓝色月牙表示点击后切换到深色模式
        draw.ellipse(
            (round(2.2 * draw_scale), round(1.4 * draw_scale), round(13.6 * draw_scale), round(14.6 * draw_scale)),
            fill="#5b8def",
        )
        draw.ellipse(
            (round(5.4 * draw_scale), round(0.4 * draw_scale), round(15.2 * draw_scale), round(11.8 * draw_scale)),
            fill=(0, 0, 0, 0),
        )
    else: # 暖黄色太阳表示点击后切换到浅色模式
        center = 8 * draw_scale
        ray_inner = 5.3 * draw_scale
        ray_outer = 7.2 * draw_scale
        ray_width = max(round(1.25 * draw_scale), 1)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            start = (center + math.cos(radians) * ray_inner, center + math.sin(radians) * ray_inner)
            end = (center + math.cos(radians) * ray_outer, center + math.sin(radians) * ray_outer)
            draw.line((start, end), fill="#f0b429", width=ray_width)
        radius = 3.2 * draw_scale
        draw.ellipse((center - radius, center - radius, center + radius, center + radius), fill="#f0b429")

    return icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

def make_theme_icon_image(target_theme: str, icon_size: int) -> Image.Image: # 优先使用系统 Emoji 的原始字形，无法渲染时使用几何图标
    symbol = "🌙" if target_theme == "dark" else "☀️"
    emoji_icon = render_system_emoji(symbol, icon_size)
    if emoji_icon is not None:
        return emoji_icon
    return draw_theme_icon_fallback(target_theme, icon_size)

def fit_cover_image(image: Image.Image, size: tuple[int, int]) -> Image.Image: # 按原始比例将封面居中放进透明画布
    cover = ImageOps.exif_transpose(image).convert("RGBA")
    cover.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(cover, ((size[0] - cover.width) // 2, (size[1] - cover.height) // 2))
    return canvas

def parse(url: str, bookmarks: bool) -> list[tuple[str, str, str, list[dict]]] | None: # 解析资源，获取资源下载链接
    try:
        resources_info: list[tuple[str, str, str, list[dict]]] = []

        # 1. 提取 URL 中的 contentId 与 contentType
        content_id: str | None = None
        content_type: str | None = None

        params = parse_qs(urlparse(url, 'https').query)
        if "contentId" in params:
            content_id = params["contentId"][0]
        else:
            return None

        if "contentType" in params:
            content_type = params["contentType"][0]
        else:
            content_type = "assets_document"

        # 2. 获取资源的信息
        # 返回数据示例：
        """
        {
            "id": "4f64356a-8df7-4579-9400-e32c9a7f6718",
            // ...
            "ti_items": [
                {
                    "ti_md5": "497110473b106d28651c41c14aa6d942",
                    "ti_size": 13075391,
                    "ti_storage": "cs_path:${ref-path}/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf", // 资源文件地址
                    "ti_storages": [
                        "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf",
                        "https://r2-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf",
                        "https://r3-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf"
                    ],
                    "ti_file_flag": "source",
                    "ti_is_source_file": true,
                    // ...
                    "ti_format": "pdf",
                    // ...
                },
                {
                    // ...（和上一个元素组成一样）
                }
            ],
            // ...
            "title": "（根据2022年版课程标准修订）义务教育教科书·语文八年级上册",
            // ...
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

        data: dict = response.json()

        # 3. 获取资源标题、下载链接及章节目录
        def get_resource_info(resource_data) -> tuple[str, str, str, list[dict]] | None:
            title: str = resource_data.get("title")
            resource_url: str | None = None

            for item in resource_data["ti_items"]: # 寻找存有资源链接列表的项
                if item["ti_is_source_file"]: # 获取并构造资源的 URL
                    resource_url = item.get("ti_storage")
                    if resource_url:
                        resource_url = resource_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn")
                    else:
                        resource_url = next((url for url in item["ti_storages"] if url), None)
                        if not resource_url:
                            continue
                    format: str = item.get("ti_format") or "pdf"
                    if format == "folder":
                       continue
                    break

            if not resource_url:
                return None

            # 通过 ebook_mapping + tree 接口组合获取章节目录
            chapters: list[dict] = []
            if bookmarks:
                try:
                    mapping_url: str | None = None
                    for item in resource_data["ti_items"]:
                        if item["ti_file_flag"] == "ebook_mapping":
                            mapping_url = item.get("ti_storage") # 形如 https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/*.pkg/ebook_mapping.txt
                            if mapping_url:
                                mapping_url = mapping_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn")
                            else:
                                mapping_url = next((url for url in item["ti_storages"] if url), None)
                            break

                    if mapping_url:
                        # a. 下载 mapping 文件获取页码和 ebook_id
                        map_resp = session.get(mapping_url)
                        map_data: dict = map_resp.json()
                        ebook_id: str = map_data.get("ebook_id")

                        # 构建 node_id 到 page_number 的映射字典
                        # 格式: [{ "node_id": "...", "page_number": 1 }, ...]
                        page_map: list[dict] = []
                        if map_data.get("mappings"):
                            for m in map_data["mappings"]:
                                page_map.append({"node_id": m["node_id"], "page_number": m.get("page_number", 1) })

                        # b. 如果有 ebook_id，在课程接口下载完整的目录树（tree API）
                        if ebook_id:
                            tree_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/{ebook_id}.json", headers=headers)
                            tree_data: list[dict] | dict = tree_resp.json()

                            # 递归函数：合并 tree 的标题和 mapping 的页码
                            def process_tree_nodes(nodes: list[dict]) -> list[dict]:
                                result: list[dict] = []
                                for node in nodes:
                                    # 从 page_map 中找页码，找不到为 None
                                    page_num: int = next((m["page_number"] for m in page_map if m["node_id"] == node["id"]), None)
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
                            elif isinstance(tree_data, dict) and tree_data.get("child_nodes"):
                                chapters = process_tree_nodes(tree_data["child_nodes"])

                        # c. 兜底方案：如果获取 tree 失败，仅使用 mapping 生成纯页码索引
                        if not chapters:
                            page_map.sort(key=lambda x: x["page_number"])
                            for i, m in enumerate(page_map):
                                chapters.append({
                                    "title": f"第 {i+1} 节 (P{m['page_number']})",
                                    "page_index": m["page_number"]
                                })

                except Exception as e:
                    print_error(e)
                    chapters = []

            return title, resource_url, format, chapters

        resource_info = get_resource_info(data)
        if resource_info:
            resources_info.append(resource_info)

        if content_type == "thematic_course": # 专题课程
            resources_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/thematic_course/{content_id}/resources/list.json")
            resources_data: list[dict] = resources_resp.json()
            for resource in resources_data:
                resource_info = get_resource_info(resource)
                if resource_info:
                    resources_info.append(resource_info)

        return resources_info

    except Exception as e:
        print_error(e)
        return None

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
        messagebox.showinfo("提示", f'资源链接已复制到剪贴板。\n注意：链接可能无法直接下载，需要加上以下 HTTP 标头才能下载{"（以下标头含有隐私信息，请勿分享给别人）" if access_token else ""}：\n\nAuthorization: Bearer {access_token or "0"}\nX-ND-AUTH: MAC id="{access_token or "0"}",nonce="0",mac="0"')

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
        title, resource_url, format, chapters = resource
        default_filename = title or "download"
        if dir_path:
            save_path = os.path.join(dir_path, f"{default_filename}.{format}") # 构造完整路径
        else:
            save_path = filedialog.asksaveasfilename(defaultextension=f".{format}", filetypes=[(f"{format.upper()} 文件", f"*.{format}"), ("所有文件", "*.*")], initialfile=default_filename) # 选择保存路径
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

    try:
        response = session.get(url, headers=headers, stream=True)

        if not response.ok: # 服务器返回表示错误的 HTTP 状态码
            current_state["finished"] = True
            current_state["failed_reason"] = f"服务器返回 HTTP 状态码 {response.status_code}" + "，Access Token 可能已过期或无效，请重新设置" if response.status_code == 401 or response.status_code == 403 else ""
        else:
            temp_path = f"{save_path}.tmp"
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

def add_bookmarks(pdf_path: str, chapters: list[dict]) -> None: # 给 PDF 添加书签
    try:
        if not chapters:
            return
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)

        def add_chapter(chapter_list: list[dict], parent=None): # 递归添加书签的内部函数
            for chapter in chapter_list:
                title: str = chapter.get("title", "未知章节")
                p_index: int | None = chapter.get("page_index")
                if p_index is None: # 如果值为 None 或者不存在，跳过这个书签
                    print_error(ValueError(f"章节 “{title}” 的页码索引无效，已跳过此处书签添加"))
                    continue

                try: # 尝试将其转为整数并减 1（pypdf 页码从 0 开始)
                    page_num: int = int(p_index) - 1
                except (ValueError, TypeError) as e: # 如果转换失败，跳过这个书签
                    print_error(e)
                    continue

                if page_num < 0 or page_num >= len(writer.pages):
                    continue

                # 添加书签，其中 parent 是父级书签对象，用于处理多级目录
                bookmark = writer.add_outline_item(title, page_num, parent=parent)

                # 如果有子章节（children），递归添加
                if chapter.get("children"):
                    add_chapter(chapter["children"], parent=bookmark)

        # 开始处理章节数据
        add_chapter(chapters)

        # 保存修改后的文件
        with open(pdf_path, "wb") as f:
            writer.write(f)

    except Exception as e:
        print_error(e)

def show_access_token_window() -> None: # 打开输入 Access Token 的窗口
    token_window = tk.Toplevel(root)
    token_window.title("设置 Access Token")
    token_window.resizable(False, False) # 禁止调整窗口大小
    # 让窗口自动根据控件自适应尺寸；如需最小尺寸可用 token_window.minsize(...)
    token_window.focus() # 自动获得焦点
    token_window.grab_set() # 阻止主窗口操作
    token_window.bind("<Escape>", lambda event: token_window.destroy()) # 绑定 Esc 键关闭窗口

    # 设置一个 Frame 用于留白，使布局更美观
    frame = ttk.Frame(token_window, padding=round(20 * ui_scale))
    frame.pack(fill="both", expand=True)

    # 提示文本
    label = ttk.Label(frame, text="请粘贴从浏览器获取的 Access Token", style="Heading.TLabel")
    label.pack(anchor="w")
    hint_label = ttk.Label(frame, text="需要先在国家中小学智慧教育平台登录账号，该凭据仅保存在本机。", style="Caption.TLabel")
    hint_label.pack(anchor="w", pady=(round(2 * ui_scale), round(10 * ui_scale)))

    # 创建多行 Text（外面套一层卡片，以获得与其他控件一致的圆角边框）
    token_card = make_card(frame)
    token_card.pack(fill="both", expand=True)
    token_text = tk.Text(token_card, width=50, height=4, wrap="char", undo=True, font="AppBodyFont")
    token_text.pack(fill="both", expand=True)
    register_themed_widget(token_text)
    bind_context_menu(token_text)
    bind_tab_navigation(token_text)
    token_text.focus()

    # 若已存在全局 token，则填入
    if access_token:
        token_text.insert("1.0", access_token)

    # 按下 Enter 键，保存 Access Token，并屏蔽换行事件
    def return_save_token(event: tk.Event) -> str:
        save_token()
        return "break"

    token_text.bind("<Return>", return_save_token)
    token_text.bind("<Shift-Return>", lambda e: "break") # 按下 Shift＋Enter 也不换行，直接屏蔽

    # 保存按钮
    def save_token():
        user_token = token_text.get("1.0", "end").strip()
        tip_info = set_access_token(user_token)
        download_btn.config(state="normal") # 重新启用下载按钮
        messagebox.showinfo("保存成功", tip_info)
        token_window.destroy()

    # 帮助按钮
    def show_token_help():
        help_win = tk.Toplevel(token_window)
        help_win.title("获取 Access Token 方法")
        help_win.resizable(False, False) # 禁止调整窗口大小
        help_win.focus() # 自动获得焦点
        help_win.grab_set() # 阻止主窗口操作
        help_win.bind("<Escape>", lambda event: help_win.destroy()) # 绑定 Esc 键关闭窗口

        help_frame = ttk.Frame(help_win, padding=round(20 * ui_scale))
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

        # 只读文本区，支持选择复制（外面套一层卡片，以获得与其他控件一致的圆角边框）
        help_card = make_card(help_frame)
        help_card.pack(fill="both", expand=True)
        txt = tk.Text(help_card, width=88, height=24, wrap="word", font="AppCaptionFont", padx=round(4 * ui_scale), pady=round(4 * ui_scale))
        txt.insert("1.0", help_text)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        register_themed_widget(txt)

        # 同样可给帮助文本区绑定右键菜单
        help_menu = tk.Menu(txt, tearoff=0)
        register_themed_widget(help_menu)
        help_menu.add_command(label="复制 (C)", underline=4, accelerator="Ctrl+C", command=lambda: txt.event_generate("<<Copy>>"))
        help_menu.add_command(label="全选 (A)", underline=4, accelerator="Ctrl+A", command=lambda: txt.event_generate("<<SelectAll>>"))

        def show_help_menu(event: tk.Event) -> None:
            help_menu.post(event.x_root, event.y_root)
            help_menu.bind("<FocusOut>", lambda e: help_menu.unpost())
            root.bind("<Button-1>", lambda e: help_menu.unpost(), add="+")

        txt.bind("<Button-3>", show_help_menu)
        txt.bind("<Menu>", show_help_menu) # BUG: 按下菜单键不起作用
        if os_name == "Darwin":
            txt.bind("<Control-Button-1>", show_help_menu)
            txt.bind("<Button-2>", show_help_menu)

        center_window(help_win, token_window) # 让帮助弹窗居中
        apply_titlebar_theme(help_win) # 让标题栏跟随主题
        help_win.lift() # 置顶可见

    # 底部按钮栏：左侧为帮助按钮，右侧为保存按钮
    button_frame = ttk.Frame(frame)
    button_frame.pack(fill="x", pady=(round(12 * ui_scale), 0))
    help_btn = ttk.Button(button_frame, text="如何获取？", command=show_token_help)
    help_btn.pack(side="left")
    save_btn = ttk.Button(button_frame, text="保存", style=ACCENT_BUTTON_STYLE, command=save_token)
    save_btn.pack(side="right")

    center_window(token_window, root) # 让弹窗居中
    apply_titlebar_theme(token_window) # 让标题栏跟随主题
    token_window.lift() # 置顶可见

REGISTRY_PATH = "Software\\tchMaterial-parser" # Windows 下存放配置的注册表键
CONFIG_KEYS = { "access_token": "AccessToken", "theme": "Theme" } # 配置项名称到注册表值名称的映射（JSON 文件直接使用配置项名称）

def config_file_path() -> str: # 获取配置文件路径（非 Windows 平台）
    if os_name == "Linux": # 在 Linux 上，配置存放于 ~/.config/tchMaterial-parser/data.json
        return os.path.join(os.path.expanduser("~"), ".config", "tchMaterial-parser", "data.json") # os.path.expanduser("~") 为当前用户主目录
    if os_name == "Darwin": # 在 macOS 上，配置存放于 ~/Library/Application Support/tchMaterial-parser/data.json
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "tchMaterial-parser", "data.json")
    raise RuntimeError(f"不支持的操作系统：{os_name}")

def config_location() -> str: # 获取配置存放位置的描述文本，用于提示用户
    if os_name == "Windows":
        return f"注册表：HKEY_CURRENT_USER\\{REGISTRY_PATH}"
    if os_name == "Linux":
        return "文件：~/.config/tchMaterial-parser/data.json"
    if os_name == "Darwin":
        return "文件：~/Library/Application Support/tchMaterial-parser/data.json"
    raise RuntimeError(f"不支持的操作系统：{os_name}")

def load_config() -> dict[str, str]: # 读取本地存储的配置
    config: dict[str, str] = {}

    if os_name == "Windows": # 在 Windows 上，从注册表读取
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ) as key:
                for name, value_name in CONFIG_KEYS.items():
                    try:
                        value, _ = winreg.QueryValueEx(key, value_name)
                    except FileNotFoundError: # 该配置项尚未写入
                        continue
                    if not isinstance(value, str):
                        raise TypeError(f"配置项 {name} 必须是字符串")
                    config[name] = value
        except FileNotFoundError: # 注册表键不存在，即从未保存过配置
            return config
        return config

    target_file = config_file_path() # 在其他平台上，从 JSON 文件读取
    if not os.path.exists(target_file): # 文件不存在表示尚未保存过配置
        return config
    with open(target_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError("配置文件的根节点必须是对象")
    for name in CONFIG_KEYS:
        if name not in data:
            continue
        value = data[name]
        if not isinstance(value, str):
            raise TypeError(f"配置项 {name} 必须是字符串")
        config[name] = value
    return config

def save_config(**updates: str) -> None: # 保存配置，并与已有配置合并
    if os_name == "Windows": # 在 Windows 上，写入注册表
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as key:
            for name, value in updates.items():
                winreg.SetValueEx(key, CONFIG_KEYS[name], 0, winreg.REG_SZ, value)
        return

    target_file = config_file_path() # 在其他平台上，写入 JSON 文件
    data = load_config() # 先读取已有配置，避免覆盖其他配置项
    data.update(updates)
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_access_token(config: dict[str, str]) -> None: # 从已读取的配置中加载 Access Token
    global access_token

    token = config.get("access_token")
    if token:
        access_token = token
        headers["Authorization"] = f"Bearer {access_token}"
        headers["X-ND-AUTH"] = f'MAC id="{access_token}",nonce="0",mac="0"'

def set_access_token(token: str) -> str: # 设置并更新 Access Token
    global access_token
    save_config(access_token=token)
    access_token = token
    headers["Authorization"] = f"Bearer {access_token or '0'}"
    headers["X-ND-AUTH"] = f'MAC id="{access_token or "0"}",nonce="0",mac="0"'
    return f"Access Token 已保存！\n已写入{config_location()}"

class resource_helper: # 获取网站上资源的数据
    def parse_hierarchy(self, hierarchy: list) -> dict: # 解析层级数据
        if not hierarchy: # 如果没有层级数据，返回空字典
            return {}

        parsed = {}
        for h in hierarchy:
            for ch in h["children"]:
                parsed[ch["tag_id"]] = { "display_name": ch["tag_name"], "children": self.parse_hierarchy(ch["hierarchies"]) }
        return parsed

    def fetch_book_list(self) -> dict: # 获取课本列表
        # 获取电子课本层级数据
        tags_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json")
        tags_data: dict = tags_resp.json()
        parsed_hier = self.parse_hierarchy(tags_data["hierarchies"])

        # 获取电子课本 URL 列表
        list_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json")
        list_data: list[str] = list_resp.json()["urls"].split(",")

        # 获取电子课本列表
        for url in list_data:
            book_resp = session.get(url)
            book_data: list[dict] = book_resp.json()
            for book in book_data:
                if book.get("tag_paths"): # 某些非课本资料的 tag_paths 属性为空数组
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

    def fetch_lesson_list(self) -> dict: # 获取课件列表
        # 获取课件层级数据
        tags_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/national_lesson_tag.json")
        tags_data: dict = tags_resp.json()
        parsed_hier = self.parse_hierarchy([{ "children": [{ "tag_id": "__internal_national_lesson", "hierarchies": tags_data["hierarchies"], "tag_name": "课件资源" }] }])

        # 获取课件 URL 列表
        list_resp = session.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson/teachingmaterials/version/data_version.json")
        list_data: list[str] = list_resp.json()["urls"]

        # 获取课件列表
        for url in list_data:
            lesson_resp = session.get(url)
            lesson_data: list[dict] = lesson_resp.json()
            for lesson in lesson_data:
                if lesson.get("tag_list"):
                    # 解析课件层级数据
                    tag_paths: list[str] = [tag["tag_id"] for tag in sorted(lesson["tag_list"], key=lambda tag: tag["order_num"])]

                    # 分别解析课件层级（tag_paths 为乱序）
                    def parse_tag_path(hier: dict) -> dict:
                        for p in tag_paths:
                            if hier["children"] and hier["children"].get(p):
                                return parse_tag_path(hier["children"].get(p))
                        return hier

                    hier = parse_tag_path(parsed_hier["__internal_national_lesson"])
                    if not hier["children"]:
                        hier["children"] = {}

                    lesson["display_name"] = lesson["title"] if "title" in lesson else lesson["name"] if "name" in lesson else f"(未知课件 {lesson['id']})"

                    hier["children"][lesson["id"]] = lesson

        return parsed_hier

    def fetch_resource_list(self) -> dict: # 获取资源列表
        book_hier = self.fetch_book_list()
        # lesson_hier = self.fetch_lesson_list()
        return { **book_hier }

def filter_resource_items(items: dict[str, dict], query: str) -> dict[str, dict]: # 按完整分类路径筛选资源树
    keywords = query.casefold().split()
    if not keywords:
        return items

    def filter_branch(branch: dict[str, dict], parent_names: tuple[str, ...]) -> dict[str, dict]:
        matches: dict[str, dict] = {}
        for option_id, option_data in branch.items():
            path_names = (*parent_names, option_data["display_name"])
            children = option_data.get("children", {})
            if children:
                filtered_children = filter_branch(children, path_names)
                if filtered_children:
                    matches[option_id] = { **option_data, "children": filtered_children }
            elif all(keyword in " ".join(path_names).casefold() for keyword in keywords):
                matches[option_id] = option_data
        return matches

    return filter_branch(items, ())

def count_resource_items(items: dict[str, dict]) -> int: # 统计资源树中的末级资源数量
    return sum(
        count_resource_items(children) if (children := option_data.get("children", {})) else 1
        for option_data in items.values()
    )

def thread_it(func: callable, *args: tuple, **kwargs: dict) -> None: # 打包函数到线程
    t = threading.Thread(target=func, args=args, kwargs=kwargs)
    t.daemon = True
    t.start()

def ui_call(func: callable, *args: tuple, **kwargs: dict) -> None: # 在主线程执行 Tkinter UI 更新
    if app_closing:
        return

    try:
        root.after(0, lambda: not app_closing and func(*args, **kwargs))
    except Exception:
        # 主窗口销毁后，root.after 会抛错，直接忽略即可
        pass

def pick_ui_font_family() -> str: # 选择一个合适的字体
    try:
        available = set(tkfont.families(root)) # 获取所有字体的列表
    except Exception:
        return "TkDefaultFont"

    for name in ("Microsoft YaHei UI", "微软雅黑", "PingFang SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "Arial Unicode MS"): # 在这些字体中选择一个可用的字体
        if name in available:
            return name

    try: # 若上述字体都不可用，则返回默认字体
        return tkfont.nametofont("TkDefaultFont").actual("family")
    except Exception:
        return "TkDefaultFont"

def setup_fonts() -> None: # 创建（或更新）所有命名字体，使其使用中文字体并跟随缩放因子
    # 此处直接调用 Tcl 命令而不使用 tkinter.font.Font，因为后者创建的字体会随 Python 对象被垃圾回收而一并删除
    existing_fonts: tuple[str, ...] = root.tk.splitlist(root.tk.call("font", "names"))
    for name, (size, bold) in { **APP_FONTS, **SV_FONTS }.items():
        # 字号取负值表示以像素为单位，从而避开 tk scaling 的二次缩放，与 sv-ttk 的取值方式保持一致
        options = ("-family", ui_font_family, "-size", -round(size * ui_scale), "-weight", "bold" if bold else "normal")
        root.tk.call("font", "configure" if name in existing_fonts else "create", name, *options)

def detect_system_theme() -> str: # 获取系统当前使用的是浅色还是深色模式
    try:
        if os_name == "Windows" and winreg: # 在 Windows 上，读取注册表中的个性化设置
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize") as key:
                apps_use_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if apps_use_light_theme else "dark"
        elif os_name == "Darwin": # 在 macOS 上，读取全局偏好设置（仅深色模式下存在 AppleInterfaceStyle 项，其值为 Dark）
            result = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True, timeout=2)
            return "dark" if result.stdout.strip() == "Dark" else "light"
        elif os_name == "Linux": # 在 Linux 上，读取 GNOME 的配色方案设置（其值形如 'prefer-dark'）
            try:
                result = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"], capture_output=True, text=True, timeout=2)
            except FileNotFoundError: # 非 GNOME 桌面环境多半没有 gsettings，此时无从判断，按浅色处理
                return "light"
            return "dark" if "dark" in result.stdout.lower() else "light"
    except Exception as e:
        print_error(e)

    return "light" # 其余情况一律视为浅色模式

def apply_titlebar_theme(window: tk.Tk | tk.Toplevel) -> None: # 在 Windows 上让窗口标题栏跟随深色模式
    # macOS 与 Linux 的标题栏由系统或窗口管理器绘制，没有对应的接口可供单独设置，
    # 因此在这两个平台上，手动切换主题后标题栏仍会保持系统的深浅色，只有窗口内部会随之改变
    if os_name != "Windows" or not ctypes:
        return

    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) # Tk 窗口的父窗口才是带标题栏的那个窗口
        value = ctypes.c_int(1 if current_theme == "dark" else 0)
        for attribute in (20, 19): # DWMWA_USE_IMMERSIVE_DARK_MODE，20 适用于 Windows 10 20H1 及更新版本，19 适用于更早的版本
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break

        if window.winfo_viewable(): # 让窗口宽度增减 1 像素，以强制标题栏重绘，否则切换主题后标题栏不会立即更新
            width, height = window.winfo_width(), window.winfo_height()
            window.geometry(f"{width + 1}x{height}")
            window.update_idletasks()
            window.geometry(f"{width}x{height}")

    except Exception as e:
        print_error(e)

def register_themed_widget(widget: tk.Widget) -> None: # 登记需要跟随主题手动调整配色的 tk 原生控件（ttk 控件由主题自动处理），并立即应用当前配色
    themed_widgets.add(widget)
    widget.bind("<Destroy>", lambda _event: themed_widgets.discard(widget), add="+")
    apply_widget_theme(widget)

def apply_widget_theme(widget: tk.Widget) -> None: # 为单个 tk 原生控件应用当前主题配色
    if isinstance(widget, tk.Menu):
        widget.configure(background=current_colors["surface"], foreground=current_colors["fg"], activebackground=current_colors["selbg"], activeforeground=current_colors["selfg"], activeborderwidth=0, borderwidth=0, relief="flat")
    else: # tk.Text
        widget.configure(background=current_colors["surface"], foreground=current_colors["fg"], insertbackground=current_colors["fg"], selectbackground=current_colors["selbg"], selectforeground=current_colors["selfg"], borderwidth=0, relief="flat", highlightthickness=0)

def apply_theme(theme: str) -> None: # 应用浅色/深色主题
    global current_theme, current_colors
    current_theme = theme
    current_colors = THEME_COLORS[current_theme]

    sv_ttk.set_theme(current_theme, root)
    # sv-ttk 把配色函数绑定在 <<ThemeChanged>> 事件上，但一来该事件不会送达尚无 ttk 子控件的根窗口（首次启动时配色不生效），
    # 二来后面每次调用 ttk::style configure 都会重新触发该事件，从而把下面的自定义配色覆盖回去。因此解绑它，改为在此显式调用一次。
    root.unbind_class("Tk", "<<ThemeChanged>>")
    root.tk.call("configure_colors")

    setup_fonts() # sv-ttk 会在首次加载主题时创建自己的命名字体，因此字体要在其之后设置
    style = ttk.Style(root)

    # 切换主题会重置以下自定义样式，因此每次应用主题时都要重新设置
    style.configure(".", font="AppBodyFont", background=current_colors["page"])
    style.configure("Title.TLabel", font="AppTitleFont")
    style.configure("Heading.TLabel", font="AppStrongFont")
    style.configure("Caption.TLabel", font="AppCaptionFont", foreground=current_colors["muted"])
    style.configure("Description.TLabel", font="AppBodyFont", foreground=current_colors["muted"], background=current_colors["surface"]) # 该样式用于卡片内的文字，背景需与卡片一致
    style.configure("Custom.Treeview", font="AppBodyFont", background=current_colors["surface"], rowheight=round(38 * ui_scale))
    button_padding = (round(10 * ui_scale), round(4 * ui_scale)) # 增加纵向留白，使按钮在各 DPI 下保持接近 Win11 的紧凑比例
    style.configure("TButton", padding=button_padding)
    style.configure("Accent.TButton", padding=button_padding)

    for widget in themed_widgets:
        apply_widget_theme(widget)

    apply_titlebar_theme(root)

def make_card(parent: tk.Widget, **kwargs: dict) -> ttk.Frame: # 创建卡片式容器，用于给 tk 原生控件加上圆角边框
    return ttk.Frame(parent, style="Card.TFrame", **kwargs)

def bind_context_menu(parent: tk.Widget) -> None: # 创建右键菜单
    context_menu = tk.Menu(parent, tearoff=0)
    register_themed_widget(context_menu)
    context_menu.add_command(label="撤销 (U)", underline=4, accelerator="Ctrl+Z", command=lambda: parent.event_generate("<<Undo>>"))
    context_menu.add_separator()
    context_menu.add_command(label="剪切 (T)", underline=4, accelerator="Ctrl+X", command=lambda: parent.event_generate("<<Cut>>"))
    context_menu.add_command(label="复制 (C)", underline=4, accelerator="Ctrl+C", command=lambda: parent.event_generate("<<Copy>>"))
    context_menu.add_command(label="粘贴 (P)", underline=4, accelerator="Ctrl+V", command=lambda: parent.event_generate("<<Paste>>"))
    context_menu.add_separator()
    context_menu.add_command(label="全选 (A)", underline=4, accelerator="Ctrl+A", command=lambda: parent.event_generate("<<SelectAll>>"))

    def show_context_menu(event: tk.Event) -> None:
        context_menu.post(event.x_root, event.y_root)
        context_menu.bind("<FocusOut>", lambda e: context_menu.unpost()) # 绑定失焦事件，失焦时自动关闭菜单
        root.bind("<Button-1>", lambda e: context_menu.unpost(), add="+") # 绑定左键点击事件，点击其他地方也关闭菜单

    # 绑定右键菜单到文本框（3 代表鼠标的右键按钮）
    parent.bind("<Button-3>", show_context_menu)
    parent.bind("<Menu>", show_context_menu) # BUG: 按下菜单键不起作用
    if os_name == "Darwin":
        parent.bind("<Control-Button-1>", show_context_menu)
        parent.bind("<Button-2>", show_context_menu)

def auto_hide_scrollbar(scrollbar: ttk.Scrollbar, first: str, last: str) -> None: # 根据内容自动显示或隐藏滚动条
    scrollbar.set(first, last)
    if first == "0.0" and last == "1.0":
        scrollbar.grid_remove()
    else:
        scrollbar.grid()

def bind_tab_navigation(widget: tk.Widget) -> None: # 绑定 Tab 键导航，避免当按下 Tab 键时输入制表符
    def focus_next_widget(event: tk.Event) -> str:
        next_widget = event.widget.tk_focusNext()
        if next_widget:
            next_widget.focus_set()
        return "break"
    def focus_prev_widget(event: tk.Event) -> str:
        prev_widget = event.widget.tk_focusPrev()
        if prev_widget:
            prev_widget.focus_set()
        return "break"
    widget.bind("<Tab>", focus_next_widget)
    widget.bind("<Shift-Tab>", focus_prev_widget)

def center_window(window: tk.Tk | tk.Toplevel, parent: tk.Tk | tk.Toplevel | None = None) -> None: # 让窗口居中
    window.update_idletasks()
    x = parent.winfo_x() + parent.winfo_width() // 2 - window.winfo_width() // 2 if parent else window.winfo_screenwidth() // 2 - window.winfo_width() // 2
    y = parent.winfo_y() + parent.winfo_height() // 2 - window.winfo_height() // 2 if parent else window.winfo_screenheight() // 2 - window.winfo_height() // 2
    window.geometry(f"+{x}+{y}")

session = requests.Session() # 初始化请求
download_states: list[dict] = [] # 初始化下载状态
app_closing = False
access_token: str | None = None
headers = { "Authorization": "Bearer 0", "X-ND-AUTH": 'MAC id="0",nonce="0",mac="0"' } # 设置请求头部，包含认证信息，其中 “MAC id” 即为 Access Token，“nonce” 和 “mac” 不可缺省但可为任意非空值
session.proxies = {} # 全局忽略代理

ui_scale = 1.0 # 界面缩放因子，在 main() 中根据屏幕 DPI 计算
current_theme = "light" # 当前主题
current_colors: dict[str, str] = {} # 当前主题的配色，在 apply_theme() 中填充
themed_widgets: set[tk.Widget] = set() # 当前仍存在且需要跟随主题调整配色的 tk 原生控件

# 主题配色。surface 为 sv-ttk 卡片贴图的填充色，须与之一致，否则卡片内会出现色差；
# page 比 surface 略深，用作页面底色，让卡片、列表、文本框显出层次
THEME_COLORS = {
    "light": { "page": "#f2f2f2", "surface": "#fafafa", "fg": "#1c1c1c", "muted": "#5d5d5d", "selbg": "#2f60d8", "selfg": "#ffffff" },
    "dark": { "page": "#141414", "surface": "#1c1c1c", "fg": "#fafafa", "muted": "#a0a0a0", "selbg": "#2f60d8", "selfg": "#ffffff" },
}

ACCENT_BUTTON_STYLE = "Accent.TButton"
SWITCH_STYLE = "Switch.TCheckbutton"

# 本程序使用的命名字体，格式为 字体名称: (基准字号（像素）, 是否加粗)
APP_FONTS = { "AppCaptionFont": (12, False), "AppBodyFont": (14, False), "AppStrongFont": (14, True), "AppTitleFont": (20, True) }
# sv-ttk 内置的命名字体，需要一并改为中文字体（其默认字体不含中文字形），基准字号与 sv-ttk 原始取值保持一致
SV_FONTS = {
    "SunValleyCaptionFont": (12, False), "SunValleyBodyFont": (14, False), "SunValleyBodyStrongFont": (14, True), "SunValleyBodyLargeFont": (18, False),
    "SunValleySubtitleFont": (20, True), "SunValleyTitleFont": (28, True), "SunValleyTitleLargeFont": (40, True), "SunValleyDisplayFont": (68, True),
}


# 主界面上方的功能说明：Emoji 与正文分开渲染以保留系统字体的完整字形
DESCRIPTION_ITEMS = (
    ("📌", "在右侧的文本框中输入一个或多个资源页面的网址（每行一个），或直接在左侧的列表中选择资源。"),
    ("🔗️", "网址示例：https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=..."),
    ("📥", "点击 “下载” 解析并下载资源；点击 “解析并复制” 则只把资源的直链复制到剪贴板。"),
    ("ℹ️", "为了更可靠地下载，建议先点击 “设置 Token”，参照里面的说明完成设置。"),
)


def main() -> None: # 程序入口：初始化界面并进入主循环
    # 下列变量在本函数中创建，但前面定义的函数会通过全局作用域访问它们，
    # 因此必须声明为 global，否则相关功能会在运行时抛出 NameError
    global root, ui_font_family, ui_scale, url_text, bookmark_var
    global download_btn, download_progress_bar, progress_label

    scale: float | None = None

    # 在 Windows 上进行高 DPI 适配
    if os_name == "Windows" and win32print and win32gui and win32con and win32api and ctypes:
        scale = round(win32print.GetDeviceCaps(win32gui.GetDC(0), win32con.DESKTOPHORZRES) / win32api.GetSystemMetrics(0), 2) # 获取当前的缩放因子

        # 调用 API 设置成由应用程序缩放
        try: # Windows 8.1 或更新
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception: # Windows 8 或更老
            ctypes.windll.user32.SetProcessDPIAware()

    # 配置只读取一次，同时用于恢复 Access Token 与主题
    saved_config = load_config()
    load_access_token(saved_config)

    # 获取资源列表
    try:
        resource_list = resource_helper().fetch_resource_list()
    except Exception as e:
        print_error(e)
        resource_list = {}
        messagebox.showwarning("警告", "获取资源列表失败，请手动填写资源链接，或重新打开本程序") # 弹出警告窗口

    # GUI
    root = tk.Tk()

    ui_font_family = pick_ui_font_family()

    if not scale: # 若获取缩放因子失败，通过 Tkinter 估算缩放因子
        try:
            scale: float = round(root.winfo_fpixels("1i") / 96.0, 2)
        except Exception:
            scale = 1.0
    root.tk.call("tk", "scaling", scale / 0.75) # 设置缩放因子

    # 界面元素的尺寸另算：Tk 在 macOS 上把屏幕 DPI 报成 72（即上面算出的 scale 为 0.75），
    # 部分 X server 也是如此，若直接拿来乘字号会把界面缩小四分之一。macOS 会自行处理 Retina 缩放，故固定取 1
    ui_scale = 1.0 if os_name == "Darwin" else max(scale, 1.0)
    root.title(f"国家中小学智慧教育平台 资源下载工具 {VERSION}") # 设置窗口标题

    # 应用主题：优先沿用用户上次手动切换的结果，否则跟随系统的浅色/深色模式
    saved_theme = saved_config.get("theme")
    apply_theme(saved_theme if saved_theme in THEME_COLORS else detect_system_theme())

    def set_icon() -> Image.Image: # 设置窗口图标，并返回图标图像以供标题栏左侧的 logo 复用
        # 源码运行时直接读取 assets 中的原图；打包后由 spec 的 datas 收集到相同的相对路径
        with Image.open(resource_path("assets", "window_icon.png")) as icon:
            icon_image = icon.copy()
        photo = ImageTk.PhotoImage(icon_image)
        root.iconphoto(True, photo)
        setattr(root, "_icon_ref", photo) # 为防止图片被垃圾回收，保存引用
        return icon_image

    icon_image = set_icon() # 设置窗口图标

    def on_closing() -> None: # 处理窗口关闭事件
        global app_closing

        if app_closing:
            return

        if not all(state["finished"] for state in download_states): # 当正在下载时，询问用户
            if not messagebox.askokcancel("提示", "下载任务未完成，是否退出？"):
                return

        app_closing = True

        current_process = psutil.Process(os.getpid()) # 获取自身的进程 ID
        child_processes = current_process.children(recursive=True) # 获取自身的所有子进程

        for child in child_processes: # 结束所有子进程
            try:
                child.terminate() # 结束进程
            except Exception: # 进程可能已经结束
                pass

        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_closing) # 注册窗口关闭事件的处理函数

    # 创建一个容器框架
    container_frame = ttk.Frame(root, padding=(round(24 * ui_scale), round(18 * ui_scale))) # 通过内边距在窗口四周留白
    container_frame.pack(expand=True, fill="both")

    # 顶部：左侧为图标与标题，右侧为主题切换按钮
    header_frame = ttk.Frame(container_frame)
    header_frame.pack(fill="x")

    # 标题左侧的图标复用已经成功读取的窗口图标
    logo_image = icon_image.copy()
    logo_image.thumbnail((round(42 * ui_scale), round(42 * ui_scale)), Image.Resampling.LANCZOS)
    logo_photo = ImageTk.PhotoImage(logo_image)
    logo_label = ttk.Label(header_frame, image=logo_photo)
    logo_label.pack(side="left", padx=(0, round(12 * ui_scale)))
    setattr(logo_label, "_image_ref", logo_photo) # 为防止图片被垃圾回收，保存引用

    title_frame = ttk.Frame(header_frame)
    title_frame.pack(side="left")
    title_label = ttk.Label(title_frame, text="国家中小学智慧教育平台 资源下载工具", style="Title.TLabel") # 添加标题标签
    title_label.pack(anchor="w")
    subtitle_label = ttk.Label(title_frame, text=f"{VERSION} · 批量下载 · PDF 书签 · 免费开源", style="Caption.TLabel") # 添加副标题标签
    subtitle_label.pack(anchor="w")

    theme_icons: dict[str, ImageTk.PhotoImage] = {} # 缓存两个主题图标，并同时防止 Tk 图片被垃圾回收

    def update_theme_button() -> None: # 更新按钮文字与图标，使其表示点击后将切换到的主题
        target_theme = "dark" if current_theme == "light" else "light"
        if target_theme not in theme_icons:
            icon_size = max(round(16 * ui_scale), 16)
            theme_icons[target_theme] = ImageTk.PhotoImage(make_theme_icon_image(target_theme, icon_size))
        theme_btn.config(
            text=" 深色" if target_theme == "dark" else " 浅色",
            image=theme_icons[target_theme],
            compound="left",
        )

    def switch_theme() -> None: # 切换浅色/深色主题
        target_theme = "light" if current_theme == "dark" else "dark"
        save_config(theme=target_theme)
        apply_theme(target_theme)
        update_theme_button()

    theme_btn = ttk.Button(header_frame, style="Toolbutton", command=switch_theme)
    theme_btn.pack(side="right", anchor="n")
    update_theme_button()

    # 功能说明
    description_padding = round(14 * ui_scale)
    description_icon_gap = round(8 * ui_scale)
    description_icon_size = max(round(18 * ui_scale), 18)
    description_card = make_card(container_frame, padding=(description_padding, round(10 * ui_scale)))
    description_card.pack(fill="x", pady=(round(14 * ui_scale), 0))
    description_card.columnconfigure(1, weight=1)

    description_icons: list[ImageTk.PhotoImage] = [] # 保存 Tk 图片引用，避免图标被垃圾回收
    description_labels: list[ttk.Label] = []
    for row, (symbol, text) in enumerate(DESCRIPTION_ITEMS):
        row_padding = (0, round(1 * ui_scale)) if row < len(DESCRIPTION_ITEMS) - 1 else 0
        emoji_image = render_system_emoji(symbol, description_icon_size)
        if emoji_image is not None:
            photo = ImageTk.PhotoImage(emoji_image)
            description_icons.append(photo)
            description_icon_label = ttk.Label(description_card, image=photo, style="Description.TLabel")
        else: # Pillow 无法读取系统 Emoji 字体时，退回改版前由 Tk 直接显示字符的方式
            description_icon_label = ttk.Label(description_card, text=symbol, style="Description.TLabel")
        description_icon_label.grid(
            row=row,
            column=0,
            sticky="n",
            padx=(0, description_icon_gap),
            pady=row_padding,
        )
        description_label = ttk.Label(
            description_card,
            text=text,
            style="Description.TLabel",
            justify="left",
            anchor="w",
            wraplength=round(760 * ui_scale),
        )
        description_label.grid(row=row, column=1, sticky="ew", pady=row_padding)
        description_labels.append(description_label)

    def on_description_resize(event: tk.Event) -> None: # 窗口宽度变化时，同步调整说明文字的折行宽度，避免文字被裁切
        occupied_width = description_padding * 2 + description_icon_size + description_icon_gap + round(4 * ui_scale)
        wraplength = max(event.width - occupied_width, round(220 * ui_scale))
        for label in description_labels:
            if int(label.cget("wraplength")) != wraplength:
                label.config(wraplength=wraplength)

    description_card.bind("<Configure>", on_description_resize)

    paned = ttk.PanedWindow(container_frame, orient="horizontal") # 创建水平分割窗口（在底部各栏之后才打包，见文件末尾）
    treeview_pane = ttk.Frame(paned, padding=(0, 0, round(8 * ui_scale), 0)) # 创建树视图的子框架，放在分割窗口的左侧（右侧留出与分割条之间的间距）
    treeview_pane.columnconfigure(0, weight=1)
    treeview_pane.rowconfigure(2, weight=1)
    text_pane = ttk.Frame(paned, padding=(round(8 * ui_scale), 0, 0, 0)) # 创建文本框的子框架，放在分割窗口的右侧
    text_pane.columnconfigure(0, weight=1)
    text_pane.rowconfigure(1, weight=1)
    paned.add(treeview_pane)
    paned.add(text_pane)
    paned.update_idletasks()
    root.after(0, lambda: paned.sashpos(0, int(paned.winfo_width() * 0.4))) # 设置分割条的位置为窗口宽度的 40%（不能使用 ui_call）

    treeview_header = ttk.Frame(treeview_pane)
    treeview_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, round(6 * ui_scale)))
    treeview_header.columnconfigure(0, weight=1)
    treeview_label = ttk.Label(treeview_header, text="资源列表", style="Heading.TLabel") # 添加树视图标签
    treeview_label.grid(row=0, column=0, sticky="w")
    search_status_label = ttk.Label(treeview_header, style="Caption.TLabel")
    search_status_label.grid(row=0, column=1, sticky="e")

    search_frame = ttk.Frame(treeview_pane)
    search_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, round(8 * ui_scale)))
    search_frame.columnconfigure(1, weight=1)
    ttk.Label(search_frame, text="搜索").grid(row=0, column=0, padx=(0, round(8 * ui_scale)))
    search_var = tk.StringVar()
    search_entry = ttk.Entry(search_frame, textvariable=search_var)
    search_entry.grid(row=0, column=1, sticky="ew")
    clear_search_btn = ttk.Button(search_frame, text="清除", width=5, command=lambda: search_var.set(""))
    clear_search_btn.grid(row=0, column=2, padx=(round(6 * ui_scale), 0))

    treeview = ttk.Treeview(treeview_pane, style="Custom.Treeview", show="tree", selectmode="browse", height=12) # 创建树视图，使用自定义样式（该样式在 apply_theme() 中配置），隐藏列标题，设置选择模式为单选
    treeview.column("#0", stretch=False)
    treeview.grid(row=2, column=0, sticky="nsew")
    treeview_scrollbar = ttk.Scrollbar(treeview_pane, orient="vertical", command=treeview.yview)
    treeview_scrollbar.grid(row=2, column=1, sticky="ns")
    treeview_horizontal_scrollbar = ttk.Scrollbar(treeview_pane, orient="horizontal", command=treeview.xview)
    treeview.configure(xscrollcommand=lambda f, l: auto_hide_scrollbar(treeview_horizontal_scrollbar, f, l))
    treeview_horizontal_scrollbar.grid(row=3, column=0, sticky="ew")

    url_label = ttk.Label(text_pane, text="资源页面网址", style="Heading.TLabel") # 添加 URL 标签
    url_label.grid(row=0, column=0, sticky="w", pady=(0, round(6 * ui_scale)))
    url_card = make_card(text_pane) # 外面套一层卡片，使输入框拥有与树视图一致的圆角边框
    url_card.grid(row=1, column=0, sticky="nsew")
    url_text = tk.Text(url_card, width=40, height=8, wrap="char", undo=True, font="AppBodyFont", padx=round(6 * ui_scale), pady=round(4 * ui_scale)) # 添加 URL 输入框
    url_text.pack(fill="both", expand=True)
    register_themed_widget(url_text) # 让输入框的配色跟随主题
    bind_context_menu(url_text) # 为 URL 输入框创建右键菜单
    bind_tab_navigation(url_text) # 绑定 Tab 键导航
    text_scrollbar = ttk.Scrollbar(text_pane, orient="vertical", command=url_text.yview)
    url_text.configure(yscrollcommand=lambda f, l: auto_hide_scrollbar(text_scrollbar, f, l))
    text_scrollbar.grid(row=1, column=1, sticky="ns")
    url_text.focus()

    tree_item_data: dict[str, dict] = {} # 键为树项 ID，值为资源数据
    tree_item_paths: dict[str, tuple[str, ...]] = {} # 保存完整分类路径，用于悬停提示
    tree_item_images: dict[str, ImageTk.PhotoImage] = {} # 缓存已加载的封面，筛选后继续复用
    tree_preview_images: dict[str, ImageTk.PhotoImage] = {} # 缓存大尺寸封面，用于悬停预览
    loading_tree_images: set[str] = set()
    tree_font = tkfont.nametofont("AppBodyFont")
    tree_cover_size = (round(26 * ui_scale), round(28 * ui_scale))
    tree_cover_gap = round(8 * ui_scale) # 用透明区域拉开封面与标题，避免改变封面尺寸
    preview_cover_size = (round(80 * ui_scale), round(112 * ui_scale))
    tree_content_width = 0

    def get_tree_cover_gap(display_name: str) -> int: # 名称以中文左括号开头时不添加封面与标题间隔
        return 0 if display_name.startswith("（") else tree_cover_gap

    def build_tree_items(parent: str, items: dict[str, dict], parent_names: tuple[str, ...], expand_all: bool) -> None: # 递归构建树视图项
        nonlocal tree_content_width
        for option_id, option_data in items.items():
            item_id = f"{parent}:{option_id}" if parent else option_id
            display_name = option_data["display_name"]
            path_names = (*parent_names, display_name)
            tree_item_data[item_id] = option_data
            tree_item_paths[item_id] = path_names
            treeview.insert(
                parent,
                "end",
                iid=item_id,
                text=display_name,
                image=tree_item_images.get(item_id, ""),
                open=expand_all or not parent,
            )
            children: dict[str, dict] = option_data.get("children", {})
            if children: # 如果有子项，递归构建子树项
                build_tree_items(item_id, children, path_names, expand_all)

            depth_width = len(path_names) * round(20 * ui_scale)
            image_width = tree_cover_size[0] + get_tree_cover_gap(display_name) + round(4 * ui_scale) if option_data.get("custom_properties", {}).get("thumbnails") else 0
            tree_content_width = max(tree_content_width, depth_width + image_width + tree_font.measure(display_name) + round(20 * ui_scale))

    def resize_tree_column(width: int) -> None: # 让树列至少铺满可视区域，内容过长时启用横向滚动
        treeview.column("#0", width=max(tree_content_width, width - round(2 * ui_scale)))

    def apply_tree_icon(item_id: str, image: Image.Image | None) -> None:
        loading_tree_images.discard(item_id)
        if image is None:
            return
        tree_image = fit_cover_image(image, tree_cover_size)
        cover_gap = get_tree_cover_gap(tree_item_data[item_id]["display_name"])
        if cover_gap:
            tree_image = ImageOps.expand(tree_image, border=(0, 0, cover_gap, 0), fill=(0, 0, 0, 0))
        tree_item_images[item_id] = ImageTk.PhotoImage(tree_image)
        tree_preview_images[item_id] = ImageTk.PhotoImage(image)
        if treeview.exists(item_id):
            treeview.item(item_id, image=tree_item_images[item_id])

    def load_tree_icon(item_id: str, url: str) -> None: # 在线程中下载封面，在主线程中更新控件
        try:
            resp = session.get(url)
            if not resp.ok:
                ui_call(apply_tree_icon, item_id, None)
                return
            image = fit_cover_image(Image.open(io.BytesIO(resp.content)), preview_cover_size)
            ui_call(apply_tree_icon, item_id, image)
        except Exception as e:
            print_error(e)
            ui_call(apply_tree_icon, item_id, None)

    def queue_tree_icon(item_id: str) -> None:
        resource_data = tree_item_data[item_id]
        thumbnails = resource_data.get("custom_properties", {}).get("thumbnails")
        if thumbnails and item_id not in tree_item_images and item_id not in loading_tree_images:
            loading_tree_images.add(item_id)
            thread_it(load_tree_icon, item_id, thumbnails[0])

    def load_visible_tree_icons() -> None: # 搜索或滚动后只加载当前可见资源的封面
        for item_id, resource_data in tree_item_data.items():
            if not resource_data.get("children") and treeview.bbox(item_id):
                queue_tree_icon(item_id)

    def on_tree_view_change(first: str, last: str) -> None:
        auto_hide_scrollbar(treeview_scrollbar, first, last)
        root.after_idle(load_visible_tree_icons)

    def refresh_resource_tree() -> None: # 根据搜索词重建树视图
        nonlocal tree_content_width
        query = search_var.get().strip()
        visible_items = filter_resource_items(resource_list, query)

        leave_tree()
        treeview.delete(*treeview.get_children())
        tree_item_data.clear()
        tree_item_paths.clear()
        tree_content_width = 0
        build_tree_items("", visible_items, (), expand_all=bool(query))
        resize_tree_column(treeview.winfo_width())

        result_count = count_resource_items(visible_items)
        search_status_label.config(text=f"{result_count} 项" if result_count else "无匹配资源")
        clear_search_btn.state(["!disabled"] if query else ["disabled"])
        root.after_idle(load_visible_tree_icons)

    def on_tree_select(event: tk.Event) -> None: # 处理树视图选择事件
        selection = treeview.selection()
        if not selection:
            return

        item = selection[0]
        children = treeview.get_children(item)
        if children: # 如果选中的项有子项，则加载子项的预览图，否则插入 URL
            for child in children: # 遍历子项，设置子项的图片
                queue_tree_icon(child)
        else:
            resource_data = tree_item_data.get(item)
            if not resource_data:
                return

            resource_type = resource_data.get("resource_type_code") or "assets_document"
            content_id = resource_data.get("content_id") or item.split(":")[-1]
            if resource_type == "teachingmaterials":
                url = f"https://basic.smartedu.cn/syncClassroom?defaultTag={"%2F".join(item.split(':')[1:])}"
            else:
                url = f"https://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={content_id}&catalogType=tchMaterial&subCatalog=tchMaterial"

            url_text_content = url_text.get("1.0", "end")[:-1] # 获取 URL 输入框的内容，去掉最后一个换行符
            if url in url_text_content.splitlines(): # 如果 URL 已经存在于输入框中，则不再插入
                return
            if not url_text_content or url_text_content[-1] == "\n": # URL 输入框为空或最后一个字符为换行符时，插入的内容前面不加换行
                url_text.insert("end", url)
            else:
                url_text.insert("end", f"\n{url}")
            url_text.see("end") # 滚动到文本框底部

    tooltip_window: tk.Toplevel | None = None
    tooltip_after_id: str | None = None
    hovered_tree_item = ""

    def hide_tree_tooltip() -> None:
        nonlocal tooltip_window, tooltip_after_id
        if tooltip_after_id:
            root.after_cancel(tooltip_after_id)
            tooltip_after_id = None
        if tooltip_window:
            tooltip_window.destroy()
            tooltip_window = None

    def show_tree_tooltip(item_id: str, x_root: int, y_root: int) -> None: # 悬停时显示完整名称与分类路径
        nonlocal tooltip_window, tooltip_after_id
        tooltip_after_id = None
        if item_id != hovered_tree_item or not treeview.exists(item_id):
            return

        path_names = tree_item_paths[item_id]
        tooltip_window = tk.Toplevel(root)
        tooltip_window.overrideredirect(True)
        tooltip_body = tk.Frame(
            tooltip_window,
            background=current_colors["surface"],
            relief="solid",
            borderwidth=1,
            padx=round(10 * ui_scale),
            pady=round(9 * ui_scale),
        )
        tooltip_body.pack()

        preview_image = tree_preview_images.get(item_id)
        if preview_image:
            tk.Label(
                tooltip_body,
                image=preview_image,
                background=current_colors["surface"],
                borderwidth=0,
            ).grid(row=0, column=0, rowspan=2, padx=(0, round(12 * ui_scale)))

        text_column = 1 if preview_image else 0
        tk.Label(
            tooltip_body,
            text=path_names[-1],
            justify="left",
            anchor="w",
            wraplength=round(360 * ui_scale),
            font="AppStrongFont",
            background=current_colors["surface"],
            foreground=current_colors["fg"],
        ).grid(row=0, column=text_column, sticky="new")
        if len(path_names) > 1:
            tk.Label(
                tooltip_body,
                text=" › ".join(path_names[:-1]),
                justify="left",
                anchor="w",
                wraplength=round(360 * ui_scale),
                font="AppCaptionFont",
                background=current_colors["surface"],
                foreground=current_colors["muted"],
            ).grid(row=1, column=text_column, sticky="sew", pady=(round(8 * ui_scale), 0))

        tooltip_window.update_idletasks()
        x = min(x_root + round(12 * ui_scale), root.winfo_screenwidth() - tooltip_window.winfo_reqwidth())
        y = min(y_root + round(18 * ui_scale), root.winfo_screenheight() - tooltip_window.winfo_reqheight())
        tooltip_window.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def on_tree_motion(event: tk.Event) -> None:
        nonlocal hovered_tree_item, tooltip_after_id
        item_id = treeview.identify_row(event.y)
        if item_id == hovered_tree_item:
            return
        hide_tree_tooltip()
        hovered_tree_item = item_id
        if item_id:
            tooltip_after_id = root.after(
                450,
                lambda: show_tree_tooltip(item_id, event.x_root, event.y_root),
            )

    def leave_tree() -> None:
        nonlocal hovered_tree_item
        hovered_tree_item = ""
        hide_tree_tooltip()

    search_after_id: str | None = None

    def schedule_search(*_args: str) -> None: # 输入停止片刻后执行筛选，避免连续重建树视图
        nonlocal search_after_id
        if search_after_id:
            root.after_cancel(search_after_id)

        def run_search() -> None:
            nonlocal search_after_id
            search_after_id = None
            refresh_resource_tree()

        search_after_id = root.after(150, run_search)

    def focus_search(_event: tk.Event) -> str:
        search_entry.focus_set()
        search_entry.selection_range(0, "end")
        return "break"

    def scroll_tree_horizontally(steps: float) -> str:
        hide_tree_tooltip()
        first, last = treeview.xview()
        treeview.xview_moveto(first + steps * (last - first) * 0.2)
        return "break"

    def on_tree_shift_mousewheel(event: tk.Event) -> str:
        delta_unit = 1 if os_name == "Darwin" else 120
        return scroll_tree_horizontally(-event.delta / delta_unit)

    refresh_resource_tree() # 初始展示完整资源树并展开一级目录
    search_var.trace_add("write", schedule_search)
    treeview.configure(yscrollcommand=on_tree_view_change)
    treeview.bind("<<TreeviewSelect>>", on_tree_select)
    treeview.bind("<<TreeviewOpen>>", lambda _event: root.after_idle(load_visible_tree_icons))
    treeview.bind("<Configure>", lambda event: resize_tree_column(event.width))
    treeview.bind("<Motion>", on_tree_motion)
    treeview.bind("<Leave>", lambda _event: leave_tree())
    treeview.bind("<ButtonPress>", lambda _event: hide_tree_tooltip())
    treeview.bind("<Shift-MouseWheel>", on_tree_shift_mousewheel)
    treeview.bind("<Shift-Button-4>", lambda _event: scroll_tree_horizontally(-1))
    treeview.bind("<Shift-Button-5>", lambda _event: scroll_tree_horizontally(1))
    search_entry.bind("<Escape>", lambda _event: search_var.set(""))
    root.bind("<Control-f>", focus_search)
    if os_name == "Darwin":
        root.bind("<Command-f>", focus_search)

    # 底部状态栏：下载进度标签与横向铺满的进度条
    # 底部各栏都以 side="bottom" 先行打包，最后才打包上方的内容区，这样窗口高度不足时被压缩的是内容区，而不是把底部控件挤出窗口
    status_frame = ttk.Frame(container_frame)
    status_frame.pack(side="bottom", fill="x", pady=(round(12 * ui_scale), 0))
    status_frame.columnconfigure(0, weight=1)

    progress_label = ttk.Label(status_frame, text="等待下载", style="Caption.TLabel") # 添加下载进度标签
    progress_label.grid(row=0, column=0, sticky="w")
    download_progress_bar = ttk.Progressbar(status_frame, mode="determinate") # 添加下载进度条
    download_progress_bar.grid(row=1, column=0, sticky="ew", pady=(round(6 * ui_scale), 0))

    # 底部操作栏：左侧为辅助操作，右侧为主要操作
    button_frame = ttk.Frame(container_frame)
    button_frame.pack(side="bottom", fill="x")
    ttk.Separator(container_frame, orient="horizontal").pack(side="bottom", fill="x", pady=(round(16 * ui_scale), round(14 * ui_scale))) # 用分隔线把操作区与内容区分开

    # 按钮：设置 Token
    token_btn = ttk.Button(button_frame, text="设置 Token", command=show_access_token_window)
    token_btn.pack(side="left")

    # 开关：添加书签
    bookmark_var = tk.BooleanVar(value=True)
    bookmark_checkbox = ttk.Checkbutton(button_frame, text="添加 PDF 书签", variable=bookmark_var, style=SWITCH_STYLE)
    bookmark_checkbox.pack(side="left", padx=(round(16 * ui_scale), 0))

    # 按钮：下载（作为主要操作，使用强调色）
    download_btn = ttk.Button(button_frame, text="下载", style=ACCENT_BUTTON_STYLE, width=9, command=download)
    download_btn.pack(side="right")

    # 按钮：解析并复制
    copy_btn = ttk.Button(button_frame, text="解析并复制", width=9, command=parse_and_copy)
    copy_btn.pack(side="right", padx=(0, round(8 * ui_scale)))

    # 最后打包内容区，使其占据剩余的全部空间
    paned.pack(side="top", fill="both", expand=True, pady=(round(14 * ui_scale), 0))

    # 设置窗口初始尺寸与最小尺寸（不超过屏幕可用范围）
    root.geometry(f"{min(round(1000 * ui_scale), root.winfo_screenwidth() - round(80 * ui_scale))}x{min(round(700 * ui_scale), root.winfo_screenheight() - round(120 * ui_scale))}")
    root.minsize(round(680 * ui_scale), round(540 * ui_scale))

    center_window(root) # 让窗口居中
    root.mainloop() # 开始主循环


if __name__ == "__main__":
    main()
