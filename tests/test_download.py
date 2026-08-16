import unittest

from src.tchmaterial_parser.ui import download_panel, runtime


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.ok = False
        self.status_code = status_code


class FakeSession:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.requested_urls: list[str] = []

    def get(self, *args: tuple, **kwargs: dict) -> FakeResponse:
        self.requested_urls.append(args[0])
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
        previous_token = download_panel.config.access_token
        self.addCleanup(setattr, download_panel.config, "access_token", previous_token)
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

    def test_adds_access_token_only_to_private_request_url(self) -> None:
        token = "private-token"
        download_panel.config.access_token = token
        fake_session = FakeSession(404)
        download_panel.session = fake_session
        original_url = "https://r1-ndr-private.ykt.cbern.com.cn/book.pdf?source=catalog"

        download_panel.download_states = []
        download_panel.download_file(original_url, "book.pdf")

        requested_url = fake_session.requested_urls[0]
        self.assertIn("source=catalog", requested_url)
        self.assertIn("accessToken=private-token", requested_url)
        self.assertEqual(download_panel.download_states[0]["download_url"], original_url)
        self.assertNotIn(token, download_panel.download_states[0]["failed_reason"])

    def test_keeps_anonymous_and_non_private_urls_unchanged(self) -> None:
        private_url = "https://r1-ndr-private.ykt.cbern.com.cn/book.pdf"
        public_url = "https://example.com/book.pdf"

        download_panel.config.access_token = None
        self.assertEqual(download_panel.authenticated_download_url(private_url), private_url)

        download_panel.config.access_token = "private-token"
        self.assertEqual(download_panel.authenticated_download_url(public_url), public_url)


if __name__ == "__main__":
    unittest.main()
