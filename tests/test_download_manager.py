from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import queue
import tempfile
import threading
import time
from unittest.mock import Mock

import pytest
from pypdf import PdfReader, PdfWriter, apply_configuration

from src.tchmaterial_parser.api import ResourceInfo
from src.tchmaterial_parser.ui import download_panel as panel
from src.tchmaterial_parser.ui.download_manager import task_details, task_group, task_progress


@pytest.fixture
def downloads(monkeypatch):
    root = Path(__file__).resolve().parents[1] / ".tmp"
    root.mkdir(exist_ok=True)
    callbacks = queue.Queue()
    threads = []
    monkeypatch.setattr(panel, "download_states", [])
    monkeypatch.setattr(panel, "_batch_running", False)
    monkeypatch.setattr(panel, "_parsing_download", False)
    monkeypatch.setattr(panel, "_stop_requested", threading.Event())
    monkeypatch.setattr(panel, "show_download_manager", Mock())
    for name in ("download_btn", "progress_label", "download_progress_bar"):
        monkeypatch.setattr(panel, name, Mock(), raising=False)
    monkeypatch.setattr(panel, "ui_call", lambda fn, *args: callbacks.put((fn, args)))

    def thread_it(fn):
        thread = threading.Thread(target=fn, daemon=True)
        threads.append(thread)
        thread.start()

    def finish():
        for thread in threads:
            thread.join(timeout=5)
            assert not thread.is_alive()
        while not callbacks.empty():
            fn, args = callbacks.get_nowait()
            fn(*args)

    monkeypatch.setattr(panel, "thread_it", thread_it)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        yield Path(directory), finish
        panel._stop_requested.set()
        panel.stop_tasks(panel.download_states)
        finish()


class Response:
    ok = True

    def __init__(self, headers=None, chunks=None):
        self.headers = headers or {}
        self.chunks = chunks if chunks is not None else [b"abc"]
        self.closed = False

    def iter_content(self, **kwargs):
        yield from self.chunks

    def close(self):
        self.closed = True


def resource(name="book"):
    return ResourceInfo(name, f"https://example.com/{name}.pdf", "pdf", [])


@pytest.mark.parametrize("headers", [{}, {"Content-Length": "invalid"}, {"Content-Length": "-1"}, {"Content-Length": "99", "Content-Encoding": "gzip"}])
def test_unknown_or_compressed_lengths_do_not_fake_failure(downloads, monkeypatch, headers):
    directory, _ = downloads
    response = Response(headers)
    monkeypatch.setattr(panel, "request_download", lambda *args: (response, []))
    path = directory / "book.pdf"
    panel.download_file("https://example.com/book.pdf", str(path))
    state = panel.download_states[0]
    assert panel.task_status(state) == "已完成"
    assert task_progress(state) == "100%"
    assert state["total_size"] == 0
    assert path.read_bytes() == b"abc"
    assert response.closed


def test_incomplete_transfer_preserves_progress_but_cleans_temp(downloads, monkeypatch):
    directory, _ = downloads
    path = directory / "book.pdf"
    monkeypatch.setattr(panel, "request_download", lambda *args: (Response({"Content-Length": "6"}), []))
    panel.download_file("https://example.com/book.pdf", str(path))
    state = panel.download_states[0]
    assert panel.task_status(state) == "下载失败"
    assert task_group(state) == "attention"
    assert task_progress(state) == "50.0%"
    assert state["downloaded_size"] == 3
    assert not list(directory.iterdir())


def test_retry_updates_same_record_and_keeps_other_batch_history(downloads, monkeypatch):
    directory, finish = downloads
    monkeypatch.setattr(panel, "request_download", lambda *args: (Response({"Content-Length": "6"}), []))
    panel.start_download_batch([(resource(), str(directory / "book.pdf"))], str(directory))
    finish()
    failed = panel.download_states[0]
    monkeypatch.setattr(panel, "request_download", lambda *args: (Response(), []))
    panel.start_download_batch([(resource("other"), str(directory / "other.pdf"))], str(directory))
    finish()
    panel.retry_tasks([failed])
    finish()
    assert len(panel.download_states) == 2
    assert panel.download_states[0] is failed
    assert failed["attempt"] == 2
    assert not failed["failed_reason"]
    assert (directory / "book.pdf").read_bytes() == b"abc"


def test_retry_does_not_overwrite_file_created_since_failure(downloads, monkeypatch):
    directory, _ = downloads
    path = directory / "book.pdf"
    path.write_bytes(b"keep me")
    state = panel.create_download_state(resource().url, str(path))
    state.update(finished=True, failed_reason="timeout")
    panel.download_states.append(state)
    request = Mock()
    monkeypatch.setattr(panel, "request_download", request)
    panel.retry_tasks([state])
    request.assert_not_called()
    assert "已有文件" in state["failed_reason"]
    assert path.read_bytes() == b"keep me"


