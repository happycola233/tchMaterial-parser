import { useState, useCallback, useEffect } from 'react'
import axios from 'axios'
import './index.css'

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

  const handleResolve = useCallback(async () => {
    if (!urlInput.trim()) {
      setResult('请输入资源链接')
      setResultType('error')
      return
    }

    setLoading(true)
    setResult(null)
    setDownloadUrl(null)

    try {
      const res = await axios.post('/api/parse', {
        url: urlInput.trim(),
        bookmarks: true
      })

      setTitle(res.data.title || '未知标题')
      setDownloadUrl(res.data.resource_url)
      setResult('解析成功！')
      setResultType('success')
    } catch (err) {
      setResult('解析失败: ' + (err.response?.data?.error || err.message))
      setResultType('error')
    } finally {
      setLoading(false)
    }
  }, [urlInput])

  const handleDownload = useCallback(async () => {
    if (!urlInput.trim()) {
      setResult('请输入资源链接')
      setResultType('error')
      return
    }

    setLoading(true)
    try {
      const res = await axios.post('/api/download', {
        url: urlInput.trim(),
        bookmarks: true
      }, { responseType: 'blob' })

      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = (title || 'download') + '.pdf'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      setResult('下载完成！')
      setResultType('success')
    } catch (err) {
      setResult('下载失败: ' + err.message)
      setResultType('error')
    } finally {
      setLoading(false)
    }
  }, [urlInput, title])

  const handleCopyCurl = useCallback(() => {
    if (!downloadUrl) return
    const filename = (title || 'download') + '.pdf'
    const authHeader = token
      ? `-H "X-ND-AUTH: MAC id=\\"${token}\\",nonce=\\"0\\",mac=\\"0\\""`
      : '-H "X-ND-AUTH: MAC id=\\"0\\",nonce=\\"0\\",mac=\\"0\\""'
    const encodedUrl = encodeURI(downloadUrl)
    const curlCmd = `curl -L -o "$HOME/Downloads/${filename}" ${authHeader} "${encodedUrl}"`
    navigator.clipboard.writeText(curlCmd)
    alert('curl 命令已复制到剪贴板')
  }, [downloadUrl, token, title])

  return (
    <div className="container">
      <div className="header">
        <h1>📚 国家中小学智慧教育平台 资源下载工具</h1>
        <p>React + Express 版本</p>
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
          <button className="btn btn-primary" onClick={handleDownload} disabled={loading}>
            📥 下载
          </button>
        </div>

        {loading && (
          <div className="loading">
            <div className="spinner"></div>
            <p>处理中...</p>
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
            <button className="btn btn-secondary" onClick={handleCopyCurl}>
              📋 复制 curl 命令
            </button>
          </div>
        )}

        <div className="notice-box">
          <div className="section-title">💡 使用说明</div>
          <ul className="notice-list">
            <li>支持 PDF 书签功能</li>
            <li>部分资源需要设置 Token 才能下载</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

export default App
