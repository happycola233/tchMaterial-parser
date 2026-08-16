import unittest

from src.tchmaterial_parser.api import combine_resource_title


class ResourceTitleTest(unittest.TestCase):
    def test_keeps_child_title_when_parent_is_missing(self) -> None:
        self.assertEqual(combine_resource_title(None, "子资源"), "子资源")

    def test_joins_distinct_parent_and_child_titles(self) -> None:
        self.assertEqual(combine_resource_title("英语七年级上册", "听力 1"), "英语七年级上册 - 听力 1")

    def test_deduplicates_titles_that_only_differ_in_whitespace(self) -> None:
        child_title = "义务教育教科书•体育与健康教师用书 基本运动技能（全一册）"
        parent_title = "义务教育教科书•体育与健康教师用书  基本运动技能（全一册）"
        self.assertEqual(combine_resource_title(parent_title, child_title), child_title)

    def test_issue_76_title_stays_within_common_filesystem_limit(self) -> None:
        title = "（根据2022年版课程标准修订）义务教育教科书•体育与健康教师用书  基本运动技能（全一册）"
        filename = f"{combine_resource_title(title, title)}.pdf.tmp"
        self.assertLessEqual(len(filename.encode("utf-8")), 255)


if __name__ == "__main__":
    unittest.main()
