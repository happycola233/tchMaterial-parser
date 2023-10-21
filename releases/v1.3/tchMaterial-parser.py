# -*- coding: utf-8 -*-
# 国家中小学智慧教育平台 电子课本下载工具 v1.3
# 作者：肥宅水水呀（https://space.bilibili.com/324042405）
#       wuziqian211（https://space.bilibili.com/425503913）

# 导入相关库
from functools import partial
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import requests
import os
import platform
import json
import pyperclip


# 获取操作系统类型
os_name = platform.system()

# 如果是Windows操作系统，导入Windows相关库
if os_name == "Windows":
    import win32print, win32gui, win32con, win32api, ctypes

# 解析URL
def parse(url):
    try:
        # 简单提取URL中的contentId（这种方法不严谨，但为了减少导入的库只能这样了）
        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentId":
                contentId = q.split("=")[1]
                break
        
        response = requests.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{contentId}.json")
        data = json.loads(response.text)
        for item in list(data["ti_items"]):
            if item["lc_ti_format"] == "pdf": # 找到存有PDF链接列表的项
                pdf_url = item["ti_storages"][0].replace("-private", "") # 获取并构建PDF的URL
                break
        
        return pdf_url, contentId
    except:
        return None, None # 如果解析失败，返回None

# 获取默认文件名
def getDefaultFilename(contentId):
    response = requests.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{contentId}.json")
    try:
        data = json.loads(response.text)
        return data["title"] # 返回教材标题
    except:
        return None

# 下载文件的函数
def downloadFile(url, save_path):
    response = requests.get(url, stream=True)
    with open(save_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=8192): # 分块下载
            file.write(chunk)
    messagebox.showinfo("完成", f"文件已下载到：{save_path}") # 显示完成对话框

# 解析并复制链接的函数
def parseAndCopy():
    urls = [line.strip() for line in url_text.get("1.0", tk.END).splitlines() if line.strip()] # 获取所有非空行
    pdf_links = []
    failed_links = []
    
    for url in urls:
        pdf_url = parse(url)[0]
        if not pdf_url:
            failed_links.append(url) # 添加到失败链接
            continue
        pdf_links.append(pdf_url)
    
    if failed_links:
        failed_msg = "以下链接无法解析：\n" + "\n".join(failed_links)
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
        dir_path = filedialog.askdirectory() # 选择文件夹
        if os_name == "Windows":
            dir_path = dir_path.replace("/", "\\")
        if not dir_path:
            return
    else:
        dir_path = None
    
    for url in urls:
        pdf_url, contentId = parse(url)
        if not pdf_url:
            failed_links.append(url) # 添加到失败链接
            continue
        
        if dir_path:
            default_filename = getDefaultFilename(contentId) or "download"
            save_path = os.path.join(dir_path, f"{default_filename}.pdf") # 构造完整路径
        else:
            default_filename = getDefaultFilename(contentId) or "download"
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")], initialfile=default_filename) # 选择保存路径
            if os_name == "Windows":
                save_path = save_path.replace("/", "\\")

            if not save_path:
                return
        
        threading.Thread(target=downloadFile, args=(pdf_url, save_path)).start() # 开始下载
    
    if failed_links:
        failed_msg = "以下链接无法解析：\n" + "\n".join(failed_links)
        messagebox.showwarning("警告", failed_msg) # 显示警告对话框

