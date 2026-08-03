# -*- coding: utf-8 -*-
# 程序主流程：初始化配置、拉取资源列表、装配主窗口并进入主循环

import os, sys
import tkinter as tk
from tkinter import ttk, messagebox
import psutil
from PIL import Image, ImageTk

from . import __version__
from .catalog import ResourceHelper
from .config import load_access_token, load_config, save_config
from .images import make_icon_image, render_system_emoji
from .platform_utils import ctypes, os_name, print_error, resource_path, win32api, win32con, win32gui, win32print
from .ui import download_panel, runtime, theme
from .ui.about_window import show_about_window
from .ui.resource_tree import build_resource_tree
from .ui.runtime import scaled
from .ui.token_window import show_access_token_window
from .ui.widgets import auto_hide_scrollbar, bind_context_menu, bind_tab_navigation, center_window, make_card

# 主界面上方的功能说明：Emoji 与正文分开渲染以保留系统字体的完整字形
DESCRIPTION_ITEMS = (
    ("📌", "在右侧的文本框中输入一个或多个资源页面的网址（每行一个），或直接在左侧的列表中选择资源。"),
    ("🔗️", "网址示例：https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=..."),
    ("📥", "点击 “下载” 解析并下载资源；点击 “解析并复制” 则只把资源的直链复制到剪贴板。"),
    ("ℹ️", "为了更可靠地下载，建议先点击 “设置 Token”，参照里面的说明完成设置。"),
)


