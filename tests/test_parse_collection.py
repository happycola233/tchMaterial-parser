import unittest
from typing import get_type_hints

from src.tchmaterial_parser.api import ResourceInfo
from src.tchmaterial_parser.ui.download_panel import collect_parsed_resources, parse_urls_in_background


def make_resource(url: str, title: str = "资源") -> ResourceInfo:
    return ResourceInfo(title, url, "pdf", [])


class CollectParsedResourcesTest(unittest.TestCase):
    def test_callback_annotations_can_be_evaluated(self) -> None:
        # Python 3.14 延迟求值注解；显式求值以免启动错误被新版解释器掩盖。
        get_type_hints(collect_parsed_resources)
        get_type_hints(parse_urls_in_background)

    def test_flattens_multiple_resources_per_url(self) -> None:
        def fake_parse(url: str, bookmarks: bool):
            return [make_resource("https://example.com/a.pdf"), make_resource("https://example.com/b.mp3")]

        resources, failed = collect_parsed_resources(fake_parse, ["https://example.com/1"], False)

        self.assertEqual([resource.url for resource in resources], ["https://example.com/a.pdf", "https://example.com/b.mp3"])
        self.assertEqual(failed, set())

    def test_deduplicates_by_resource_url_across_urls(self) -> None:
        def fake_parse(url: str, bookmarks: bool):
            return [make_resource("https://example.com/a.pdf")]

        resources, failed = collect_parsed_resources(fake_parse, ["https://example.com/1", "https://example.com/2"], False)

        self.assertEqual([resource.url for resource in resources], ["https://example.com/a.pdf"])
        self.assertEqual(failed, set())

    def test_collects_urls_that_fail_to_parse(self) -> None:
        def fake_parse(url: str, bookmarks: bool):
            return None if url.endswith("bad") else [make_resource("https://example.com/a.pdf")]

        resources, failed = collect_parsed_resources(fake_parse, ["https://example.com/good", "https://example.com/bad"], False)

        self.assertEqual([resource.url for resource in resources], ["https://example.com/a.pdf"])
        self.assertEqual(failed, {"https://example.com/bad"})

    def test_reports_progress_for_each_url(self) -> None:
        def fake_parse(url: str, bookmarks: bool):
            return None

        progress: list[tuple[int, int]] = []

        collect_parsed_resources(fake_parse, ["https://example.com/1", "https://example.com/2", "https://example.com/3"], True, lambda current, total: progress.append((current, total)))

        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])


if __name__ == "__main__":
    unittest.main()
