# 对照官网 UC SDK 的签名原文与凭据解析。合成 fixture，不要把真实 Token 写进仓库。
import json
import unittest

from src.tchmaterial_parser.auth import (
    TokenCredentials,
    TokenInputError,
    build_nd_auth,
    format_token_json,
    parse_token_input,
    sign_mac,
    signature_string,
)


class ParseTokenInputTest(unittest.TestCase):
    def test_reads_json_credentials(self) -> None:
        raw = json.dumps({ "access_token": "tok", "mac_key": "key", "diff": 227 })
        self.assertEqual(parse_token_input(raw), TokenCredentials("tok", "key", 227))

    def test_reads_pretty_printed_json(self) -> None:
        raw = format_token_json("tok", "key", 227)
        self.assertEqual(parse_token_input(raw), TokenCredentials("tok", "key", 227))

    def test_reads_json_string_wrapper(self) -> None:
        inner = json.dumps({ "access_token": "tok", "mac_key": "key", "diff": 0 })
        self.assertEqual(parse_token_input(json.dumps(inner)), TokenCredentials("tok", "key", 0))

    def test_accepts_numeric_string_diff(self) -> None:
        raw = json.dumps({ "access_token": "tok", "mac_key": "key", "diff": "227" })
        self.assertEqual(parse_token_input(raw), TokenCredentials("tok", "key", 227))

    def test_rejects_raw_access_token(self) -> None:
        with self.assertRaises(TokenInputError):
            parse_token_input("abc123")

    def test_empty_input_clears_credentials(self) -> None:
        self.assertEqual(parse_token_input("   "), TokenCredentials(""))

    def test_rejects_json_missing_fields(self) -> None:
        with self.assertRaises(TokenInputError):
            parse_token_input('{"access_token":"tok","mac_key":"key"}')
        with self.assertRaises(TokenInputError):
            parse_token_input('{"mac_key":"key","diff":0}')

    def test_rejects_empty_mac_key(self) -> None:
        with self.assertRaises(TokenInputError):
            parse_token_input(json.dumps({ "access_token": "tok", "mac_key": "", "diff": 0 }))

    def test_rejects_nested_local_storage_blob(self) -> None:
        raw = json.dumps({ "value": json.dumps({ "access_token": "tok", "mac_key": "key", "diff": 1 }) })
        with self.assertRaises(TokenInputError):
            parse_token_input(raw)

    def test_format_token_json_backfills_old_fields(self) -> None:
        self.assertEqual(
            json.loads(format_token_json("old-token", None, 0)),
            { "access_token": "old-token", "mac_key": "", "diff": 0 },
        )


class BuildNdAuthTest(unittest.TestCase):
    def test_falls_back_to_placeholder_without_mac_key(self) -> None:
        self.assertEqual(
            build_nd_auth("https://r1-ndr-private.ykt.cbern.com.cn/book.pdf", access_token="tok"),
            'MAC id="tok",nonce="0",mac="0"',
        )
        self.assertEqual(
            build_nd_auth("https://example.com/book.pdf"),
            'MAC id="0",nonce="0",mac="0"',
        )

    def test_matches_official_uc_sdk_signature(self) -> None:
        # 查询串保留；百分号编码的中文路径先解码。期望值由独立 HMAC 预先算好，避免测试自己测自己。
        cases = [
            (
                "GET",
                "https://example.com/v1/users/1?with_ext=true",
                "1:ABCDEFGH",
                "1:ABCDEFGH\nGET\n/v1/users/1?with_ext=true\nexample.com\n",
                "VELg/RgBxeRZJWpku3Ggvkqu18Czem4bYh3D/8r6URA=",
            ),
            (
                "GET",
                "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/demo.pkg/ebook_mapping.txt",
                "2:ABCDEFGH",
                "2:ABCDEFGH\nGET\n/edu_product/esp/assets/demo.pkg/ebook_mapping.txt\nr1-ndr-private.ykt.cbern.com.cn\n",
                "n8yszXRHbMEcmrKlNUU0e5ZQak1TO8j1j8GGR8Gkanc=",
            ),
            (
                "GET",
                "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/demo.pkg/%E4%B8%AD%E6%96%87%20%E6%95%99%E6%9D%90.pdf",
                "3:ABCDEFGH",
                "3:ABCDEFGH\nGET\n/edu_product/esp/assets/demo.pkg/中文 教材.pdf\nr1-ndr-private.ykt.cbern.com.cn\n",
                "GNgACOhD4wact4qOSsix4gsp9X3oPTX6/Ct0FGFx9II=",
            ),
        ]
        mac_key = "test-mac-key"
        for method, url, nonce, expect_text, expect_mac in cases:
            with self.subTest(url=url):
                text = signature_string(url, method, nonce)
                self.assertEqual(text, expect_text)
                self.assertEqual(sign_mac(text, mac_key), expect_mac)
                self.assertEqual(
                    build_nd_auth(url, method, "tok", mac_key, nonce=nonce),
                    f'MAC id="tok",nonce="{nonce}",mac="{expect_mac}"',
                )


if __name__ == "__main__":
    unittest.main()