def main() -> None: # 程序入口：初始化界面并进入主循环
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
        resource_list = ResourceHelper().fetch_resource_list()
    except Exception as e:
        print_error(e)
        resource_list = {}
        messagebox.showwarning("警告", "获取资源列表失败，请手动填写资源链接，或重新打开本程序") # 弹出警告窗口

    # GUI
    root = tk.Tk()

    # 主窗口、界面字体与缩放因子由本函数创建，但其余模块也要用到，
    # 因此在此写入对应模块，供它们通过 runtime.root、runtime.ui_scale 等访问
    runtime.bind_root(root)
    theme.bind_font_family(theme.pick_ui_font_family())

    if not scale: # 若获取缩放因子失败，通过 Tkinter 估算缩放因子
        try:
            scale = round(root.winfo_fpixels("1i") / 96.0, 2)
        except Exception:
            scale = 1.0

    # 在 macOS 上，Tk 通常把 DPI 报成 72（即 scale 为 0.75），需把 scaling 除以 0.75 以补偿；
    # 其它平台直接使用检测到的缩放因子（至少 1.0）
    if os_name == "Darwin":
        root.tk.call("tk", "scaling", max(scale / 0.75, 1.0))
    else:
        root.tk.call("tk", "scaling", max(scale, 1.0))

    # 界面元素的尺寸另算：macOS 会自行处理 Retina 缩放，故固定取 1
    runtime.ui_scale = 1.0 if os_name == "Darwin" else max(scale, 1.0)
    root.title(f"国家中小学智慧教育平台 资源下载工具 {__version__}") # 设置窗口标题

    # 应用主题：优先沿用用户上次手动切换的结果，否则跟随系统的浅色/深色模式
    saved_theme = saved_config.get("theme")
    theme.apply_theme(saved_theme)

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
        if runtime.app_closing:
            return

        if not all(state["finished"] for state in download_panel.download_states): # 当正在下载时，询问用户
            if not messagebox.askokcancel("提示", "下载任务未完成，是否退出？"):
                return

        runtime.app_closing = True

        try:
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
        except Exception: # 获取子进程失败，直接退出当前进程
            try:
                root.destroy()
            except Exception:
                pass

            sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing) # 注册窗口关闭事件的处理函数

    # 创建一个容器框架
    container_frame = ttk.Frame(root, padding=(scaled(24), scaled(18))) # 通过内边距在窗口四周留白
    container_frame.pack(expand=True, fill="both")

    # 顶部：左侧为图标与标题，右侧为关于、主题切换按钮
    header_frame = ttk.Frame(container_frame)
    header_frame.pack(fill="x")

    # 标题左侧的图标复用已经成功读取的窗口图标
    logo_image = icon_image.copy()
    logo_image.thumbnail((scaled(42), scaled(42)), Image.Resampling.LANCZOS)
    logo_photo = ImageTk.PhotoImage(logo_image)
    logo_label = ttk.Label(header_frame, image=logo_photo)
    logo_label.pack(side="left", padx=(0, scaled(12)))
    setattr(logo_label, "_image_ref", logo_photo) # 为防止图片被垃圾回收，保存引用

    title_frame = ttk.Frame(header_frame)
    title_frame.pack(side="left")
    title_label = ttk.Label(title_frame, text="国家中小学智慧教育平台 资源下载工具", style="Title.TLabel") # 添加标题标签
    title_label.pack(anchor="w")
    subtitle_label = ttk.Label(title_frame, text=f"{__version__} · 批量下载 · PDF 书签 · 免费开源", style="Caption.TLabel") # 添加副标题标签
    subtitle_label.pack(anchor="w")

    theme_icons: dict[str, ImageTk.PhotoImage] = {} # 缓存 3 个主题图标，并同时防止 Tk 图片被垃圾回收

    def update_theme_button() -> None: # 更新按钮文字与图标，使其表示点击后将切换到的主题
        if theme.switched_theme not in theme_icons:
            icon_size = max(scaled(16), 16)
            theme_icons[theme.switched_theme] = ImageTk.PhotoImage(make_icon_image(theme.switched_theme, icon_size))
        theme_btn.config(
            text=" 浅色" if theme.switched_theme == "light" else " 深色" if theme.switched_theme == "dark" else " 跟随系统",
            image=theme_icons[theme.switched_theme],
            compound="left",
        )

    def switch_theme() -> None: # 切换主题
        target_theme = "dark" if theme.switched_theme == "light" else "light" if theme.switched_theme == "system" else "system"
        save_config(theme=target_theme)
        theme.apply_theme(target_theme)
        update_theme_button()

    header_actions = ttk.Frame(header_frame)
    header_actions.pack(side="right", anchor="n")

    # 关于按钮
    about_image = ImageTk.PhotoImage(make_icon_image("about", max(scaled(16), 16)))
    about_btn = ttk.Button(header_actions, text=" 关于", image=about_image, compound="left", style="Toolbutton", command=show_about_window)
    about_btn.pack(side="left", padx=(0, scaled(8)))

    # 切换主题按钮
    theme_btn = ttk.Button(header_actions, style="Toolbutton", command=switch_theme)
    theme_btn.pack(side="left")
    update_theme_button()

    # 功能说明
    description_padding = scaled(14)
    description_icon_gap = scaled(8)
    description_icon_size = max(scaled(18), 18)
    description_card = make_card(container_frame, padding=(description_padding, scaled(10)))
    description_card.pack(fill="x", pady=(scaled(14), 0))
    description_card.columnconfigure(1, weight=1)

    description_icons: list[ImageTk.PhotoImage] = [] # 保存 Tk 图片引用，避免图标被垃圾回收
    description_labels: list[ttk.Label] = []
    for row, (symbol, text) in enumerate(DESCRIPTION_ITEMS):
        row_padding = (0, scaled(1)) if row < len(DESCRIPTION_ITEMS) - 1 else 0
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
            wraplength=scaled(760),
        )
        description_label.grid(row=row, column=1, sticky="ew", pady=row_padding)
        description_labels.append(description_label)

    def on_description_resize(event: tk.Event) -> None: # 窗口宽度变化时，同步调整说明文字的折行宽度，避免文字被裁切
        occupied_width = description_padding * 2 + description_icon_size + description_icon_gap + scaled(4)
        wraplength = max(event.width - occupied_width, scaled(220))
        for label in description_labels:
            if int(label.cget("wraplength")) != wraplength:
                label.config(wraplength=wraplength)

    # 此处不立即绑定上面的事件，而是在所有元素加载完毕后再绑定（文件末尾）

    paned = ttk.PanedWindow(container_frame, orient="horizontal") # 创建水平分割窗口（在底部各栏之后才打包，见文件末尾）
    treeview_pane = ttk.Frame(paned, padding=(0, 0, scaled(8), 0)) # 创建树视图的子框架，放在分割窗口的左侧（右侧留出与分割条之间的间距）
    text_pane = ttk.Frame(paned, padding=(scaled(8), 0, 0, 0)) # 创建文本框的子框架，放在分割窗口的右侧
    text_pane.columnconfigure(0, weight=1)
    text_pane.rowconfigure(1, weight=1)
    paned.add(treeview_pane)
    paned.add(text_pane)
    paned.update_idletasks()
    root.after(0, lambda: paned.sashpos(0, int(paned.winfo_width() * 0.4))) # 设置分割条的位置为窗口宽度的 40%（不能使用 ui_call）

    url_label = ttk.Label(text_pane, text="资源页面网址", style="Heading.TLabel") # 添加 URL 标签
    url_label.grid(row=0, column=0, sticky="w", pady=(0, scaled(6)))
    url_card = make_card(text_pane) # 外面套一层卡片，使输入框拥有与树视图一致的圆角边框
    url_card.grid(row=1, column=0, sticky="nsew")
    url_text = tk.Text(url_card, width=40, height=8, wrap="char", undo=True, font="AppBodyFont", padx=scaled(6), pady=scaled(4)) # 添加 URL 输入框
    url_text.pack(fill="both", expand=True)
    theme.register_themed_widget(url_text) # 让输入框的配色跟随主题
    bind_context_menu(url_text) # 为 URL 输入框创建右键菜单
    bind_tab_navigation(url_text) # 绑定 Tab 键导航
    text_scrollbar = ttk.Scrollbar(text_pane, orient="vertical", command=url_text.yview)
    url_text.configure(yscrollcommand=lambda f, l: auto_hide_scrollbar(text_scrollbar, f, l))
    text_scrollbar.grid(row=1, column=1, sticky="ns")
    url_text.focus()

    build_resource_tree(treeview_pane, resource_list, url_text) # 构建左侧资源列表（需要 URL 输入框以便选中资源时写入网址）

    # 底部状态栏：下载进度标签与横向铺满的进度条
    # 底部各栏都以 side="bottom" 先行打包，最后才打包上方的内容区，这样窗口高度不足时被压缩的是内容区，而不是把底部控件挤出窗口
    status_frame = ttk.Frame(container_frame)
    status_frame.pack(side="bottom", fill="x", pady=(scaled(12), 0))
    status_frame.columnconfigure(0, weight=1)

    progress_label = ttk.Label(status_frame, text="等待下载", style="Caption.TLabel") # 添加下载进度标签
    progress_label.grid(row=0, column=0, sticky="w")
    download_progress_bar = ttk.Progressbar(status_frame, mode="determinate") # 添加下载进度条
    download_progress_bar.grid(row=1, column=0, sticky="ew", pady=(scaled(6), 0))

    # 底部操作栏：左侧为辅助操作，右侧为主要操作
    button_frame = ttk.Frame(container_frame)
    button_frame.pack(side="bottom", fill="x")
    ttk.Separator(container_frame, orient="horizontal").pack(side="bottom", fill="x", pady=(scaled(16), scaled(14))) # 用分隔线把操作区与内容区分开

    # 按钮：设置 Token
    token_btn = ttk.Button(button_frame, text="设置 Token", command=show_access_token_window)
    token_btn.pack(side="left")

    # 开关：添加 PDF 书签
    bookmark_var = tk.BooleanVar(value=True)
    bookmark_checkbox = ttk.Checkbutton(button_frame, text="添加 PDF 书签", variable=bookmark_var, style=theme.SWITCH_STYLE)
    bookmark_checkbox.pack(side="left", padx=(scaled(16), 0))

    # 按钮：下载（作为主要操作，使用强调色）
    download_btn = ttk.Button(button_frame, text="下载", style=theme.ACCENT_BUTTON_STYLE, width=9, command=download_panel.download)
    download_btn.pack(side="right")

    # 按钮：解析并复制
    copy_btn = ttk.Button(button_frame, text="解析并复制", width=9, command=download_panel.parse_and_copy)
    copy_btn.pack(side="right", padx=(0, scaled(8)))

    # 下载相关的控件全部就位后，写入下载面板模块，供其中的解析与下载流程使用
    download_panel.bind_widgets(url_text, bookmark_var, download_btn, download_progress_bar, progress_label)

    # 最后打包内容区，使其占据剩余的全部空间
    paned.pack(side="top", fill="both", expand=True, pady=(scaled(14), 0))

    # 设置窗口初始尺寸与最小尺寸（不超过屏幕可用范围）
    root.geometry(f"{min(scaled(1000), root.winfo_screenwidth() - scaled(80))}x{min(scaled(700), root.winfo_screenheight() - scaled(120))}")
    root.minsize(scaled(680), scaled(540))

    description_card.bind("<Configure>", on_description_resize)

    center_window(root) # 让窗口居中
    root.mainloop() # 开始主循环