class BookHelper:
    def __init__(self):
        self.parsedHierarchy = None
        
    # 解析层级数据
    def parse_hierarchy(self, hier):
        parsed = {}

        # 如果没有层级数据，返回空
        if not hier:
            return None
        for h in hier:
            for ch in h["children"]:
                parsed[ch["tag_id"]] = {"name": ch["tag_name"], "children": self.parse_hierarchy(ch["hierarchies"])}
        return parsed

    # 获取课本列表
    def fetch_book_list(self):
        # 获取层级数据
        tagsResp = requests.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json")
        tagsData = tagsResp.json()
        self.parsedHierarchy = self.parse_hierarchy(tagsData["hierarchies"])

        # 获取课本列表 URL 列表
        listResp = requests.get("https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json")
        listData = listResp.json()["urls"].split(",")

        # 获取课本列表
        for url in listData:
            bookResp = requests.get(url)
            bookData = bookResp.json()
            for i in bookData:
                # 解析课本层级数据
                tagPaths = i["tag_paths"][0].split("/")[2:]

                # 如果课本层级数据不在层级数据中，跳过
                tempHier = self.parsedHierarchy[i["tag_paths"][0].split("/")[1]]
                if not tagPaths[0] in tempHier["children"]:
                    continue

                # 分别解析课本层级
                for p in tagPaths:
                    if tempHier["children"] and tempHier["children"].get(p):
                        tempHier = tempHier["children"].get(p)
                if not tempHier["children"]:
                    tempHier["children"] = {}
                tempHier["children"][i["id"]] = i

        return self.parsedHierarchy
    
bookList = BookHelper().fetch_book_list()

# GUI
root = tk.Tk()

# ----------高DPI适配start---------
if os_name == "Windows":
    scale = round(win32print.GetDeviceCaps(win32gui.GetDC(0), win32con.DESKTOPHORZRES) / win32api.GetSystemMetrics(0), 2) # 获取屏幕缩放比例
    
    # 调用api设置成由应用程序缩放
    try: # 系统版本 >= Win 8.1
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except: # 系统版本 <= Win 8.0
        ctypes.windll.user32.SetProcessDPIAware()
else:
    scale = 1

# 设置缩放因子
root.tk.call("tk", "scaling", scale / 0.75)

# ----------高DPI适配end---------

root.title("国家中小学智慧教育平台 电子课本解析") # 设置窗口标题
# root.geometry("900x600") # 设置窗口大小

# 创建一个容器框架
container_frame = ttk.Frame(root)
container_frame.pack(anchor="center", expand="yes", padx=int(20 * scale), pady=int(20 * scale)) # 容器的中心位置放置，允许组件在容器中扩展，水平外边距40，垂直外边距40

title_label = ttk.Label(container_frame, text="国家中小学智慧教育平台 电子课本解析", font=("微软雅黑", 16, "bold")) # 添加标题标签
title_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

description = """请在下面的文本框中粘贴一个或多个课本原网址（支持批量每个URL一行）。
例如:
https://basic.smartedu.cn/tchMaterial/detail?contentType=
assets_document&contentId=b8e9a3fe-dae7-49c0-86cb-d146
f883fd8e&catalogType=tchMaterial&subCatalog=tchMaterial
点击下载按钮后，程序会解析并下载所有PDF文件。"""
description_label = ttk.Label(container_frame, text=description, justify="left") # 添加描述标签
description_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

url_text = tk.Text(container_frame, width=70, height=12) # 添加URL输入框，长度和宽度不使用缩放！！！
url_text.pack(padx=int(15 * scale), pady=int(15 * scale)) # 设置水平外边距、垂直外边距（跟随缩放）

# 构建选择项
options = [["---"] + [bookList[k]["name"] for k in bookList.keys()], ["---"], ["---"], ["---"], ["---"], ["---"]]

variables = [tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root)]

