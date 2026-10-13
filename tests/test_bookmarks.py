import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import pytest
from pypdf import PdfReader, apply_configuration, get_configuration
from pypdf.errors import LimitReachedError

from src.tchmaterial_parser import bookmarks


def test_large_image_keeps_content_and_nested_bookmarks(image_pdf):
    original = PdfReader(image_pdf)
    image_data = original.pages[0]["/Resources"]["/XObject"]["/Im0"].get_data()
    chapters = [{"title": "第一章", "page_index": 1,
                 "children": [{"title": "第一节", "page_index": 1}]}]

    with apply_configuration(maximum_declared_stream_length=1024) as configuration:
        bookmarks.add_bookmarks(str(image_pdf), chapters)
        assert get_configuration() == configuration

    result = PdfReader(image_pdf)
    assert len(result.pages) == 1
    assert result.outline[0].title == "第一章"
    assert result.outline[1][0].title == "第一节"
    assert result.get_destination_page_number(result.outline[1][0]) == 0
    assert result.pages[0]["/Resources"]["/XObject"]["/Im0"].get_data() == image_data


def test_declared_length_beyond_file_size_is_rejected(image_pdf):
    data = image_pdf.read_bytes()
    assert b"/Length 4096" in data
    assert len(data) < 9999
    # 保持数字位数不变，避免影响 PDF 的交叉引用偏移。
    data = data.replace(b"/Length 4096", b"/Length 9999", 1)
    image_pdf.write_bytes(data)

    with apply_configuration(maximum_declared_stream_length=1024) as configuration:
        with pytest.raises(RuntimeError, match="写入 PDF 书签失败") as error:
            bookmarks.add_bookmarks(str(image_pdf), [{"title": "第一章", "page_index": 1}])
        assert isinstance(error.value.__cause__, LimitReachedError)
        assert get_configuration() == configuration

    assert image_pdf.read_bytes() == data


def test_bookmark_limit_does_not_affect_another_thread(image_pdf, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def read_pdf(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return PdfReader(*args, **kwargs)

    monkeypatch.setattr(bookmarks, "PdfReader", read_pdf)
    with apply_configuration(maximum_declared_stream_length=1024) as configuration:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(copy_context().run, bookmarks.add_bookmarks, str(image_pdf),
                                     [{"title": "第一章", "page_index": 1}])
            try:
                assert entered.wait(timeout=5)
                assert get_configuration() == configuration
                with pytest.raises(LimitReachedError):
                    PdfReader(image_pdf).pages[0]["/Resources"]["/XObject"]["/Im0"].get_data()
            finally:
                release.set()
            future.result(timeout=5)

    assert PdfReader(image_pdf).outline[0].title == "第一章"
