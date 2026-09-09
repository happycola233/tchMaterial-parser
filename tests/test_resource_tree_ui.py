from contextlib import ExitStack
import io
from pathlib import Path
import re
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from PIL import Image
import pytest

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tchmaterial_parser.ui import resource_tree, runtime, theme


RESOURCES = {"books": {"display_name": "电子教材", "children": {
    "primary": {"display_name": "小学", "children": {
        "a": {"display_name": "语文 一年级上册", "content_id": "a"},
        "b": {"display_name": "语文 一年级下册", "content_id": "b", "custom_properties": {"thumbnails": ["https://example.com/cover.png"]}},
    }},
}}}


class ResourceTreeUITest(unittest.TestCase):
    __test__ = False # 由下方 pytest 入口在独立进程运行真实 Tk 交互测试

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            if "no display name" in str(error) or "couldn't connect to display" in str(error):
                raise unittest.SkipTest(f"当前环境没有图形显示服务：{error}") from error
            raise
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        self.addCleanup(self.destroy_widgets)
        enter = self.context.enter_context
        enter(patch.object(runtime, "root", self.root, create=True))
        enter(patch.object(runtime, "ui_scale", 1.0))
        enter(patch.object(runtime, "app_closing", False))
        enter(patch.object(theme, "ui_font_family", "TkDefaultFont", create=True))
        for name, value in (("theme_actions", []), ("themed_widgets", set()), ("current_colors", {}), ("current_theme", "light"), ("switched_theme", "light")):
            enter(patch.object(theme, name, value))
        theme.apply_theme("light")
        enter(patch.object(resource_tree, "thread_it", lambda fn, *args: fn(*args)))
        # 隐藏测试窗口，单独模拟封面进入可视区域，仍执行真实的加载与图片合成代码。
        enter(patch.object(ttk.Treeview, "bbox", return_value=(0, 0, 100, 38)))
        cover = io.BytesIO()
        Image.new("RGB", (80, 112), "#c4ded2").save(cover, format="PNG")
        response = type("CoverResponse", (), {"ok": True, "content": cover.getvalue()})()
        enter(patch.object(resource_tree.session, "get", return_value=response))
        self.pane = ttk.Frame(self.root)
        self.urls = tk.Text(self.root, undo=True)
        self.errors = []
        self.root.report_callback_exception = lambda _type, error, _traceback: self.errors.append(error)
        resource_tree.build_resource_tree(self.pane, RESOURCES, self.urls)
        widgets = list(self.descendants(self.pane))
        self.tree = next(widget for widget in widgets if isinstance(widget, ttk.Treeview))
        self.search = next(widget for widget in widgets if isinstance(widget, ttk.Entry))
        self.count = next(widget for widget in widgets if isinstance(widget, ttk.Label) and widget.grid_info().get("column") == 1)
        self.root.update()

    def tearDown(self):
        if hasattr(self, "errors"):
            self.assertEqual(self.errors, [])

    def destroy_widgets(self):
        self.root.update()
        for widget in self.root.winfo_children():
            widget.destroy()

    def descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self.descendants(child)

    def toggle(self, item_id):
        self.tree.focus(item_id)
        # 执行已注册的空格事件回调，无需让隐藏窗口抢占键盘焦点。
        command = re.search(r"\[([^\s]+)", self.tree.bind("<space>")).group(1)
        self.root.tk.call(command, "unused")
        self.root.update()

    def filter(self, query):
        self.search.delete(0, "end")
        self.search.insert(0, query)
        self.root.after(180, self.root.quit)
        self.root.mainloop()
        self.root.update()

    def url(self, suffix):
        return resource_tree.build_resource_url(f"books:primary:{suffix}", RESOURCES["books"]["children"]["primary"]["children"][suffix])

    def lines(self):
        return {line.strip() for line in self.urls.get("1.0", "end").splitlines() if line.strip()}

    def image(self, item_id):
        name = str(self.tree.item(item_id, "image")[0])
        self.assertIn(name, self.root.tk.call("image", "names"))
        return Image.open(io.BytesIO(self.root.tk.call(name, "data", "-format", "png")))

    def assert_state(self, item_id, state):
        image = self.image(item_id)
        expected = resource_tree.draw_checkbox_image(18, state, theme.current_colors)
        top = (image.height - expected.height) // 2
        self.assertEqual(image.crop((0, top, 18, top + 18)).convert("RGBA").tobytes(), expected.tobytes())

    def test_cover_and_checkbox_survive_search_clear_and_theme_changes(self):
        width = self.image("books:primary:b").width
        self.assertGreater(width, 24)
        self.toggle("books:primary:b")
        for name in ("dark", "light"):
            theme.apply_theme(name)
            for query in ("下册", ""):
                self.filter(query)
                self.assertEqual(self.image("books:primary:b").width, width)
                self.assert_state("books:primary:b", "checked")

    def test_filtered_category_only_toggles_visible_resources(self):
        self.filter("下册")
        self.toggle("books:primary")
        self.assertEqual(self.lines(), {self.url("b")})
        self.assert_state("books:primary", "checked")
        self.filter("")
        self.assert_state("books:primary", "partial")
        self.assert_state("books:primary:a", "unchecked")

    def test_filtered_uncheck_preserves_hidden_selection(self):
        self.toggle("books:primary")
        self.filter("下册")
        self.toggle("books:primary")
        self.assertEqual(self.lines(), {self.url("a")})
        self.assert_state("books:primary", "unchecked")
        self.filter("")
        self.assert_state("books:primary", "partial")

    def test_manual_deletion_then_parent_selection_restores_both_urls(self):
        self.toggle("books:primary:b")
        self.urls.delete("1.0", "end")
        self.root.update()
        self.assert_state("books:primary:b", "unchecked")
        self.assertEqual(self.count.cget("text"), "")
        self.toggle("books:primary")
        self.assertEqual(self.lines(), {self.url("a"), self.url("b")})
        self.assertEqual(self.count.cget("text"), "已选 2 项")

    def test_paste_whitespace_and_undo_sync_without_changing_other_urls(self):
        external = "https://example.com/manual"
        self.urls.insert("1.0", f"  {self.url('b')}  \n{external}")
        self.urls.edit_separator()
        self.root.update()
        self.assert_state("books:primary:b", "checked")
        self.urls.delete("1.0", "end")
        self.urls.edit_separator()
        self.root.update()
        self.assert_state("books:primary:b", "unchecked")
        self.urls.edit_undo()
        self.root.update()
        self.assertIn(self.url("b"), self.lines())
        self.assert_state("books:primary:b", "checked")
        self.toggle("books:primary:b")
        self.assertEqual(self.lines(), {external})


@pytest.mark.parametrize("case", unittest.defaultTestLoader.getTestCaseNames(ResourceTreeUITest))
def test_resource_tree_interaction(case):
    # 隔离 Tk 全局状态，并避免 pytest 切换标准流文件描述符干扰 Windows Tcl 的文件读取。
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), case],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    if result.returncode == 77:
        pytest.skip("当前环境没有图形显示服务，需在桌面环境或 Xvfb 中运行")
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.TestSuite([ResourceTreeUITest(sys.argv[1])]))
    raise SystemExit(77 if result.skipped else int(not result.wasSuccessful()))
