# -*- coding: utf-8 -*-
# 关于窗口：展示程序、作者、项目地址与第三方许可证信息

import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from PIL import Image, ImageTk

from .. import __version__
from ..platform_utils import resource_path
from . import runtime, theme
from .runtime import scaled
from .widgets import center_window, make_card

PROJECT_URL = "https://github.com/happycola233/tchMaterial-parser"
LICENSE_URL = "https://github.com/happycola233/tchMaterial-parser/blob/main/LICENSE"
FLUENT_EMOJI_LICENSE_URL = "https://github.com/microsoft/fluentui-emoji/blob/main/LICENSE"

def open_url(url: str, parent: tk.Toplevel) -> None: # 使用系统默认浏览器打开链接，并在失败时向用户给出明确提示
    try:
        if not webbrowser.open_new_tab(url):
            messagebox.showerror("无法打开链接", f"请复制链接后在浏览器中打开：\n{url}", parent=parent)
    except Exception as e:
        messagebox.showerror("无法打开链接", f"请复制链接后在浏览器中打开：\n{url}\n\n{e}", parent=parent)

def make_link(parent: tk.Widget, text: str, url: str, window: tk.Toplevel) -> ttk.Label: # 创建可通过鼠标或键盘打开的链接标签
    link = ttk.Label(parent, text=text, style="AboutLink.TLabel", cursor="hand2", takefocus=True)
    link.bind("<Button-1>", lambda _event: open_url(url, window)) # 鼠标左键
    link.bind("<Return>", lambda _event: open_url(url, window)) # 回车键
    link.bind("<space>", lambda _event: open_url(url, window)) # 空格键
    return link

def show_about_window() -> None: # 打开关于窗口
    about_window = tk.Toplevel(runtime.root)
    about_window.title("关于")
    about_window.resizable(False, False)
    about_window.focus()
    about_window.transient(runtime.root)
    about_window.bind("<Escape>", lambda _event: about_window.destroy())

    # 卡片内的标签需要使用与卡片一致的底色；链接通过下划线和强调色表明可点击
    style = ttk.Style(about_window)
    style.configure(
        "AboutCard.TLabel",
        background=theme.current_colors["surface"],
        foreground=theme.current_colors["fg"],
    )
    style.configure(
        "AboutCardMuted.TLabel",
        font="AppCaptionFont",
        background=theme.current_colors["surface"],
        foreground=theme.current_colors["muted"],
    )
    style.configure(
        "AboutCardStrong.TLabel",
        font="AppStrongFont",
        background=theme.current_colors["surface"],
        foreground=theme.current_colors["fg"],
    )
    style.configure(
        "AboutLink.TLabel",
        font="AppLinkFont",
        background=theme.current_colors["surface"],
        foreground="#3973e6" if theme.current_theme == "light" else "#75a7ff",
    )

    frame = ttk.Frame(about_window, padding=scaled(24))
    frame.pack(fill="both", expand=True)

    # 程序图标与名称
    header = ttk.Frame(frame)
    header.pack(fill="x")

    with Image.open(resource_path("assets", "window_icon.png")) as icon:
        icon_image = icon.copy()
    icon_image.thumbnail((scaled(64), scaled(64)), Image.Resampling.LANCZOS)
    icon_photo = ImageTk.PhotoImage(icon_image)
    icon_label = ttk.Label(header, image=icon_photo)
    icon_label.pack(side="left", padx=(0, scaled(16)))
    setattr(icon_label, "_image_ref", icon_photo)

    title_frame = ttk.Frame(header)
    title_frame.pack(side="left", fill="x", expand=True)
    ttk.Label(title_frame, text= "国家中小学智慧教育平台 资源下载工具", style="Title.TLabel").pack(anchor="w")
    ttk.Label(title_frame, text=f"版本 {__version__}", style="Caption.TLabel").pack(anchor="w", pady=(scaled(3), 0))

    # 作者与项目地址
    info_card = make_card(frame, padding=(scaled(16), scaled(12)))
    info_card.pack(fill="x", pady=(scaled(18), 0))
    info_card.columnconfigure(1, weight=1)

    ttk.Label(info_card, text="作者", style="AboutCardMuted.TLabel").grid(
        row=0, column=0, sticky="nw", padx=(0, scaled(16))
    )
    ttk.Label(info_card, text="肥宅水水呀、晨叶梦春 及其他贡献者", style="AboutCard.TLabel").grid(
        row=0, column=1, sticky="nw"
    )

    ttk.Label(info_card, text="仓库", style="AboutCardMuted.TLabel").grid(
        row=1, column=0, sticky="nw", padx=(0, scaled(16)), pady=(scaled(8), 0)
    )
    project_link = make_link(info_card, "happycola233/tchMaterial-parser", PROJECT_URL, about_window)
    project_link.grid(row=1, column=1, sticky="nw", pady=(scaled(8), 0))

    ttk.Label(info_card, text="许可证", style="AboutCardMuted.TLabel").grid(
        row=2, column=0, sticky="nw", padx=(0, scaled(16)), pady=(scaled(8), 0)
    )
    license_link = make_link(info_card, "MIT License", LICENSE_URL, about_window)
    license_link.grid(row=2, column=1, sticky="nw", pady=(scaled(8), 0))

    # 第三方资源与许可证说明
    license_card = make_card(frame, padding=(scaled(16), scaled(12)))
    license_card.pack(fill="x", pady=(scaled(12), 0))
    ttk.Label(license_card, text="第三方许可证", style="AboutCardStrong.TLabel").pack(anchor="w")
    ttk.Label(
        license_card,
        text="本软件使用了 Microsoft Fluent Emoji 的部分图像资源，依据 MIT 许可证授权使用。\n相关图像资源及其版权归 Microsoft 所有。",
        style="AboutCard.TLabel",
        justify="left",
        wraplength=scaled(600),
    ).pack(anchor="w", pady=(scaled(6), 0))
    license_link = make_link(license_card, "查看 Microsoft Fluent Emoji 许可证 ↗", FLUENT_EMOJI_LICENSE_URL, about_window)
    license_link.pack(anchor="w", pady=(scaled(8), 0))

    # 声明
    notice_card = make_card(frame, padding=(scaled(16), scaled(12)))
    notice_card.pack(fill="x", pady=(scaled(12), 0))
    ttk.Label(notice_card, text="声明", style="AboutCardStrong.TLabel").pack(anchor="w")
    ttk.Label(
        notice_card,
        text="本软件采用 MIT 许可证开源，官方版本永久免费。\n谨防第三方付费倒卖、捆绑软件或冒充官方等行为；任何再分发行为均须保留原有版权及许可证声明。",
        style="AboutCard.TLabel",
        justify="left",
        wraplength=scaled(600),
    ).pack(anchor="w", pady=(scaled(6), 0))

    button_frame = ttk.Frame(frame)
    button_frame.pack(fill="x", pady=(scaled(16), 0))
    ttk.Button(
        button_frame, text="关闭", style=theme.ACCENT_BUTTON_STYLE, command=about_window.destroy
    ).pack(side="right")

    center_window(about_window, runtime.root)
    theme.apply_titlebar_theme(about_window)
    about_window.lift()
