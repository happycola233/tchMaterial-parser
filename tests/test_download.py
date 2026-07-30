import unittest

from src.tchmaterial_parser.ui import download_panel, runtime


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.ok = False
        self.status_code = status_code


class FakeSession:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def get(self, *args: tuple, **kwargs: dict) -> FakeResponse:
        return FakeResponse(self.status_code)


class FakeWidget:
    def config(self, **kwargs: dict) -> None:
        pass


class DownloadFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        # 置为关闭状态后 ui_call() 不会真正执行回调，因此桩控件只需提供 config 属性
        runtime.app_closing = True
        self.addCleanup(setattr, runtime, "app_closing", False)
        self.addCleanup(setattr, download_panel, "session", download_panel.session)
        widget = FakeWidget()
        download_panel.bind_widgets(widget, widget, widget, widget, widget)

    def failure_reason(self, status_code: int) -> str:
        download_panel.session = FakeSession(status_code)
        download_panel.download_states = []
        download_panel.download_file("https://example.invalid/book.pdf", "book.pdf")
        return download_panel.download_states[0]["failed_reason"]

    def test_reports_server_errors_unrelated_to_the_token(self) -> None:
        self.assertEqual(self.failure_reason(404), "服务器返回 HTTP 状态码 404")

    def test_appends_a_token_hint_to_authentication_failures(self) -> None:
        for status_code in (401, 403):
            with self.subTest(status_code=status_code):
                self.assertEqual(
                    self.failure_reason(status_code),
                    f"服务器返回 HTTP 状态码 {status_code}，Access Token 可能已过期或无效，请重新设置",
                )


if __name__ == "__main__":
    unittest.main()
