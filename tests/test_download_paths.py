import os
import tempfile
import unittest

from src.tchmaterial_parser.api import ResourceInfo, get_relative_dir
from src.tchmaterial_parser.ui.download_panel import (
    allocate_download_paths,
    download_filename,
    sanitize_filename,
)


def resource(
    title: str,
    resource_key: str,
    edition: str | None = None,
    file_format: str = "pdf",
    relative_dir: tuple[str, ...] = (),
) -> ResourceInfo:
    return ResourceInfo(
        title=title,
        url=f"https://example.com/{resource_key}.{file_format}",
        file_format=file_format,
        chapters=[],
        edition=edition,
        relative_dir=relative_dir,
    )


class DownloadPathTest(unittest.TestCase):
    def test_keeps_unique_filenames_unchanged(self) -> None:
        resources = [
            resource("语文第一册", "book-1", "人教版"),
            resource("数学第一册", "book-2", "北师大版"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

        self.assertEqual([os.path.basename(path) for path in paths], ["语文第一册.pdf", "数学第一册.pdf"])

    def test_uses_edition_prefix_for_same_title_from_different_editions(self) -> None:
        title = "普通高中教科书·英语必修 第三册"
        resources = [
            resource(title, "bf54b36f-4c75-4c91-8b9c-53ce15e4f903", "人教版"),
            resource(title, "1e2e7507-0db6-4505-af12-87baac887bc1", "北师大版"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

        self.assertEqual([os.path.basename(path) for path in paths], [
            "[人教版] 普通高中教科书·英语必修 第三册.pdf",
            "[北师大版] 普通高中教科书·英语必修 第三册.pdf",
        ])
        self.assertEqual(len({f"{path}.tmp" for path in paths}), 2)

    def test_uses_sequence_when_edition_cannot_resolve_collision(self) -> None:
        resources = [
            resource("同名教材", "aaaaaaaa-1111-2222-3333-444444444444", "人教版"),
            resource("同名教材", "bbbbbbbb-1111-2222-3333-444444444444", "人教版"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

        self.assertEqual([os.path.basename(path) for path in paths], [
            "[人教版] 同名教材.pdf",
            "[人教版] 同名教材 (2).pdf",
        ])

    def test_avoids_existing_final_and_temporary_files(self) -> None:
        resources = [
            resource("已有教材", "book-1"),
            resource("未完成教材", "book-2"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "已有教材.pdf"), "wb").close()
            open(os.path.join(directory, "未完成教材.pdf.tmp"), "wb").close()
            paths = allocate_download_paths(resources, directory)

        self.assertEqual([os.path.basename(path) for path in paths], ["已有教材 (2).pdf", "未完成教材 (2).pdf"])

    def test_places_files_into_category_subdirectories(self) -> None:
        resources = [
            resource("必修上册", "book-1", relative_dir=("高中", "语文", "统编版")),
            resource("必修上册", "book-2", relative_dir=("高中", "语文", "人教版")),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

            self.assertEqual(paths, [
                os.path.join(directory, "高中", "语文", "统编版", "必修上册.pdf"),
                os.path.join(directory, "高中", "语文", "人教版", "必修上册.pdf"),
            ])

    def test_same_title_in_different_categories_needs_no_sequence(self) -> None:
        resources = [
            resource("必修上册", "book-1", relative_dir=("高中", "语文")),
            resource("必修上册", "book-2", relative_dir=("初中", "语文")),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

            self.assertEqual([os.path.basename(path) for path in paths], ["必修上册.pdf", "必修上册.pdf"])

    def test_sanitizes_category_directory_names(self) -> None:
        resources = [
            resource("教材", "book-1", relative_dir=("特殊:学段", "语*文")),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

            self.assertEqual(paths, [os.path.join(directory, "特殊：学段", "语＊文", "教材.pdf")])

    def test_issue_86_replaces_windows_illegal_filename_characters(self) -> None:
        resources = [
            resource(
                "（根据2022年版课程标准修订）义务教育教科书英语九年级上册 - Unit 3 Understanding ideas_2 Read the speech. What does the title mean?",
                "audio-1",
                file_format="mp3",
            ),
            resource(
                "（根据2022年版课程标准修订）义务教育教科书英语九年级上册 - Unit 4 Understanding ideas_2 Read the passage. What is the writer's relationship with Zhao Yiman?",
                "audio-2",
                file_format="mp3",
            ),
            resource("听力 * 跟读 1/2", "audio-3", file_format="mp3"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)
            names = [os.path.basename(path) for path in paths]
            self.assertEqual(names, [
                "（根据2022年版课程标准修订）义务教育教科书英语九年级上册 - Unit 3 Understanding ideas_2 Read the speech. What does the title mean？.mp3",
                "（根据2022年版课程标准修订）义务教育教科书英语九年级上册 - Unit 4 Understanding ideas_2 Read the passage. What is the writer's relationship with Zhao Yiman？.mp3",
                "听力 ＊ 跟读 1／2.mp3",
            ])
            for path in paths:
                with open(f"{path}.tmp", "wb") as file:
                    file.write(b"ok")

    def test_fullwidth_replacements_keep_distinct_punctuation_apart(self) -> None:
        resources = [
            resource("同名教材?", "book-1"),
            resource("同名教材*", "book-2"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

        self.assertEqual([os.path.basename(path) for path in paths], [
            "同名教材？.pdf",
            "同名教材＊.pdf",
        ])

    def test_sanitized_titles_that_collide_still_get_a_sequence(self) -> None:
        resources = [
            resource("同名教材?", "book-1"),
            resource("同名教材？", "book-2"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(resources, directory)

        self.assertEqual([os.path.basename(path) for path in paths], [
            "同名教材？.pdf",
            "同名教材？ (2).pdf",
        ])


class GetRelativeDirTest(unittest.TestCase):
    @staticmethod
    def tag(dimension: str, name: str, order: int = 0) -> dict:
        return {"tag_dimension_id": dimension, "tag_name": name, "order_num": order}

    def test_builds_dir_in_stage_subject_edition_order(self) -> None:
        data = {"tag_list": [
            self.tag("zxxnj", "一年级"),
            self.tag("zxxbb", "统编版"),
            self.tag("zxxxd", "小学"),
            self.tag("zxxxk", "道德与法治"),
            self.tag("tagView", "教材"),
        ]}

        self.assertEqual(get_relative_dir(data), ("小学", "道德与法治", "统编版"))

    def test_skips_missing_dimensions(self) -> None:
        data = {"tag_list": [self.tag("zxxxd", "高中"), self.tag("zxxxk", "语文")]}

        self.assertEqual(get_relative_dir(data), ("高中", "语文"))

    def test_returns_empty_dir_without_tag_list(self) -> None:
        self.assertEqual(get_relative_dir({}), ())
        self.assertEqual(get_relative_dir({"tag_list": []}), ())

    def test_ignores_other_dimensions_and_blank_names(self) -> None:
        data = {"tag_list": [self.tag("zxxcc", "上册"), self.tag("zxxbb", ""), self.tag("5036342742", "电子教材")]}

        self.assertEqual(get_relative_dir(data), ())


class SanitizeFilenameTest(unittest.TestCase):
    def test_uses_fullwidth_punctuation_and_strips_trailing_dots(self) -> None:
        self.assertEqual(sanitize_filename('a<>:"/\\|?*b'), "a＜＞：＂／＼｜？＊b")
        self.assertEqual(sanitize_filename("结束."), "结束")
        self.assertEqual(sanitize_filename("???"), "？？？")
        self.assertEqual(sanitize_filename("..."), "download")

    def test_prefixes_windows_reserved_device_names(self) -> None:
        self.assertEqual(sanitize_filename("CON.mp3"), "_CON.mp3")
        self.assertEqual(sanitize_filename("nul"), "_nul")

    def test_download_filename_sanitizes_title_but_keeps_extension(self) -> None:
        info = resource("What does the title mean?", "audio-1", file_format="mp3")
        self.assertEqual(download_filename(info), "What does the title mean？.mp3")


if __name__ == "__main__":
    unittest.main()
