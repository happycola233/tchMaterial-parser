// -*- coding: utf-8 -*-
const express = require('express');
const cors = require('cors');
const axios = require('axios');
const https = require('https');

const app = express();
const PORT = 3001;

app.use(cors());
app.use(express.json({ limit: '500mb' }));

let accessToken = null;
const headers = { 'X-ND-AUTH': 'MAC id="0",nonce="0",mac="0"' };

const httpAgent = new https.Agent({ rejectUnauthorized: false });
const session = axios.create({
  httpsAgent: httpAgent,
  proxy: false
});

async function parse(url, bookmarks) {
  try {
    let contentId = null;
    let contentType = null;
    let resourceUrl = null;
    const chapters = [];

    const queryString = url.substring(url.indexOf('?') + 1);
    const params = queryString.split('&');

    for (const param of params) {
      const [key, value] = param.split('=');
      if (key === 'contentId') {
        contentId = decodeURIComponent(value);
        break;
      }
    }
    if (!contentId) return { error: '未找到 contentId' };

    for (const param of params) {
      const [key, value] = param.split('=');
      if (key === 'contentType') {
        contentType = decodeURIComponent(value);
        break;
      }
    }
    if (!contentType) contentType = 'assets_document';

    let apiUrl;
    if (/^https?:\/\/([^/]+)\/syncClassroom\/basicWork\/detail/.test(url)) {
      apiUrl = `https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/${contentId}.json`;
    } else if (contentType === 'thematic_course') {
      apiUrl = `https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/resources/details/${contentId}.json`;
    } else {
      apiUrl = `https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/${contentId}.json`;
    }

    const response = await session.get(apiUrl, { headers });
    const data = response.data;
    const title = data.title;

    for (const item of data.ti_items) {
      if (item.ti_is_source_file) {
        resourceUrl = item.ti_storage;
        if (resourceUrl) {
          resourceUrl = resourceUrl.replace(
            'cs_path:${ref-path}',
            accessToken ? 'https://r1-ndr-private.ykt.cbern.com.cn' : 'https://c1.ykt.cbern.com.cn'
          );
        } else {
          resourceUrl = item.ti_storages?.find(u => u);
          if (resourceUrl && !accessToken) {
            resourceUrl = resourceUrl.replace(/^https?:\/\/.+\.ykt\.cbern\.com\.cn\/(.+)$/, 'https://c1.ykt.cbern.com.cn/$1');
          }
        }
        break;
      }
    }

    if (!resourceUrl) {
      if (contentType === 'thematic_course') {
        const resourcesResp = await session.get(
          `https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/special_edu/thematic_course/${contentId}/resources/list.json`,
          { headers }
        );
        for (const resource of resourcesResp.data) {
          if (resource.resource_type_code === 'assets_document') {
            for (const item of resource.ti_items || []) {
              if (item.ti_is_source_file) {
                resourceUrl = item.ti_storage || item.ti_storages?.find(u => u);
                if (resourceUrl) {
                  resourceUrl = resourceUrl.replace('cs_path:${ref-path}',
                    accessToken ? 'https://r1-ndr-private.ykt.cbern.com.cn' : 'https://c1.ykt.cbern.com.cn');
                }
                if (resourceUrl) break;
              }
            }
          }
          if (resourceUrl) break;
        }
      }
      if (!resourceUrl) return { error: '无法获取下载链接' };
    }

    if (bookmarks) {
      try {
        let mappingUrl = null;
        for (const item of data.ti_items) {
          if (item.ti_file_flag === 'ebook_mapping') {
            mappingUrl = item.ti_storage?.replace('cs_path:${ref-path}', 'https://r1-ndr-private.ykt.cbern.com.cn')
                      || item.ti_storages?.find(u => u);
            break;
          }
        }

        if (mappingUrl) {
          const mapResp = await session.get(mappingUrl, { headers });
          const mapData = mapResp.data;
          const ebookId = mapData.ebook_id;
          const pageMap = [];
          if (mapData.mappings) {
            for (const m of mapData.mappings) {
              pageMap.push({ node_id: m.node_id, page_number: m.page_number || 1 });
            }
          }

          if (ebookId) {
            const treeResp = await session.get(
              `https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/${ebookId}.json`,
              { headers }
            );
            const treeData = treeResp.data;

            function processTreeNodes(nodes) {
              const result = [];
              for (const node of nodes) {
                const pageNum = pageMap.find(m => m.node_id === node.id)?.page_number;
                const chapterItem = { title: node.title, page_index: pageNum };
                if (node.child_nodes) {
                  chapterItem.children = processTreeNodes(node.child_nodes);
                }
                result.push(chapterItem);
              }
              return result;
            }

            if (Array.isArray(treeData)) {
              chapters.push(...processTreeNodes(treeData));
            } else if (treeData.child_nodes) {
              chapters.push(...processTreeNodes(treeData.child_nodes));
            }
          }
        }
      } catch (e) {
        console.error('Error getting chapters:', e.message);
      }
    }

    return { resourceUrl, title, chapters };
  } catch (error) {
    console.error('Parse error:', error.message);
    return { error: error.message };
  }
}

app.post('/api/set_token', (req, res) => {
  const { token } = req.body;
  accessToken = token;
  headers['X-ND-AUTH'] = `MAC id="${accessToken}",nonce="0",mac="0"`;
  res.json({ success: true });
});

app.post('/api/parse', async (req, res) => {
  const { url, bookmarks = false } = req.body;
  if (!url) return res.status(400).json({ error: '请输入URL' });

  const result = await parse(url, bookmarks);
  if (result.error) return res.status(400).json({ error: result.error });

  res.json({
    resource_url: result.resourceUrl,
    title: result.title,
    chapters: result.chapters,
    has_bookmarks: result.chapters.length > 0
  });
});

app.post('/api/download', async (req, res) => {
  const { url, bookmarks = false } = req.body;
  if (!url) return res.status(400).json({ error: '请输入URL' });

  const result = await parse(url, bookmarks);
  if (result.error) return res.status(400).json({ error: result.error });

  try {
    const response = await session.get(result.resourceUrl, {
      headers,
      responseType: 'stream',
      maxContentLength: Infinity,
      maxBodyLength: Infinity
    });

    const filename = (result.title || 'download') + '.pdf';
    const asciiFilename = filename.replace(/[^\x20-\x7E]/g, '').trim() || 'download';

    res.setHeader('Content-Disposition', `attachment; filename="${asciiFilename}"; filename*=UTF-8''${encodeURIComponent(filename)}`);
    res.setHeader('Content-Type', 'application/pdf');

    response.data.pipe(res);
  } catch (error) {
    console.error('Download error:', error.message);
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
