import tempfile
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject


@pytest.fixture
def image_pdf():
    # 缩小版的未压缩 CMYK 图片；测试中降低读取上限，避免生成百兆测试文件。
    writer = PdfWriter()
    page = writer.add_blank_page(width=32, height=32)
    image = DecodedStreamObject()
    image.set_data(b"\x10\x20\x30\x40" * 1024)
    image.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(32),
        NameObject("/Height"): NumberObject(32),
        NameObject("/ColorSpace"): NameObject("/DeviceCMYK"),
        NameObject("/BitsPerComponent"): NumberObject(8),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): writer._add_object(image)}),
    })
    content = DecodedStreamObject()
    content.set_data(b"q 32 0 0 32 0 0 cm /Im0 Do Q\n")
    page[NameObject("/Contents")] = writer._add_object(content)

    root = Path(__file__).resolve().parents[1] / ".tmp"
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        path = Path(directory) / "image.pdf"
        writer.write(path)
        yield path
