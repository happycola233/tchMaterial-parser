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

    def test_keeps_existing_final_file_path_but_avoids_temporary_files(self) -> None:
        resources = [
            resource("已有教材", "book-1"),
            resource("未完成教材", "book-2"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "已有教材.pdf"), "wb").close()
            open(os.path.join(directory, "未完成教材.pdf.tmp"), "wb").close()
            paths = allocate_download_paths(resources, directory)

        # 已下载完成的文件保留原路径，交由批次跳过；.tmp 可能属于另一个运行中的实例，仍需避开
        self.assertEqual([os.path.basename(path) for path in paths], ["已有教材.pdf", "未完成教材 (2).pdf"])

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
                os.makedirs(os.path.dirname(path), exist_ok=True)
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



class AudioDownloadPathTest(unittest.TestCase):
    book = "（根据2022年版课程标准修订）义务教育教科书·英语 三年级 下册"
    category = ("小学", "英语", "外研社版（主编：孙有中）")

    def audio(self, child="Unit 1_Start up_1 Read and answer", book=None, key="a", fmt="mp3"):
        book = book or self.book
        return resource(f"{book} - {child}", key, file_format=fmt, relative_dir=self.category)._replace(
            textbook_title=book, audio_title=child, edition="外研社版",
        )

    def test_issue_97_real_title_keeps_pdf_and_shortens_audio(self):
        audio = self.audio()
        pdf = resource(self.book, "pdf", relative_dir=self.category)
        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths([pdf, audio], directory)
            category = os.path.join(directory, *self.category)
            self.assertEqual(paths, [os.path.join(category, self.book + ".pdf"),
                                    os.path.join(category, "mp3", self.book, audio.audio_title + ".mp3")])
            os.makedirs(os.path.dirname(paths[1]))
            with open(paths[1] + ".tmp", "wb") as file:
                file.write(b"busy")
            self.assertTrue(allocate_download_paths([audio], directory)[0].endswith(" (2).mp3"))
            self.assertEqual(open(paths[1] + ".tmp", "rb").read(), b"busy")

    def test_different_books_same_audio_are_stable_in_separate_batches(self):
        audios = [self.audio("Unit 1", book="英语 三年级 上册"),
                  self.audio("Unit 1", book="英语 三年级 下册", key="b")]
        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(audios, directory)
            self.assertNotEqual(paths[0], paths[1])
            for audio, path in zip(audios, paths):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").close()
                self.assertEqual(allocate_download_paths([audio], directory), [path])

    def test_hyphens_and_known_prefix_are_handled_without_guessing(self):
        audios = [self.audio("Unit 1 - Start-up", book="英语 - 三年级"),
                  self.audio("英语 - 三年级 - Unit 2 - Follow-up", book="英语 - 三年级", key="b"),
                  self.audio("英语 - 三年级", book="英语 - 三年级", key="c")]
        with tempfile.TemporaryDirectory() as directory:
            names = [os.path.basename(p) for p in allocate_download_paths(audios, directory)]
        self.assertEqual(names, ["Unit 1 - Start-up.mp3", "Unit 2 - Follow-up.mp3", "英语 - 三年级.mp3"])

    def test_missing_metadata_preserves_full_title_and_formats_stay_distinct(self):
        audios = [resource("教材 - Unit 1", "a", file_format="mp3"),
                  resource("教材 - Unit 1", "b", file_format="wav"),
                  resource("教材 - Unit 1", "c", file_format="pdf")]
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(allocate_download_paths(audios, directory), [
                os.path.join(directory, "mp3", "教材 - Unit 1.mp3"),
                os.path.join(directory, "mp3", "教材 - Unit 1.wav"),
                os.path.join(directory, "教材 - Unit 1.pdf"),
            ])

    def test_same_book_duplicates_case_unicode_and_sanitization(self):
        audios = [self.audio(child, key=str(i)) for i, child in enumerate([
            "Unit?", "Unit？", "UNIT？", "Café", "Cafe\u0301", "CON", "1/2: What?",
        ])]
        with tempfile.TemporaryDirectory() as directory:
            paths = allocate_download_paths(audios, directory)
        self.assertEqual([os.path.basename(p) for p in paths], [
            "Unit？.mp3", "Unit？ (2).mp3", "UNIT？ (3).mp3", "Café.mp3", "Cafe\u0301 (2).mp3",
            "_CON.mp3", "1／2： What？.mp3",
        ])

    def test_legacy_complete_file_is_reused_without_moving(self):
        audio = self.audio()
        with tempfile.TemporaryDirectory() as directory:
            old_path = os.path.join(directory, *self.category, download_filename(audio))
            os.makedirs(os.path.dirname(old_path))
            with open(old_path, "wb") as file:
                file.write(b"complete")
            self.assertEqual(allocate_download_paths([audio], directory), [old_path])
            self.assertEqual(open(old_path, "rb").read(), b"complete")
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(old_path), "mp3")))
            # 旧 .tmp 不属于本次任务，即使旧文件存在，也不采用正在写入的位置。
            open(old_path + ".tmp", "wb").close()
            self.assertNotEqual(allocate_download_paths([audio], directory), [old_path])

    def test_legacy_edition_prefix_is_recognized_in_a_smaller_batch(self):
        audio = self.audio()
        with tempfile.TemporaryDirectory() as directory:
            old_path = os.path.join(directory, *self.category, f"[{audio.edition}] {download_filename(audio)}")
            os.makedirs(os.path.dirname(old_path))
            open(old_path, "wb").close()
            self.assertEqual(allocate_download_paths([audio], directory), [old_path])

    def test_new_complete_file_has_priority_over_legacy(self):
        audio = self.audio()
        with tempfile.TemporaryDirectory() as directory:
            new_path = allocate_download_paths([audio], directory)[0]
            old_path = os.path.join(directory, *self.category, download_filename(audio))
            os.makedirs(os.path.dirname(new_path))
            for path in (old_path, new_path):
                open(path, "wb").close()
            self.assertEqual(allocate_download_paths([audio], directory), [new_path])

    def test_directory_and_file_path_conflicts_do_not_overwrite(self):
        audio = self.audio()
        with tempfile.TemporaryDirectory() as directory:
            category = os.path.join(directory, *self.category)
            os.makedirs(category)
            with open(os.path.join(category, "mp3"), "wb") as file:
                file.write(b"keep")
            path = allocate_download_paths([audio], directory)[0]
            self.assertIn(os.path.join("mp3 (2)", self.book), path)
            os.makedirs(path)
            self.assertTrue(allocate_download_paths([audio], directory)[0].endswith(" (2).mp3"))
            self.assertEqual(open(os.path.join(category, "mp3"), "rb").read(), b"keep")


if __name__ == "__main__":
    unittest.main()
