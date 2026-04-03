# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_file, Response
import requests
import io
import re
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)

session = requests.Session()
access_token = None
headers = {"X-ND-AUTH": 'MAC id="0",nonce="0",mac="0"'}
session.proxies = {}

def parse(url, bookmarks):
    """解析资源，获取资源下载链接"""
    try:
        content_id = None
        content_type = None
        resource_url = None
        chapters = []

        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentId":
                content_id = q.split("=")[1]
                break
        if not content_id:
            return None, None, None

        for q in url[url.find("?") + 1:].split("&"):
            if q.split("=")[0] == "contentType":
                content_type = q.split("=")[1]
                break
        if not content_type:
            content_type = "assets_document"

        if re.search(r"^https?://([^/]+)/syncClassroom/basicWork/detail", url):
            response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
        else:
            if content_type == "thematic_course":
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/{content_id}.json")
            else:
                response = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{content_id}.json")

        data = response.json()
        title = data.get("title")

        for item in data["ti_items"]:
            if item["ti_is_source_file"]:
                resource_url = item.get("ti_storage")
                if resource_url:
                    resource_url = resource_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn" if access_token else "https://c1.ykt.cbern.com.cn")
                else:
                    resource_url = next((url for url in item["ti_storages"] if url), None)
                    if not resource_url:
                        continue
                    if not access_token:
                        resource_url = re.sub(r"^https?://(?:.+).ykt.cbern.com.cn/(.+)$", r"https://c1.ykt.cbern.com.cn/\1", resource_url)
                break

        if not resource_url:
            if content_type == "thematic_course":
                resources_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/thematic_course/{content_id}/resources/list.json")
                resources_data = resources_resp.json()
                for resource in resources_data:
                    if resource["resource_type_code"] == "assets_document":
                        for item in resource["ti_items"]:
                            if item["ti_is_source_file"]:
                                resource_url = item.get("ti_storage")
                                if resource_url:
                                    resource_url = resource_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn" if access_token else "https://c1.ykt.cbern.com.cn")
                                else:
                                    resource_url = next((url for url in item["ti_storages"] if url), None)
                                    if not resource_url:
                                        continue
                                    if not access_token:
                                        resource_url = re.sub(r"^https?://(?:.+).ykt.cbern.com.cn/(.+)$", r"https://c1.ykt.cbern.com.cn/\1", resource_url)
                                break
                if not resource_url:
                    return None, None, None
            else:
                return None, None, None

        if bookmarks:
            try:
                mapping_url = None
                for item in data["ti_items"]:
                    if item["ti_file_flag"] == "ebook_mapping":
                        mapping_url = item.get("ti_storage")
                        if mapping_url:
                            mapping_url = mapping_url.replace("cs_path:${ref-path}", "https://r1-ndr-private.ykt.cbern.com.cn")
                        else:
                            mapping_url = next((url for url in item["ti_storages"] if url), None)
                        break

                if mapping_url:
                    map_resp = session.get(mapping_url)
                    map_data = map_resp.json()
                    ebook_id = map_data.get("ebook_id")
                    page_map = []
                    if map_data.get("mappings"):
                        for m in map_data["mappings"]:
                            page_map.append({"node_id": m["node_id"], "page_number": m.get("page_number", 1)})

                    if ebook_id:
                        tree_resp = session.get(f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/{ebook_id}.json", headers=headers)
                        tree_data = tree_resp.json()

                        def process_tree_nodes(nodes):
                            result = []
                            for node in nodes:
                                page_num = next((m["page_number"] for m in page_map if m["node_id"] == node["id"]), None)
                                chapter_item = {"title": node["title"], "page_index": page_num}
                                if node.get("child_nodes"):
                                    chapter_item["children"] = process_tree_nodes(node["child_nodes"])
                                result.append(chapter_item)
                            return result

                        if isinstance(tree_data, list):
                            chapters = process_tree_nodes(tree_data)
                        elif isinstance(tree_data, dict) and tree_data.get("child_nodes"):
                            chapters = process_tree_nodes(tree_data["child_nodes"])
            except Exception as e:
                print(f"Error getting chapters: {e}")
                chapters = []

        return resource_url, title, chapters
    except Exception as e:
        print(f"Error parsing URL: {e}")
        return None, None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/set_token', methods=['POST'])
def api_set_token():
    global access_token
    data = request.get_json()
    token = data.get('token', '').strip()
    access_token = token
    headers["X-ND-AUTH"] = f'MAC id="{access_token}",nonce="0",mac="0"'
    return jsonify({'success': True})

@app.route('/api/parse', methods=['POST'])
def api_parse():
    data = request.get_json()
    url = data.get('url', '').strip()
    bookmarks = data.get('bookmarks', False)

    if not url:
        return jsonify({'error': '请输入URL'}), 400

    resource_url, title, chapters = parse(url, bookmarks)

    if not resource_url:
        return jsonify({'error': '解析失败'}), 400

    return jsonify({
        'resource_url': resource_url,
        'title': title,
        'chapters': chapters,
        'has_bookmarks': len(chapters) > 0 if chapters else False
    })

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json()
    url = data.get('url', '').strip()
    bookmarks = data.get('bookmarks', False)

    if not url:
        return jsonify({'error': '请输入URL'}), 400

    resource_url, title, chapters = parse(url, bookmarks)

    if not resource_url:
        return jsonify({'error': '解析失败'}), 400

    filename = (title or 'download') + '.pdf'

    try:
        response = session.get(resource_url, headers=headers, stream=True)

        if not response.ok:
            return jsonify({'error': f'服务器返回 {response.status_code}'}), 400

        file_content = b''
        for chunk in response.iter_content(chunk_size=262144):
            file_content += chunk

        if bookmarks and chapters:
            try:
                pdf_buffer = io.BytesIO(file_content)
                reader = PdfReader(pdf_buffer)
                writer = PdfWriter()

                def add_chapter(chapter_list, parent=None):
                    for chapter in chapter_list:
                        title_ch = chapter.get('title', '未知章节')
                        p_index = chapter.get('page_index')
                        if p_index is None:
                            continue
                        try:
                            page_num = int(p_index) - 1
                        except (ValueError, TypeError):
                            continue
                        if page_num < 0 or page_num >= len(reader.pages):
                            continue
                        bookmark = writer.add_outline_item(title_ch, page_num, parent=parent)
                        if chapter.get('children'):
                            add_chapter(chapter['children'], parent=bookmark)

                writer.append_pages_from_reader(reader)
                add_chapter(chapters)
                output_buffer = io.BytesIO()
                writer.write(output_buffer)
                file_content = output_buffer.getvalue()
            except Exception as e:
                print(f"Error adding bookmarks: {e}")

        ascii_filename = ''.join(c if ord(c) < 128 else '_' for c in filename) or 'download'

        return send_file(
            io.BytesIO(file_content),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=ascii_filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
