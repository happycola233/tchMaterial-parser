# -*- coding: utf-8 -*-
# 左侧资源列表：勾选教材或分类、搜索筛选、封面按需加载与悬停预览

import io
import tkinter as tk
from collections.abc import Iterator
from tkinter import ttk
import tkinter.font as tkfont
from PIL import Image, ImageDraw, ImageOps, ImageTk

from . import runtime, theme
from .runtime import scaled, thread_it, ui_call
from .widgets import auto_hide_scrollbar, bind_context_menu
from ..catalog import count_resource_items, filter_resource_items
from ..images import fit_cover_image
from ..network import session
from ..platform_utils import os_name, print_error

def build_resource_url(item_path: str, resource_data: dict) -> str: # 根据树项路径与资源数据生成资源页面链接
    resource_type = resource_data.get("resource_type_code") or "assets_document"
    content_id = resource_data.get("content_id") or item_path.split(":")[-1]
    root_id = item_path.split(":")[0]
    if resource_type == "teachingmaterials":
        return f"https://basic.smartedu.cn/syncClassroom{'/prepare' if root_id == '__internal_prepare_lesson' else ''}?defaultTag={'%2F'.join(item_path.split(':')[1:])}"
    return f"https://basic.smartedu.cn/tchMaterial/detail?contentType={resource_type}&contentId={content_id}&catalogType=tchMaterial&subCatalog=tchMaterial"

def iter_leaf_resources(items: dict[str, dict], parent_path: str = "") -> Iterator[tuple[str, dict]]: # 遍历分类子树，产出每个末级资源的（树项路径， 资源数据）
    for option_id, option_data in items.items():
        item_path = f"{parent_path}:{option_id}" if parent_path else option_id
        children: dict[str, dict] = option_data.get("children", {})
        if children: # 分类节点继续向下遍历
            yield from iter_leaf_resources(children, item_path)
        else:
            yield item_path, option_data

def collect_resource_urls(items: dict[str, dict], parent_path: str = "") -> list[str]: # 递归收集分类子树中所有末级资源的链接
    return [build_resource_url(item_path, resource_data) for item_path, resource_data in iter_leaf_resources(items, parent_path)]

def find_tree_node(items: dict[str, dict], item_path: str) -> dict | None: # 按树项路径在分类树中定位节点数据
    node = None
    branch = items
    for segment in item_path.split(":"):
        node = branch.get(segment)
        if node is None:
            return None
        branch = node.get("children", {})
    return node

def category_check_state(leaf_ids: list[str], checked_items: set[str]) -> str: # 依据子树内末级资源的勾选情况得出分类的三态
    if not leaf_ids:
        return "unchecked"
    checked_count = sum(1 for leaf_id in leaf_ids if leaf_id in checked_items)
    if checked_count == 0:
        return "unchecked"
    return "checked" if checked_count == len(leaf_ids) else "partial"

def should_check_category(leaf_ids: list[str], checked_items: set[str]) -> bool: # 点击分类时的目标状态：未全选时补全勾选，已全选时取消
    return category_check_state(leaf_ids, checked_items) != "checked"

