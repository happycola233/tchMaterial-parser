# -*- coding: utf-8 -*-
# 设置 Access Token 的窗口，以及其中的获取方法说明窗口

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import webbrowser

from . import runtime, theme
from .runtime import scaled
from .theme import ACCENT_BUTTON_STYLE, apply_titlebar_theme, register_themed_widget
from .widgets import bind_context_menu, bind_tab_navigation, center_window
from .. import config
from ..auth import format_token_json

ACCESS_TOKEN_LOGIN_URL = "https://auth.smartedu.cn/uias/login"
# 从官网 ND_UC_AUTH 取出签名所需的 access_token、mac_key、diff。
ACCESS_TOKEN_SCRIPT = """\
(function () {
  const authKey = Object.keys(localStorage).find(
    (key) => key.startsWith("ND_UC_AUTH")
  );
  if (!authKey) {
    console.error("未找到登录凭据，请确保已登录！");
    return;
  }
  const tokenData = JSON.parse(localStorage.getItem(authKey));
  const value = JSON.parse(tokenData.value);
  const credentials = JSON.stringify({
    access_token: value.access_token,
    mac_key: value.mac_key,
    diff: value.diff,
  });
  console.log(
    "%c请复制下面整段 JSON 并粘贴到下载工具：",
    "color: green; font-weight: bold"
  );
  console.log(credentials);
})();"""

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
    label = ttk.Label(frame, text="请粘贴从浏览器获取的登录凭据", style="Heading.TLabel")
    label.pack(anchor="w")
    hint_label = ttk.Label(
        frame,
        text="请先点击左下角“如何获取？”查看操作步骤，再把控制台输出的整段 JSON 粘贴到下方。凭据仅保存在本机；留空并保存即可清除。",
        style="Caption.TLabel",
        wraplength=scaled(360),
        justify="left",
    )
    hint_label.pack(anchor="w", pady=(scaled(2), scaled(10)))

    # 创建多行 Text（外面套一层卡片，以获得与其他控件一致的圆角边框）
    token_card = ttk.Frame(frame, style="Card.TFrame")
    token_card.pack(fill="both", expand=True)
    token_text = tk.Text(token_card, width=50, height=6, wrap="char", undo=True, font="AppBodyFont", padx=scaled(6), pady=scaled(4))
    token_text.pack(fill="both", expand=True)
    register_themed_widget(token_text)
    bind_context_menu(token_text)
    bind_tab_navigation(token_text)
    token_text.focus()

    # 旧版可能只存了 Access Token。一律回填三项 JSON，避免输入框仍是纯 Token。
    if config.access_token:
        token_text.insert("1.0", format_token_json(
            config.access_token,
            config.mac_key,
            config.token_diff,
        ))

    # 按下 Enter 键，保存 Access Token，并屏蔽换行事件
    def return_save_token(event: tk.Event) -> str:
        save_token()
        return "break"

    token_text.bind("<Return>", return_save_token)
    token_text.bind("<Shift-Return>", lambda e: "break") # 按下 Shift＋Enter 也不换行，直接屏蔽

    # 保存按钮
    def save_token() -> None:
        user_token = token_text.get("1.0", "end").strip()
        try:
            tip_info = config.set_access_token(user_token)
        except ValueError as error:
            messagebox.showerror("保存失败", str(error), parent=token_window)
            return
        messagebox.showinfo("保存成功", tip_info, parent=token_window)
        token_window.destroy()

    # 帮助按钮
    def show_token_help() -> None:
        help_win = tk.Toplevel(token_window)
        help_win.title("获取 Access Token 方法")
        help_win.resizable(True, True)
        help_win.focus() # 自动获得焦点
        help_win.transient(token_window) # 使窗口依赖于主窗口
        help_win.bind("<Escape>", lambda event: help_win.destroy()) # 绑定 Esc 键关闭窗口

        # 卡片中的文字需要使用与卡片一致的背景色，避免主题切换时出现色块。
        style = ttk.Style(help_win)
        style.configure(
            "TokenHelpCard.TFrame",
            background=theme.current_colors["surface"],
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "TokenHelpCard.TLabel",
            background=theme.current_colors["surface"],
            foreground=theme.current_colors["fg"],
        )
        style.configure(
            "TokenHelpCardStrong.TLabel",
            font="AppStrongFont",
            background=theme.current_colors["surface"],
            foreground=theme.current_colors["fg"],
        )
        style.configure(
            "TokenHelpCardCaption.TLabel",
            font="AppCaptionFont",
            background=theme.current_colors["surface"],
            foreground=theme.current_colors["muted"],
        )
        style.configure(
            "TokenHelpWarning.TLabel",
            font="AppCaptionFont",
            foreground="#9a5b00" if theme.current_theme == "light" else "#f2b95f",
        )

        help_frame = ttk.Frame(help_win, padding=(scaled(24), scaled(20)))
        help_frame.pack(fill="both", expand=True)

        ttk.Label(help_frame, text="从浏览器获取登录凭据", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            help_frame,
            text="按下面的步骤操作即可。复制控制台输出的整段 JSON，登录凭据只会保存在本机。",
            style="Caption.TLabel",
        ).pack(anchor="w", pady=(scaled(3), scaled(16)))

        def add_step(number: str, title: str, description: str) -> ttk.Frame:
            step = ttk.Frame(help_frame)
            step.pack(fill="x", pady=(0, scaled(12)))
            ttk.Label(step, text=number, style="Heading.TLabel", width=2).grid(row=0, column=0, sticky="nw")
            content = ttk.Frame(step)
            content.grid(row=0, column=1, sticky="ew")
            step.columnconfigure(1, weight=1)
            ttk.Label(content, text=title, style="Heading.TLabel").pack(anchor="w")
            ttk.Label(
                content,
                text=description,
                style="Caption.TLabel",
                justify="left",
                wraplength=scaled(650),
            ).pack(anchor="w", pady=(scaled(2), 0))
            return content

        login_step = add_step(
            "1",
            "登录国家中小学智慧教育平台",
            "使用你的平台账号完成登录；如果还没有账号，请先注册。",
        )

        def open_login_page() -> None:
            try:
                if not webbrowser.open_new_tab(ACCESS_TOKEN_LOGIN_URL):
                    raise RuntimeError("系统未能打开默认浏览器")
            except Exception as error:
                messagebox.showerror(
                    "无法打开登录页面",
                    f"请复制下面的地址并在浏览器中打开：\n{ACCESS_TOKEN_LOGIN_URL}\n\n{error}",
                    parent=help_win,
                )

        ttk.Button(login_step, text="打开登录页面 ↗", command=open_login_page).pack(anchor="w", pady=(scaled(8), 0))

        add_step(
            "2",
            "打开浏览器控制台",
            "按 F12 或 Ctrl + Shift + I，也可以右键页面并选择“检查”；然后切换到“控制台（Console）”。",
        )
        paste_step = add_step(
            "3",
            "复制并运行脚本",
            "点击“复制代码”，粘贴到浏览器控制台，然后按 Enter 运行。只需复制下面代码框中的内容。",
        )
        ttk.Label(
            paste_step,
            text=(
                "控制台阻止粘贴？这是浏览器的安全机制。本脚本只读取当前页面的本地登录数据并输出 Token；"
                "确认后，必须用键盘手动输入黄色提示要求的短语（如“allow pasting”或“允许粘贴”，"
                "以实际提示为准），按 Enter 后再重新粘贴。"
            ),
            style="TokenHelpWarning.TLabel",
            justify="left",
            wraplength=scaled(650),
        ).pack(anchor="w", pady=(scaled(6), 0))

        # 代码与说明分离，用户可以清楚看到唯一需要复制到控制台的内容。
        code_card = ttk.Frame(help_frame, style="Card.TFrame", padding=(scaled(14), scaled(12)))
        code_card.pack(fill="both", expand=True, padx=(scaled(28), 0))

        # Card.TFrame 自带边框，只用于最外层卡片；内部容器使用无边框样式，避免出现重叠细线。
        code_header = ttk.Frame(code_card, style="TokenHelpCard.TFrame")
        code_header.pack(fill="x", pady=(0, scaled(8)))
        code_title = ttk.Frame(code_header, style="TokenHelpCard.TFrame")
        code_title.pack(side="left", fill="x", expand=True)
        ttk.Label(
            code_title,
            text="复制到浏览器控制台",
            style="TokenHelpCardStrong.TLabel",
        ).pack(anchor="w")
        copy_status = ttk.Label(
            code_title,
            text="此按钮只复制脚本，不会复制其他说明文字",
            style="TokenHelpCardCaption.TLabel",
        )
        copy_status.pack(anchor="w", pady=(scaled(2), 0))

        def copy_script() -> None:
            try:
                help_win.clipboard_clear()
                help_win.clipboard_append(ACCESS_TOKEN_SCRIPT)
                copy_button.configure(text="✓ 已复制")
                copy_status.configure(text="已复制；若粘贴被拦截，请按上方第 3 步操作")
            except tk.TclError as error:
                messagebox.showerror("复制失败", f"无法写入剪贴板：\n{error}", parent=help_win)

        copy_button = ttk.Button(
            code_header,
            text="复制代码",
            style=ACCENT_BUTTON_STYLE,
            command=copy_script,
        )
        copy_button.pack(side="right", padx=(scaled(12), 0))

        # Cascadia Mono 的代码字形更清晰美观；系统未安装时保留 TkFixedFont 原有的字体回退逻辑。
        code_font = tkfont.nametofont("TkFixedFont").copy()
        if "Cascadia Mono" in tkfont.families(help_win):
            code_font.configure(family="Cascadia Mono")

        code_text = tk.Text(
            code_card,
            width=78,
            height=14,
            wrap="none",
            font=code_font,
            padx=scaled(10),
            pady=scaled(8),
            cursor="arrow",
        )
        setattr(code_text, "_font_ref", code_font) # 防止局部字体对象被垃圾回收后失效
        code_text.insert("1.0", ACCESS_TOKEN_SCRIPT)
        code_text.config(state="disabled")
        code_text.pack(fill="both", expand=True)
        register_themed_widget(code_text)
        bind_context_menu(code_text, "readonly")

        result_card = ttk.Frame(help_frame, style="Card.TFrame", padding=(scaled(14), scaled(11)))
        result_card.pack(fill="x", padx=(scaled(28), 0), pady=(scaled(12), 0))
        ttk.Label(
            result_card,
            text="运行后，复制控制台输出的整段 JSON",
            style="TokenHelpCardStrong.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            result_card,
            text="复制花括号包起来的那一整行，再返回上一窗口粘贴并保存。",
            style="TokenHelpCard.TLabel",
            justify="left",
            wraplength=scaled(700),
        ).pack(anchor="w", pady=(scaled(3), 0))

        button_frame = ttk.Frame(help_frame)
        button_frame.pack(fill="x", pady=(scaled(16), 0))
        ttk.Button(button_frame, text="关闭", command=help_win.destroy).pack(side="right")

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
