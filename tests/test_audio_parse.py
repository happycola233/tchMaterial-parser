import unittest

from src.tchmaterial_parser import api


class FakeResponse:
    def __init__(self, json_data: object) -> None:
        self._json = json_data

    def json(self) -> object:
        return self._json


class FakeSession:
    def __init__(self, details: dict, audios: list[dict]) -> None:
        self.details = details
        self.audios = audios

    def get(self, url: str, *args: tuple, **kwargs: dict) -> FakeResponse:
        if "relation_audios.json" in url:
            return FakeResponse(self.audios)
        return FakeResponse(self.details)


DETAILS = {
    "id": "book-1",
    "title": "英语七年级上册",
    "tag_list": [
        {
            "tag_dimension_id": "zxxbb",
            "tag_name": "人教版",
        },
    ],
    "ti_items": [
        {
            "ti_is_source_file": True,
            "ti_format": "pdf",
            "ti_storage": "cs_path:${ref-path}/edu_product/esp/assets/book-1.pkg/英语七年级上册.pdf",
        },
    ],
}

AUDIOS = [
    {
        "id": "audio-1",
        "global_title": {"zh-CN": "1 Starter Section 2 Activity 2"},
        "ti_items": [
            {
                "ti_file_flag": "href",
                "ti_format": "mp3",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/assets/audio-1.t/1.mp3",
            },
            {
                "ti_file_flag": "source",
                "ti_format": "wav",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/assets/audio-1.t/1.wav",
            },
        ],
    },
    {
        "id": "audio-2",
        "global_title": {"zh-CN": "2 Starter Section 3 Activity 1"},
        "ti_items": [
            {
                "ti_file_flag": "href",
                "ti_format": "mp3",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/assets/audio-2.t/2.mp3",
            },
        ],
    },
]


class AudioParseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(setattr, api, "session", api.session)

    def parse_book(self) -> list[api.ResourceInfo] | None:
        api.session = FakeSession(DETAILS, AUDIOS)
        url = "https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=book-1&catalogType=tchMaterial&subCatalog=tchMaterial"
        return api.parse(url, False)

    def test_textbook_with_audio_returns_pdf_and_mp3s(self) -> None:
        results = self.parse_book()
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][2], "pdf")
        self.assertEqual(results[0].edition, "人教版")
        self.assertEqual(results[1][1], "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/audio-1.t/1.mp3")
        self.assertEqual(results[1][2], "mp3")
        self.assertEqual(results[1][0], "英语七年级上册 - 1 Starter Section 2 Activity 2")
        self.assertEqual(results[1].edition, "人教版")
        self.assertEqual(results[2][0], "英语七年级上册 - 2 Starter Section 3 Activity 1")

    def test_textbook_without_audio_returns_only_pdf(self) -> None:
        api.session = FakeSession(DETAILS, [])
        url = "https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=book-1&catalogType=tchMaterial&subCatalog=tchMaterial"
        results = api.parse(url, False)
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], "pdf")

    def test_audio_fetch_failure_is_ignored(self) -> None:
        class FailingAudiosSession(FakeSession):
            def get(self, url: str, *args: tuple, **kwargs: dict) -> FakeResponse:
                if "relation_audios.json" in url:
                    raise RuntimeError("network error")
                return super().get(url, *args, **kwargs)

        api.session = FailingAudiosSession(DETAILS, [])
        url = "https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=book-1&catalogType=tchMaterial&subCatalog=tchMaterial"
        results = api.parse(url, False)
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
