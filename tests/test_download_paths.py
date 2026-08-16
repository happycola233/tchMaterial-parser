import os
import tempfile
import unittest

from src.tchmaterial_parser.api import ResourceInfo
from src.tchmaterial_parser.ui.download_panel import allocate_download_paths


def resource(
    title: str,
    resource_key: str,
    edition: str | None = None,
    file_format: str = "pdf",
) -> ResourceInfo:
    return ResourceInfo(
        title=title,
        url=f"https://example.com/{resource_key}.{file_format}",
        file_format=file_format,
        chapters=[],
        edition=edition,
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


if __name__ == "__main__":
    unittest.main()
