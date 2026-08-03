# -*- coding: utf-8 -*-
# 设置 Access Token 的窗口，以及其中的获取方法说明窗口

import tkinter as tk
from tkinter import ttk, messagebox

from . import runtime
from .runtime import scaled
from .theme import ACCENT_BUTTON_STYLE, apply_titlebar_theme, register_themed_widget
from .widgets import bind_context_menu, bind_tab_navigation, center_window, make_card
from .. import config

def show_access_token_window() -> None: # 打开输入 Access Token 的窗口
    token_window = tk.Toplevel(runtime.root)
    token_window.title("设置 Access Token")
    token_window.resizable(False, False) # 禁止调整窗口大小
    # 让窗口自动根据控件自适应尺寸；如需最小尺寸可用 token_window.minsize(...)
    token_window.focus() # 自动获得焦点
    token_window.grab_set() # 阻止主窗口操作
    token_window.transient(runtime.root) # 使窗口依赖于主窗口
    token_window.bind("<Escape>", lambda event: token_window.destroy()) # 绑定 Esc 键关闭窗口

    # 设置一个 Frame 用于留白，使布局更美观
    frame = ttk.Frame(token_window, padding=scaled(20))
    frame.pack(fill="both", expand=True)

    # 提示文本
    label = ttk.Label(frame, text="请粘贴从浏览器获取的 Access Token", style="Heading.TLabel")
    label.pack(anchor="w")
    hint_label = ttk.Label(frame, text="需要先在国家中小学智慧教育平台登录账号，该凭据仅保存在本机。", style="Caption.TLabel")
    hint_label.pack(anchor="w", pady=(scaled(2), scaled(10)))

    # 创建多行 Text（外面套一层卡片，以获得与其他控件一致的圆角边框）
    token_card = make_card(frame)
    token_card.pack(fill="both", expand=True)
    token_text = tk.Text(token_card, width=50, height=4, wrap="char", undo=True, font="AppBodyFont", padx=scaled(6), pady=scaled(4))
    token_text.pack(fill="both", expand=True)
    register_themed_widget(token_text)
    bind_context_menu(token_text)
    bind_tab_navigation(token_text)
    token_text.focus()

    # 若已存在全局 token，则填入
    if config.access_token:
        token_text.insert("1.0", config.access_token)

    # 按下 Enter 键，保存 Access Token，并屏蔽换行事件
    def return_save_token(event: tk.Event) -> str:
        save_token()
        return "break"

    token_text.bind("<Return>", return_save_token)
    token_text.bind("<Shift-Return>", lambda e: "break") # 按下 Shift＋Enter 也不换行，直接屏蔽

    # 保存按钮
    def save_token() -> None:
        user_token = token_text.get("1.0", "end").strip()
        tip_info = config.set_access_token(user_token)
        messagebox.showinfo("保存成功", tip_info, parent=token_window)
        token_window.destroy()

    # 帮助按钮
    def show_token_help() -> None:
        help_win = tk.Toplevel(token_window)
        help_win.title("获取 Access Token 方法")
        help_win.resizable(False, False) # 禁止调整窗口大小
        help_win.focus() # 自动获得焦点
        help_win.transient(token_window) # 使窗口依赖于主窗口
        help_win.bind("<Escape>", lambda event: help_win.destroy()) # 绑定 Esc 键关闭窗口

        help_frame = ttk.Frame(help_win, padding=scaled(20))
        help_frame.pack(fill="both", expand=True)

        help_text = """\
国家中小学智慧教育平台需要登录后才可获取资源，因此要使用本程序下载资源，您需要在平台内登录账号（如没有需注册），然后获得登录凭据（Access Token）。本程序仅保存该凭据至本地。

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
        txt = tk.Text(help_card, width=88, height=24, wrap="word", font="AppCaptionFont", padx=scaled(4), pady=scaled(4))
        txt.insert("1.0", help_text)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        register_themed_widget(txt)
        bind_context_menu(txt, "readonly")

        center_window(help_win, token_window) # 让帮助弹窗居中
        apply_titlebar_theme(help_win) # 让标题栏跟随主题
        help_win.lift() # 置顶可见

    # 底部按钮栏：左侧为帮助按钮，右侧为保存按钮
    button_frame = ttk.Frame(frame)
    button_frame.pack(fill="x", pady=(scaled(12), 0))
    help_btn = ttk.Button(button_frame, text="如何获取？", command=show_token_help)
    help_btn.pack(side="left")
    save_btn = ttk.Button(button_frame, text="保存", style=ACCENT_BUTTON_STYLE, command=save_token)
    save_btn.pack(side="right")

    center_window(token_window, runtime.root) # 让弹窗居中
    apply_titlebar_theme(token_window) # 让标题栏跟随主题
    token_window.lift() # 置顶可见
