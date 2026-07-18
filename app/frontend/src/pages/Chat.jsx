import { useState, useRef, useEffect } from 'react'
import HelpButton from '../components/HelpButton'
import { useNavigate } from 'react-router-dom'
import { chat as chatApi, suggestions as sugApi, brain as brainApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'

function ProposalCard({ step, onConfirm, onCancel }) {
  const { summary, actions } = step.output || {}
  return (
    <div className="mt-3 border border-orange-300 dark:border-orange-700 rounded-xl p-4 bg-orange-50 dark:bg-orange-950/30">
      <p className="text-xs font-semibold text-orange-600 dark:text-orange-400 mb-1 uppercase tracking-wide">Proposed plan</p>
      <p className="text-sm text-charcoal-800 dark:text-charcoal-100 mb-3">{summary}</p>
      {actions?.length > 0 && (
        <ul className="text-xs text-charcoal-600 dark:text-charcoal-300 space-y-1 mb-4">
          {actions.map((a, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-orange-400 shrink-0">·</span>
              <span>{a}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <button onClick={onConfirm} className="btn-primary text-xs px-3 py-1.5">Confirm</button>
        <button onClick={onCancel} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
      </div>
    </div>
  )
}

function ApprovalCard({ steps, onApprove, onDeny }) {
  return (
    <div className="mt-3 border border-orange-300 dark:border-orange-700 rounded-xl p-4 bg-orange-50 dark:bg-orange-950/30">
      <p className="text-xs font-semibold text-orange-600 dark:text-orange-400 mb-2 uppercase tracking-wide">Waiting for your approval</p>
      <ul className="text-xs text-charcoal-600 dark:text-charcoal-300 space-y-1.5 mb-4">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-orange-400 shrink-0">·</span>
            <span className="min-w-0 break-words">
              <span className="font-semibold">{s.tool.replaceAll('_', ' ')}</span>
              {s.input && Object.keys(s.input).length > 0 && (
                <span className="opacity-80"> — {Object.entries(s.input).map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`).join(', ')}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <button onClick={onApprove} className="btn-primary text-xs px-3 py-1.5">Approve</button>
        <button onClick={onDeny} className="btn-ghost text-xs px-3 py-1.5">Deny</button>
      </div>
    </div>
  )
}

// Shape thread state into a history the /chat validator accepts: no injected
// proactive notifications, must start with a user message and end with an
// assistant one (older archives can carry leading notification messages).
function toApiHistory(msgs) {
  const h = msgs.filter(m => !m._proactive).map(m => ({ role: m.role, content: m.content }))
  while (h.length && h[0].role !== 'user') h.shift()
  while (h.length && h[h.length - 1].role !== 'assistant') h.pop()
  return h
}

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
  const { workspace } = useWorkspace()
  const hasBothWorkspaces = (user?.workspaces?.length ?? 0) > 1
  const navigate = useNavigate()
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Hi, ${user?.name?.split(' ')[0] || 'there'}, what can I help you with today?`,
      steps: [],
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [continuedFromFile, setContinuedFromFile] = useState(null) // { filename, title }
  const [chatMode, setChatMode] = useState('approve')
  const [crossWorkspace, setCrossWorkspace] = useState(false)
  const [showModeDrawer, setShowModeDrawer] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [savedChats, setSavedChats] = useState([])
  const [selectedChat, setSelectedChat] = useState(null) // { filename, content }
  const [historyLoading, setHistoryLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const modeRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Inject unread chat-delivery notifications as AI messages on mount
  useEffect(() => {
    sugApi.chatNotifications().then(notifs => {
      if (!Array.isArray(notifs)) return
      const unread = notifs.filter(n => !n.read && n.delivery === 'chat')
      if (unread.length === 0) return
      const injected = unread.map(n => ({
        role: 'assistant',
        content: `**${n.title}**\n\n${n.body}`,
        steps: [],
        _proactive: true,
      }))
      setMessages(prev => [prev[0], ...injected, ...prev.slice(1)])
      unread.forEach(n => sugApi.markRead(n.id).catch(() => {}))
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Close mode drawer when clicking outside
  useEffect(() => {
    if (!showModeDrawer) return
    function handler(e) {
      if (modeRef.current && !modeRef.current.contains(e.target)) setShowModeDrawer(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showModeDrawer])

  // When workspace changes, reload saved chats list (if panel open) and clear cross-workspace toggle
  useEffect(() => {
    setCrossWorkspace(false)
    setContinuedFromFile(null)
    if (showHistory) {
      chatApi.listSaved().then(list => setSavedChats(list || [])).catch(() => setSavedChats([]))
    }
  }, [workspace])

  // Auto-save after each AI response. Injected proactive notifications are
  // display-only: they stay out of archives, and a thread that contains nothing
  // else must not be saved at all.
  useEffect(() => {
    if (loading) return
    const history = messages
      .slice(1)
      .filter(m => !m._proactive)
      .map(m => ({ role: m.role, content: m.content }))
    if (history.length === 0) return
    const t = setTimeout(async () => {
      const firstUser = history.find(m => m.role === 'user')
      const autoTitle = firstUser
        ? firstUser.content.slice(0, 60) + (firstUser.content.length > 60 ? '…' : '')
        : 'Chat'
      try {
        const res = await chatApi.saveChat(
          history,
          continuedFromFile?.title || autoTitle,
          continuedFromFile?.filename || ''
        )
        if (!continuedFromFile) {
          setContinuedFromFile({ filename: res.filename, title: res.title })
        }
      } catch { /* silent — auto-save failures don't interrupt the user */ }
    }, 1500)
    return () => clearTimeout(t)
  }, [messages, loading])

  async function send(e, overrideMsg, modeOverride) {
    e?.preventDefault()
    const msg = overrideMsg ?? input.trim()
    if (!msg || loading) return

    const userMsg = { role: 'user', content: msg, steps: [] }
    const updated = [...messages, userMsg]
    setMessages(updated)
    if (!overrideMsg) setInput('')
    setLoading(true)

    try {
      const history = toApiHistory(updated.slice(1, -1))
      const res = await chatApi.send(msg, history, modeOverride || chatMode, crossWorkspace)
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

  function newChat() {
    setMessages([{
      role: 'assistant',
      content: `Hi, ${user?.name?.split(' ')[0] || 'there'}, what can I help you with today?`,
      steps: [],
    }])
    setContinuedFromFile(null)
    setInput('')
  }

  // Multi-line messages: only the first line carries the **You**:/**AI**: marker,
  // so continuation lines must be accumulated — dropping them here truncates the
  // archive on the next auto-save overwrite.
  function parseSavedChat(content) {
    const parsed = []
    let current = null
    for (const line of content.split('\n')) {
      if (line.startsWith('**You**:')) {
        current = { role: 'user', content: line.slice(8).trimStart(), steps: [] }
        parsed.push(current)
      } else if (line.startsWith('**AI**:')) {
        current = { role: 'assistant', content: line.slice(7).trimStart(), steps: [] }
        parsed.push(current)
      } else if (current) {
        current.content += '\n' + line
      }
    }
    for (const m of parsed) m.content = m.content.trim()
    return parsed
  }

  function continueChat(content, filename, title) {
    const parsed = parseSavedChat(content)
    if (parsed.length === 0) return
    setMessages([messages[0], ...parsed])
    setContinuedFromFile({ filename, title })
    setShowHistory(false)
    setSelectedChat(null)
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }

  async function deleteSavedChat(chat, e) {
    e.stopPropagation()
    try {
      await chatApi.deleteSaved(chat.filename)
      setSavedChats(prev => prev.filter(c => c.filename !== chat.filename))
    } catch (err) {
      alert(err.message || 'Failed to delete chat')
    }
  }

  async function openHistory() {
    setShowHistory(true)
    setSelectedChat(null)
    setHistoryLoading(true)
    try {
      const list = await chatApi.listSaved()
      setSavedChats(list || [])
    } catch (err) {
      setSavedChats([])
      setSelectedChat({ filename: '', title: 'Error', content: err.message || 'Failed to load chat history.' })
    } finally {
      setHistoryLoading(false)
    }
  }

  async function openSavedChat(chat) {
    setHistoryLoading(true)
    try {
      const file = await brainApi.getFile(chat.path)
      setSelectedChat({ filename: chat.filename, title: chat.title, content: file.content })
    } catch { setSelectedChat({ filename: chat.filename, title: chat.title, content: 'Failed to load chat.' }) }
    finally { setHistoryLoading(false) }
  }

  function fmtFilename(filename) {
    // "2026-06-21_14-30-00.md" → "Jun 21, 2026 · 2:30 PM"
    try {
      const [datePart, timePart] = filename.replace('.md', '').split('_')
      const [y, mo, d] = datePart.split('-')
      const [h, m] = timePart.split('-')
      const dt = new Date(+y, +mo - 1, +d, +h, +m)
      return dt.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
    } catch { return filename }
  }

  const hasConversation = messages.length > 1

  return (
    <div className="max-w-2xl mx-auto w-full flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-between mb-4 shrink-0">
        <span className="flex items-center gap-2"><h1 className="text-2xl font-bold">AI Chat</h1><HelpButton section="chat" /></span>
        <div className="flex items-center gap-2">
          <button
            onClick={newChat}
            className="btn-ghost text-xs px-3 py-1.5"
            title="Start a new conversation"
          >
            + New Chat
          </button>
          <button
            onClick={openHistory}
            className="btn-ghost text-xs px-3 py-1.5"
            title="Browse saved chats"
          >
            🗂 Chats
          </button>
        </div>
      </div>


      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-4 pb-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {m.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-orange-500 flex items-center justify-center text-white text-xs font-bold shrink-0 mr-2 mt-1">
                L
              </div>
            )}
            <div className="max-w-[85%]">
              {m._proactive && (
                <p className="text-[10px] text-orange-400 font-semibold mb-1 ml-1 uppercase tracking-wide">Proactive</p>
              )}
              <div
                className={`px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                  m.role === 'user'
                    ? 'bg-orange-500 text-white rounded-br-sm'
                    : 'card rounded-bl-sm text-charcoal-900 dark:text-gray-100'
                }`}
              >
                {m.content}
              </div>
              {m.role === 'assistant' && (() => {
                const proposalStep = m.steps?.find(s => s.type === 'tool_call' && s.tool === 'propose_plan')
                const pendingWrites = m.steps?.filter(s => s.type === 'pending_write') || []
                const isLastMsg = i === messages.length - 1
                return (
                  <>
                    <StepTrace steps={m.steps} />
                    {proposalStep && isLastMsg && !loading && (
                      <ProposalCard
                        step={proposalStep}
                        onConfirm={() => send(null, 'Yes, go ahead.')}
                        onCancel={() => send(null, "Cancel that, don't make any changes.")}
                      />
                    )}
                    {pendingWrites.length > 0 && isLastMsg && !loading && (
                      <ApprovalCard
                        steps={pendingWrites}
                        onApprove={() => send(null, 'Yes, go ahead.', 'auto')}
                        onDeny={() => send(null, "No — don't make those changes.")}
                      />
                    )}
                  </>
                )
              })()}
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

      {/* Memory shortcuts + mode selector */}
      <div className="flex items-center gap-2 shrink-0 pt-2 pb-1">
        {/* Mode drawer — fixed width so the row never reflows between modes */}
        <div className="relative" ref={modeRef}>
          <button
            type="button"
            onClick={() => setShowModeDrawer(o => !o)}
            className="btn-ghost text-xs px-2 py-1 flex items-center justify-between gap-1 w-[112px]"
            title="Switch chat mode"
          >
            <span>{chatMode === 'approve' ? '✓ Approve' : chatMode === 'plan' ? '📋 Plan' : chatMode === 'auto' ? '⚡ Auto' : '🔍 Research'}</span>
            <span className="text-[10px] opacity-60">▾</span>
          </button>
          {showModeDrawer && (
            <div className="absolute bottom-full mb-1 left-0 bg-white dark:bg-charcoal-900 border border-charcoal-200 dark:border-charcoal-700 rounded-xl shadow-lg z-50 overflow-hidden min-w-[150px]">
              {[
                { id: 'approve',  label: '✓ Approve',   title: 'AI asks before each change' },
                { id: 'plan',     label: '📋 Plan',      title: 'AI proposes before acting' },
                { id: 'auto',     label: '⚡ Auto',     title: 'AI executes without asking' },
                { id: 'research', label: '🔍 Research',  title: 'Read-only analysis and web search' },
              ].map(m => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => { setChatMode(m.id); setShowModeDrawer(false) }}
                  title={m.title}
                  className={`w-full text-left text-xs px-3 py-2 transition-colors ${
                    chatMode === m.id
                      ? 'bg-orange-500 text-white'
                      : 'text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-50 dark:hover:bg-charcoal-800'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Icon memory controls — fixed-size, tooltip on hover */}
        {hasBothWorkspaces && (
          <button
            type="button"
            onClick={() => setCrossWorkspace(x => !x)}
            title={crossWorkspace
              ? 'Brain scope: Both workspaces — click to limit to the current one'
              : `Brain scope: ${workspace === 'business' ? 'Business' : 'Personal'} only — click to include both`}
            aria-label="Toggle Brain scope"
            className={`w-8 h-8 flex items-center justify-center rounded border transition-colors ${
              crossWorkspace
                ? 'bg-blue-500 border-blue-500 text-white'
                : 'btn-ghost border-transparent'
            }`}
          >
            🧠
          </button>
        )}
        <button
          type="button"
          onClick={() => navigate('/brain?file=Short_Term_Memory.md', { state: { from: '/chat' } })}
          className="btn-ghost w-8 h-8 flex items-center justify-center"
          title="Short-term memory"
          aria-label="Short-term memory"
        >
          ⏳
        </button>
        <button
          type="button"
          onClick={() => navigate('/brain?file=Long_Term_Memory.md', { state: { from: '/chat' } })}
          className="btn-ghost w-8 h-8 flex items-center justify-center"
          title="Long-term memory"
          aria-label="Long-term memory"
        >
          📚
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

      {/* Saved chats drawer */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-black/40" onClick={() => { setShowHistory(false); setSelectedChat(null) }} />
          <div className="w-80 md:w-96 h-full bg-white dark:bg-charcoal-900 border-l border-charcoal-200 dark:border-charcoal-700 flex flex-col shadow-xl">

            {/* Drawer header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-charcoal-200 dark:border-charcoal-700 shrink-0">
              {selectedChat ? (
                <button
                  onClick={() => setSelectedChat(null)}
                  className="flex items-center gap-1 text-sm font-medium text-charcoal-500 hover:text-orange-500 transition-colors"
                >
                  ← Back
                </button>
              ) : (
                <h3 className="text-sm font-semibold">Saved Chats</h3>
              )}
              <button
                onClick={() => { setShowHistory(false); setSelectedChat(null) }}
                className="text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 text-lg leading-none"
              >
                ✕
              </button>
            </div>

            {/* Drawer body */}
            <div className="flex-1 min-h-0 overflow-y-auto">
              {historyLoading ? (
                <div className="flex items-center justify-center h-24">
                  <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : selectedChat ? (
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-charcoal-400 dark:text-charcoal-500 font-mono">{selectedChat.filename}</p>
                    <button
                      onClick={() => continueChat(selectedChat.content, selectedChat.filename, selectedChat.title)}
                      className="btn-primary text-xs px-3 py-1.5"
                    >
                      Continue →
                    </button>
                  </div>
                  {(() => {
                    const titleLine = selectedChat.content.split('\n').find(l => l.startsWith('# '))
                    return titleLine ? (
                      <p className="text-sm font-semibold text-charcoal-700 dark:text-charcoal-200">{titleLine.slice(2)}</p>
                    ) : null
                  })()}
                  {parseSavedChat(selectedChat.content).map((m, i) => (
                    <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div
                        className={`text-sm px-3 py-2 rounded-2xl max-w-[85%] whitespace-pre-wrap ${
                          m.role === 'user'
                            ? 'bg-orange-500 text-white rounded-br-sm'
                            : 'card rounded-bl-sm text-charcoal-800 dark:text-charcoal-100'
                        }`}
                      >
                        {m.content}
                      </div>
                    </div>
                  ))}
                </div>
              ) : savedChats.length === 0 ? (
                <p className="text-sm text-charcoal-400 dark:text-charcoal-500 text-center py-10">No saved chats yet.</p>
              ) : (
                <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800">
                  {savedChats.map(chat => (
                    <div
                      key={chat.filename}
                      className="flex items-center gap-2 px-4 py-3 hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors group"
                    >
                      <button
                        onClick={() => openSavedChat(chat)}
                        className="flex-1 text-left min-w-0"
                      >
                        <p className="text-sm font-medium text-charcoal-800 dark:text-charcoal-100 truncate">{chat.title || fmtFilename(chat.filename)}</p>
                        <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-0.5">{fmtFilename(chat.filename)}</p>
                      </button>
                      <button
                        onClick={e => deleteSavedChat(chat, e)}
                        className="shrink-0 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-charcoal-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                        title="Delete chat"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </div>
      )}
    </div>
  )
}
