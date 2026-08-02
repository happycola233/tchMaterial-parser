# -*- coding: utf-8 -*-
# 左侧资源列表：搜索筛选、封面按需加载与悬停预览

import io
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from PIL import Image, ImageOps, ImageTk

from . import runtime, theme
from .runtime import scaled, thread_it, ui_call
from .widgets import auto_hide_scrollbar, bind_context_menu
from ..catalog import count_resource_items, filter_resource_items
from ..images import fit_cover_image
from ..network import session
from ..platform_utils import os_name, print_error

def build_resource_tree(pane: ttk.Frame, resource_list: dict[str, dict], url_text: tk.Text) -> None: # 在给定的子框架内构建资源列表
    pane.columnconfigure(0, weight=1)
    pane.rowconfigure(2, weight=1)

    treeview_header = ttk.Frame(pane)
    treeview_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, scaled(6)))
    treeview_header.columnconfigure(0, weight=1)
    treeview_label = ttk.Label(treeview_header, text="资源列表", style="Heading.TLabel") # 添加树视图标签
    treeview_label.grid(row=0, column=0, sticky="w")
    search_status_label = ttk.Label(treeview_header, style="Caption.TLabel")
    search_status_label.grid(row=0, column=1, sticky="e")

    search_frame = ttk.Frame(pane)
    search_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, scaled(8)))
    search_frame.columnconfigure(1, weight=1)
    search_label = ttk.Label(search_frame, text="搜索")
    search_label.grid(row=0, column=0, padx=(0, scaled(8)))
    search_var = tk.StringVar()
    search_entry = ttk.Entry(search_frame, textvariable=search_var, font="AppBodyFont")
    search_entry.grid(row=0, column=1, sticky="ew")
    bind_context_menu(search_entry, "noundo")

    clear_search_btn = ttk.Button(search_frame, text="清除", width=5, command=lambda: search_var.set(""))
    clear_search_btn.grid(row=0, column=2, padx=(scaled(6), 0))

    treeview = ttk.Treeview(pane, style="Custom.Treeview", show="tree", selectmode="browse", height=12) # 创建树视图，使用自定义样式（该样式在 apply_theme() 中配置），隐藏列标题，设置选择模式为单选
    treeview.column("#0", stretch=False)
    treeview.grid(row=2, column=0, sticky="nsew")
    treeview_scrollbar = ttk.Scrollbar(pane, orient="vertical", command=treeview.yview)
    treeview_scrollbar.grid(row=2, column=1, sticky="ns")
    treeview_horizontal_scrollbar = ttk.Scrollbar(pane, orient="horizontal", command=treeview.xview)
    treeview.configure(xscrollcommand=lambda f, l: auto_hide_scrollbar(treeview_horizontal_scrollbar, f, l))
    treeview_horizontal_scrollbar.grid(row=3, column=0, sticky="ew")

    tree_item_data: dict[str, dict] = {} # 键为树项 ID，值为资源数据
    tree_item_paths: dict[str, tuple[str, ...]] = {} # 保存完整分类路径，用于悬停提示
    tree_item_images: dict[str, ImageTk.PhotoImage] = {} # 缓存已加载的封面，筛选后继续复用
    tree_preview_images: dict[str, ImageTk.PhotoImage] = {} # 缓存大尺寸封面，用于悬停预览
    loading_tree_images: set[str] = set()
    tree_font = tkfont.nametofont("AppBodyFont")
    tree_cover_size = (scaled(26), scaled(28))
    tree_cover_gap = scaled(8) # 用透明区域拉开封面与标题，避免改变封面尺寸
    preview_cover_size = (scaled(80), scaled(112))
    tree_content_width = 0

    def get_tree_cover_gap(display_name: str) -> int: # 名称以中文左括号开头时不添加封面与标题间隔
        return 0 if display_name.startswith("（") else tree_cover_gap

    def build_tree_items(parent: str, items: dict[str, dict], parent_names: tuple[str, ...], expand_all: bool) -> None: # 递归构建树视图项
        nonlocal tree_content_width
        for option_id, option_data in items.items():
            item_id = f"{parent}:{option_id}" if parent else option_id
            display_name = option_data["display_name"]
            path_names = (*parent_names, display_name)
            tree_item_data[item_id] = option_data
            tree_item_paths[item_id] = path_names
            treeview.insert(
                parent,
                "end",
                iid=item_id,
                text=display_name,
                image=tree_item_images.get(item_id, ""),
                open=expand_all or not parent,
            )
            children: dict[str, dict] = option_data.get("children", {})
            if children: # 如果有子项，递归构建子树项
                build_tree_items(item_id, children, path_names, expand_all)

            depth_width = len(path_names) * scaled(20)
            image_width = tree_cover_size[0] + get_tree_cover_gap(display_name) + scaled(4) if option_data.get("custom_properties", {}).get("thumbnails") else 0
            tree_content_width = max(tree_content_width, depth_width + image_width + tree_font.measure(display_name) + scaled(20))

    def resize_tree_column(width: int) -> None: # 让树列至少铺满可视区域，内容过长时启用横向滚动
        treeview.column("#0", width=max(tree_content_width, width - scaled(2)))

    def apply_tree_icon(item_id: str, image: Image.Image | None) -> None:
        loading_tree_images.discard(item_id)
        if image is None:
            return
        tree_image = fit_cover_image(image, tree_cover_size)
        cover_gap = get_tree_cover_gap(tree_item_data[item_id]["display_name"])
        if cover_gap:
            tree_image = ImageOps.expand(tree_image, border=(0, 0, cover_gap, 0), fill=(0, 0, 0, 0))
        tree_item_images[item_id] = ImageTk.PhotoImage(tree_image)
        tree_preview_images[item_id] = ImageTk.PhotoImage(image)
        if treeview.exists(item_id):
            treeview.item(item_id, image=tree_item_images[item_id])

    def load_tree_icon(item_id: str, url: str) -> None: # 在线程中下载封面，在主线程中更新控件
        try:
            resp = session.get(url)
            if not resp.ok:
                ui_call(apply_tree_icon, item_id, None)
                return
            image = fit_cover_image(Image.open(io.BytesIO(resp.content)), preview_cover_size)
            ui_call(apply_tree_icon, item_id, image)
        except Exception as e:
            print_error(e)
            ui_call(apply_tree_icon, item_id, None)

    def queue_tree_icon(item_id: str) -> None:
        resource_data = tree_item_data[item_id]
        thumbnails = resource_data.get("custom_properties", {}).get("thumbnails")
        if thumbnails and item_id not in tree_item_images and item_id not in loading_tree_images:
            loading_tree_images.add(item_id)
            thread_it(load_tree_icon, item_id, thumbnails[0])

    def load_visible_tree_icons() -> None: # 搜索或滚动后只加载当前可见资源的封面
        for item_id, resource_data in tree_item_data.items():
            if not resource_data.get("children") and treeview.bbox(item_id):
                queue_tree_icon(item_id)

    def on_tree_view_change(first: str, last: str) -> None:
        auto_hide_scrollbar(treeview_scrollbar, first, last)
        runtime.root.after_idle(load_visible_tree_icons)

    def refresh_resource_tree() -> None: # 根据搜索词重建树视图
        nonlocal tree_content_width
        query = search_var.get().strip()
        visible_items = filter_resource_items(resource_list, query)

        leave_tree()
        treeview.delete(*treeview.get_children())
        tree_item_data.clear()
        tree_item_paths.clear()
        tree_content_width = 0
        build_tree_items("", visible_items, (), expand_all=bool(query))
        resize_tree_column(treeview.winfo_width())

        result_count = count_resource_items(visible_items)
        search_status_label.config(text=f"{result_count} 项" if result_count else "无匹配资源")
        clear_search_btn.state(["!disabled"] if query else ["disabled"])
        runtime.root.after_idle(load_visible_tree_icons)

    def on_tree_select(event: tk.Event) -> None: # 处理树视图选择事件
        selection = treeview.selection()
        if not selection:
            return

        item = selection[0]
        children = treeview.get_children(item)
        if children: # 如果选中的项有子项，则加载子项的预览图，否则插入 URL
            for child in children: # 遍历子项，设置子项的图片
                queue_tree_icon(child)
        else:
            resource_data = tree_item_data.get(item)
            if not resource_data:
                return

            resource_type = resource_data.get("resource_type_code") or "assets_document"
            content_id = resource_data.get("content_id") or item.split(":")[-1]
            root_id = item.split(":")[0]
            if resource_type == "teachingmaterials":
                url = f"https://basic.smartedu.cn/syncClassroom{'/prepare' if root_id == '__internal_prepare_lesson' else ''}?defaultTag={'%2F'.join(item.split(':')[1:])}"
            else:
                url = f"https://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={content_id}&catalogType=tchMaterial&subCatalog=tchMaterial"

            url_text_content = url_text.get("1.0", "end")[:-1] # 获取 URL 输入框的内容，去掉最后一个换行符
            if url in url_text_content.splitlines(): # 如果 URL 已经存在于输入框中，则不再插入
                return
            if not url_text_content or url_text_content[-1] == "\n": # URL 输入框为空或最后一个字符为换行符时，插入的内容前面不加换行
                url_text.insert("end", url)
            else:
                url_text.insert("end", f"\n{url}")
            url_text.see("end") # 滚动到文本框底部

    tooltip_window: tk.Toplevel | None = None
    tooltip_after_id: str | None = None
    hovered_tree_item = ""

    def hide_tree_tooltip() -> None:
        nonlocal tooltip_window, tooltip_after_id
        if tooltip_after_id:
            runtime.root.after_cancel(tooltip_after_id)
            tooltip_after_id = None
        if tooltip_window:
            tooltip_window.destroy()
            tooltip_window = None

    def show_tree_tooltip(item_id: str, x_root: int, y_root: int) -> None: # 悬停时显示完整名称与分类路径
        nonlocal tooltip_window, tooltip_after_id
        tooltip_after_id = None
        if item_id != hovered_tree_item or not treeview.exists(item_id):
            return

        path_names = tree_item_paths[item_id]
        tooltip_window = tk.Toplevel(runtime.root)
        tooltip_window.overrideredirect(True)
        tooltip_body = tk.Frame(
            tooltip_window,
            background=theme.current_colors["surface"],
            relief="solid",
            borderwidth=1,
            padx=scaled(10),
            pady=scaled(9),
        )
        tooltip_body.pack()

        preview_image = tree_preview_images.get(item_id)
        if preview_image:
            tk.Label(
                tooltip_body,
                image=preview_image,
                background=theme.current_colors["surface"],
                borderwidth=0,
            ).grid(row=0, column=0, rowspan=2, padx=(0, scaled(12)))

        text_column = 1 if preview_image else 0
        tk.Label(
            tooltip_body,
            text=path_names[-1],
            justify="left",
            anchor="w",
            wraplength=scaled(360),
            font="AppStrongFont",
            background=theme.current_colors["surface"],
            foreground=theme.current_colors["fg"],
        ).grid(row=0, column=text_column, sticky="new")
        if len(path_names) > 1:
            tk.Label(
                tooltip_body,
                text=" › ".join(path_names[:-1]),
                justify="left",
                anchor="w",
                wraplength=scaled(360),
                font="AppCaptionFont",
                background=theme.current_colors["surface"],
                foreground=theme.current_colors["muted"],
            ).grid(row=1, column=text_column, sticky="sew", pady=(scaled(8), 0))

        tooltip_window.update_idletasks()
        x = min(x_root + scaled(12), runtime.root.winfo_screenwidth() - tooltip_window.winfo_reqwidth())
        y = min(y_root + scaled(18), runtime.root.winfo_screenheight() - tooltip_window.winfo_reqheight())
        tooltip_window.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def on_tree_motion(event: tk.Event) -> None:
        nonlocal hovered_tree_item, tooltip_after_id
        item_id = treeview.identify_row(event.y)
        if item_id == hovered_tree_item:
            return
        hide_tree_tooltip()
        hovered_tree_item = item_id
        if item_id:
            tooltip_after_id = runtime.root.after(
                450,
                lambda: show_tree_tooltip(item_id, event.x_root, event.y_root),
            )

    def leave_tree() -> None:
        nonlocal hovered_tree_item
        hovered_tree_item = ""
        hide_tree_tooltip()

    search_after_id: str | None = None

    def schedule_search(*_args: str) -> None: # 输入停止片刻后执行筛选，避免连续重建树视图
        nonlocal search_after_id
        if search_after_id:
            runtime.root.after_cancel(search_after_id)

        def run_search() -> None:
            nonlocal search_after_id
            search_after_id = None
            refresh_resource_tree()

        search_after_id = runtime.root.after(150, run_search)

    def focus_search(_event: tk.Event) -> str:
        search_entry.focus_set()
        search_entry.selection_range(0, "end")
        return "break"

    def scroll_tree_horizontally(steps: float) -> str:
        hide_tree_tooltip()
        first, last = treeview.xview()
        treeview.xview_moveto(first + steps * (last - first) * 0.2)
        return "break"

    def on_tree_shift_mousewheel(event: tk.Event) -> str:
        delta_unit = 1 if os_name == "Darwin" else 120
        return scroll_tree_horizontally(-event.delta / delta_unit)

    refresh_resource_tree() # 初始展示完整资源树并展开一级目录
    search_var.trace_add("write", schedule_search)
    treeview.configure(yscrollcommand=on_tree_view_change)
    treeview.bind("<<TreeviewSelect>>", on_tree_select)
    treeview.bind("<<TreeviewOpen>>", lambda _event: runtime.root.after_idle(load_visible_tree_icons))
    treeview.bind("<Configure>", lambda event: resize_tree_column(event.width))
    treeview.bind("<Motion>", on_tree_motion)
    treeview.bind("<Leave>", lambda _event: leave_tree())
    treeview.bind("<ButtonPress>", lambda _event: hide_tree_tooltip())
    treeview.bind("<Shift-MouseWheel>", on_tree_shift_mousewheel)
    treeview.bind("<Shift-Button-4>", lambda _event: scroll_tree_horizontally(-1))
    treeview.bind("<Shift-Button-5>", lambda _event: scroll_tree_horizontally(1))
    search_entry.bind("<Escape>", lambda _event: search_var.set(""))
    runtime.root.bind("<Control-f>", focus_search)
    if os_name == "Darwin":
        runtime.root.bind("<Command-f>", focus_search)
