# 导入相关库
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import requests
import os
import json
import pyperclip
import win32print,win32gui,win32con,win32api,ctypes

# 定义解析URL的函数
def analyze(url):
    try:
        contentId = url.split("&")[1].split("=")[1] # 提取URL中的contentId
        pdf_url = "https://r2-ndr.ykt.cbern.com.cn/edu_product/esp/assets_document/" + contentId + ".pkg/pdf.pdf" # 构建PDF的URL
        return pdf_url, contentId
    except:
        return None, None # 如果解析失败，返回None

# 获取默认文件名
def get_default_filename(contentId):
    response = requests.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{contentId}.json")
    try:
        data = json.loads(response.text)
        return data["title"] # 返回教材标题
    except:
        return None

# 下载文件的函数
def download_file(url, save_path):
    response = requests.get(url, stream=True)
    with open(save_path, 'wb') as file:
        for chunk in response.iter_content(chunk_size=8192): # 分块下载
            file.write(chunk)
    messagebox.showinfo("完成", f"文件已下载到：{save_path}") # 显示完成对话框

# 解析并复制链接的函数
def analyze_and_copy():
    urls = [line.strip() for line in url_text.get("1.0", tk.END).splitlines() if line.strip()] # 获取所有非空行
    pdf_links = []
    failed_links = []

    for url in urls:
        pdf_url, _ = analyze(url)
        if not pdf_url:
            failed_links.append(url) # 添加到失败链接
            continue
        pdf_links.append(pdf_url)

    if failed_links:
        failed_msg = "以下链接无法解析：\n" + '\n'.join(failed_links)
        messagebox.showwarning("警告", failed_msg) # 显示警告对话框

    if pdf_links:
        pyperclip.copy("\n".join(pdf_links)) # 将链接复制到剪贴板
        messagebox.showinfo("提示", "PDF链接已复制到剪贴板")

# 下载PDF文件的函数
def download():
    urls = [line.strip() for line in url_text.get("1.0", tk.END).splitlines() if line.strip()] # 获取所有非空行
    failed_links = []

    if len(urls) > 1:
        messagebox.showinfo("提示", "您选择了多个链接，将在选定的文件夹中使用教材名称作为文件名进行下载。")
        dir_path = filedialog.askdirectory().replace("/","\\") # 选择文件夹
        if not dir_path:
            return
    else:
        dir_path = None

    for url in urls:
        pdf_url, contentId = analyze(url)
        if not pdf_url:
            failed_links.append(url) # 添加到失败链接
            continue

        if dir_path:
            default_filename = get_default_filename(contentId) or "download"
            save_path = os.path.join(dir_path, f"{default_filename}.pdf") # 构造完整路径
        else:
            default_filename = get_default_filename(contentId) or "download"
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")], initialfile=default_filename).replace("/","\\") # 选择保存路径
            if not save_path:
                return

        threading.Thread(target=download_file, args=(pdf_url, save_path)).start() # 开始下载

    if failed_links:
        failed_msg = "以下链接无法解析：\n" + '\n'.join(failed_links)
        messagebox.showwarning("警告", failed_msg) # 显示警告对话框

# GUI
root = tk.Tk()
#----------高DPI适配start---------

#获得当前的缩放因子
ScaleFactor=round(win32print.GetDeviceCaps(win32gui.GetDC(0), win32con.DESKTOPHORZRES) / win32api.GetSystemMetrics (0), 2)

#调用api设置成由应用程序缩放
try:  # 系统版本 >= win 8.1
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:  # 系统版本 <= win 8.0
    ctypes.windll.user32.SetProcessDPIAware()

#设置缩放因子
root.tk.call('tk', 'scaling', ScaleFactor/0.75)

#----------高DPI适配end---------
root.title("国家中小学智慧教育平台 电子课本解析") # 设置窗口标题
root.geometry("900x600") # 设置窗口大小

title_label = tk.Label(root, text="国家中小学智慧教育平台 电子课本解析", font=("微软雅黑", 16, "bold")) # 添加标题标签
title_label.pack(pady=10)

description = '''请在下面的文本框中粘贴一个或多个课本原网址（支持批量每个URL一行）。
例如:
https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=b8e9a3fe-dae7-49c0-86cb-d146f883fd8e&catalogType=tchMaterial&subCatalog=tchMaterial
点击下载按钮后，程序会解析并下载所有PDF文件。'''
description_label = tk.Label(root, text=description, wraplength=650, justify="left") # 添加描述标签
description_label.pack(pady=5)

url_text = tk.Text(root, width=80, height=10) # 添加URL输入框
url_text.pack(pady=10)

download_btn = ttk.Button(root, text="下载", command=download) # 添加下载按钮
download_btn.pack(side="left", padx=10, pady=10)

copy_btn = ttk.Button(root, text="解析并复制", command=analyze_and_copy) # 添加解析并复制按钮
copy_btn.pack(side="right", padx=10, pady=10)

root.mainloop() # 开始主循环