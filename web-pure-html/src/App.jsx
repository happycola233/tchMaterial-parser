import { useState, useCallback, useEffect } from 'react'
import axios from 'axios'
import './index.css'

const API_URL = 'https://s-file-1.ykt.cbern.com.cn'

function App() {
  const [urlInput, setUrlInput] = useState('')
  const [token, setToken] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [resultType, setResultType] = useState('')
  const [downloadUrl, setDownloadUrl] = useState(null)
  const [title, setTitle] = useState('')

  useEffect(() => {
    const saved = localStorage.getItem('nd_access_token')
    if (saved) setToken(saved)
  }, [])

  const handleSetToken = useCallback(() => {
    const t = prompt('请输入 Access Token:', token)
    if (t !== null) {
      setToken(t)
      localStorage.setItem('nd_access_token', t)
    }
  }, [token])

  const parseUrlParams = (url) => {
    try {
      const query = url.substring(url.indexOf('?') + 1)
      const params = new URLSearchParams(query)
      const contentId = params.get('contentId')
      const contentType = params.get('contentType') || 'assets_document'
      return { contentId, contentType }
    } catch {
      return { contentId: null, contentType: null }
    }
  }

  const handleResolve = useCallback(async () => {
    if (!urlInput.trim()) {
      setResult('请输入资源链接')
      setResultType('error')
      return
    }

    const { contentId, contentType } = parseUrlParams(urlInput.trim())
    if (!contentId) {
      setResult('无法从链接中提取 contentId')
      setResultType('error')
      return
    }

    setLoading(true)
    setResult(null)
    setDownloadUrl(null)

    try {
      const headers = {
        'X-ND-AUTH': token ? `MAC id="${token}",nonce="0",mac="0"` : 'MAC id="0",nonce="0",mac="0"'
      }

      let apiUrl
      if (/syncClassroom\/basicWork\/detail/.test(urlInput)) {
        apiUrl = `${API_URL}/zxx/ndrs/special_edu/resources/details/${contentId}.json`
      } else if (contentType === 'thematic_course') {
        apiUrl = `${API_URL}/zxx/ndrs/special_edu/resources/details/${contentId}.json`
      } else {
        apiUrl = `${API_URL}/zxx/ndrv2/resources/tch_material/details/${contentId}.json`
      }

      const res = await axios.get(apiUrl, { headers, timeout: 30000 })
      const data = res.data
      setTitle(data.title || '未知标题')

      let dlUrl = null
      for (const item of data.ti_items || []) {
        if (item.ti_is_source_file) {
          dlUrl = item.ti_storage
          if (dlUrl) {
            dlUrl = dlUrl.replace(
              'cs_path:${ref-path}',
              token ? 'https://r1-ndr-private.ykt.cbern.com.cn' : 'https://c1.ykt.cbern.com.cn'
            )
          } else {
            dlUrl = item.ti_storages?.find(u => u)
            if (dlUrl && !token) {
              dlUrl = dlUrl.replace(/^https?:\/\/.+\.ykt\.cbern\.com\.cn\/(.+)$/, 'https://c1.ykt.cbern.com.cn/$1')
            }
          }
          break
        }
      }

      if (!dlUrl) {
        setResult('无法获取下载链接，资源可能不存在或需要登录')
        setResultType('error')
      } else {
        setDownloadUrl(dlUrl)
        setResult('解析成功！')
        setResultType('success')
      }
    } catch (err) {
      setResult('解析失败: ' + (err.response?.data?.message || err.message))
      setResultType('error')
    } finally {
      setLoading(false)
    }
  }, [urlInput, token])

  const handleDownload = useCallback(() => {
    if (!downloadUrl) return
    window.open(downloadUrl, '_blank')
  }, [downloadUrl])

  const handleCopyCurl = useCallback(() => {
    if (!downloadUrl) return
    const filename = (title || 'download') + '.pdf'
    const authHeader = token
      ? `-H "X-ND-AUTH: MAC id=\"${token}\",nonce=\"0\",mac=\"0\""`
      : '-H "X-ND-AUTH: MAC id=\"0\",nonce=\"0\",mac=\"0\""'
    const encodedUrl = encodeURI(downloadUrl)
    const curlCmd = `curl -L -o "$HOME/Downloads/${filename}" ${authHeader} "${encodedUrl}"`
    navigator.clipboard.writeText(curlCmd)
    alert('curl 命令已复制到剪贴板')
  }, [downloadUrl, token, title])

  return (
    <div className="container">
      <div className="header">
        <h1>📚 国家中小学智慧教育平台 资源下载工具</h1>
        <p>纯前端版本</p>
      </div>

      <div className="content">
        <div className="token-section">
          <div className="section-title">
            <span>Access Token</span>
            {token && <span className="token-badge">已设置</span>}
          </div>
          <div className="token-input">
            <input
              type="text"
              placeholder="留空可下载部分公开资源"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <button className="btn btn-secondary" onClick={handleSetToken}>
              {token ? '修改' : '设置'}
            </button>
          </div>
          <div className="help-text">
            <strong>获取方法：</strong>登录后按F12，在控制台执行：
            <code>JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith("ND_UC_AUTH")))).access_token</code>
          </div>
        </div>

        <div className="section">
          <div className="section-title">资源链接</div>
          <textarea
            placeholder="粘贴资源页面网址"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
          />
        </div>

        <div className="btn-group">
          <button className="btn btn-primary" onClick={handleResolve} disabled={loading}>
            🔍 解析
          </button>
        </div>

        {loading && (
          <div className="loading">
            <div className="spinner"></div>
            <p>解析中...</p>
          </div>
        )}

        {result && (
          <div className={`result ${resultType}`}>
            <h3>{result}</h3>
            {title && <p><strong>标题：</strong>{title}</p>}
            {downloadUrl && <p><strong>链接：</strong><a href={downloadUrl} target="_blank">{downloadUrl}</a></p>}
          </div>
        )}

        {downloadUrl && (
          <div className="btn-group" style={{ marginTop: '20px' }}>
            <button className="btn btn-primary" onClick={handleDownload}>
              🌐 浏览器下载
            </button>
            <button className="btn btn-secondary" onClick={handleCopyCurl}>
              📋 复制 curl 命令
            </button>
          </div>
        )}

        <div className="notice-box">
          <div className="section-title">💡 使用说明</div>
          <ul className="notice-list">
            <li>解析后可直接下载，或复制 curl 命令在终端执行</li>
            <li>部分资源需要设置 Token 才能下载</li>
            <li>如遇跨域错误，需使用 CORS 浏览器扩展</li>
            <li>不支持 PDF 书签功能</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

export default App
