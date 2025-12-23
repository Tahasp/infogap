import { useEffect, useState } from 'react'

// Default to the hosted Render backend; override with VITE_API_URL for other environments.
const API_BASE = import.meta.env.VITE_API_URL || 'https://infogap.onrender.com'

export default function App() {
  const [topicInput, setTopicInput] = useState('')
  const [topics, setTopics] = useState<string[]>([])
  const [lang, setLang] = useState('fr')
  const [jobId, setJobId] = useState<string | null>(null)
  const [status, setStatus] = useState<string>('idle')
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [logPath, setLogPath] = useState<string | null>(null)
  const [logText, setLogText] = useState<string | null>(null)
  const [showTopicTooltip, setShowTopicTooltip] = useState(false)
  const [apiKey, setApiKey] = useState('')

  function addTopic() {
    const t = topicInput.trim()
    if (!t) return
    if (!topics.includes(t)) setTopics((prev) => [...prev, t])
    setTopicInput('')
  }

  function removeTopic(value: string) {
    setTopics((prev) => prev.filter((t) => t !== value))
  }

  async function runScraper() {
    if (topics.length === 0) {
      setStatus('please add topics')
      return
    }
    setStatus('submitting')
    try {
      const payload: { topics: string[]; tgt_lang: string; the_key?: string } = { topics, tgt_lang: lang }
      if (apiKey.trim()) payload.the_key = apiKey.trim()
      const res = await fetch(`${API_BASE}/jobs/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      const data = await res.json()
      setJobId(data.id || 'dev-placeholder')
      setStatus('submitted')
      setProgress(0)
      setError(null)
    } catch (e) {
      setStatus('error')
    }
  }

  async function runPipeline() {
    if (topics.length === 0) {
      setStatus('please add topics')
      return
    }
    setStatus('submitting')
    try {
      const payload: { topic: string; tgt_lang: string; the_key?: string } = { topic: topics[0], tgt_lang: lang }
      if (apiKey.trim()) payload.the_key = apiKey.trim()
      const res = await fetch(`${API_BASE}/jobs/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      const data = await res.json()
      setJobId(data.id || 'dev-placeholder')
      setProgress(0)
      setError(null)
      setLogText(null)
    } catch (e) {
      setStatus('error')
    }
  }

  async function fetchLogs() {
    if (!jobId) return
    try {
      const res = await fetch(`${API_BASE}/logs/${jobId}`)
      if (!res.ok) return
      const data = await res.json()
      setLogText(data.log)
    } catch (_) {}
  }

  async function handleLangChange(newLang: string) {
    setLang(newLang)
    try {
      await fetch(`${API_BASE}/config/tgt-lang`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tgt_lang: newLang })
      })
    } catch (e) {
      setError('Failed to update target language')
    }
  }

  async function downloadCsv() {
    const first = topics[0]
    if (!first) return
    try {
      const res = await fetch(`${API_BASE}/results/${encodeURIComponent(first)}/${lang}/csv`)
      if (!res.ok) {
        setError('CSV not available yet')
        return
      }
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${first}_${lang}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (e) {
      setError('Failed to download CSV')
    }
  }

  // Poll job status when jobId is present
  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    const iv = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`)
        const data = await res.json()
        if (cancelled) return
        setStatus(data.status || 'unknown')
        setProgress(typeof data.progress === 'number' ? data.progress : null)
        setError(data.error || null)
        setLogPath(data.log || null)
        if (['finished', 'failed'].includes(data.status)) {
          clearInterval(iv)
        }
      } catch (_) {
        // ignore transient errors
      }
    }, 1500)
    return () => { cancelled = true; clearInterval(iv) }
  }, [jobId])

  const page = {
    wrap: {
      fontFamily: 'Inter, system-ui, Arial',
      color: '#0a0a0a',
      background: '#fff'
    } as React.CSSProperties,
    container: {
      maxWidth: 1200,
      margin: '0 auto'
    } as React.CSSProperties,
    section: {
      padding: '64px 24px',
      borderTop: '1px solid #eee'
    } as React.CSSProperties,
    h1: { fontSize: 20, margin: 0 } as React.CSSProperties,
    button: (primary = false) => ({
      padding: '10px 16px',
      borderRadius: 999,
      border: primary ? '1px solid #1e3a8a' : '1px solid #d1d5db',
      background: primary ? '#2563eb' : '#f9fafb',
      color: primary ? '#fff' : '#111827',
      cursor: 'pointer',
      textDecoration: 'none',
      display: 'inline-block'
    }) as React.CSSProperties,
    card: {
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      padding: 24
    } as React.CSSProperties,
    muted: { color: '#6b7280' } as React.CSSProperties
  }

  return (
    <div style={page.wrap}>
      {/* Navbar */}
      <nav style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px', borderBottom: '1px solid #eee', position: 'sticky', top: 0, background: '#fff', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 10, height: 10, borderRadius: 20, background: '#2563eb' }} />
          <h1 style={page.h1}>InfoGap</h1>
        </div>
        <div style={{ display: 'flex', gap: 10, fontSize: 14 }}>
          <a href="#home" style={page.button(false)}>Home</a>
          <a href="#run" style={page.button(false)}>Run</a>
          <a href="#setup" style={page.button(false)}>Setup</a>
          <a href="#features" style={page.button(false)}>Features</a>
          <a href="#pipeline" style={page.button(false)}>Pipeline</a>
        </div>
        <a href="http://arxiv.org/abs/2410.04282" target="_blank" rel="noopener noreferrer" style={page.button(true) as any}>Research Paper</a>
      </nav>

      {/* Hero (centered, no diagram) */}
      <section id="home" style={{ ...page.section }}>
        <div style={{ ...page.container, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 16 }}>
          <h2 style={{ fontSize: 44, lineHeight: 1.15, margin: 0, maxWidth: 900 }}>Bridge the information gap across languages.</h2>
          <p style={{ ...page.muted, maxWidth: 820 }}>InfoGap discovers missing or inconsistent facts across multilingual Wikipedia — simplified for fast setup and dataset creation via the WikiGap branch.</p>
          <div style={{ display: 'flex', gap: 12 }}>
            <a href="#run" style={page.button(true) as any}>Get Started</a>
            <a href="#setup" style={page.button(false) as any}>View Setup</a>
          </div>
        </div>
      </section>

      {/* Run section moved up */}
      <section id="run" style={{ ...page.section }}>
        <div style={{ ...page.container, maxWidth: 720 }}>
          <h2 style={{ fontSize: 28, margin: 0 }}>Run InfoGap Pipeline</h2>
          <p style={page.muted}>Add one or more topics, select target language, then run the tool.</p>

          <div style={{ display: 'grid', gap: 16 }}>
            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, position: 'relative' }}>
                <span>Add Topic</span>
                <span
                  style={{
                    width: 16,
                    height: 16,
                    borderRadius: '50%',
                    border: '1px solid #94a3b8',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    color: '#64748b',
                    cursor: 'help'
                  }}
                  onMouseEnter={() => setShowTopicTooltip(true)}
                  onMouseLeave={() => setShowTopicTooltip(false)}
                >
                  i
                </span>
                {showTopicTooltip && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '120%',
                      left: 0,
                      background: '#0f172a',
                      color: '#f8fafc',
                      padding: '8px 10px',
                      borderRadius: 6,
                      fontSize: 12,
                      maxWidth: 280,
                      boxShadow: '0 10px 25px rgba(15,23,42,0.15)'
                    }}
                  >
                    Add an English topic title. If it has multiple words, use the exact text from the Wikipedia URL.
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <input
                    value={topicInput}
                    onChange={(e) => setTopicInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') addTopic() }}
                    placeholder="e.g., Peking duck"
                    style={{ flex: 1, padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 8 }}
                  />
                  <button onClick={addTopic} style={page.button(true)}>Add</button>
                </div>
              </label>
              {topics.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
                  {topics.map((t) => (
                    <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 10px', border: '1px solid #e5e7eb', borderRadius: 999 }}>
                      {t}
                      <button onClick={() => removeTopic(t)} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#6b7280' }}>×</button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            <label>
              Target language code
              <select
                value={lang}
                onChange={(e) => handleLangChange(e.target.value)}
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 8 }}
              >
                <option value="fr">French (fr)</option>
                <option value="ru">Russian (ru)</option>
                <option value="zh">Chinese (zh)</option>
              </select>
            </label>

            <div style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 14, background: '#f8fafc' }}>
              <label style={{ display: 'block', fontWeight: 600 }}>
                Use your OpenAI API key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #dbe2ea', borderRadius: 8, marginTop: 8, background: '#fff' }}
              />
              <div style={{ ...page.muted, fontSize: 12, marginTop: 6, lineHeight: 1.4 }}>
                Key is sent only with this request to the backend, not saved in local storage or logs. Leave blank to rely on server configuration.
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button onClick={runScraper} style={page.button(true)}>Run Scraper</button>
                <button onClick={runPipeline} style={page.button(false)}>Run Pipeline</button>
                {jobId && <button onClick={fetchLogs} style={page.button(false)}>View Logs</button>}
                {topics.length > 0 && <button onClick={downloadCsv} style={page.button(false)}>Download CSV</button>}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 12, ...page.muted }}>
            <div>Status: {status}{progress != null ? ` (${progress}%)` : ''}</div>
            {jobId && <div>Job ID: {jobId}</div>}
            {error && <div style={{ color: '#b91c1c' }}>Error: {error}</div>}
            {logPath && <div>Log: {logPath}</div>}
            {logText && (
              <pre style={{ marginTop: 8, maxHeight: 280, overflow: 'auto', background: '#0b1020', color: '#d1d5db', padding: 12, borderRadius: 8 }}>
                {logText}
              </pre>
            )}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" style={{ ...page.section }}>
        <div style={{ ...page.container, display: 'grid', gap: 16, gridTemplateColumns: 'repeat(3, 1fr)' }}>
          {[
            { title: 'Simpler Setup', desc: 'One .env file and single requirements file.' },
            { title: 'Topic-based Runs', desc: 'Generate datasets by topic with one command.' },
            { title: 'Multi-Language Ready', desc: 'Supports English, French, Russian, Chinese, and more.' }
          ].map((f) => (
            <div key={f.title} style={page.card}>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{f.title}</div>
              <div style={page.muted}>{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Quick Start */}
      <section id="setup" style={{ ...page.section }}>
        <div style={{ ...page.container, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <h2 style={{ fontSize: 28, margin: 0 }}>Run WikiGap in 3 steps</h2>
          <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(3, 1fr)' }}>
            {[
              { step: '1. Set Environment', code: 'Create .env with SCRATCH_DIR and THE_KEY' },
              { step: '2. Install Requirements', code: 'pip install -r requirements.txt' },
              { step: '3. Run', code: 'Start API server, then use the web UI' }
            ].map((s) => (
              <div key={s.step} style={page.card}>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{s.step}</div>
                <div style={page.muted}>{s.code}</div>
              </div>
            ))}
          </div>
          
        </div>
      </section>

      {/* Pipeline */}
      <section id="pipeline" style={{ ...page.section }}>
        <div style={{ ...page.container, display: 'grid', gap: 16, gridTemplateColumns: 'repeat(3, 1fr)' }}>
          {[
            { title: 'Scrape', desc: 'Pull multilingual Wikipedia bios for chosen topics.' },
            { title: 'Analyze', desc: 'LLMs evaluate cross-language factual consistency.' },
            { title: 'Export', desc: 'JSON outputs integrate into the WikiGap extension.' }
          ].map((p) => (
            <div key={p.title} style={page.card}>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{p.title}</div>
              <div style={page.muted}>{p.desc}</div>
            </div>
          ))}
        </div>
      </section>

      

      {/* Footer */}
      <footer style={{ ...page.section, borderTop: '1px solid #eee', paddingTop: 24 }}>
        <div style={{ ...page.container, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={page.muted}>© 2025 InfoGap Project</div>
          <div style={{ display: 'flex', gap: 16, fontSize: 14 }}>
            <a href="#setup">Setup</a>
            <a href="#pipeline">Pipeline</a>
            <a href="#input">Try</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
