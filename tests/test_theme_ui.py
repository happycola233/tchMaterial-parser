from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import unittest

import pytest

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tchmaterial_parser.ui import runtime, theme


class ThemeUITest(unittest.TestCase):
    __test__ = False # 由下方 pytest 入口在独立进程运行真实 Tk 交互测试

    def setUp(self):
        try:
            # 与主窗口一致地指定 className，根窗口的类名因此不再是 Tk
            self.root = tk.Tk(className="tchmaterial-parser")
        except tk.TclError as error:
            if "no display name" in str(error) or "couldn't connect to display" in str(error):
                self.skipTest(str(error))
            raise
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        enter = self.context.enter_context
        enter(patch.object(runtime, "root", self.root, create=True))
        enter(patch.object(runtime, "ui_scale", 1.0))
        enter(patch.object(theme, "ui_font_family", "TkDefaultFont", create=True))
        for name, value in (("theme_actions", []), ("themed_widgets", set()), ("current_colors", {}), ("current_theme", "light"), ("switched_theme", "light")):
            enter(patch.object(theme, name, value))
        ttk.Label(self.root, text="测试").pack()

    def assert_custom_style_kept(self, theme_name):
        theme.apply_theme(theme_name)
        self.root.update()
        self.assertEqual(self.root.bind_class(self.root.winfo_class(), "<<ThemeChanged>>"), "")

        # 其他窗口创建时会配置自己的样式，由此触发的 <<ThemeChanged>> 不应把全局字体与底色改回 sv-ttk 默认值
        style = ttk.Style(self.root)
        style.configure("Probe.TLabel", padding=1)
        self.root.update()
        self.assertEqual(str(style.lookup(".", "font")), "AppBodyFont")
        self.assertEqual(str(style.lookup(".", "background")), theme.THEME_COLORS[theme_name]["page"])

    def test_custom_style_survives_later_style_configure(self):
        self.assert_custom_style_kept("light")

    def test_custom_style_survives_theme_switch(self):
        self.assert_custom_style_kept("light")
        self.assert_custom_style_kept("dark")


@pytest.mark.parametrize("case", unittest.defaultTestLoader.getTestCaseNames(ThemeUITest))
def test_theme_interaction(case):
    # 隔离 Tk 全局状态，并避免 pytest 切换标准流文件描述符干扰 Windows Tcl 的文件读取。
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), case],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    if result.returncode == 77:
        pytest.skip("当前环境没有图形显示服务，需在桌面环境或 Xvfb 中运行")
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.TestSuite([ThemeUITest(sys.argv[1])]))
    raise SystemExit(77 if result.skipped else int(not result.wasSuccessful()))
