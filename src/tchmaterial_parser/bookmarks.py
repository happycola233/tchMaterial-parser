# -*- coding: utf-8 -*-
# 为下载好的 PDF 写入章节书签

from pypdf import PdfReader, PdfWriter

from .platform_utils import print_error

def add_bookmarks(pdf_path: str, chapters: list[dict]) -> None: # 给 PDF 添加书签
    try:
        if not chapters:
            return
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)

        def add_chapter(chapter_list: list[dict], parent=None): # 递归添加书签的内部函数
            for chapter in chapter_list:
                title: str = chapter.get("title", "未知章节")
                p_index: int | None = chapter.get("page_index")
                if p_index is None: # 如果值为 None 或者不存在，跳过这个书签
                    print_error(ValueError(f"章节 “{title}” 的页码索引无效，已跳过此处书签添加"))
                    continue

                try: # 尝试将其转为整数并减 1（pypdf 页码从 0 开始)
                    page_num: int = int(p_index) - 1
                except (ValueError, TypeError) as e: # 如果转换失败，跳过这个书签
                    print_error(e)
                    continue

                if page_num < 0 or page_num >= len(writer.pages):
                    continue

                # 添加书签，其中 parent 是父级书签对象，用于处理多级目录
                bookmark = writer.add_outline_item(title, page_num, parent=parent)

                # 如果有子章节（children），递归添加
                if chapter.get("children"):
                    add_chapter(chapter["children"], parent=bookmark)

        # 开始处理章节数据
        add_chapter(chapters)

        # 保存修改后的文件
        with open(pdf_path, "wb") as f:
            writer.write(f)

    except Exception as e:
        print_error(e)
