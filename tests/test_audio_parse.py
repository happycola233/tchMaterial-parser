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

    def test_listening_courseware_prefers_transcoded_mp3(self) -> None:
        # 源文件名里的逗号会让私有 CDN 返回 400，详情里的 href 才是可下载地址。
        class ListeningSession:
            def get(self, url: str, *args: tuple, **kwargs: dict) -> FakeResponse:
                self.url = url
                return FakeResponse({
                    "id": "listen-1",
                    "title": "Starter Unit 1 Section A, 2b",
                    "global_title": {"zh-CN": "Starter Unit 1 Section A, 2b"},
                    "ti_items": [
                        {
                            "ti_file_flag": "href",
                            "ti_format": "mp3",
                            "ti_is_source_file": False,
                            "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/listen-1.t/transcode/audios/listen-1.mp3",
                        },
                        {
                            "ti_file_flag": "href-clip",
                            "ti_format": "mp3",
                            "ti_is_source_file": False,
                            "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/listen-1.t/transcode/audios/clip-listen-1.mp3",
                        },
                        {
                            "ti_file_flag": "source",
                            "ti_format": "mp3",
                            "ti_is_source_file": True,
                            "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/listen-1.pkg/02 Starter Unit 1 Section A, 2b.mp3",
                        },
                    ],
                })

        session = ListeningSession()
        api.session = session
        url = "https://basic.smartedu.cn/syncClassroom/detail?resourceId=listen-1&resourceType=listening"
        results = api.parse(url, False)
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Starter Unit 1 Section A, 2b")
        self.assertEqual(results[0].file_format, "mp3")
        self.assertEqual(
            results[0].url,
            "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/listening/listen-1.t/transcode/audios/listen-1.mp3",
        )
        self.assertEqual(
            session.url,
            "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/listening/resources/details/listen-1.json",
        )

    def test_audio_playback_ignores_source_order_and_falls_back_to_clip(self) -> None:
        source_first = api.select_audio_playback([
            {
                "ti_file_flag": "source",
                "ti_format": "mp3",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/a.pkg/Section A, 2b.mp3",
            },
            {
                "ti_file_flag": "href",
                "ti_format": "mp3",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/a.t/transcode/audios/a.mp3",
            },
        ])
        self.assertEqual(
            source_first,
            ("https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/listening/a.t/transcode/audios/a.mp3", "mp3"),
        )

        clip_only = api.select_audio_playback([
            {
                "ti_file_flag": "source",
                "ti_format": "mp3",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/a.pkg/Section A, 2b.mp3",
            },
            {
                "ti_file_flag": "href-clip",
                "ti_format": "mp3",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/a.t/transcode/audios/clip-a.mp3",
            },
            {
                "ti_file_flag": "href-ogg",
                "ti_format": "ogg",
                "ti_storage": "cs_path:${ref-path}/edu_product/esp/listening/a.t/transcode/audios/a.ogg",
            },
        ])
        self.assertEqual(
            clip_only,
            ("https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/listening/a.t/transcode/audios/clip-a.mp3", "mp3"),
        )
        self.assertIsNone(api.select_audio_playback([
            {"ti_file_flag": "source", "ti_format": "pdf", "ti_storage": "https://example.com/book.pdf"},
            {"ti_file_flag": "href", "ti_format": "m3u8", "ti_storage": "https://example.com/video.m3u8"},
        ]))

    def test_course_package_keeps_pdf_and_skips_video_playlist(self) -> None:
        class PackageSession:
            def get(self, url: str, *args: tuple, **kwargs: dict) -> FakeResponse:
                return FakeResponse({
                    "id": "package-1",
                    "title": "Section A",
                    "relations": {
                        "national_course_resource": [
                            {
                                "title": "视频课程",
                                "ti_items": [
                                    {"ti_file_flag": "href", "ti_format": "m3u8", "ti_is_source_file": False, "ti_storage": "https://example.com/video.m3u8"},
                                ],
                            },
                            {
                                "title": "课件",
                                "ti_items": [
                                    {"ti_file_flag": "pdf", "ti_format": "pdf", "ti_is_source_file": False, "ti_storage": "cs_path:${ref-path}/edu_product/esp/coursewares/a.t/transcode/pdf.pdf"},
                                ],
                            },
                        ],
                    },
                })

        api.session = PackageSession()
        url = "https://basic.smartedu.cn/syncClassroom/detail?resourceId=package-1&resourceType=national_lesson"
        results = api.parse(url, False)
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_format, "pdf")
        self.assertEqual(
            results[0].url,
            "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/coursewares/a.t/transcode/pdf.pdf",
        )

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
