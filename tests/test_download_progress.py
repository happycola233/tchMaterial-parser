import unittest
from unittest.mock import patch

from src.tchmaterial_parser.network import REQUEST_TIMEOUT
from src.tchmaterial_parser.ui import download_panel


class RecordingWidget:
    def __init__(self) -> None:
        self.configs: list[dict] = []

    def config(self, **kwargs: dict) -> None:
        self.configs.append(kwargs)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.ok = status_code < 400
        self.status_code = status_code

    def close(self) -> None:
        pass


class TimeoutRecordingSession:
    def __init__(self) -> None:
        self.timeouts: list[tuple | None] = []

    def get(self, url: str, **kwargs: dict) -> FakeResponse:
        self.timeouts.append(kwargs.get("timeout"))
        return FakeResponse(200)


class DownloadProgressTest(unittest.TestCase):
    def setUp(self) -> None:
        # 让 ui_call 直接同步执行，便于断言标签与进度条的实际更新内容
        previous_call = download_panel.ui_call
        self.addCleanup(setattr, download_panel, "ui_call", previous_call)
        download_panel.ui_call = lambda func, *args, **kwargs: func(*args, **kwargs)

        previous_states = download_panel.download_states
        self.addCleanup(setattr, download_panel, "download_states", previous_states)
        download_panel.download_states = []

        self.label = RecordingWidget()
        self.bar = RecordingWidget()
        for name, widget in (("progress_label", self.label), ("download_progress_bar", self.bar)):
            widget_patch = patch.object(download_panel, name, widget, create=True)
            widget_patch.start()
            self.addCleanup(widget_patch.stop)

    def latest_label_text(self) -> str:
        return self.label.configs[-1]["text"]

    def test_shows_percentage_when_total_size_known(self) -> None:
        download_panel.download_states = [
            {"downloaded_size": 50, "total_size": 100, "finished": True, "failed_reason": None},
            {"downloaded_size": 50, "total_size": 100, "finished": False, "failed_reason": None},
        ]

        download_panel.refresh_download_progress()

        self.assertIn("50.00%", self.latest_label_text())
        self.assertIn("已下载 1/2", self.latest_label_text())
        self.assertEqual(self.bar.configs[-1], {"value": 50.0})

    def test_shows_finished_count_without_total_size(self) -> None:
        download_panel.download_states = [
            {"downloaded_size": 0, "total_size": 0, "finished": True, "failed_reason": None},
            {"downloaded_size": 0, "total_size": 0, "finished": False, "failed_reason": None},
        ]

        download_panel.refresh_download_progress()

        self.assertIn("已完成 1/2 个文件", self.latest_label_text())
        self.assertEqual(self.bar.configs, []) # 未知总大小时不驱动进度条

    def test_counts_failed_downloads(self) -> None:
        download_panel.download_states = [
            {"downloaded_size": 0, "total_size": 0, "finished": True, "failed_reason": "服务器返回 HTTP 状态码 403"},
            {"downloaded_size": 0, "total_size": 0, "finished": False, "failed_reason": None},
        ]

        download_panel.refresh_download_progress()

        self.assertIn("1 个失败", self.latest_label_text())

    def test_private_download_requests_carry_timeout(self) -> None:
        fake_session = TimeoutRecordingSession()
        previous_session = download_panel.session
        self.addCleanup(setattr, download_panel, "session", previous_session)
        download_panel.session = fake_session
        previous_interval = download_panel._MIN_REQUEST_INTERVAL
        self.addCleanup(setattr, download_panel, "_MIN_REQUEST_INTERVAL", previous_interval)
        download_panel._MIN_REQUEST_INTERVAL = 0

        response, _attempted_urls = download_panel.request_download("https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/test.pkg/book.pdf")

        self.assertTrue(response.ok)
        self.assertTrue(fake_session.timeouts)
        self.assertTrue(all(timeout == REQUEST_TIMEOUT for timeout in fake_session.timeouts))


if __name__ == "__main__":
    unittest.main()
