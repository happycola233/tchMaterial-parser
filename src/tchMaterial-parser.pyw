# -*- coding: utf-8 -*-
# 国家中小学智慧教育平台 电子课本下载工具 v2.1
#   https://github.com/happycola233/tchMaterial-parser
# 最近更新于：2024-08-19
# 作者：肥宅水水呀（https://space.bilibili.com/324042405）以及其他为本工具作出贡献的用户

# 导入相关库
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os, sys
from functools import partial
import platform
import time, json, base64, tempfile
import threading, requests, pyperclip, psutil

os_name = platform.system() # 获取操作系统类型
if os_name == "Windows": # 如果是 Windows 操作系统，导入 Windows 相关库
    import win32print, win32gui, win32con, win32api, ctypes

    # 高 DPI 适配
    scale = round(win32print.GetDeviceCaps(win32gui.GetDC(0), win32con.DESKTOPHORZRES) / win32api.GetSystemMetrics(0), 2) # 获取当前的缩放因子

    # 调用 API 设置成由应用程序缩放
    try: # Windows 8.1 或更新
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except: # Windows 8 或更老
        ctypes.windll.user32.SetProcessDPIAware()
else:
    scale = 1

def parse(url): # 解析 URL
    try:
        # 简单提取 URL 中的 contentId（这种方法不严谨，但为了减少导入的库只能这样了）
        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentId":
                contentId = q.split("=")[1]
                break
        
        # 获得该 contentId 下电子课本的信息，返回数据示例：
        """
        {
            "id": "4f64356a-8df7-4579-9400-e32c9a7f6718",
            // ...
            "ti_items": [
                {
                    // ...
                    "ti_storages": [ // PDF 源文件地址
                        "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/pdf.pdf",
                        "https://r2-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/pdf.pdf",
                        "https://r3-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/pdf.pdf"
                    ],
                    // ...
                },
                {
                    // ...（和上一个元素组成一样）
                }
            ]
        }
        """
        # 其中 $.ti_items 的每一项对应一个电子课本
        response = requests.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{contentId}.json", proxies={ "http": None, "https": None })
        data = json.loads(response.text)
        for item in list(data["ti_items"]):
            if item["lc_ti_format"] == "pdf": # 找到存有 PDF 链接列表的项
                pdf_url = item["ti_storages"][0].replace("-private", "") # 获取并构建 PDF 的 URL
                break
        return pdf_url, contentId
    except:
        return None, None # 如果解析失败，返回 None

def getDefaultFilename(contentId): # 获取默认文件名
    response = requests.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{contentId}.json", proxies={ "http": None, "https": None })
    try:
        data = json.loads(response.text)
        return data["title"] # 返回教材标题
    except:
        return None

def download_file(url, save_path): # 下载文件
    global all_download_size, all_total_size, downloaded_number, task_number
    task_number += 1
    response = requests.get(url, stream=True, proxies={ "http": None, "https": None })
    total_size = int(response.headers.get("Content-Length", 0))
    all_total_size += total_size
    with open(save_path, "wb") as file:
        download_size = 0
        for chunk in response.iter_content(chunk_size=131072): # 分块下载，每次下载 131072 字节（128 KB）
            file.write(chunk)
            def update_progress():
                global all_download_size, all_total_size
                all_download_size += len(chunk)
                if all_total_size > 0: # 防止下面一行代码除以 0 而报错
                    download_progress = (all_download_size / all_total_size) * 100
                    # 更新进度条
                    download_progress_bar["value"] = download_progress
                    # 更新标签以显示当前下载进度
                    progress_label.config(text=f"{format_bytes(all_download_size)}/{format_bytes(all_total_size)} ({download_progress:.2f}%) 已下载 {downloaded_number}/{task_number}") # 更新标签
                    
                    if all_download_size >= all_total_size:
                        time.sleep(0.5) # 延迟 0.5 秒
                        download_progress_bar["value"] = 0 # 重置进度条
                        progress_label.config(text="等待下载") # 清空进度标签
                        download_btn.config(state="normal") # 设置下载按钮为启用状态
                        messagebox.showinfo("完成", f"文件已下载到：{os.path.dirname(save_path)}") # 显示完成对话框
            
            thread_it(update_progress)
        downloaded_number += 1

