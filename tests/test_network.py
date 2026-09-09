import json
import unittest
from unittest.mock import Mock, patch

from requests import ReadTimeout, Response
from requests.adapters import BaseAdapter

from src.tchmaterial_parser import api, network
from src.tchmaterial_parser.ui import download_panel


class MetadataAdapter(BaseAdapter):
    def __init__(self):
        self.calls = []

    def send(self, request, **kwargs):
        self.calls.append((request.url, kwargs.get("timeout")))
        if "bad.json" in request.url:
            raise ReadTimeout("模拟读取超时")
        if "mapping.json" in request.url:
            data = {"ebook_id": "book", "mappings": [{"node_id": "chapter", "page_number": 1}]}
        elif "/trees/" in request.url:
            data = [{"id": "chapter", "title": "第一章"}]
        elif "relation_audios.json" in request.url:
            data = []
        else:
            data = {"title": "教材", "ti_items": [
                {"ti_is_source_file": True, "ti_file_flag": "source", "ti_format": "pdf", "ti_storage": "https://example.com/book.pdf"},
                {"ti_file_flag": "ebook_mapping", "ti_storage": "https://example.com/mapping.json"},
            ]}
        response = Response()
        response.status_code = 200
        response.url = request.url
        response._content = json.dumps(data).encode("utf-8")
        return response

    def close(self):
        pass


class RequestTimeoutTest(unittest.TestCase):
    def setUp(self):
        self.session = network.TimeoutSession()
        self.session.trust_env = False
        self.adapter = MetadataAdapter()
        self.session.mount("https://", self.adapter)
        self.addCleanup(self.session.close)

    def test_defaults_cover_details_mapping_chapters_and_audio(self):
        with patch.object(api, "session", self.session):
            result = api.parse("https://basic.smartedu.cn/tchMaterial/detail?contentId=book", True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].chapters, [{"title": "第一章", "page_index": 1}])
        self.assertEqual(len(self.adapter.calls), 4)
        self.assertTrue(all(timeout == network.REQUEST_TIMEOUT for _, timeout in self.adapter.calls))

    def test_explicit_timeout_is_preserved(self):
        self.session.get("https://example.com/details.json", timeout=(1, 2))
        self.assertEqual(self.adapter.calls[0][1], (1, 2))

    def test_timeout_does_not_block_remaining_urls_or_completion_callback(self):
        bad = "https://basic.smartedu.cn/tchMaterial/detail?contentId=bad"
        good = "https://basic.smartedu.cn/tchMaterial/detail?contentId=good"
        completed = Mock()
        with patch.object(api, "session", self.session), patch.object(api, "print_error"), patch.object(download_panel, "progress_label", Mock(), create=True), patch.object(download_panel, "download_states", []), patch.object(download_panel, "thread_it", lambda fn: fn()), patch.object(download_panel, "ui_call", lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            download_panel.parse_urls_in_background([bad, good], False, completed)

        completed.assert_called_once()
        resources, failed = completed.call_args.args
        self.assertEqual([resource.url for resource in resources], ["https://example.com/book.pdf"])
        self.assertEqual(failed, {bad})