# 处理用户选择事件
eventFlag = False # 防止事件循环调用
def SelEvent(index, *args):
    global eventFlag

    if eventFlag:
        eventFlag = False # 检测到循环调用，重置标志位并返回
        return
    
    # 重置后面的选择项
    if variables[index].get() == "---":
        for i in range(index + 1, len(drops)):
            drops[i]["menu"].delete(0, "end")
            drops[i]["menu"].add_command(label="---", command=tk._setit(variables[i], "---"))

            eventFlag = True
            variables[i].set("---")
            # drops[i]["menu"].configure(state="disabled")
        return
    
    # 更新选择项
    if index < len(drops) - 1:
        currP1 = drops[index + 1]
        
        currHier = bookList
        currID = [element for element in currHier if currHier[element]["name"] == variables[0].get()][0]
        currHier = currHier[currID]["children"]

        endFlag = False # 是否到达最终目标
        for i in range(index):
            try:
                currID = [element for element in currHier if currHier[element]["name"] == variables[i + 1].get()][0]
                currHier = currHier[currID]["children"]
            except KeyError: # 无法继续向下选择，说明已经到达最终目标
                endFlag = True

        if endFlag:
            currOptions = ["---"]
        if not "name" in currHier[list(currHier.keys())[0]]:
            currOptions = ["---"] + [currHier[k]["title"] for k in currHier.keys()]
        else:
            currOptions = ["---"] + [currHier[k]["name"] for k in currHier.keys()]

        currP1["menu"].delete(0, "end")
        for choice in currOptions:
            currP1["menu"].add_command(label=choice, command=tk._setit(variables[index + 1], choice))

        # 到达目标，显示 URL
        if endFlag:
            currID = [element for element in currHier if currHier[element]["title"] == variables[index].get()][0]
            if url_text.get("1.0", tk.END) == "\n": # URL输入框为空的时候，插入的内容前面不加换行
                url_text.insert("end", f"https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")
            else:
                url_text.insert("end", f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")
            drops[-1]["menu"].delete(0, "end")
            drops[-1]["menu"].add_command(label="---", command=tk._setit(variables[-1], "---"))
            variables[-1].set("---")
            return

        # 重置后面的选择项
        for i in range(index + 2, len(drops)):
            drops[i]["menu"].delete(0, "end")
            drops[i]["menu"].add_command(label="---", command=tk._setit(variables[i], "---"))
            # drops[i]["menu"].configure(state="disabled")
        
        for i in range(index + 1, len(drops)):
            eventFlag = True
            variables[i].set("---")
            
    else: # 最后一项，必为最终目标，显示 URL
        if variables[-1].get() == "---":
            return

        currHier = bookList
        currID = [element for element in currHier if currHier[element]["name"] == variables[0].get()][0]
        currHier = currHier[currID]["children"]
        for i in range(index - 1):
            currID = [element for element in currHier if currHier[element]["name"] == variables[i + 1].get()][0]
            currHier = currHier[currID]["children"]

        currID = [element for element in currHier if currHier[element]["title"] == variables[index].get()][0]
        if url_text.get("1.0", tk.END) == "\n": # URL输入框为空的时候，插入的内容前面不加换行
            url_text.insert("end", f"https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")
        else:
            url_text.insert("end", f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")

# 绑定事件
for index in range(6):
    variables[index].trace_add("write", partial(SelEvent, index))

# 添加 Container
dropdown_frame = ttk.Frame(root)
dropdown_frame.pack(padx=int(10 * scale), pady=int(10 * scale))

drops = []

# 添加菜单栏
for i in range(6):
    drop = ttk.OptionMenu( dropdown_frame , variables[i] , *options[i] ) 
    drop.config(state="active") # 配置下拉菜单为始终活跃状态，保证下拉菜单一直有形状
    drop.bind("<Leave>", lambda e: "break") # 绑定鼠标移出事件，当鼠标移出下拉菜单时，执行lambda函数，"break"表示中止事件传递
    drop.grid(row=i // 3, column=i % 3, padx=int(15 * scale), pady=int(15 * scale)) # 设置位置，2行3列（跟随缩放）
    variables[i].set("---")
    drops.append(drop)

download_btn = ttk.Button(container_frame, text="下载", command=download) # 添加下载按钮
download_btn.pack(side="left", padx=int(40 * scale), pady=int(5 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置按钮高度（跟随缩放）

copy_btn = ttk.Button(container_frame, text="解析并复制", command=parseAndCopy) # 添加“解析并复制”按钮
copy_btn.pack(side="right", padx=int(40 * scale), pady=int(5 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置按钮高度（跟随缩放）

root.mainloop() # 开始主循环