def draw_checkbox_image(size: int, state: str, colors: dict[str, str]) -> Image.Image: # 绘制跟随主题配色的三态复选框图标
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    selected = state in ("checked", "partial")
    border_width = max(2, size // 10)
    draw.rounded_rectangle(
        (border_width // 2, border_width // 2, size - 1 - border_width // 2, size - 1 - border_width // 2),
        radius=max(2, size // 5),
        fill=colors["selbg"] if state == "checked" else colors["surface"],
        outline=colors["selbg"] if selected else colors["muted"],
        width=border_width,
    )
    if state == "checked": # 对勾
        draw.line(
            (size * 0.24, size * 0.53, size * 0.44, size * 0.74, size * 0.78, size * 0.3),
            fill=colors["selfg"],
            width=max(2, size // 7),
            joint="curve",
        )
    elif state == "partial": # 半选横线
        inset = size * 0.32
        draw.line((inset, size / 2, size - inset, size / 2), fill=colors["selbg"], width=max(2, size // 10))
    return image

def build_resource_tree(pane: ttk.Frame, resource_list: dict[str, dict], url_text: tk.Text) -> None: # 在给定的子框架内构建资源列表
    pane.columnconfigure(0, weight=1)
    pane.rowconfigure(2, weight=1)

    treeview_header = ttk.Frame(pane)
    treeview_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, scaled(6)))
    treeview_header.columnconfigure(1, weight=1)
    treeview_label = ttk.Label(treeview_header, text="资源列表", style="Heading.TLabel") # 添加树视图标签
    treeview_label.grid(row=0, column=0, sticky="w")
    checked_count_label = ttk.Label(treeview_header, style="Caption.TLabel") # 显示当前勾选的教材数量
    checked_count_label.grid(row=0, column=1, sticky="e", padx=(0, scaled(8)))
    search_status_label = ttk.Label(treeview_header, style="Caption.TLabel")
    search_status_label.grid(row=0, column=2, sticky="e")

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

    treeview = ttk.Treeview(pane, style="Custom.Treeview", show="tree", selectmode="extended", height=12) # 创建树视图，使用自定义样式（该样式在 apply_theme() 中配置），隐藏列标题；勾选状态用复选框图标表达，选择模式仅供键盘导航
    treeview.column("#0", stretch=False)
    treeview.grid(row=2, column=0, sticky="nsew")
    treeview_scrollbar = ttk.Scrollbar(pane, orient="vertical", command=treeview.yview)
    treeview_scrollbar.grid(row=2, column=1, sticky="ns")
    treeview_horizontal_scrollbar = ttk.Scrollbar(pane, orient="horizontal", command=treeview.xview)
    treeview.configure(xscrollcommand=lambda f, l: auto_hide_scrollbar(treeview_horizontal_scrollbar, f, l))
    treeview_horizontal_scrollbar.grid(row=3, column=0, sticky="ew")

    tree_item_data: dict[str, dict] = {} # 键为树项 ID，值为资源数据
    tree_item_paths: dict[str, tuple[str, ...]] = {} # 保存完整分类路径，用于悬停提示
    tree_item_images: dict[str, ImageTk.PhotoImage] = {} # 持有树项图标（复选框与封面的合成图）的引用防止被回收，筛选后继续复用
    tree_cover_images: dict[str, Image.Image] = {} # 已加载封面的缩放图，勾选状态变化时与复选框重新合成
    tree_preview_images: dict[str, ImageTk.PhotoImage] = {} # 缓存大尺寸封面，用于悬停预览
    loading_tree_images: set[str] = set()
    checked_items: set[str] = set() # 已勾选末级资源的树项路径，搜索重建树视图后仍保留
    checkbox_pils: dict[str, Image.Image] = {} # 三态复选框底图，跟随主题配色重建
    checkbox_icons: dict[str, ImageTk.PhotoImage] = {} # 无封面树项直接使用的复选框图标（已含右侧间距）
    tree_font = tkfont.nametofont("AppBodyFont")
    tree_cover_size = (scaled(26), scaled(28))
    tree_cover_gap = scaled(8) # 用透明区域拉开封面与标题，避免改变封面尺寸
    checkbox_size = scaled(18)
    checkbox_gap = scaled(6) # 复选框与封面、标题之间的间距
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
                image=compose_item_image(item_id),
                open=expand_all or not parent,
            )
            children: dict[str, dict] = option_data.get("children", {})
            if children: # 如果有子项，递归构建子树项
                build_tree_items(item_id, children, path_names, expand_all)

            depth_width = len(path_names) * scaled(20)
            if option_data.get("custom_properties", {}).get("thumbnails"):
                image_width = checkbox_size + checkbox_gap + tree_cover_size[0] + get_tree_cover_gap(display_name) + scaled(4)
            else:
                image_width = checkbox_size + checkbox_gap
            tree_content_width = max(tree_content_width, depth_width + image_width + tree_font.measure(display_name) + scaled(20))

    def resize_tree_column(width: int) -> None: # 让树列至少铺满可视区域，内容过长时启用横向滚动
        treeview.column("#0", width=max(tree_content_width, width - scaled(2)))

    def rebuild_checkbox_images() -> None: # 按当前主题配色生成三态复选框图标
        checkbox_pils.clear()
        checkbox_icons.clear()
        for state in ("checked", "partial", "unchecked"):
            checkbox_pils[state] = draw_checkbox_image(checkbox_size, state, theme.current_colors)
            checkbox_icons[state] = ImageTk.PhotoImage(ImageOps.expand(checkbox_pils[state], border=(0, 0, checkbox_gap, 0), fill=(0, 0, 0, 0)))

    def on_theme_changed() -> None: # 主题切换后重建复选框配色并刷新全部树项图标
        rebuild_checkbox_images()
        for item_id in list(tree_item_data):
            refresh_item_image(item_id)

    def item_check_state(item_id: str) -> str: # 末级资源为勾选/未勾选两态，分类按后代整体勾选情况显示三态
        node = find_tree_node(resource_list, item_id)
        if node is None:
            return "unchecked"
        children = node.get("children")
        if children:
            leaf_ids = [leaf_id for leaf_id, _leaf_data in iter_leaf_resources(children, item_id)]
            return category_check_state(leaf_ids, checked_items)
        return "checked" if item_id in checked_items else "unchecked"

    def compose_item_image(item_id: str) -> ImageTk.PhotoImage: # 合成树项图标：勾选状态对应的复选框与已加载的封面
        state = item_check_state(item_id)
        cover = tree_cover_images.get(item_id)
        if cover is None: # 尚未加载封面的树项直接复用带间距的复选框图标
            return checkbox_icons[state]
        checkbox = checkbox_pils[state]
        height = max(checkbox.height, cover.height)
        image = Image.new("RGBA", (checkbox.width + checkbox_gap + cover.width, height), (0, 0, 0, 0))
        image.paste(checkbox, (0, (height - checkbox.height) // 2), checkbox)
        image.paste(cover, (checkbox.width + checkbox_gap, (height - cover.height) // 2), cover)
        return ImageTk.PhotoImage(image)

    def refresh_item_image(item_id: str) -> None: # 重新合成并应用树项图标（勾选状态或封面变化后调用）
        image = compose_item_image(item_id)
        tree_item_images[item_id] = image
        if treeview.exists(item_id):
            treeview.item(item_id, image=image)

    def apply_tree_icon(item_id: str, image: Image.Image | None) -> None:
        loading_tree_images.discard(item_id)
        if image is not None:
            tree_image = fit_cover_image(image, tree_cover_size)
            # 搜索重建后树项可能暂不在当前视图中，仍缓存封面供下次合成复用
            resource_data = tree_item_data.get(item_id) or find_tree_node(resource_list, item_id) or {}
            cover_gap = get_tree_cover_gap(resource_data.get("display_name", ""))
            if cover_gap:
                tree_image = ImageOps.expand(tree_image, border=(0, 0, cover_gap, 0), fill=(0, 0, 0, 0))
            tree_cover_images[item_id] = tree_image
            tree_preview_images[item_id] = ImageTk.PhotoImage(image)
        refresh_item_image(item_id)

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
        if thumbnails and item_id not in tree_cover_images and item_id not in loading_tree_images:
            loading_tree_images.add(item_id)
            thread_it(load_tree_icon, item_id, thumbnails[0])

    def load_visible_tree_icons() -> None: # 搜索或滚动后只加载当前可见资源的封面
        for item_id, resource_data in tree_item_data.items():
            if not resource_data.get("children") and treeview.bbox(item_id):
                queue_tree_icon(item_id)

    def on_tree_view_change(first: str, last: str) -> None:
        auto_hide_scrollbar(treeview_scrollbar, first, last)
        ui_call(load_visible_tree_icons)

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
        ui_call(load_visible_tree_icons)

    def insert_resource_urls(urls: list[str]) -> None: # 将链接追加到 URL 输入框，跳过已存在的行
        existing_lines = set(url_text.get("1.0", "end").splitlines())
        new_urls = [url for url in dict.fromkeys(urls) if url and url not in existing_lines] # 保序去重，并跳过已存在的链接
        if not new_urls:
            return

        url_text_content = url_text.get("1.0", "end")[:-1] # 获取 URL 输入框的内容，去掉最后一个换行符
        # URL 输入框为空或最后一个字符为换行符时，插入的内容前面不加换行
        prefix = "" if not url_text_content or url_text_content[-1] == "\n" else "\n"
        url_text.insert("end", prefix + "\n".join(new_urls))
        url_text.see("end") # 滚动到文本框底部

    def remove_resource_urls(urls: list[str]) -> None: # 从 URL 输入框移除已取消勾选资源的链接行
        if not urls:
            return
        url_set = set(urls)
        lines = url_text.get("1.0", "end").splitlines()
        kept_lines = [line for line in lines if line not in url_set]
        if len(kept_lines) == len(lines):
            return
        url_text.delete("1.0", "end")
        if kept_lines:
            url_text.insert("1.0", "\n".join(kept_lines))

    def update_checked_count() -> None: # 更新已勾选教材数量提示
        checked_count_label.config(text=f"已选 {len(checked_items)} 项" if checked_items else "")

    def toggle_item(item_id: str) -> None: # 切换树项勾选状态：分类按三态决定目标状态并级联其下所有末级资源
        node = find_tree_node(resource_list, item_id)
        if node is None:
            return
        children = node.get("children")
        if children:
            leafs = list(iter_leaf_resources(children, item_id))
            checked = should_check_category([leaf_id for leaf_id, _leaf_data in leafs], checked_items)
        else:
            leafs = [(item_id, node)]
            checked = item_id not in checked_items
        set_items_checked(leafs, checked)

    def set_items_checked(leafs: list[tuple[str, dict]], checked: bool) -> None: # 批量更新末级资源勾选状态，级联刷新图标并同步 URL 输入框
        changed_leafs: list[tuple[str, dict]] = []
        for leaf_id, leaf_data in leafs:
            if checked == (leaf_id in checked_items):
                continue
            if checked:
                checked_items.add(leaf_id)
            else:
                checked_items.discard(leaf_id)
            changed_leafs.append((leaf_id, leaf_data))
        if not changed_leafs:
            return

        refresh_ids: set[str] = set() # 状态变化的末级资源及其各级祖先分类都需要刷新图标
        for leaf_id, _leaf_data in changed_leafs:
            segments = leaf_id.split(":")
            refresh_ids.update(":".join(segments[:index]) for index in range(1, len(segments) + 1))
        for refresh_id in refresh_ids:
            if refresh_id in tree_item_data:
                refresh_item_image(refresh_id)

        urls = [build_resource_url(leaf_id, leaf_data) for leaf_id, leaf_data in changed_leafs]
        if checked:
            insert_resource_urls(urls)
        else:
            remove_resource_urls(urls)
        update_checked_count()

    def on_tree_press(event: tk.Event) -> str | None: # 按下鼠标时隐藏悬停提示；左键点击标题或封面（含复选框）时切换勾选，点击箭头或缩进保持展开收起
        hide_tree_tooltip()
        if event.num != 1 or treeview.identify("element", event.x, event.y) not in ("text", "image"):
            return None
        item_id = treeview.identify_row(event.y)
        if not item_id:
            return None
        treeview.focus_set() # 确保随后可以直接用方向键与空格操作
        treeview.selection_set(item_id)
        treeview.focus(item_id)
        toggle_item(item_id)
        return "break"

    def on_tree_space(_event: tk.Event) -> str: # 空格键切换当前焦点树项的勾选状态
        item_id = treeview.focus()
        if item_id:
            toggle_item(item_id)
        return "break"

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
            tooltip_after_id = runtime.root.after(450, lambda: show_tree_tooltip(item_id, event.x_root, event.y_root))

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

    rebuild_checkbox_images() # 构建树项前先生成三态复选框图标
    theme.on_theme_applied(on_theme_changed) # 主题切换后重建复选框配色并刷新树项图标
    update_checked_count()
    refresh_resource_tree() # 初始展示完整资源树并展开一级目录
    search_var.trace_add("write", schedule_search)
    treeview.configure(yscrollcommand=on_tree_view_change)
    treeview.bind("<space>", on_tree_space)
    treeview.bind("<<TreeviewOpen>>", lambda _event: ui_call(load_visible_tree_icons))
    treeview.bind("<Configure>", lambda event: resize_tree_column(event.width))
    treeview.bind("<Motion>", on_tree_motion)
    treeview.bind("<Leave>", lambda _event: leave_tree())
    treeview.bind("<ButtonPress>", on_tree_press)
    treeview.bind("<Shift-MouseWheel>", on_tree_shift_mousewheel)
    treeview.bind("<Shift-Button-4>", lambda _event: scroll_tree_horizontally(-1))
    treeview.bind("<Shift-Button-5>", lambda _event: scroll_tree_horizontally(1))
    search_entry.bind("<Escape>", lambda _event: search_var.set(""))
    runtime.root.bind("<Control-f>", focus_search)
    if os_name == "Darwin":
        runtime.root.bind("<Command-f>", focus_search)
