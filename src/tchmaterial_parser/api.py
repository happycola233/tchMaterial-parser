# -*- coding: utf-8 -*-
# 解析单个资源页面，获取资源标题、下载直链、文件格式与章节目录

import re
from typing import NamedTuple
from urllib.parse import urlparse, parse_qs

from .network import headers, request_headers, session
from .platform_utils import print_error

class ResourceInfo(NamedTuple):
    title: str
    url: str
    file_format: str
    chapters: list[dict]
    edition: str | None = None

def get_edition_name(resource_data: dict) -> str | None:
    """读取资源分类中的教材版别，例如“人教版”“北师大版”。"""
    for tag in resource_data.get("tag_list") or []:
        if tag.get("tag_dimension_id") == "zxxbb" and tag.get("tag_name"):
            return tag["tag_name"]
    return None

def combine_resource_title(root_title: str | None, resource_title: str) -> str:
    """组合专题标题与实际资源标题，并避免平台重复标题造成超长文件名。"""
    if not root_title:
        return resource_title

    # 例如“体育与健康教师用书 基本运动技能（全一册）”的专题父记录与内部 PDF 标题相同；
    # 先折叠连续空白再比较，命中时保留子资源原文，避免生成“标题 - 标题”的超长文件名。
    normalized_root = " ".join(root_title.split()).casefold()
    normalized_resource = " ".join(resource_title.split()).casefold()
    if normalized_root == normalized_resource:
        return resource_title
    return f"{root_title} - {resource_title}"

