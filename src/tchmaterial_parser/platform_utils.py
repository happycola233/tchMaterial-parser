# -*- coding: utf-8 -*-
# 平台相关的基础设施：错误输出、只读资源定位、操作系统判定与 Windows 专有库

import sys, platform, traceback
from pathlib import Path

def print_error(e: Exception) -> None: # 打印错误信息到控制台
    if sys.stderr: # 无控制台运行时 sys.stderr 可能为 None
        traceback.print_exception(e)

def resource_path(*parts: str) -> Path: # 获取源码或 PyInstaller 打包后的只读资源路径
    # 源码入口位于 src/，资源位于项目根目录；PyInstaller 则把 datas 放到 sys._MEIPASS。
    # 因此不能依赖当前工作目录或可执行文件所在目录，后者在单文件模式下并非资源的实际位置
    source_root = Path(__file__).resolve().parent.parent.parent # 本模块位于 src/tchmaterial_parser/ 下，上溯三级才是项目根目录
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
