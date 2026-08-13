# -*- coding: utf-8 -*-
# 浅色／深色主题：配色常量、命名字体、系统主题探测与主题应用

import subprocess
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from typing import Literal
import sv_ttk # Sun Valley（Windows 11 风格）主题

from . import runtime
from .runtime import scaled
from ..platform_utils import ctypes, os_name, print_error, winreg

switched_theme = "system" # 选择的主题
current_theme = "light" # 当前主题，若 switched_theme 为 `system` 则 current_theme 为系统主题（`light` 或 `dark`）
current_colors: dict[str, str] = {} # 当前主题的配色，在 apply_theme() 中填充
themed_widgets: set[tk.Widget] = set() # 当前仍存在且需要跟随主题调整配色的 tk 原生控件

# 主题配色，surface 为 sv-ttk 卡片贴图的填充色，须与之一致，否则卡片内会出现色差；
# page 比 surface 略深，用作页面底色，让卡片、列表、文本框显出层次
THEME_COLORS = {
    "light": { "page": "#f2f2f2", "surface": "#fafafa", "fg": "#1c1c1c", "muted": "#5d5d5d", "selbg": "#2f60d8", "selfg": "#ffffff" },
    "dark": { "page": "#141414", "surface": "#1c1c1c", "fg": "#fafafa", "muted": "#a0a0a0", "selbg": "#2f60d8", "selfg": "#ffffff" },
}

ACCENT_BUTTON_STYLE = "Accent.TButton"
SWITCH_STYLE = "Switch.TCheckbutton"

# 本程序使用的命名字体，格式为 字体名称: (基准字号（像素）, 是否加粗, 是否添加下划线)
APP_FONTS = {
    "AppCaptionFont": (12, False, False), "AppBodyFont": (14, False, False), "AppStrongFont": (14, True, False),
    "AppTitleFont": (20, True, False), "AppLinkFont": (14, False, True)
}
# sv-ttk 内置的命名字体，需要一并改为中文字体（其默认字体不含中文字形），基准字号与 sv-ttk 原始取值保持一致
SV_FONTS = {
    "SunValleyCaptionFont": (12, False, False), "SunValleyBodyFont": (14, False, False),
    "SunValleyBodyStrongFont": (14, True, False), "SunValleyBodyLargeFont": (18, False, False),
    "SunValleySubtitleFont": (20, True, False), "SunValleyTitleFont": (28, True, False),
    "SunValleyTitleLargeFont": (40, True, False), "SunValleyDisplayFont": (68, True, False),
}

def bind_font_family(family: str) -> None: # 由 app.py 在选定界面字体后写入，供 setup_fonts() 使用
    global ui_font_family
    ui_font_family = family

def pick_ui_font_family() -> str: # 选择一个合适的字体
    try:
        available = set(tkfont.families(runtime.root)) # 获取所有字体的列表
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
    existing_fonts: tuple[str, ...] = runtime.root.tk.splitlist(runtime.root.tk.call("font", "names"))
    for name, (size, bold, underline) in { **APP_FONTS, **SV_FONTS }.items():
        # 字号取负值表示以像素为单位，从而避开 tk scaling 的二次缩放，与 sv-ttk 的取值方式保持一致
        options = (
            "-family", ui_font_family,
            "-size", -scaled(size),
            "-weight", "bold" if bold else "normal",
            "-underline", 1 if underline else 0,
        )
        runtime.root.tk.call("font", "configure" if name in existing_fonts else "create", name, *options)

def detect_system_theme() -> Literal["light", "dark"]: # 获取系统当前使用的是浅色还是深色模式
    try:
        if os_name == "Windows" and winreg: # 在 Windows 上，读取注册表中的个性化设置
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
            ) as key:
                apps_use_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if apps_use_light_theme else "dark"
        elif os_name == "Darwin": # 在 macOS 上，读取全局偏好设置（仅深色模式下存在 AppleInterfaceStyle 项，其值为 Dark）
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2,
            )
            return "dark" if result.stdout.strip() == "Dark" else "light"
        elif os_name == "Linux": # 在 Linux 上，读取 GNOME 的配色方案设置（其值形如 "prefer-dark"）
            try:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                    capture_output=True, text=True, timeout=2,
                )
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
    except Exception as e:
        print_error(e)

def register_themed_widget(widget: tk.Widget) -> None: # 登记需要跟随主题手动调整配色的 tk 原生控件（ttk 控件由主题自动处理），并立即应用当前配色
    themed_widgets.add(widget)
    widget.bind("<Destroy>", lambda _event: themed_widgets.discard(widget), add="+")
    apply_widget_theme(widget)

def apply_widget_theme(widget: tk.Widget) -> None: # 为单个 tk 原生控件应用当前主题配色
    if isinstance(widget, tk.Menu):
        widget.configure(
            background=current_colors["page"], foreground=current_colors["fg"],
            activebackground=current_colors["selbg"], activeforeground=current_colors["selfg"],
            relief="flat",
        )
    elif isinstance(widget, tk.Text):
        widget.configure(
            background=current_colors["surface"], foreground=current_colors["fg"],
            insertbackground=current_colors["fg"], selectbackground=current_colors["selbg"],
            selectforeground=current_colors["selfg"], borderwidth=0, relief="flat", highlightthickness=0,
        )

def apply_theme(theme: Literal["system", "light", "dark"]) -> None: # 应用浅色/深色主题
    global switched_theme, current_theme, current_colors
    switched_theme = theme if theme in ("system", "light", "dark") else "system"
    current_theme = theme if theme in THEME_COLORS else detect_system_theme()
    current_colors = THEME_COLORS[current_theme]

    sv_ttk.set_theme(current_theme, runtime.root)
    # sv-ttk 把配色函数绑定在 <<ThemeChanged>> 事件上，但一来该事件不会送达尚无 ttk 子控件的根窗口（首次启动时配色不生效），
    # 二来后面每次调用 ttk::style configure 都会重新触发该事件，从而把下面的自定义配色覆盖回去，因此解绑它，改为在此显式调用一次
    runtime.root.unbind_class("Tk", "<<ThemeChanged>>")
    runtime.root.tk.call("configure_colors")

    setup_fonts() # sv-ttk 会在首次加载主题时创建自己的命名字体，因此字体要在其之后设置
    style = ttk.Style(runtime.root)

    # 切换主题会重置以下自定义样式，因此每次应用主题时都要重新设置
    style.configure(".", font="AppBodyFont", background=current_colors["page"])
    style.configure("Title.TLabel", font="AppTitleFont")
    style.configure("Heading.TLabel", font="AppStrongFont")
    style.configure("Caption.TLabel", font="AppCaptionFont", foreground=current_colors["muted"])
    style.configure("Description.TLabel", font="AppBodyFont", foreground=current_colors["muted"], background=current_colors["surface"]) # 该样式用于卡片内的文字，背景需与卡片一致
    style.configure("Custom.Treeview", font="AppBodyFont", background=current_colors["surface"], rowheight=scaled(38))
    button_padding = (scaled(10), scaled(4)) # 增加纵向留白，使按钮在各 DPI 下保持接近 Win11 的紧凑比例
    style.configure("TButton", padding=button_padding)
    style.configure("Accent.TButton", padding=button_padding)

    for widget in themed_widgets:
        apply_widget_theme(widget)

    apply_titlebar_theme(runtime.root)