def parse(url: str, bookmarks: bool) -> list[ResourceInfo] | None: # 解析资源，获取资源下载链接
    try:
        resources_info: list[ResourceInfo] = []

        # 1. 提取 URL 中的 contentId 与 contentType
        content_id: str | None = None
        content_type: str | None = None

        params = parse_qs(urlparse(url, "https").query)

        if "contentId" in params:
            content_id = params["contentId"][0]
        elif re.search(r"^https?://([^/]+)/syncClassroom/classActivity", url): # 课程资源
            content_type = "national_lesson"
            if "activityId" in params:
                content_id = params["activityId"][0]
            else:
                return None
        elif re.search(r"^https?://([^/]+)/syncClassroom/prepare/detail", url): # 备课资源（课件、教学设计等）
            content_type = "prepare_sub_type"
            if "resourceId" in params:
                content_id = params["resourceId"][0]
            else:
                return None
        elif re.search(r"^https?://([^/]+)/syncClassroom/detail", url): # 知识点微课等课程资源
            if "resourceId" in params and "resourceType" in params:
                content_id = params["resourceId"][0]
                content_type = params["resourceType"][0]
            else:
                return None
        elif re.search(r"^https?://([^/]+)/qualityCourse", url): # 精品课
            content_type = "quality_course"
            if "courseId" in params:
                content_id = params["courseId"][0]
            else:
                return None
        else:
            return None

        if not content_type:
            if "contentType" in params:
                content_type = params["contentType"][0]
            else:
                content_type = "assets_document"

        # 2. 获取资源的信息
        # 返回数据示例：
        """
        {
            "id": "4f64356a-8df7-4579-9400-e32c9a7f6718",
            // ...
            "ti_items": [
                {
                    "ti_md5": "497110473b106d28651c41c14aa6d942",
                    "ti_size": 13075391,
                    "ti_storage": "cs_path:${ref-path}/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf", // 资源文件地址
                    "ti_storages": [
                        "https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf",
                        "https://r2-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf",
                        "https://r3-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/4f64356a-8df7-4579-9400-e32c9a7f6718.pkg/义务教育教科书 语文 八年级 上册_1756191813436.pdf"
                    ],
                    "ti_file_flag": "source",
                    "ti_is_source_file": true,
                    // ...
                    "ti_format": "pdf",
                    // ...
                },
                {
                    // ...（和上一个元素组成一样）
                }
            ],
            // ...
            "title": "（根据2022年版课程标准修订）义务教育教科书·语文八年级上册",
            // ...
        }
        """
        # 其中 $.ti_items 的每一项对应一个资源

        if re.search(r"^https?://([^/]+)/tchMaterial/detail", url) and content_type == "assets_document": # 对普通电子课本的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{content_id}.json")
        elif content_type == "national_lesson": # 对课程资源的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/{content_id}.json")
        elif content_type == "quality_course": # 对精品课的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/{content_id}.json")
        elif content_type == "prepare_sub_type": # 对备课资源的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/prepare_sub_type/resources/details/{content_id}.json")
        elif re.search(r"^https?://([^/]+)/syncClassroom/detail", url): # 知识点微课等
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/{content_type}/resources/details/{content_id}.json")
        else: # 对专题课程（含电子课本、视频等）、其他类型资源的解析
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")

        data: dict = response.json()
        root_edition = get_edition_name(data)

        # 3. 获取资源标题、下载链接及章节目录
        def get_resource_info(resource_data: dict, root_title: str | None = None, edition: str | None = None) -> ResourceInfo | None:
            title_data = resource_data.get("global_title")
            resource_title: str = title_data.get("zh-CN") or title_data.get("en") if isinstance(title_data, dict) else title_data or resource_data.get("title") or resource_data.get("id")
            title = combine_resource_title(root_title, resource_title)
            resource_url: str | None = None
            resource_format = "pdf"

            for item in resource_data["ti_items"]: # 寻找存有资源链接列表的项
                if not item["ti_is_source_file"]:
                    continue

                resource_format = item.get("ti_format") or "pdf"
                if resource_format == "folder":
                   continue

                resource_url = item.get("ti_storage") # 获取并构造资源的 URL
                if resource_url:
                    resource_url = resource_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn")
                else:
                    resource_url = next((url for url in item["ti_storages"] if url), None)
                    if not resource_url:
                        continue
                break

            if not resource_url: # 使用不同的判断条件寻找源文件
                for item in resource_data["ti_items"]:
                    if item["ti_file_flag"] not in ("source", "pdf", "ppt", "pptx", "doc", "docx"):
                        continue

                    resource_format = item.get("ti_format") or "pdf"
                    if resource_format == "folder":
                      continue

                    resource_url = item.get("ti_storage")
                    if resource_url:
                        resource_url = resource_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn")
                    else:
                        resource_url = next((url for url in item["ti_storages"] if url), None)
                        if not resource_url:
                            continue
                    break

            if not resource_url:
                return None

            # 通过 ebook_mapping + tree 接口组合获取章节目录
            chapters: list[dict] = []
            if bookmarks and resource_format == "pdf":
                try:
                    mapping_url: str | None = None
                    for item in resource_data["ti_items"]:
                        if item["ti_file_flag"] == "ebook_mapping":
                            mapping_url = item.get("ti_storage") # 形如 https://r1-ndr-private.ykt.cbern.com.cn/edu_product/esp/assets/*.pkg/ebook_mapping.txt
                            if mapping_url:
                                mapping_url = mapping_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn")
                            else:
                                mapping_url = next((url for url in item["ti_storages"] if url), None)
                            break

                    if mapping_url:
                        # a. 下载 mapping 文件获取页码和 ebook_id。
                        # mapping 也在 ndr-private 上，必须按 URL 现算 X-ND-AUTH，不能用全局占位头。
                        map_resp = session.get(mapping_url, headers=request_headers(mapping_url))
                        map_data: dict = map_resp.json()
                        ebook_id: str = map_data.get("ebook_id")

                        # 构建 node_id 到 page_number 的映射字典
                        # 格式: [{ "node_id": "...", "page_number": 1 }, ...]
                        page_map: list[dict] = []
                        if map_data.get("mappings"):
                            for m in map_data["mappings"]:
                                page_map.append({ "node_id": m["node_id"], "page_number": m.get("page_number", 1) })

                        # b. 如果有 ebook_id，在课程接口下载完整的目录树（tree API）
                        if ebook_id:
                            tree_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/{ebook_id}.json", headers=headers)
                            tree_data: list[dict] | dict = tree_resp.json()

                            # 递归函数：合并 tree 的标题和 mapping 的页码
                            def process_tree_nodes(nodes: list[dict]) -> list[dict]:
                                result: list[dict] = []
                                for node in nodes:
                                    # 从 page_map 中找页码，找不到为 None
                                    page_num: int | None = next((m["page_number"] for m in page_map if m["node_id"] == node["id"]), None)
                                    chapter_item = {
                                        "title": node["title"],
                                        "page_index": page_num,
                                    }

                                    # 如果有子节点，递归处理
                                    if node.get("child_nodes"):
                                        chapter_item["children"] = process_tree_nodes(node["child_nodes"])

                                    result.append(chapter_item)
                                return result

                            # 开始解析
                            if isinstance(tree_data, list):
                                chapters = process_tree_nodes(tree_data)
                            elif isinstance(tree_data, dict) and tree_data.get("child_nodes"):
                                chapters = process_tree_nodes(tree_data["child_nodes"])

                        # c. 兜底方案：如果获取 tree 失败，仅使用 mapping 生成纯页码索引
                        if not chapters:
                            page_map.sort(key=lambda x: x["page_number"])
                            for i, m in enumerate(page_map):
                                chapters.append({
                                    "title": f"第 {i+1} 节 (P{m['page_number']})",
                                    "page_index": m["page_number"],
                                })

                except Exception as e:
                    print_error(e)
                    chapters = []

            return ResourceInfo(
                title,
                resource_url,
                resource_format,
                chapters,
                edition or get_edition_name(resource_data),
            )

        def get_audio_info(audio_data: dict, root_title: str | None = None, edition: str | None = None) -> ResourceInfo | None: # 解析教材关联的音频资源（如英语教材听力）
            # 音频资源的标题存放在 global_title 字典中（键为语言代码，如 zh-CN）
            title_data = audio_data.get("global_title")
            audio_title: str = title_data.get("zh-CN") or title_data.get("en") if isinstance(title_data, dict) else title_data or audio_data.get("title") or audio_data.get("id")
            title = combine_resource_title(root_title, audio_title)
            resource_url: str | None = None
            resource_format = "mp3"

            # 优先选择转码后的 MP3 文件（ti_file_flag 为 href），否则回退到源文件
            for item in audio_data["ti_items"]:
                if item.get("ti_file_flag") not in ("href", "source") or item.get("ti_format") != "mp3":
                    continue

                resource_url = item.get("ti_storage") # 获取并构造资源的 URL
                if resource_url:
                    resource_url = resource_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn")
                else:
                    resource_url = next((url for url in item.get("ti_storages") or [] if url), None)
                if resource_url:
                    resource_format = item.get("ti_format") or "mp3"
                    break

            if not resource_url:
                return None

            return ResourceInfo(
                title,
                resource_url,
                resource_format,
                [],
                edition or get_edition_name(audio_data),
            )

        if content_type == "thematic_course": # 专题课程
            resources_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/thematic_course/{content_id}/resources/list.json")
            resources_data: list[dict] = resources_resp.json()
            for resource in resources_data:
                resource_info = get_resource_info(resource, data["title"], root_edition)
                if resource_info:
                    resources_info.append(resource_info)
        elif data.get("relations"): # 课程包等多资源页面（含导学案、课件、PPT 等）
            for resources in data["relations"].values():
                if not isinstance(resources, list):
                    continue
                for resource in resources:
                    resource_info = get_resource_info(resource, data.get("title"), root_edition)
                    if resource_info:
                        resources_info.append(resource_info)
        else: # 其他类型资源
            resource_info = get_resource_info(data)
            if resource_info:
                resources_info.append(resource_info)

            if content_type == "assets_document": # 教材可能带有配套的音频资源（如英语教材听力）
                try:
                    audios_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/{content_id}/relation_audios.json")
                    audios_data: list[dict] = audios_resp.json()
                    for audio in audios_data:
                        audio_info = get_audio_info(audio, data.get("title"), root_edition)
                        if audio_info:
                            resources_info.append(audio_info)
                except Exception: # 音频资源不是必需的，获取失败时直接跳过
                    pass

        return resources_info

    except Exception as e:
        print_error(e)
        return None