def test_retry_reserves_each_destination_once_across_history(downloads, monkeypatch):
    directory, finish = downloads
    for _ in range(2):
        state = panel.create_download_state(resource().url, str(directory / "book.pdf"))
        state.update(finished=True, failed_reason="timeout")
        panel.download_states.append(state)
    request = Mock(return_value=(Response(), []))
    monkeypatch.setattr(panel, "request_download", request)
    panel.retry_tasks(panel.download_states)
    finish()
    request.assert_called_once()
    assert panel.task_status(panel.download_states[0]) == "已完成"
    assert "另一条任务" in panel.download_states[1]["failed_reason"]


def test_existing_temp_belongs_to_another_download(downloads, monkeypatch):
    directory, _ = downloads
    path = directory / "book.pdf"
    temporary = directory / "book.pdf.tmp"
    temporary.write_bytes(b"another process")
    monkeypatch.setattr(panel, "request_download", lambda *args: (Response(), []))
    panel.download_file(resource().url, str(path))
    assert temporary.read_bytes() == b"another process"
    assert panel.download_states[0]["failed_reason"]


def test_stopping_after_last_chunk_does_not_publish_file(downloads, monkeypatch):
    directory, _ = downloads
    path = directory / "book.pdf"
    state = panel.create_download_state(resource().url, str(path))

    def chunks():
        yield b"abc"
        state["cancel"].set()

    response = Response({"Content-Length": "3"}, chunks())
    monkeypatch.setattr(panel, "request_download", lambda *args: (response, []))
    panel.download_file(resource().url, str(path), current_state=state)
    assert panel.task_status(state) == "已停止"
    assert not list(directory.iterdir())
    assert response.closed


def test_timeout_after_stop_is_reported_as_stopped(downloads, monkeypatch):
    directory, _ = downloads
    state = panel.create_download_state(resource().url, str(directory / "book.pdf"))

    def request(*args):
        state["cancel"].set()
        raise TimeoutError("server did not respond")

    monkeypatch.setattr(panel, "request_download", request)
    panel.download_file(resource().url, state["save_path"], current_state=state)
    assert panel.task_status(state) == "已停止"
    assert not state["failed_reason"]


def test_stop_one_queued_task_allows_other_tasks_to_finish(downloads, monkeypatch):
    directory, finish = downloads
    release = threading.Event()
    entered = threading.Barrier(4)
    requested = []

    def request(url, cancel):
        requested.append(url)
        if len(requested) <= 3:
            entered.wait(timeout=3)
            release.wait(timeout=3)
        return Response(), []

    monkeypatch.setattr(panel, "request_download", request)
    targets = [(resource(str(i)), str(directory / f"{i}.pdf")) for i in range(5)]
    panel.start_download_batch(targets, str(directory))
    entered.wait(timeout=3)
    try:
        assert panel.task_status(panel.download_states[4]) == "排队中"
        panel.stop_tasks([panel.download_states[4]])
        # 所有行暂时 finished 也不能在旧批次回调抵达前启动另一批。
        panel.retry_tasks(panel.download_states)
    finally:
        release.set()
    finish()
    assert targets[4][0].url not in requested
    assert panel.task_status(panel.download_states[4]) == "已停止"
    assert len(list(directory.iterdir())) == 4


def test_bookmark_failure_is_not_reported_as_success(downloads, monkeypatch):
    directory, _ = downloads
    monkeypatch.setattr(panel, "request_download", lambda *args: (Response(), []))
    monkeypatch.setattr(panel, "add_bookmarks", Mock(side_effect=ValueError("invalid PDF")))
    panel.download_file(resource().url, str(directory / "book.pdf"), [{"title": "chapter"}])
    assert "invalid PDF" in panel.download_states[0]["failed_reason"]
    assert not list(directory.iterdir())


def test_real_pdf_bookmarks_are_written_before_completion(downloads, monkeypatch):
    directory, _ = downloads
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.write(buffer)
    response = Response(chunks=[buffer.getvalue()])
    monkeypatch.setattr(panel, "request_download", lambda *args: (response, []))
    path = directory / "book.pdf"
    panel.download_file(resource().url, str(path), [{"title": "第一章", "page_index": 1}])
    assert panel.task_status(panel.download_states[0]) == "已完成"
    with path.open("rb") as file:
        assert PdfReader(file).outline[0].title == "第一章"


