import requests

# 解析层级数据
def parse_hierarchy(hier):
    parsed = {}

    # 如果没有层级数据，返回空
    if not hier:
        return None
    for h in hier:
        for ch in h["children"]:
            parsed[ch["tag_id"]] = {"name": ch["tag_name"], "children": parse_hierarchy(ch["hierarchies"])}
    return parsed

# 获取课本列表
def fetch_book_list():
    # 获取层级数据
    tagsResp = requests.get("https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json")
    tagsData = tagsResp.json()
    parsedHierarchy = parse_hierarchy(tagsData["hierarchies"])

    # 获取课本列表 URL 列表
    listResp = requests.get("https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json")
    listData = listResp.json()["urls"].split(",")

    # 获取课本列表
    for url in listData:
        bookResp = requests.get(url)
        bookData = bookResp.json()
        for i in bookData:
            # 解析课本层级数据
            tagPaths = i["tag_paths"][0].split("/")[2:]

            # 如果课本层级数据不在层级数据中，跳过
            tempHier = parsedHierarchy[i["tag_paths"][0].split("/")[1]]
            if not tagPaths[0] in tempHier["children"]:
                continue

            # 分别解析课本层级
            for p in tagPaths:
                if tempHier["children"] and tempHier["children"].get(p):
                    tempHier = tempHier["children"].get(p)
            if not tempHier["children"]:
                tempHier["children"] = {}
            tempHier["children"][i["id"]] = i

    return parsedHierarchy