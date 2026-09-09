import unittest

from src.tchmaterial_parser.ui.resource_tree import build_resource_url, collect_resource_urls


RESOURCE_ITEMS = {
    "books": {
        "display_name": "电子教材",
        "children": {
            "high": {
                "display_name": "高中",
                "children": {
                    "chinese": {
                        "display_name": "语文",
                        "children": {
                            "tbb": {
                                "display_name": "统编版",
                                "children": {
                                    "book-a": {
                                        "display_name": "普通高中教科书·语文 必修上册",
                                        "resource_type_code": "assets_document",
                                        "content_id": "a0001",
                                    },
                                    "book-b": {
                                        "display_name": "普通高中教科书·语文 必修下册",
                                        "resource_type_code": "assets_document",
                                        "content_id": "a0002",
                                    },
                                },
                            },
                            "rjb": {
                                "display_name": "人教版",
                                "children": {
                                    "book-c": {
                                        "display_name": "普通高中教科书·语文 选择性必修上册",
                                        "resource_type_code": "assets_document",
                                        "content_id": "a0003",
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def detail_url(content_id: str) -> str:
    return f"https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={content_id}&catalogType=tchMaterial&subCatalog=tchMaterial"


def chinese_subject() -> dict:
    return RESOURCE_ITEMS["books"]["children"]["high"]["children"]["chinese"]


class BuildResourceUrlTest(unittest.TestCase):
    def test_builds_detail_url_for_regular_book(self) -> None:
        book = chinese_subject()["children"]["tbb"]["children"]["book-a"]

        url = build_resource_url("books:high:chinese:tbb:book-a", book)

        self.assertEqual(url, detail_url("a0001"))

    def test_falls_back_to_default_type_and_path_id(self) -> None:
        url = build_resource_url("books:book-x", {"display_name": "未知资源"})

        self.assertEqual(url, detail_url("book-x"))

    def test_builds_sync_classroom_url_for_teaching_materials(self) -> None:
        url = build_resource_url("__internal_national_lesson:tag1:tag2", {"resource_type_code": "teachingmaterials"})

        self.assertEqual(url, "https://basic.smartedu.cn/syncClassroom?defaultTag=tag1%2Ftag2")

    def test_prepare_lesson_root_adds_prepare_path(self) -> None:
        url = build_resource_url("__internal_prepare_lesson:tag1", {"resource_type_code": "teachingmaterials"})

        self.assertEqual(url, "https://basic.smartedu.cn/syncClassroom/prepare?defaultTag=tag1")


class CollectResourceUrlsTest(unittest.TestCase):
    def test_collects_all_leaf_urls_under_subject(self) -> None:
        urls = collect_resource_urls(chinese_subject()["children"], "books:high:chinese")

        self.assertEqual(urls, [detail_url("a0001"), detail_url("a0002"), detail_url("a0003")])

    def test_single_edition_only_collects_its_own_books(self) -> None:
        tbb = chinese_subject()["children"]["tbb"]

        urls = collect_resource_urls(tbb["children"], "books:high:chinese:tbb")

        self.assertEqual(urls, [detail_url("a0001"), detail_url("a0002")])

    def test_empty_category_collects_nothing(self) -> None:
        self.assertEqual(collect_resource_urls({}), [])


if __name__ == "__main__":
    unittest.main()