def format_bytes(size): # 格式化字节
    # 返回以 KB、MB、GB、TB 为单位的数据大小
    for x in ["bytes", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f'{size:3.1f} {x}'
        size /= 1024.0

def parseAndCopy(): # 解析并复制链接
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
        messagebox.showwarning("警告", "以下“行”无法解析：\n" + "\n".join(failed_links)) # 显示警告对话框
    
    if pdf_links:
        pyperclip.copy("\n".join(pdf_links)) # 将链接复制到剪贴板
        messagebox.showinfo("提示", "PDF 链接已复制到剪贴板")

def download(): # 下载 PDF 文件
    global all_download_size, all_total_size, downloaded_number, task_number
    download_btn.config(state="disabled") # 设置下载按钮为禁用状态
    all_download_size, all_total_size, downloaded_number, task_number = 0, 0, 0, 0 # 初始化
    urls = [line.strip() for line in url_text.get("1.0", tk.END).splitlines() if line.strip()] # 获取所有非空行
    failed_links = []
    
    if len(urls) > 1:
        messagebox.showinfo("提示", "您选择了多个链接，将在选定的文件夹中使用教材名称作为文件名进行下载。")
        dir_path = filedialog.askdirectory() # 选择文件夹
        if os_name == "Windows":
            dir_path = dir_path.replace("/", "\\")
        if not dir_path:
            download_btn.config(state="normal") # 设置下载按钮为启用状态
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
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")], initialfile = default_filename) # 选择保存路径
            if not save_path: # 用户取消了文件保存操作
                download_btn.config(state="normal") # 设置下载按钮为启用状态
                return
            if os_name == "Windows":
                save_path = save_path.replace("/", "\\")
        
        thread_it(download_file, (pdf_url, save_path)) # 开始下载（多线程，防止窗口卡死）
    
    if failed_links:
        messagebox.showwarning("警告", "以下“行”无法解析：\n" + "\n".join(failed_links)) # 显示警告对话框
        download_btn.config(state="normal") # 设置下载按钮为启用状态
    
    if not urls and not failed_links:
        download_btn.config(state="normal") # 设置下载按钮为启用状态

class BookHelper: # 获取网站上所有课本的数据
    def __init__(self):
        self.parsedHierarchy = None
    
    def parse_hierarchy(self, hierarchy): # 解析层级数据
        if not hierarchy: # 如果没有层级数据，返回空
            return None
        
        parsed = {}
        for h in hierarchy:
            for ch in h["children"]:
                parsed[ch["tag_id"]] = {"name": ch["tag_name"], "children": self.parse_hierarchy(ch["hierarchies"])}
        return parsed
    
    def fetch_book_list(self): # 获取课本列表
        # 获取层级数据
        tagsResp = requests.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json", proxies={ "http": None, "https": None })
        tagsData = tagsResp.json()
        self.parsedHierarchy = self.parse_hierarchy(tagsData["hierarchies"])
        
        # 获取课本 URL 列表
        listResp = requests.get("https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json", proxies={ "http": None, "https": None })
        listData = listResp.json()["urls"].split(",")
        
        # 获取课本列表
        for url in listData:
            bookResp = requests.get(url, proxies={ "http": None, "https": None })
            bookData = bookResp.json()
            for i in bookData:
                if (len(i["tag_paths"]) > 0): # 某些非课本资料的 tag_paths 属性为空数组
                    # 解析课本层级数据
                    tagPaths = i["tag_paths"][0].split("/")[2:] # 电子课本 tag_paths 的前两项为“教材”、“电子教材”
                    
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

def thread_it(func, args: tuple = ()): # args 为元组，且默认值是空元组
    # 打包函数到线程
    t = threading.Thread(target=func, args=args)
    # t.daemon = True
    t.start()

try:
    bookList = BookHelper().fetch_book_list()
except:
    bookList = {}
    messagebox.showwarning("警告", "获取电子课本列表失败，请手动填写电子课本链接，或重新打开本程序") # 弹出警告窗口

# GUI
root = tk.Tk()

root.tk.call("tk", "scaling", scale / 0.75) # 设置缩放因子

root.title("国家中小学智慧教育平台 电子课本解析") # 设置窗口标题
# root.geometry("900x600") # 设置窗口大小

def set_icon(): # 设置窗口图标
    # 窗口左上角小图标
    icon = base64.b64decode("AAABAAEAMDAAAAEAIACoJQAAFgAAACgAAAAwAAAAYAAAAAEAIAAAAAAAACQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA6GMdAOxhHgbrYR0g7GEdNOxiHjzsYh4+7GIdNuxhHSjrYh0S62EeBOdkGwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOtjIALrYh5I7GIdq+tiHe3sYh7/7GId/+xiHv/sYh7/7GId/+xiHv/sYR3962Ee6ethHcXsYh2R7GEdVOxhHRYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62EdJuthHcHrYh7/7GId/+xiHv/rYR7/62Id/+tiHv/rYR7/62Id/+tiHv/rYR7/62Id/+tiHv/rYR7/62Id/+thHfnsYR6/7GEdYuthHhIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADrYR1C62Ed7ethHf/rYR7/62Ee/+thHv/rYR7/62Id/+thHv/rYR7/62Ed/+thHv/rYR7/62Id/+tiHv/rYR7/62Id/+thHv/rYh7/62Ee/+thHe3rYh2P62IeHutiHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOthHTTrYR3z7GId/+xiHf/sYR3/7GIe/+xiHf/sYh7/7GId/+xiHv/sYh7/7GIe/+xiHf/sYh3/7GId/+xhHf/sYh7/7GId/+xiHf/sYh3/7GIe/+xiHv/sYh7/7GId+ethHaPrYR087GAfAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62IdCutiHUwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYR0M7GEeTOxhHdnrYh3/7GIe/+tiHf/rYh3/7GId/+thHv/sYh7/7GId/+thHv/sYh7/7GId/+thHv/sYh7/7GId/+thHv/sYh7/7GId/+thHv/sYh7/62Id/+xhHv/sYh7/62Id/+xhHv/rYR7962Ed2exiHYnrYh1C7GIdEuxgHAIAAAAAAAAAAAAAAADqYB0C62IdEOthHULsYh2R62EdqethHiAAAAAAAAAAAAAAAAAAAAAA62IdCutiHnzrYR7p62Ie/+thHf/rYR7/62Ie/+thHv/rYh7/62Ie/+thHv/rYh7/62Id/+thHv/rYR7/62Id/+thHv/sYh7/62Ie/+thHv/rYh7/62Ie/+thHv/sYh7/62Ee/+thHf/rYR7/62Ee/+thHf/rYR3/62Ie/+thHf/rYR3/7GId9+xhHd/rYR3H62EdvexhHcPsYR3b7GId9ethHe/sYh1u62EeBgAAAAAAAAAAAAAAAAAAAADrYR0u62Ee1+xiHf/sYh3/7GId/+xhHf/sYh3/7GId/+xhHf/sYh7/7GId/+xiHv/sYh3562Ed2exhHbXsYR2X7GEdgexhHXLsYh5s62IdbOthHW7sYh127GEdhethHZnsYR2v62EdyexhHePsYR357GEd/+xhHf/sYR3/7GId/+xhHf/sYR3/7GId/+xhHf/sYh7/7GId/+xiHf/sYR3n62Edg+thHRQAAAAAAAAAAAAAAAAAAAAAAAAAAOthHTLrYh3t62Ee/+xiHv/sYR3/7GIe/+thHf/sYR3/7GIe/+thHf/sYh7x62IdoethHk7sYR0W7GEdAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOxiHg7rYR1Q7GEdcOxhHWzsYR1Y62EdROxiHVjsYR2D62EdsexhHdvsYR3v7GEd8ethHefsYR3H62Edk+thHUrrYh0KAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62EdFuthHeHrYR7/62Ee/+tiHv/rYR7/62Ie/+tiHf/rYR7/7GEd++xiHYvrYR4WAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62EdUOtiHufrYR7/62Ee/+thHv/rYR3/62Ee9exhHq/rYR00/kAAAAAAAADtYBoE72EbBuZhHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA7GIdoexiHf/sYh3/7GId/+xiHf/sYh3/62Id/+xiHf/sYh3/7GEdtexhHVTsYR6f7GIdLgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADrYR0+62Ed++xiHv/sYh3/7GIe/+xiHv/sYh3/7GIe/+xiHv/sYh397GEdi+tiHQYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYh0o7GId+exhHf/sYh7/7GIe/+tiHf/sYh3/7GIe/+xiHf/sYh3/7GEduetiHn7sYR3v62EeweZmGgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpcGgDsYh3D62Id/+xhHv/sYh3/62Ie/+xhHv/sYh3/62Ie/+xhHv/sYh3/62Id/+thHa/rYR0IAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYR2D62Ie/+thHv/sYh7/62Ee/+tiHv/rYR7/62Ie/+tiHf/rYR7/7GIewethHXbsYh2/62Id8+tiHTQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOxhHRTsYR337GIe/+thHv/rYR3/62Ie/+thHv/rYR3/62Ee/+thHv/rYR3/62Ie/+thHf/rYR2V6mEeAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYh3F7GIe/+xiHf/sYh3/7GId/+xiHf/sYh3/7GIe/+xiHv/sYh7/62EeyethHWzsYR3N62Idr+thHqXmZhoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOxiHhrsYh797GId/+xiHf/sYh7/7GId/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/rYR3962IdRgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYh3t7GIe/+thHf/rYh3/7GIe/+thHf/sYh7/62Ie/+xhHf/sYh7/62Ed0ethHmTsYR3r62IdWOthHvfsYh0eAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOxiHgjsYh7p7GId/+xhHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xhHv/sYh7/7GIe/+xhHv/sYh7/7GEdyexgHQIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYR397GEd/+thHf/rYh3/62Ed/+thHf/rYR3/62Id/+xhHf/sYR3/62Ed2+xiHlrsYR3562EdIOthHe3rYR6JAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADrYR6P7GId/+tiHf/sYR3/62Id/+thHf/sYh3/62Ed/+thHf/sYh3/62Ed/+thHf/sYh3/7GEd/ethHTYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYh7z7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/62Ed4exhHVDsYh7/7GIdOOtiHpnrYR7r7GIdEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYR4O62Ed0exiHv/sYh7/62Ie/+xiHv/sYh7/62Ie/+xiHv/sYh7/62Ie/+xiHv/sYh7/62Ie/+xiHn4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADrYh3P62Ed/+xiHv/sYh7/7GIe/+xiHv/rYR3/7GEe/+thHf/rYR3/7GEd6etiHkjrYR3/62EdWuthHTzrYR3962EebAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62EdFuxhHbnsYR3/62Ie/+xhHf/sYR3/62Ie/+xhHf/sYR3/62Ie/+xhHf/sYR3/62Ie/+xiHa0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADrYR2T7GId/+thHf/sYh3/62Ed/+thHf/rYR3/62Id/+xiHf/rYR3/7GId8+tiHUDrYR3/7GEefupiHQTrYh3b62Ie2+xiHQIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOxhHQrsYR3j7GId/+thHf/rYR3/62Id/+thHf/rYR3/62Ed/+thHf/rYR3/62Id/+thHsMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADrYR047GEd/exiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/62Id+ethHTbsYh7/62EeoQAAAADsYh2B7GIe/+thHlAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOxhHQ7sYR7l62Ie/+xiHv/sYh7/62Ie/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+thHsEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADtYBoC62Edu+xiHv/sYR3/7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/62Ed++thHTbsYh7/62IdxQAAAADsYh0q7GId/etiHb/sYh4CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62EdFuthHbfsYh3/7GIe/+xiHv/sYh3/7GIe/+xiHv/rYh3/7GIe/+xiHv/sYh3/7GIe/+xiHqcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62EdKuxhHfHrYh3/7GEd/+tiHf/rYR3/62Ed/+xiHf/rYR3/62Ed++thHSjsYR3X62Id6+xhHXTrYh3V62Ed/+tiHf3rYR42AAAAAAAAAAAAAAAAAAAAAOtiHRDrYR5y62Ed6+thHf/sYR3/62Id/+thHf/rYR3/62Id/+thHf/sYR3/62Ed/+thHf/sYh3/62Ed/+tiHXIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOtiHVTrYh357GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/62Ee/+xhHuXrYh397GIe/+xiHv/sYh7/7GIe/+xiHv/sYh2lAAAAAOxiHgbrYR087GIdl+thHe3sYh7/7GIe/+xiHv/sYh7/62Ie/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GId++xhHSgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADsYh1S7GId8exhHf/sYh7/62Ie/+xhHf/sYh7/62Ie/+xhHf/sYh7/7GIe/+xhHf/sYR7/7GIe/+xhHf/rYR7562Eeq+xiHePsYR7/7GIe/+xhHf/sYR7/7GIe/+xhHf/sYh7/62Id/+xhHv/sYh7/62Id/+xhHv/sYh7/62Id/+xhHv/sYh7/62Edt+xiHgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA7GIdIuxhHq3sYR3762Ed/+xiHf/sYh3/62Id/+thHf/rYR3/62Id/+thHf/rYR3/7GId/+thHf/rYR3/7GId/+tiHf/rYR3/62Id/+tiHv/rYh7/62Id/+tiHf/rYR3/62Id/+thHf/sYR3/62Id/+xhHf/rYR3/62Ed/+thHf/rYh337GEdLAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpgIADrYR0862Ed++xiHv/sYh7/62Ie/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/rYh7/7GIe/+xiHv/sYh7/7GIe/+tiHv/sYh7/62Ie/+xiHv/sYh7/7GIe/+xiHv/sYh7/62Ie/+xiHv3sYR1q52IcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqYB8C7GEdz+thHf/rYR3/7GIe/+thHf/rYR3/62Ed/+xhHv/sYh7/7GEd/+xhHv/sYh7/62Ed/+xhHv/sYh7/62Ed/+xiHv/sYh7/7GEd/+xiHv/sYh7/7GId/+xiHv/sYh7/7GId/+xhHv/sYh7/62Id++thHXTqYCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA62IdYOxhHf/sYR3/62Ed/+thHf/sYR3/62Ed/+thHf/rYR3/62Ed/+thHv/rYR3/62Ed/+xhHv/rYR3/62Ed/+thHv/rYR3/62Ed/+thHv/sYR3/62Ed/+thHf/sYR3/62Ed/+xhHf/rYR7b7GEdRO1fGwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA7GAcBuxhHcnsYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GEe/+xiHv/sYh7/7GIe/+xiHv/sYh7/62Id7+xiHffsYR7/62Ie/+thHv3rYR3z62IeuethHl7rYR4KAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOxiHSbsYR7r7GIe/+thHf/rYR7/7GIe/+thHv/sYh7/7GId/+thHv/sYh7/7GId/+thHv/sYh7/7GId/+thHv/rYR3h62EdGuxiHRTsYR0u7GEdNOthHSjrYR0KAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADrYR027GEd5ethHf/sYh3/62Id/+thHf/rYh3/62Id/+tiHf/sYh3/62Id/+thHf/sYh3/62Ed/+thHdvrYR0oAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA7GIdHuthHbXrYh397GIe/+xiHv/sYh7/7GIe/+xiHv/sYh7/7GIe/+xiHv/rYh7962Idp+xiHRYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpiGwLrYR5A62Iep+tiHu3rYR7/7GIe/+thHv/rYR7/62Ed6ethHp/rYh44AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA6WMbAOthHQbsYh0k62EeOuthHTrsYR0g6mEdBN9gIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD///////8AAP///////wAA////////AAD///////8AAP///////wAA////////AAD///////8AAP///////wAA//gAf///AAD/4AAP//8AAP/AAAH//wAA/4AAAH//AAD/AAAAD/kAAPwAAAAABwAA8AAPgAAPAADgA///gH8AAMAP/8B//wAAgBf/gB//AACAE/8AD/8AAAAT/wAH/wAAABH/AAf/AAAAFf8AA/8AAAAU/wAD/wAAABT/gAP/AAAAFv/AAf8AAAAWf+AB/wAAgBJ/4AH/AACAEz/AAf8AAMASP4AD/wAA4AAcAAP/AADwAAAAA/8AAPgAAAAH/wAA/gAAAA//AAD+AAAAH/8AAP8AAAA//wAA/wAAAP//AAD/gAB///8AAP/AAP///wAA/+AB////AAD/+Af///8AAP///////wAA////////AAD///////8AAP///////wAA////////AAD///////8AAP///////wAA////////AAA=")

    with open(tempfile.gettempdir() + "/icon.ico", "wb") as f:
        f.write(icon)
    root.iconbitmap(tempfile.gettempdir() + "/icon.ico") # 更改窗口左上角的小图标

thread_it(set_icon) # 设置窗口图标耗时较长，为不影响窗口绘制，采用多线程

def on_closing(): # 处理窗口关闭事件
    current_process = psutil.Process(os.getpid()) # 获取自身的进程 ID
    child_processes = current_process.children(recursive=True) # 获取自身的所有子进程
    
    for child in child_processes: # 结束所有子进程
        try:
            child.terminate() # 结束进程
        except: # 进程可能已经结束
            pass
    
    # 结束自身进程
    try:
        current_process.terminate()
    except: # 进程可能已经结束
        pass

root.protocol("WM_DELETE_WINDOW", on_closing) # 注册窗口关闭事件的处理函数

# 创建一个容器框架
container_frame = ttk.Frame(root)
container_frame.pack(anchor="center", expand="yes", padx=int(40 * scale), pady=int(20 * scale)) # 在容器的中心位置放置，允许组件在容器中扩展，水平外边距 40，垂直外边距 40

title_label = ttk.Label(container_frame, text="国家中小学智慧教育平台 电子课本解析", font=("微软雅黑", 16, "bold")) # 添加标题标签
title_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

description = """请在下面的文本框中输入一个或多个电子课本预览页面的网址（每个网址一行）。
电子课本预览页面网址示例：
https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_
document&contentId=b8e9a3fe-dae7-49c0-86cb-d146f883fd8e
&catalogType=tchMaterial&subCatalog=tchMaterial
点击下面的“下载”按钮后，程序会解析并下载所有 PDF 文件。"""
description_label = ttk.Label(container_frame, text=description, justify="left") # 添加描述标签
description_label.pack(pady=int(5 * scale)) # 设置垂直外边距（跟随缩放）

url_text = tk.Text(container_frame, width=70, height=12) # 添加 URL 输入框，长度和宽度不使用缩放！！！
url_text.pack(padx=int(15 * scale), pady=int(15 * scale)) # 设置水平外边距、垂直外边距（跟随缩放）

# 创建右键菜单
context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="剪切 (Ctrl + X)", command=lambda: url_text.event_generate("<<Cut>>"))
context_menu.add_command(label="复制 (Ctrl + C)", command=lambda: url_text.event_generate("<<Copy>>"))
context_menu.add_command(label="粘贴 (Ctrl + V)", command=lambda: url_text.event_generate("<<Paste>>"))

