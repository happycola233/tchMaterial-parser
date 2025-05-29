#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac系统专用启动脚本
解决macOS下的兼容性问题
"""

import sys
import os
import platform

def check_macos_compatibility():
    """检查macOS兼容性"""
    if platform.system() != "Darwin":
        print("警告：此脚本专为macOS设计")
        return False
    
    # 检查Python版本
    if sys.version_info < (3, 6):
        print("错误：需要Python 3.6或更高版本")
        return False
    
    return True

def setup_macos_environment():
    """设置macOS环境"""
    # 设置环境变量以支持中文显示
    os.environ['LANG'] = 'zh_CN.UTF-8'
    os.environ['LC_ALL'] = 'zh_CN.UTF-8'
    
    # 确保Tkinter可以正常工作
    try:
        import tkinter as tk
        import tkinter.ttk as ttk
        # 创建一个测试窗口来验证Tkinter是否正常工作
        test_root = tk.Tk()
        ttk.Style(test_root)
        test_root.withdraw()  # 隐藏测试窗口
        test_root.destroy()
        print("✓ Tkinter GUI支持正常")
    except ImportError:
        print("错误：未找到Tkinter，请安装Python的Tkinter支持")
        print("可以尝试：brew install python-tk")
        return False
    except Exception as e:
        print(f"警告：Tkinter测试失败: {e}")
        print("如果遇到GUI问题，请确保已安装XQuartz或在支持GUI的环境中运行")
    
    return True

def main():
    """主函数"""
    print("=== 国家中小学智慧教育平台 资源下载工具 (macOS版) ===")
    print(f"Python版本: {sys.version}")
    print(f"操作系统: {platform.system()} {platform.release()}")
    print()
    
    # 检查兼容性
    if not check_macos_compatibility():
        sys.exit(1)
    
    # 设置环境
    if not setup_macos_environment():
        sys.exit(1)
    
    # 导入并运行主程序
    try:
        print("正在启动程序...")
        # 将src目录添加到Python路径
        project_root = os.path.dirname(os.path.abspath(__file__))
        src_path = os.path.join(project_root, 'src')
        sys.path.insert(0, src_path)
        
        # 导入主程序
        import importlib.util
        module_path = os.path.join(src_path, "tchMaterial_parser.py")
        print(f"DEBUG: Attempting to load module from: {module_path}")
        spec = importlib.util.spec_from_file_location(
            "tchMaterial_parser",
            module_path
        )
        print(f"DEBUG: spec is {spec}")
        main_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main_module)
        
    except ImportError as e:
        print(f"错误：导入模块失败: {e}")
        print("请确保所有依赖已正确安装：pip3 install -r requirements-mac.txt")
        sys.exit(1)
    except Exception as e:
        print(f"错误：程序运行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 