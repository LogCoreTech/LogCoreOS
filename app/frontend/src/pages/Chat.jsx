import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { chat as chatApi } from '../lib/api'
import { useAuth } from '../lib/auth'

function StepTrace({ steps }) {
  const [expanded, setExpanded] = useState({})

  if (!steps || steps.length === 0) return null

  const toolSteps = steps.filter(s => s.type === 'tool_call' || s.type === 'thought')

  return (
    <div className="mt-2 text-xs">
      <button
        onClick={() => setExpanded(p => ({ ...p, _open: !p._open }))}
        className="flex items-center gap-1 text-charcoal-400 dark:text-charcoal-500 hover:text-orange-500 transition-colors mb-1"
      >
        <span>{expanded._open ? '▾' : '▸'}</span>
        <span>{toolSteps.filter(s => s.type === 'tool_call').length} action{toolSteps.filter(s => s.type === 'tool_call').length !== 1 ? 's' : ''} taken</span>
      </button>

      {expanded._open && (
        <div className="space-y-1.5 pl-3 border-l-2 border-charcoal-200 dark:border-charcoal-700">
          {toolSteps.map((s, i) => {
            if (s.type === 'thought') {
              return (
                <div key={i} className="bg-charcoal-50 dark:bg-charcoal-800 rounded px-2 py-1 italic text-charcoal-500 dark:text-charcoal-400">
                  ◎ {s.content}
                </div>
              )
            }

            const hasError = typeof s.output === 'object' && s.output?.error
            const isOpen = expanded[i]

            return (
              <div
                key={i}
                className={`rounded border ${hasError ? 'border-red-300 dark:border-red-800' : 'border-charcoal-200 dark:border-charcoal-700'}`}
              >
                <button
                  onClick={() => setExpanded(p => ({ ...p, [i]: !p[i] }))}
                  className="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-charcoal-50 dark:hover:bg-charcoal-800 rounded"
                >
                  <span className="font-mono text-orange-500">{s.tool}</span>
                  {hasError && <span className="text-red-500 ml-auto">error</span>}
                  <span className="ml-auto text-charcoal-400">{isOpen ? '▾' : '▸'}</span>
                </button>
                {isOpen && (
                  <div className="px-2 pb-2 space-y-1">
                    <div className="font-medium text-charcoal-400 dark:text-charcoal-500 mt-1">Input</div>
                    <pre className="bg-charcoal-50 dark:bg-charcoal-900 rounded p-1.5 overflow-x-auto text-xs">
                      {JSON.stringify(s.input, null, 2)}
                    </pre>
                    <div className="font-medium text-charcoal-400 dark:text-charcoal-500">Output</div>
                    <pre className={`rounded p-1.5 overflow-x-auto text-xs ${hasError ? 'bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300' : 'bg-charcoal-50 dark:bg-charcoal-900'}`}>
                      {JSON.stringify(s.output, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Chat() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Hi ${user?.name?.split(' ')[0] || 'there'}! I know your priorities and tasks. What's on your mind?`,
      steps: [],
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveTarget, setSaveTarget] = useState('short')
  const [saveResult, setSaveResult] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Dismiss save result after 4 seconds
  useEffect(() => {
    if (!saveResult) return
    const t = setTimeout(() => setSaveResult(null), 4000)
    return () => clearTimeout(t)
  }, [saveResult])

  async function send(e) {
    e?.preventDefault()
    const msg = input.trim()
    if (!msg || loading) return

    const userMsg = { role: 'user', content: msg, steps: [] }
    const updated = [...messages, userMsg]
    setMessages(updated)
    setInput('')
    setLoading(true)

    try {
      const history = updated.slice(1, -1).map(m => ({ role: m.role, content: m.content }))
      const res = await chatApi.send(msg, history)
      setMessages([...updated, {
        role: 'assistant',
        content: res.response,
        steps: res.steps || [],
      }])
    } catch (err) {
      setMessages([...updated, { role: 'assistant', content: `Error: ${err.message}`, steps: [] }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  async function saveToMemory() {
    if (saving) return
    // Build history excluding the greeting
    const history = messages.slice(1).map(m => ({ role: m.role, content: m.content }))
    if (history.length === 0) return
    setSaving(true)
    setSaveResult(null)
    try {
      const res = await chatApi.saveMemory(history, saveTarget)
      setSaveResult({ ok: true, target: res.target })
    } catch (err) {
      setSaveResult({ ok: false, error: err.message })
    } finally {
      setSaving(false)
    }
  }

  const hasConversation = messages.length > 1

  return (
    <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-3rem)]">
      <div className="flex items-center justify-between mb-4 shrink-0">
        <h1 className="text-2xl font-bold">AI Chat</h1>
        {hasConversation && (
          <div className="flex items-center gap-2">
            <select
              value={saveTarget}
              onChange={e => setSaveTarget(e.target.value)}
              className="text-xs border border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800 rounded-lg px-2 py-1"
              disabled={saving}
            >
              <option value="short">Short-term</option>
              <option value="long">Long-term</option>
            </select>
            <button
              onClick={saveToMemory}
              disabled={saving}
              className="btn-ghost text-xs px-3 py-1.5 disabled:opacity-50"
              title="Extract key insights from this conversation and save to memory"
            >
              {saving ? 'Saving…' : '🧠 Save to Memory'}
            </button>
          </div>
        )}
      </div>

      {saveResult && (
        <div className={`shrink-0 mb-3 px-3 py-2 rounded-lg text-sm ${
          saveResult.ok
            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
            : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
        }`}>
          {saveResult.ok
            ? `Saved to ${saveResult.target}`
            : `Save failed: ${saveResult.error}`}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {m.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-orange-500 flex items-center justify-center text-white text-xs font-bold shrink-0 mr-2 mt-1">
                L
              </div>
            )}
            <div className="max-w-[85%]">
              <div
                className={`px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                  m.role === 'user'
                    ? 'bg-orange-500 text-white rounded-br-sm'
                    : 'card rounded-bl-sm text-charcoal-900 dark:text-gray-100'
                }`}
              >
                {m.content}
              </div>
              {m.role === 'assistant' && <StepTrace steps={m.steps} />}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="w-7 h-7 rounded-full bg-orange-500 flex items-center justify-center text-white text-xs font-bold shrink-0 mr-2 mt-1">L</div>
            <div className="card px-4 py-3 rounded-bl-sm">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-charcoal-400 rounded-full animate-bounce" style={{animationDelay:'0ms'}} />
                <div className="w-2 h-2 bg-charcoal-400 rounded-full animate-bounce" style={{animationDelay:'150ms'}} />
                <div className="w-2 h-2 bg-charcoal-400 rounded-full animate-bounce" style={{animationDelay:'300ms'}} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Memory shortcuts */}
      <div className="flex gap-2 shrink-0 pt-2 pb-1">
        <button
          type="button"
          onClick={() => navigate('/brain?file=Short_Term_Memory.md', { state: { from: '/chat' } })}
          className="btn-ghost text-xs px-2 py-1"
        >
          Short-term memory
        </button>
        <button
          type="button"
          onClick={() => navigate('/brain?file=Long_Term_Memory.md', { state: { from: '/chat' } })}
          className="btn-ghost text-xs px-2 py-1"
        >
          Long-term memory
        </button>
      </div>

      {/* Input */}
      <form onSubmit={send} className="flex gap-2 shrink-0 pt-2 border-t border-charcoal-200 dark:border-charcoal-700">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask about your priorities, tasks, goals…"
          className="input flex-1"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="btn-primary px-4 disabled:opacity-50"
        >
          →
        </button>
      </form>
    </div>
  )
}