# 绑定右键菜单到文本框（3 代表鼠标的右键按钮）
url_text.bind("<Button-3>", lambda event: context_menu.post(event.x_root, event.y_root))

options = [["---"] + [bookList[k]["name"] for k in bookList.keys()], ["---"], ["---"], ["---"], ["---"], ["---"]] # 构建选择项

variables = [tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root), tk.StringVar(root)]

# 处理用户选择事件
eventFlag = False # 防止事件循环调用
def SelEvent(index, *args):
    global eventFlag
    
    if eventFlag:
        eventFlag = False # 检测到循环调用，重置标志位并返回
        return
    
    if variables[index].get() == "---": # 重置后面的选择项
        for i in range(index + 1, len(drops)):
            drops[i]["menu"].delete(0, "end")
            drops[i]["menu"].add_command(label="---", command=tk._setit(variables[i], "---"))

            eventFlag = True
            variables[i].set("---")
            # drops[i]["menu"].configure(state="disabled")
        return
    
    if index < len(drops) - 1: # 更新选择项
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
        
        if endFlag: # 到达目标，显示 URL
            currID = [element for element in currHier if currHier[element]["title"] == variables[index].get()][0]
            if url_text.get("1.0", tk.END) == "\n": # URL 输入框为空的时候，插入的内容前面不加换行
                url_text.insert("end", f"https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")
            else:
                url_text.insert("end", f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")
            drops[-1]["menu"].delete(0, "end")
            drops[-1]["menu"].add_command(label="---", command=tk._setit(variables[-1], "---"))
            variables[-1].set("---")
            return
        
        for i in range(index + 2, len(drops)): # 重置后面的选择项
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
        if url_text.get("1.0", tk.END) == "\n": # URL 输入框为空的时候，插入的内容前面不加换行
            url_text.insert("end", f"https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")
        else:
            url_text.insert("end", f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial")

for index in range(6): # 绑定事件
    variables[index].trace_add("write", partial(SelEvent, index))

# 添加 Container
dropdown_frame = ttk.Frame(root)
dropdown_frame.pack(padx=int(10 * scale), pady=int(10 * scale))

drops = []

# 添加菜单栏
for i in range(6):
    drop = ttk.OptionMenu(dropdown_frame , variables[i] , *options[i])
    drop.config(state="active") # 配置下拉菜单为始终活跃状态，保证下拉菜单一直有形状
    drop.bind("<Leave>", lambda e: "break") # 绑定鼠标移出事件，当鼠标移出下拉菜单时，执行 lambda 函数，“break”表示中止事件传递
    drop.grid(row=i // 3, column=i % 3, padx=int(15 * scale), pady=int(15 * scale)) # 设置位置，2 行 3 列（跟随缩放）
    variables[i].set("---")
    drops.append(drop)

download_btn = ttk.Button(container_frame, text="下载", command=lambda: thread_it(download)) # 添加下载按钮
download_btn.pack(side="left", padx=int(5 * scale), pady=int(5 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置按钮高度（跟随缩放）

copy_btn = ttk.Button(container_frame, text="解析并复制", command=parseAndCopy) # 添加“解析并复制”按钮
copy_btn.pack(side="right", padx=int(5 * scale), pady=int(5 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置按钮高度（跟随缩放）

download_progress_bar = ttk.Progressbar(container_frame, length=(125 * scale), mode="determinate") # 添加下载进度条
download_progress_bar.pack(side="bottom", padx=int(40 * scale), pady=int(10 * scale), ipady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置进度条高度（跟随缩放）

# 创建一个新标签来显示下载进度
progress_label = ttk.Label(container_frame, text="等待下载", anchor="center") # 初始时文本为空，居中
progress_label.pack(side="bottom", padx=int(5 * scale), pady=int(5 * scale)) # 设置水平外边距、垂直外边距（跟随缩放），设置标签高度（跟随缩放）

root.mainloop() # 开始主循环
