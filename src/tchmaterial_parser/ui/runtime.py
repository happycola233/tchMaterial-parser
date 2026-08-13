# -*- coding: utf-8 -*-
# 界面运行时状态：主窗口、缩放因子，以及跨线程的调度封装

import threading
import tkinter as tk

ui_scale = 1.0 # 界面缩放因子，由 app.py 根据屏幕 DPI 写入
app_closing = False

def bind_root(window: tk.Tk) -> None: # 由 app.py 在创建主窗口后写入，供其余模块调度到主线程
    global root
    root = window

def scaled(size: float) -> int: # 按缩放因子换算界面元素的像素尺寸
    return round(size * ui_scale)

def thread_it(func: callable, *args: tuple, **kwargs: dict) -> None: # 打包函数到线程
    t = threading.Thread(target=func, args=args, kwargs=kwargs)
    t.daemon = True
    t.start()

def ui_call(func: callable, *args: tuple, **kwargs: dict) -> str | None: # 在主线程执行 Tkinter UI 更新
    if app_closing:
        return None

    try:
        return root.after_idle(lambda: not app_closing and func(*args, **kwargs))
    except Exception:
        # 主窗口销毁后，root.after_idle 会抛错，直接忽略即可
        return None
