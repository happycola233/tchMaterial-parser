from pathlib import Path
from contextlib import ExitStack
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from src.tchmaterial_parser.api import ResourceInfo
from src.tchmaterial_parser.ui import download_panel as panel


class DownloadBatchTest(unittest.TestCase):
    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        self.callbacks = queue.Queue()
        self.threads = []
        self.root_directory = Path(__file__).resolve().parents[1] / ".tmp"
        self.root_directory.mkdir(exist_ok=True)
        self.directory = self.context.enter_context(tempfile.TemporaryDirectory(dir=self.root_directory))
        self.context.enter_context(patch.object(panel, "download_states", []))
        for name in ("progress_label", "download_progress_bar", "download_btn"):
            self.context.enter_context(patch.object(panel, name, Mock(), create=True))
        self.notice = self.context.enter_context(patch.object(panel.messagebox, "showinfo"))
        self.warning = self.context.enter_context(patch.object(panel.messagebox, "showwarning"))
        self.context.enter_context(patch.object(panel, "ui_call", lambda fn, *args, **kwargs: self.callbacks.put((fn, args, kwargs))))

        def thread_it(fn):
            thread = threading.Thread(target=fn, daemon=True)
            self.threads.append(thread)
            thread.start()

        self.context.enter_context(patch.object(panel, "thread_it", thread_it))

    def targets(self, count):
        return [(ResourceInfo(f"教材{index}", f"https://example.com/{index}.pdf", "pdf", []), str(Path(self.directory) / f"教材{index}.pdf")) for index in range(count)]

    def finish(self):
        for thread in self.threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "批次线程没有退出")
        while not self.callbacks.empty():
            fn, args, kwargs = self.callbacks.get_nowait()
            fn(*args, **kwargs)

    def test_all_tasks_registered_before_fast_failure_and_queued_work(self):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        observed = []

        def download(url, path, chapters, state):
            observed.append(len(panel.download_states))
            if url.endswith("/0.pdf"):
                state["failed_reason"] = "HTTP 404"
            else:
                entered.set()
                release.wait(timeout=5)
            state["finished"] = True

        with patch.object(panel, "download_file", download):
            panel.start_download_batch(self.targets(5), self.directory)
            self.assertTrue(entered.wait(timeout=3))
            self.assertTrue(panel.downloads_active())
            self.assertTrue(self.callbacks.empty())
            panel.download_btn.config.assert_not_called()
            release.set()
            self.finish()

        self.assertEqual(observed, [5] * 5)
        self.warning.assert_called_once()
        self.notice.assert_not_called()
        panel.download_btn.config.assert_called_once_with(state="normal", text="下载")

    def test_concurrent_downloads_emit_one_batch_notice(self):
        barrier = threading.Barrier(2)

        class Response:
            ok = False
            status_code = 404
            content = b""

            def close(self):
                barrier.wait(timeout=3)

        with patch.object(panel, "request_download", side_effect=lambda url: (Response(), [url])):
            panel.start_download_batch(self.targets(2), self.directory)
            self.finish()

        self.warning.assert_called_once()
        self.assertFalse(panel.downloads_active())
        self.assertTrue(all(state["failed_reason"] for state in panel.download_states))

    def test_skips_files_that_were_already_downloaded(self):
        targets = self.targets(3)
        Path(targets[0][1]).write_bytes(b"old")
        Path(targets[2][1]).write_bytes(b"old")
        requested = []

        def download(url, path, chapters, state):
            requested.append(url)
            state["finished"] = True

        with patch.object(panel, "download_file", download):
            panel.start_download_batch(targets, self.directory, skip_existing=True)
            self.finish()

        self.assertEqual(requested, [targets[1][0].url]) # 只下载缺失的那个文件
        self.assertEqual([state["skipped"] for state in panel.download_states], [True, False, True])
        self.assertEqual(Path(targets[0][1]).read_bytes(), b"old") # 已有文件保持原样
        self.notice.assert_called_once_with("下载完成", f"文件已下载到：{self.directory}\n已跳过 2 个此前已下载完成的文件。")

    def test_skipping_every_file_needs_no_download_thread(self):
        targets = self.targets(2)
        for _, path in targets:
            Path(path).write_bytes(b"old")

        with patch.object(panel, "request_download", side_effect=AssertionError("不应发起请求")):
            panel.start_download_batch(targets, self.directory, skip_existing=True)
            self.finish()

        self.assertEqual(self.threads, [])
        self.assertFalse(panel.downloads_active())
        self.notice.assert_called_once_with("下载完成", f"文件已下载到：{self.directory}\n已跳过 2 个此前已下载完成的文件。")

    def test_stop_keeps_finished_files_and_discards_unfinished_ones(self):
        targets = self.targets(4)
        finished_path = Path(targets[0][1])

        class CompleteResponse: # 停止请求前就下载完成的文件
            ok = True
            headers = {"Content-Length": "3"}

            def iter_content(self, **kwargs):
                yield b"abc"

            def close(self):
                pass

        class BlockingResponse: # 传输途中等待停止请求
            ok = True
            headers = {"Content-Length": "6"}

            def iter_content(self, **kwargs):
                yield b"abc"
                deadline = time.monotonic() + 5
                while not panel._stop_requested.is_set() and time.monotonic() < deadline:
                    time.sleep(0.01)
                yield b"def"

            def close(self):
                pass

        def request_download(url):
            return (CompleteResponse() if url.endswith("/0.pdf") else BlockingResponse()), [url]

        with patch.object(panel, "request_download", side_effect=request_download):
            panel.start_download_batch(targets, self.directory)
            deadline = time.monotonic() + 5
            while not finished_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(finished_path.exists(), "第一个文件应在停止前下载完成")
            panel.stop_downloads()
            self.finish()

        states = panel.download_states
        self.assertTrue(all(state["finished"] for state in states))
        self.assertFalse([state["failed_reason"] for state in states if state["failed_reason"]])
        self.assertTrue(any(state["stopped"] for state in states))
        self.assertEqual(finished_path.read_bytes(), b"abc")
        # 未完成的文件不留下半截内容，也不留下临时文件
        self.assertEqual([path.name for path in Path(self.directory).iterdir()], [finished_path.name])
        self.notice.assert_called_once_with("下载已停止", f"下载已停止。\n文件已下载到：{self.directory}")
        panel.download_btn.config.assert_any_call(state="normal", text="下载")

    def test_successful_batch_creates_subdirectories_and_reports_root(self):
        class Response:
            ok = True
            headers = {"Content-Length": "2"}

            def iter_content(self, **kwargs):
                yield b"ok"

            def close(self):
                pass

        targets = [(resource, str(Path(self.directory) / resource.title / "book.pdf")) for resource, _ in self.targets(2)]
        with patch.object(panel, "request_download", side_effect=lambda url: (Response(), [url])):
            panel.start_download_batch(targets, self.directory)
            self.finish()

        self.notice.assert_called_once_with("下载完成", f"文件已下载到：{self.directory}")
        self.warning.assert_not_called()
        for _, path in targets:
            self.assertEqual(Path(path).read_bytes(), b"ok")
            self.assertFalse(Path(f"{path}.tmp").exists())
