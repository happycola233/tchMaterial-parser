import unittest

from PIL import Image

from src.tchmaterial_parser import count_resource_items, filter_resource_items, fit_cover_image


RESOURCE_ITEMS = {
    "books": {
        "display_name": "电子教材",
        "children": {
            "middle": {
                "display_name": "初中",
                "children": {
                    "chinese": {
                        "display_name": "语文",
                        "children": {
                            "grade7": {
                                "display_name": "七年级",
                                "children": {
                                    "book-a": {
                                        "display_name": "义务教育教科书 七年级上册",
                                    },
                                    "book-b": {
                                        "display_name": "义务教育教科书 七年级下册",
                                    },
                                },
                            },
                        },
                    },
                    "math": {
                        "display_name": "数学",
                        "children": {
                            "grade8": {
                                "display_name": "八年级",
                                "children": {
                                    "book-c": {
                                        "display_name": "义务教育教科书 八年级上册",
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


class ResourceSearchTest(unittest.TestCase):
    def test_searches_across_the_full_category_path(self) -> None:
        matches = filter_resource_items(RESOURCE_ITEMS, "语文 七年级 下册")

        grade_items = matches["books"]["children"]["middle"]["children"]["chinese"]["children"]["grade7"]["children"]
        self.assertEqual(list(grade_items), ["book-b"])

    def test_category_search_keeps_all_matching_resources(self) -> None:
        matches = filter_resource_items(RESOURCE_ITEMS, "数学")

        self.assertEqual(count_resource_items(matches), 1)

    def test_empty_query_returns_all_resources(self) -> None:
        self.assertIs(filter_resource_items(RESOURCE_ITEMS, "  "), RESOURCE_ITEMS)
        self.assertEqual(count_resource_items(RESOURCE_ITEMS), 3)

    def test_unknown_keyword_returns_an_empty_tree(self) -> None:
        self.assertEqual(filter_resource_items(RESOURCE_ITEMS, "不存在"), {})


class CoverImageTest(unittest.TestCase):
    def test_centers_portrait_cover_on_fixed_canvas(self) -> None:
        image = Image.new("RGB", (100, 200), "white")

        result = fit_cover_image(image, (80, 80))

        self.assertEqual(result.size, (80, 80))
        self.assertEqual(result.getbbox(), (20, 0, 60, 80))


if __name__ == "__main__":
    unittest.main()
