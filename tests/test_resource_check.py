import unittest

from PIL import Image, ImageColor

from src.tchmaterial_parser.ui.resource_tree import (
    category_check_state,
    draw_checkbox_image,
    find_tree_node,
    iter_leaf_resources,
    should_check_category,
)
from src.tchmaterial_parser.ui.theme import THEME_COLORS


RESOURCE_ITEMS = {
    "books": {
        "display_name": "电子教材",
        "children": {
            "primary": {
                "display_name": "小学",
                "children": {
                    "chinese": {
                        "display_name": "语文",
                        "children": {
                            "book-a": {"display_name": "语文 一年级上册", "content_id": "a001"},
                            "book-b": {"display_name": "语文 一年级下册", "content_id": "a002"},
                        },
                    },
                },
            },
            "middle": {
                "display_name": "初中",
                "children": {
                    "math": {
                        "display_name": "数学",
                        "children": {
                            "book-c": {"display_name": "数学 七年级上册", "content_id": "a003"},
                        },
                    },
                },
            },
        },
    },
}


class IterLeafResourcesTest(unittest.TestCase):
    def test_yields_paths_and_data_of_all_leaf_nodes(self) -> None:
        leafs = list(iter_leaf_resources(RESOURCE_ITEMS))

        self.assertEqual(
            [leaf_id for leaf_id, _leaf_data in leafs],
            ["books:primary:chinese:book-a", "books:primary:chinese:book-b", "books:middle:math:book-c"],
        )
        self.assertEqual(leafs[0][1]["content_id"], "a001")

    def test_yields_only_leaves_under_given_parent_path(self) -> None:
        leafs = list(iter_leaf_resources(RESOURCE_ITEMS["books"]["children"], "books"))

        self.assertEqual([leaf_id for leaf_id, _leaf_data in leafs], ["books:primary:chinese:book-a", "books:primary:chinese:book-b", "books:middle:math:book-c"])

    def test_treats_empty_children_as_leaf(self) -> None: # 与 count_resource_items 的口径一致：children 为空字典的节点视为末级资源
        self.assertEqual(list(iter_leaf_resources({})), [])
        leafs = list(iter_leaf_resources({"empty": {"display_name": "空分类", "children": {}}}, "books"))
        self.assertEqual([leaf_id for leaf_id, _leaf_data in leafs], ["books:empty"])


class FindTreeNodeTest(unittest.TestCase):
    def test_locates_node_by_colon_path(self) -> None:
        node = find_tree_node(RESOURCE_ITEMS, "books:primary:chinese:book-b")

        self.assertEqual(node["content_id"], "a002")

    def test_locates_category_and_root_nodes(self) -> None:
        self.assertEqual(find_tree_node(RESOURCE_ITEMS, "books")["display_name"], "电子教材")
        self.assertEqual(find_tree_node(RESOURCE_ITEMS, "books:primary:chinese")["display_name"], "语文")

    def test_returns_none_for_unknown_path(self) -> None:
        self.assertIsNone(find_tree_node(RESOURCE_ITEMS, "books:unknown:chinese"))
        self.assertIsNone(find_tree_node(RESOURCE_ITEMS, "not-exist"))


class CategoryCheckStateTest(unittest.TestCase):
    LEAF_IDS = ["books:primary:chinese:book-a", "books:primary:chinese:book-b", "books:middle:math:book-c"]

    def test_returns_unchecked_when_no_leaf_is_checked(self) -> None:
        self.assertEqual(category_check_state(self.LEAF_IDS, set()), "unchecked")
        self.assertEqual(category_check_state([], {"books:middle:math:book-c"}), "unchecked")

    def test_returns_partial_when_some_leaves_are_checked(self) -> None:
        checked = {"books:primary:chinese:book-a"}

        self.assertEqual(category_check_state(self.LEAF_IDS, checked), "partial")

    def test_returns_checked_when_all_leaves_are_checked(self) -> None:
        checked = set(self.LEAF_IDS)

        self.assertEqual(category_check_state(self.LEAF_IDS, checked), "checked")

    def test_ignores_checked_items_outside_the_category(self) -> None:
        checked = {"books:primary:chinese:book-a", "books:primary:chinese:book-b", "books:other:book-x"}

        self.assertEqual(category_check_state(self.LEAF_IDS[:2], checked), "checked")


class ShouldCheckCategoryTest(unittest.TestCase):
    LEAF_IDS = ["book-a", "book-b"]

    def test_checks_when_not_all_leaves_are_checked(self) -> None:
        self.assertTrue(should_check_category(self.LEAF_IDS, set()))
        self.assertTrue(should_check_category(self.LEAF_IDS, {"book-a"}))

    def test_unchecks_when_all_leaves_are_already_checked(self) -> None:
        self.assertFalse(should_check_category(self.LEAF_IDS, {"book-a", "book-b"}))


class DrawCheckboxImageTest(unittest.TestCase):
    def test_draws_all_states_on_transparent_canvas(self) -> None:
        colors = THEME_COLORS["light"]

        for state in ("checked", "partial", "unchecked"):
            with self.subTest(state=state):
                image = draw_checkbox_image(18, state, colors)

                self.assertIsInstance(image, Image.Image)
                self.assertEqual(image.size, (18, 18))
                self.assertEqual(image.mode, "RGBA")
                # 中心区域被复选框底色填充（不透明）
                self.assertEqual(image.getpixel((9, 9))[3], 255)

    def test_edges_are_antialiased_in_both_themes_at_common_scales(self) -> None:
        for theme_name, colors in THEME_COLORS.items():
            for size in (18, 23, 27, 36):
                for state in ("checked", "partial", "unchecked"):
                    with self.subTest(theme=theme_name, size=size, state=state):
                        image = draw_checkbox_image(size, state, colors)

                        self.assertEqual(image.size, (size, size))
                        self.assertEqual(image.getpixel((0, 0))[3], 0)
                        self.assertGreater(sum(image.getchannel("A").histogram()[1:255]), 0)

    def test_checkmark_has_smooth_color_transitions(self) -> None:
        for theme_name, colors in THEME_COLORS.items():
            with self.subTest(theme=theme_name):
                image = draw_checkbox_image(27, "checked", colors)
                background = ImageColor.getrgb(colors["selbg"])
                foreground = ImageColor.getrgb(colors["selfg"])
                # 检查内部对勾的颜色过渡，避免仅外框抗锯齿而对勾仍有锯齿。
                interior = image.crop((6, 6, 21, 21))
                pixels = (interior.getpixel((x, y)) for y in range(interior.height) for x in range(interior.width))
                self.assertTrue(any(
                    alpha == 255 and all(low < channel < high for channel, low, high in zip((r, g, b), background, foreground))
                    for r, g, b, alpha in pixels
                ))


if __name__ == "__main__":
    unittest.main()