def test_large_pdf_stream_finishes_download_with_bookmarks(downloads, monkeypatch, image_pdf):
    directory, _ = downloads
    data = image_pdf.read_bytes()
    response = Response({"Content-Length": str(len(data))}, [data])
    monkeypatch.setattr(panel, "request_download", lambda *args: (response, []))
    path = directory / "book.pdf"
    with apply_configuration(maximum_declared_stream_length=1024):
        panel.download_file(resource().url, str(path), [{"title": "第一章", "page_index": 1}])
    assert panel.task_status(panel.download_states[0]) == "已完成"
    assert not path.with_suffix(".pdf.tmp").exists()
    assert PdfReader(path).outline[0].title == "第一章"


def test_invalid_pdf_does_not_replace_existing_file(downloads, monkeypatch):
    directory, _ = downloads
    path = directory / "book.pdf"
    path.write_bytes(b"original file")
    monkeypatch.setattr(panel, "request_download", lambda *args: (Response(), []))
    panel.download_file(resource().url, str(path), [{"title": "第一章", "page_index": 1}])
    assert "写入 PDF 书签失败" in panel.download_states[0]["failed_reason"]
    assert path.read_bytes() == b"original file"
    assert not path.with_suffix(".pdf.tmp").exists()


def test_parse_failure_records_are_deduplicated_and_resolved(downloads):
    urls = ["https://example.com/1", "https://example.com/2"]
    panel.record_parse_results(urls, set(urls))
    panel.record_parse_results(urls, {urls[0]})
    assert len(panel.download_states) == 1
    assert panel.task_status(panel.download_states[0]) == "解析失败"
    assert panel.download_states[0]["download_url"] == urls[0]
    panel.record_parse_results([urls[0]], set())
    assert not panel.download_states


def test_task_details_redact_credentials_in_urls_paths_and_errors(downloads, monkeypatch):
    monkeypatch.setattr(panel.config, "access_token", "sample-test-token")
    monkeypatch.setattr(panel.config, "mac_key", "sample-test-mac-key")
    state = panel.create_download_state("https://example.com/?accessToken=sample-query-token", "sample-test-token.pdf")
    state.update(finished=True, failed_reason="Authorization: Bearer sample-test-token; sample-test-mac-key")
    text = task_details(state)
    for secret in ("sample-test-token", "sample-test-mac-key", "sample-query-token"):
        assert secret not in text
    assert "<已隐藏>" in text


def test_progress_updates_never_call_tk_from_download_worker(downloads, monkeypatch):
    directory, _ = downloads
    monkeypatch.setattr(panel, "request_download", lambda *args: (Response(chunks=[b"a"] * 1000), []))
    update = Mock(side_effect=AssertionError("工作线程不应调度 Tk"))
    monkeypatch.setattr(panel, "ui_call", update)
    panel.download_file(resource().url, str(directory / "book.pdf"))
    update.assert_not_called()
    panel.progress_label.config.assert_not_called()
    assert (directory / "book.pdf").stat().st_size == 1000


def test_cancel_interrupts_retry_backoff(downloads, monkeypatch):
    cancel = threading.Event()

    class RetryResponse(Response):
        ok = False
        status_code = 400

        def close(self):
            super().close()
            cancel.set()

    response = RetryResponse()
    request = Mock(return_value=response)
    monkeypatch.setattr(panel, "_MIN_REQUEST_INTERVAL", 0)
    monkeypatch.setattr(panel.session, "get", request)
    with pytest.raises(panel.DownloadStopped):
        panel.request_download(resource().url, cancel)
    assert request.call_count == 1
    assert response.closed


def test_real_http_transfer_reports_bytes_and_stops_cleanly(downloads, monkeypatch):
    directory, finish = downloads
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(512 * 1024))
            self.end_headers()
            self.wfile.write(b"a" * (256 * 1024))
            self.wfile.flush()
            release.wait(timeout=3)
            try:
                self.wfile.write(b"b" * (256 * 1024))
            except OSError:
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    monkeypatch.setattr(panel, "REQUEST_TIMEOUT", (1, 1))
    monkeypatch.setattr(panel, "_MIN_REQUEST_INTERVAL", 0)
    try:
        source = ResourceInfo("book", f"http://127.0.0.1:{server.server_port}/book.pdf", "pdf", [])
        panel.start_download_batch([(source, str(directory / "book.pdf"))], str(directory))
        state = panel.download_states[0]
        deadline = time.monotonic() + 3
        while not state["downloaded_size"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert state["downloaded_size"] > 0
        assert state["total_size"] == 512 * 1024
        panel.stop_tasks([state])
        release.set()
        finish()
        assert panel.task_status(state) == "已停止"
        assert not list(directory.iterdir())
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)
