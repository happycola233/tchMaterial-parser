# -*- coding: utf-8 -*-
# 通用控件辅助：右键菜单、滚动条自动隐藏、Tab 键导航与窗口居中

import tkinter as tk
from tkinter import ttk
from typing import Literal

from . import runtime
from .theme import register_themed_widget
from ..platform_utils import os_name

root_handlers_bound: dict[tk.Menu, bool] = {} # 用于记录每个右键菜单是否已绑定根窗口事件，避免重复绑定

def bind_context_menu(parent: tk.Widget, type: Literal["normal", "noundo", "readonly"] = "normal") -> None: # 创建右键菜单
    context_menu = tk.Menu(parent, tearoff=False, font="AppBodyFont")
    register_themed_widget(context_menu)
    root_handlers_bound[context_menu] = False # 初始化为未绑定根窗口事件
    if type == "normal":
        context_menu.add_command(label="撤销 (U)", underline=4, accelerator="Ctrl+Z", command=lambda: parent.event_generate("<<Undo>>"))
        context_menu.add_separator()
    if type != "readonly":
        context_menu.add_command(label="剪切 (T)", underline=4, accelerator="Ctrl+X", command=lambda: parent.event_generate("<<Cut>>"))
    context_menu.add_command(label="复制 (C)", underline=4, accelerator="Ctrl+C", command=lambda: parent.event_generate("<<Copy>>"))
    if type != "readonly":
        context_menu.add_command(label="粘贴 (P)", underline=4, accelerator="Ctrl+V", command=lambda: parent.event_generate("<<Paste>>"))
        context_menu.add_separator()
    context_menu.add_command(label="全选 (A)", underline=4, accelerator="Ctrl+A", command=lambda: parent.event_generate("<<SelectAll>>"))

    def show_context_menu(event: tk.Event, keyboard: bool = False) -> None:
        if not keyboard and event.x_root >= 0 and event.y_root >= 0:
            context_menu.post(event.x_root, event.y_root)
        else: # 通过键盘打开菜单或 x_root 与 y_root 无效时
            try: # 优先尝试在插入点（文本控件）位置显示菜单
                bbox = parent.bbox("insert") # 此处可能抛异常或返回 None
                if bbox:
                    bx, by, bw, bh = bbox
                    x_root = parent.winfo_rootx() + bx
                    y_root = parent.winfo_rooty() + by + bh
                else:
                    raise Exception("无法获取插入点位置")
            except Exception: # 再尝试使用鼠标指针位置（如果有）
                px, py = parent.winfo_pointerx(), parent.winfo_pointery()
                if px >= 0 and py >= 0:
                    x_root, y_root = px, py
                else: # 最后回退到控件中心
                    x_root = round(parent.winfo_rootx() + parent.winfo_width() // 2)
                    y_root = round(parent.winfo_rooty() + parent.winfo_height() // 2)
            context_menu.post(x_root, y_root)
        context_menu.bind("<FocusOut>", lambda e: context_menu.unpost()) # 绑定失焦事件，失焦时自动关闭菜单
        context_menu.bind("<Escape>", lambda e: context_menu.unpost(), add="+") # 绑定 Esc 键，按下时关闭菜单
        if not root_handlers_bound.get(context_menu):
            root_handlers_bound[context_menu] = True
            runtime.root.bind("<Escape>", lambda e: context_menu.unpost(), add="+") # 绑定 Esc 键，按下时关闭菜单
            runtime.root.bind("<Button-1>", lambda e: context_menu.unpost(), add="+") # 绑定左键点击事件，点击其他地方也关闭菜单

    # 绑定右键菜单到文本框
    parent.bind("<Button-3>", show_context_menu) # 鼠标右键
    parent.bind("<Menu>", lambda e: show_context_menu(e, True)) # BUG: 按下菜单键不起作用
    parent.bind("<Shift-F10>", lambda e: show_context_menu(e, True))
    if os_name == "Darwin":
        parent.bind("<Control-Button-1>", show_context_menu) # Command + 鼠标左键
        parent.bind("<Button-2>", show_context_menu) # 鼠标中键

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
