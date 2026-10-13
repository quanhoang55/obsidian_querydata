import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import './App.css'

type Config = { obsidian_url: string | null; obsidian_key_configured: boolean; gemini_api_key_configured: boolean; port: number }
type QueryResponse = {
  answer: string
  rows_parsed?: number
  matched_rows?: number
  data?: { columns: string[]; rows: Array<{ file: string; values: Record<string, unknown> }> }
}
type Message = { id: number; role: 'assistant' | 'user'; content: string; response?: QueryResponse; error?: boolean }
type VaultFile = { path: string; type: 'markdown' | 'excel'; content?: string; sheets?: Array<{ name: string; rows: unknown[][] }> }
const API = import.meta.env.VITE_API_BASE_URL ?? ''
const suggestions = ['Tổng doanh số tháng này', 'Doanh số của Nam trong tuần qua', 'Mặt hàng bán ngày 11/10/2026']

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`)
  return body as T
}

function Icon({ name }: { name: 'spark' | 'send' | 'plus' | 'files' | 'settings' | 'search' | 'close' | 'arrow' }) {
  const paths: Record<typeof name, string> = {
    spark: 'm12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3Z',
    send: 'm21 3-7.2 18-3.9-7.9L2 9.2 21 3ZM10 13 21 3',
    plus: 'M12 5v14M5 12h14', files: 'M3 6.5A1.5 1.5 0 0 1 4.5 5H10l2 2h7.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5v-11Z',
    settings: 'M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7ZM19.4 15a1.8 1.8 0 0 0 .36 1.99l.06.06-1.7 2.94-.08-.02a1.8 1.8 0 0 0-1.87.74l-.05.07h-3.4l-.03-.08a1.8 1.8 0 0 0-1.55-1.2 1.8 1.8 0 0 0-1.25.45l-.07.06-2.94-1.7.02-.08a1.8 1.8 0 0 0-.74-1.87l-.07-.05v-3.4l.08-.03a1.8 1.8 0 0 0 1.2-1.55 1.8 1.8 0 0 0-.45-1.25l-.06-.07 1.7-2.94.08.02a1.8 1.8 0 0 0 1.87-.74l.05-.07h3.4l.03.08a1.8 1.8 0 0 0 1.55 1.2 1.8 1.8 0 0 0 1.25-.45l.07-.06 2.94 1.7-.02.08a1.8 1.8 0 0 0 .74 1.87l.07.05v3.4l-.08.03Z',
    search: 'm20 20-4.4-4.4M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z', close: 'm6 6 12 12M18 6 6 18', arrow: 'M5 12h14m-6-6 6 6-6 6',
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={paths[name]} /></svg>
}

function displayCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function DataSummary({ data }: { data: NonNullable<QueryResponse['data']> }) {
  if (!data.rows.length || !data.columns.length) return null
  const fileCount = new Set(data.rows.map((row) => row.file)).size
  return <section className="data-summary" aria-label="Dữ liệu truy vấn">
    <div className="data-summary-heading"><span className="data-summary-spark"><Icon name="spark" /></span><div><strong>Dữ liệu từ vault</strong><small>{data.rows.length} dòng · {data.columns.length} cột · {fileCount} tệp</small></div></div>
    <div className="column-cloud">{data.columns.map((column, index) => {
      const values = [...new Set(data.rows.map((row) => displayCell(row.values[column])).filter((value) => value !== '—'))]
      return <div className={`column-card tone-${index % 5}`} key={column}><span className="column-name">{column}</span><div className="column-values">{values.length ? values.map((value) => <span className="value-chip" key={value}>{value}</span>) : <span className="value-empty">Không có giá trị</span>}</div></div>
    })}</div>
  </section>
}

function App() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState<'checking' | 'online' | 'offline'>('checking')
  const [config, setConfig] = useState<Config | null>(null)
  const [panel, setPanel] = useState<'settings' | 'files' | null>(null)
  const [files, setFiles] = useState<string[]>([])
  const [fileFilter, setFileFilter] = useState('')
  const [selectedFile, setSelectedFile] = useState<VaultFile | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [searchResults, setSearchResults] = useState<unknown[]>([])
  const [searchBusy, setSearchBusy] = useState(false)
  const [settingsUrl, setSettingsUrl] = useState('')
  const [settingsKey, setSettingsKey] = useState('')
  const [settingsBusy, setSettingsBusy] = useState(false)
  const [settingsNotice, setSettingsNotice] = useState('')
  const messagesEnd = useRef<HTMLDivElement>(null)

  const refreshConnection = useCallback(async () => {
    try {
      const [, nextConfig] = await Promise.all([request('/health'), request<Config>('/api/v1/config')])
      setHealth('online')
      setConfig(nextConfig)
      setSettingsUrl(nextConfig.obsidian_url || '')
    } catch {
      setHealth('offline')
    }
  }, [])

  const refreshFiles = useCallback(async () => {
    try {
      const response = await request<{ files: string[] }>('/api/v1/vault/files')
      setFiles(response.files)
    } catch (error) {
      setFiles([])
      setSettingsNotice(error instanceof Error ? error.message : 'Không thể tải danh sách tệp.')
    }
  }, [])

  useEffect(() => { void refreshConnection() }, [refreshConnection])
  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  async function submitPrompt(prompt: string) {
    const content = prompt.trim()
    if (!content || busy) return
    setMessages((current) => [...current, { id: Date.now(), role: 'user', content }])
    setInput('')
    setBusy(true)
    try {
      const result = await request<QueryResponse>('/api/v1/query', { method: 'POST', body: JSON.stringify({ prompt: content }) })
      setMessages((current) => [...current, { id: Date.now() + 1, role: 'assistant', content: result.answer, response: result }])
    } catch (error) {
      setMessages((current) => [...current, { id: Date.now() + 1, role: 'assistant', content: error instanceof Error ? error.message : 'Không thể kết nối backend.', error: true }])
    } finally { setBusy(false) }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void submitPrompt(input) }
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submitPrompt(input) }
  }
  function resetChat() { setMessages([]); setInput('') }

  async function openFile(path: string) {
    setFileLoading(true)
    try {
      const encodedPath = path.split('/').map(encodeURIComponent).join('/')
      setSelectedFile(await request<VaultFile>(`/api/v1/vault/files/${encodedPath}`))
    } catch (error) { setSettingsNotice(error instanceof Error ? error.message : 'Không thể đọc tệp.') }
    finally { setFileLoading(false) }
  }

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!searchText.trim()) return
    setSearchBusy(true)
    try {
      const response = await request<{ results: unknown[] }>('/api/v1/vault/search', { method: 'POST', body: JSON.stringify({ query: searchText.trim(), context_length: 120 }) })
      setSearchResults(response.results)
    } catch (error) { setSettingsNotice(error instanceof Error ? error.message : 'Không thể tìm kiếm.') }
    finally { setSearchBusy(false) }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSettingsBusy(true); setSettingsNotice('')
    const payload: Record<string, string> = { obsidian_url: settingsUrl.trim() }
    if (settingsKey.trim()) payload.obsidian_key = settingsKey.trim()
    try {
      const next = await request<Config>('/api/v1/config', { method: 'PUT', body: JSON.stringify(payload) })
      setConfig(next); setSettingsKey(''); setSettingsNotice('Đã lưu kết nối Obsidian cho phiên backend hiện tại.')
      await refreshConnection()
    } catch (error) { setSettingsNotice(error instanceof Error ? error.message : 'Không thể lưu cấu hình.') }
    finally { setSettingsBusy(false) }
  }

  const visibleFiles = files.filter((path) => path.toLowerCase().includes(fileFilter.toLowerCase()))

  return <main className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#home" aria-label="Querydata home"><span className="brand-mark"><Icon name="spark" /></span><span>query<span className="brand-light">data</span></span></a>
      <button className="new-chat" onClick={resetChat} type="button"><Icon name="plus" /><span>Cuộc trò chuyện mới</span></button>
      <div className="sidebar-label">Workspace</div>
      <button className={`nav-item ${panel === null ? 'active' : ''}`} onClick={() => setPanel(null)} type="button"><Icon name="spark" /> Trợ lý truy vấn</button>
      <button className={`nav-item ${panel === 'files' ? 'active' : ''}`} onClick={() => { setPanel('files'); setSelectedFile(null); void refreshFiles() }} type="button"><Icon name="files" /> Tệp trong vault</button>
      <button className={`nav-item ${panel === 'settings' ? 'active' : ''}`} onClick={() => { setPanel('settings'); setSettingsNotice('') }} type="button"><Icon name="settings" /> Kết nối Obsidian</button>
      <div className="sidebar-bottom">
        <button className="vault-card" type="button" onClick={() => setPanel('settings')}><span className="vault-icon">⌘</span><span className="vault-label"><strong>Obsidian vault</strong><small>{config?.obsidian_url || 'Chưa cấu hình'}</small></span><span className={`status-dot ${health}`} /></button>
        <div className="sidebar-foot"><span className={`health-indicator ${health}`} />{health === 'online' ? 'Backend đang hoạt động' : health === 'checking' ? 'Đang kiểm tra backend…' : 'Không kết nối được backend'}</div>
      </div>
    </aside>

    <section className="main-panel" id="home">
      <header className="topbar"><div className="breadcrumb">Workspace <span className="crumb-divider">/</span> <span>{panel === 'files' ? 'Vault' : panel === 'settings' ? 'Kết nối' : 'Chat'}</span></div><div className="topbar-right"><span className={`local-badge ${health}`}><span />{health === 'online' ? 'Backend online' : health === 'checking' ? 'Đang kết nối' : 'Backend offline'}</span><button className="icon-button" aria-label="Cấu hình kết nối" title="Cấu hình kết nối" onClick={() => { setPanel('settings'); setSettingsNotice('') }} type="button"><Icon name="settings" /></button></div></header>

      {panel === 'settings' ? <section className="utility-page"><div className="page-heading"><span className="page-icon"><Icon name="settings" /></span><div><p className="eyebrow">KẾT NỐI</p><h1>Cấu hình workspace</h1><p>Kết nối giao diện với backend và Obsidian Local REST API.</p></div></div>
        <form className="settings-card" onSubmit={(event) => void saveSettings(event)}><label>Obsidian API URL<input value={settingsUrl} onChange={(event) => setSettingsUrl(event.target.value)} placeholder="https://127.0.0.1:27124" required /></label><label>Obsidian API key<input type="password" value={settingsKey} onChange={(event) => setSettingsKey(event.target.value)} placeholder={config?.obsidian_key_configured ? 'Đã cấu hình · để trống để giữ nguyên' : 'Nhập API key'} autoComplete="new-password" /></label><div className="config-status"><span><i className={config?.obsidian_key_configured ? 'configured' : ''} />Obsidian key {config?.obsidian_key_configured ? 'đã cấu hình' : 'chưa cấu hình'}</span><span><i className={config?.gemini_api_key_configured ? 'configured' : ''} />Gemini {config?.gemini_api_key_configured ? 'đã cấu hình' : 'chưa cấu hình'}</span></div><button className="primary-button" disabled={settingsBusy}>{settingsBusy ? 'Đang lưu…' : 'Lưu cấu hình'}</button>{settingsNotice && <p className="inline-notice" role="status">{settingsNotice}</p>}<p className="form-hint">Cấu hình được lưu trong bộ nhớ backend đến khi tiến trình khởi động lại. GEMINI_API_KEY vẫn được đọc từ file .env.</p></form></section>
      : panel === 'files' ? <section className="vault-page"><div className="vault-heading"><div><p className="eyebrow">OBSIDIAN VAULT</p><h1>Tệp của bạn</h1><p>{files.length} tệp Markdown và Excel</p></div><button className="quiet-button" onClick={() => { setSelectedFile(null); void refreshFiles() }} type="button">Làm mới</button></div><form className="file-search" onSubmit={(event) => void runSearch(event)}><Icon name="search" /><input aria-label="Tìm kiếm trong vault" placeholder="Tìm nội dung trong vault..." value={searchText} onChange={(event) => setSearchText(event.target.value)} /><button type="submit" disabled={searchBusy}>{searchBusy ? 'Đang tìm…' : 'Tìm'}</button></form>
        {searchResults.length > 0 && <div className="search-results"><div className="section-caption">KẾT QUẢ TÌM KIẾM <button type="button" onClick={() => setSearchResults([])}>Xóa</button></div>{searchResults.slice(0, 8).map((result, index) => <pre key={index}>{typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>)}</div>}
        <div className="file-layout"><div className="file-list-pane"><div className="file-filter"><Icon name="search" /><input aria-label="Lọc danh sách tệp" placeholder="Lọc tệp..." value={fileFilter} onChange={(event) => setFileFilter(event.target.value)} /></div><div className="file-list">{visibleFiles.map((path) => <button key={path} type="button" className={`file-row ${selectedFile?.path === path ? 'selected' : ''}`} onClick={() => void openFile(path)}><span className={`file-type ${path.endsWith('.xlsx') ? 'excel' : ''}`}>{path.endsWith('.xlsx') ? 'XLS' : 'MD'}</span><span>{path}</span></button>)}{!visibleFiles.length && <p className="empty-note">{health === 'offline' ? 'Kết nối backend để tải tệp.' : 'Không tìm thấy tệp phù hợp.'}</p>}</div></div><div className="file-preview">{fileLoading ? <p className="empty-note">Đang tải tệp…</p> : selectedFile ? <><div className="preview-title"><span className={`file-type ${selectedFile.type === 'excel' ? 'excel' : ''}`}>{selectedFile.type === 'excel' ? 'XLS' : 'MD'}</span><strong>{selectedFile.path}</strong></div>{selectedFile.type === 'markdown' ? <pre className="markdown-preview">{selectedFile.content}</pre> : selectedFile.sheets?.map((sheet) => <div className="sheet" key={sheet.name}><strong>{sheet.name}</strong><div className="table-scroll"><table><tbody>{sheet.rows.slice(0, 100).map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{String(cell ?? '')}</td>)}</tr>)}</tbody></table></div></div>)}</> : <div className="preview-empty"><span><Icon name="files" /></span><p>Chọn một tệp để xem nội dung</p></div>}</div></div>
      </section>
      : <><div className={`conversation ${messages.length ? 'has-messages' : ''}`}>
        {messages.length === 0 ? <div className="welcome"><div className="welcome-icon"><Icon name="spark" /></div><p className="eyebrow">OBSIDIAN QUERY ASSISTANT</p><h1>Hôm nay bạn muốn<br /><span>tìm hiểu điều gì?</span></h1><p className="welcome-copy">Hỏi về dữ liệu trong vault của bạn.<br />Câu trả lời được xử lý qua backend cục bộ.</p><div className="suggestions">{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => void submitPrompt(suggestion)}>{suggestion}<span>↗</span></button>)}</div></div>
          : <div className="message-list" aria-live="polite">
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                {message.role === 'assistant' && <div className="assistant-avatar"><Icon name="spark" /></div>}
                <div className="message-content">
                  <span className="message-author">{message.role === 'user' ? 'Bạn' : 'Querydata'}</span>
                  <p className={message.error ? 'error-copy' : 'assistant-copy'}>{message.content}</p>
                  {message.response?.data && <DataSummary data={message.response.data} />}
                </div>
              </article>
            ))}
            {busy && <article className="message assistant"><div className="assistant-avatar"><Icon name="spark" /></div><div className="message-content"><span className="message-author">Querydata</span><p className="loading-copy"><i />Đang đọc yêu cầu và truy vấn vault…</p></div></article>}
            <div ref={messagesEnd} />
          </div>}
        </div><div className="composer-wrap"><form className="composer" onSubmit={handleSubmit}><textarea aria-label="Nhập câu hỏi" onChange={(event) => setInput(event.target.value)} onKeyDown={handleKeyDown} placeholder="Hỏi bất kỳ điều gì về vault của bạn..." rows={1} value={input} disabled={busy} /><div className="composer-footer"><span><span className={`composer-status ${health}`} /> {health === 'online' ? 'Kết nối backend' : 'Kiểm tra kết nối backend'}</span><button className="send-button" disabled={!input.trim() || busy} aria-label="Gửi câu hỏi" type="submit"><Icon name="send" /></button></div></form><p className="disclaimer">Kiểm tra lại kết quả quan trọng với dữ liệu nguồn.</p></div></>}
    </section>
  </main>
}

export default App
