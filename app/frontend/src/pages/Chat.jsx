import { useState, useRef, useEffect } from 'react'
import HelpButton from '../components/HelpButton'
import { useNavigate } from 'react-router-dom'
import { chat as chatApi, suggestions as sugApi, brain as brainApi, aiUsage as aiUsageApi, dashboards as dashboardsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import DashboardGrid from '../components/dashboard/DashboardGrid'
import { BLOCK_REGISTRY } from '../components/dashboard/blockRegistry'

const _DASHBOARD_PREVIEW_TOOLS = new Set(['add_dashboard_block', 'update_dashboard_block'])

// Dependency-free markdown rendering (2026-08-10) — no npm registry access in
// this environment, so this hand-rolls just the subset the agent's replies
// actually use rather than pulling in a library. Real React elements only,
// never dangerouslySetInnerHTML.
const _INLINE_PATTERNS = [
  { type: 'code', re: /`([^`]+)`/ },
  { type: 'link', re: /\[([^\]]+)\]\(([^)\s]+)\)/ },
  { type: 'bold', re: /\*\*([^*]+)\*\*/ },
  { type: 'italic', re: /\*([^*]+)\*/ },
]

function renderInline(text, keyPrefix) {
  const out = []
  let remaining = text
  let key = 0
  while (remaining.length > 0) {
    let best = null
    for (const pattern of _INLINE_PATTERNS) {
      const m = pattern.re.exec(remaining)
      if (m && (!best || m.index < best.match.index)) best = { pattern, match: m }
    }
    if (!best) { out.push(remaining); break }
    const { pattern, match } = best
    if (match.index > 0) out.push(remaining.slice(0, match.index))
    const k = `${keyPrefix}-${key++}`
    if (pattern.type === 'code') {
      out.push(<code key={k} className="px-1 py-0.5 rounded bg-charcoal-100 dark:bg-charcoal-800 text-[0.85em] font-mono">{match[1]}</code>)
    } else if (pattern.type === 'link') {
      const external = /^https?:\/\//i.test(match[2])
      out.push(
        <a key={k} href={match[2]} className="text-orange-500 hover:underline" {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
          {match[1]}
        </a>
      )
    } else if (pattern.type === 'bold') {
      out.push(<strong key={k} className="font-semibold">{match[1]}</strong>)
    } else {
      out.push(<em key={k}>{match[1]}</em>)
    }
    remaining = remaining.slice(match.index + match[0].length)
  }
  return out
}

// Line-by-line block parser: headings, fenced code, bullet/numbered lists,
// plain paragraphs. Deliberately not CommonMark-complete — covers what the
// agent's own replies actually use.
function Markdown({ text }) {
  const lines = text.split('\n')
  const blocks = []
  let list = null // { ordered, items }

  function flushList() {
    if (!list) return
    const Tag = list.ordered ? 'ol' : 'ul'
    const cls = list.ordered ? 'list-decimal pl-5 space-y-0.5' : 'list-disc pl-5 space-y-0.5'
    blocks.push(
      <Tag key={`b${blocks.length}`} className={cls}>
        {list.items.map((item, idx) => <li key={idx}>{renderInline(item, `b${blocks.length}-${idx}`)}</li>)}
      </Tag>
    )
    list = null
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i]

    if (line.trim().startsWith('```')) {
      flushList()
      const codeLines = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) { codeLines.push(lines[i]); i++ }
      i++
      blocks.push(
        <pre key={`b${blocks.length}`} className="bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-2.5 my-1 overflow-x-auto text-xs">
          <code className="font-mono">{codeLines.join('\n')}</code>
        </pre>
      )
      continue
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line)
    if (heading) {
      flushList()
      const level = heading[1].length
      const HTag = level === 1 ? 'h3' : level === 2 ? 'h4' : 'h5'
      const size = level === 1 ? 'text-base font-bold' : level === 2 ? 'text-sm font-bold' : 'text-sm font-semibold'
      blocks.push(<HTag key={`b${blocks.length}`} className={`${size} mt-1.5 mb-0.5`}>{renderInline(heading[2], `b${blocks.length}`)}</HTag>)
      i++
      continue
    }

    const bullet = /^\s*[-*]\s+(.*)$/.exec(line)
    if (bullet) {
      if (!list || list.ordered) { flushList(); list = { ordered: false, items: [] } }
      list.items.push(bullet[1])
      i++
      continue
    }

    const numbered = /^\s*\d+\.\s+(.*)$/.exec(line)
    if (numbered) {
      if (!list || !list.ordered) { flushList(); list = { ordered: true, items: [] } }
      list.items.push(numbered[1])
      i++
      continue
    }

    flushList()
    if (line.trim() === '') { i++; continue }
    blocks.push(<p key={`b${blocks.length}`}>{renderInline(line, `b${blocks.length}`)}</p>)
    i++
  }
  flushList()

  return <div className="space-y-1">{blocks}</div>
}

// Rich preview for a pending Dashboard-tool approval (2026-08-09) — reuses the
// real DashboardGrid/BlockRenderer rendering path in read-only mode instead of
// ApprovalCard's plain tool/input bullet list, scoped to the two tools where
// there's an existing dashboard to show. create_dashboard has no prior state
// to preview against, so it falls back to ApprovalCard alone.
function DashboardBlockPreview({ step }) {
  const [rendered, setRendered] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setRendered(null)
    setFailed(false)
    dashboardsApi.render(step.input.dashboard_id)
      .then(r => { if (!cancelled) setRendered(r) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [step.input.dashboard_id])

  if (failed || !rendered) return null

  function nextRow(blocks, bp) {
    return blocks.reduce((max, b) => {
      const l = b.layout?.[bp]
      if (!l) return max
      return Math.max(max, (Number(l.y) || 0) + (Number(l.h) || 0))
    }, 0)
  }

  let previewBlocks
  if (step.tool === 'add_dashboard_block') {
    const meta = BLOCK_REGISTRY[step.input.type]
    const w = meta?.defaultLayout?.w || 12
    const h = meta?.defaultLayout?.h || 9
    const pending = {
      id: '__pending__',
      type: step.input.type,
      config: step.input.config || {},
      ok: false,
      locked_reason: 'pending_approval',
      layout: {
        lg: { x: 0, y: nextRow(rendered.blocks, 'lg'), w, h },
        sm: { x: 0, y: nextRow(rendered.blocks, 'sm'), w: 12, h },
      },
    }
    previewBlocks = [...rendered.blocks, pending]
  } else if (step.tool === 'update_dashboard_block') {
    if (!rendered.blocks.some(b => b.id === step.input.block_id)) return null
    previewBlocks = rendered.blocks.map(b =>
      b.id === step.input.block_id
        ? { ...b, config: step.input.config || {}, ok: false, locked_reason: 'pending_approval' }
        : b
    )
  } else {
    return null
  }

  return (
    <div className="chat-fade-in mt-3 border border-charcoal-300 dark:border-charcoal-600 rounded-xl p-3 bg-charcoal-50 dark:bg-charcoal-800/50">
      <p className="text-xs font-semibold text-charcoal-500 dark:text-charcoal-400 mb-2 uppercase tracking-wide">👁 Preview</p>
      {/* editing=true so BlockRenderer shows icon+label headers (view mode hides
          them entirely); pointer-events-none makes the real drag/resize
          wiring inert since this is a read-only preview, not an editor. */}
      <div className="pointer-events-none">
        <DashboardGrid
          blocks={previewBlocks}
          editing={true}
          blocksLocked={true}
          onRemoveBlock={() => {}}
          onEditBlock={() => {}}
          onBlockAction={() => {}}
          onLayoutChange={() => {}}
        />
      </div>
    </div>
  )
}

function ProposalCard({ step, onConfirm, onCancel }) {
  const { summary, actions } = step
  return (
    <div className="chat-fade-in mt-3 border border-orange-300 dark:border-orange-700 rounded-xl p-4 bg-orange-50 dark:bg-orange-950/30">
      <p className="text-xs font-semibold text-orange-600 dark:text-orange-400 mb-1 uppercase tracking-wide">📋 Proposed plan</p>
      <p className="text-sm text-charcoal-800 dark:text-charcoal-100 mb-3">{renderInline(summary, 'proposal-summary')}</p>
      {actions?.length > 0 && (
        <ul className="text-xs text-charcoal-600 dark:text-charcoal-300 space-y-1 mb-4">
          {actions.map((a, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-orange-400 shrink-0">·</span>
              <span>{renderInline(a, `proposal-action-${i}`)}</span>
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
    <div className="chat-fade-in mt-3 border border-orange-300 dark:border-orange-700 rounded-xl p-4 bg-orange-50 dark:bg-orange-950/30">
      <p className="text-xs font-semibold text-orange-600 dark:text-orange-400 mb-2 uppercase tracking-wide">⚠ Waiting for your approval</p>
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

function AskUserQuestionCard({ step, onSubmit }) {
  const [selected, setSelected] = useState(step.multi_select ? [] : null)
  const options = step.options || []

  function toggle(label) {
    if (step.multi_select) {
      setSelected(prev => prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label])
    } else {
      setSelected(label)
    }
  }

  function submit() {
    const answer = step.multi_select ? selected : (selected ? [selected] : [])
    if (answer.length === 0) return
    onSubmit(answer)
  }

  const hasSelection = step.multi_select ? selected.length > 0 : !!selected

  return (
    <div className="chat-fade-in mt-3 border border-blue-300 dark:border-blue-700 rounded-xl p-4 bg-blue-50 dark:bg-blue-950/30">
      <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-1 uppercase tracking-wide">💬 {step.header || 'Question'}</p>
      <p className="text-sm text-charcoal-800 dark:text-charcoal-100 mb-3">{step.question}</p>
      <div className="space-y-1.5 mb-4">
        {options.map((o, i) => {
          const isChecked = step.multi_select ? selected.includes(o.label) : selected === o.label
          return (
            <label key={i} className="flex items-start gap-2 text-sm cursor-pointer">
              <input
                type={step.multi_select ? 'checkbox' : 'radio'}
                name={`ask-user-question-${step.step}`}
                checked={isChecked}
                onChange={() => toggle(o.label)}
                className="mt-0.5 shrink-0 accent-blue-500"
              />
              <span className="min-w-0">
                <span className="font-semibold">{o.label}</span>
                {o.description && <span className="text-charcoal-500 dark:text-charcoal-400"> — {o.description}</span>}
              </span>
            </label>
          )
        })}
      </div>
      <button
        onClick={submit}
        disabled={!hasSelection}
        className="bg-blue-500 hover:bg-blue-600 text-white font-medium px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
        style={{ borderRadius: 'calc(var(--card-radius) * 0.6)' }}
      >
        Submit
      </button>
    </div>
  )
}

function UsageConfirmCard({ onContinue, onCancel }) {
  return (
    <div className="chat-fade-in mt-3 border border-red-300 dark:border-red-700 rounded-xl p-4 bg-red-50 dark:bg-red-950/30">
      <p className="text-xs font-semibold text-red-600 dark:text-red-400 mb-2 uppercase tracking-wide">
        AI usage limit reached
      </p>
      <div className="flex gap-2">
        <button onClick={onContinue} className="btn-primary text-xs px-3 py-1.5">Continue anyway</button>
        <button onClick={onCancel} className="btn-ghost text-xs px-3 py-1.5">Never mind</button>
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
  const [showMemoryPopup, setShowMemoryPopup] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [savedChats, setSavedChats] = useState([])
  const [selectedChat, setSelectedChat] = useState(null) // { filename, content }
  const [historyLoading, setHistoryLoading] = useState(false)
  const [usage, setUsage] = useState(null) // { mode, pct } — null until loaded
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const modeRef = useRef(null)
  const memoryRef = useRef(null)

  function refreshUsage() {
    aiUsageApi.me().then(setUsage).catch(() => {})
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-grow the composer textarea with content, capped so it can't swallow
  // the whole screen; collapses back to one line once `input` is cleared.
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [input])

  useEffect(refreshUsage, [workspace])

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

  // Close memory popup when clicking outside
  useEffect(() => {
    if (!showMemoryPopup) return
    function handler(e) {
      if (memoryRef.current && !memoryRef.current.contains(e.target)) setShowMemoryPopup(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMemoryPopup])

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

  async function send(e, overrideMsg, modeOverride, acceptOverage) {
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
      const res = await chatApi.send(msg, history, modeOverride || chatMode, crossWorkspace, acceptOverage)
      setMessages([...updated, {
        role: 'assistant',
        content: res.response,
        steps: res.steps || [],
        mode: res.mode,
        runId: res.run_id,
        triggerMsg: msg,
      }])
      refreshUsage()
    } catch (err) {
      setMessages([...updated, { role: 'assistant', content: `Error: ${err.message}`, steps: [] }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  // Enter submits (matches the old single-line input's behavior); Shift+Enter
  // inserts a real newline instead, now that this is a multi-line textarea.
  function handleComposerKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(e)
    }
  }

  // Approve/Decline a paused write, or answer a paused clarifying question:
  // replays/answers the exact paused turn server-side instead of sending
  // synthetic chat text for the model to re-guess from.
  async function sendResume(runId, decision, answer) {
    if (loading) return
    setLoading(true)
    try {
      // The pending turn (the message carrying the pending_write/pending_question/
      // pending_plan step) IS this same assistant turn, not a separate one —
      // replace it in place rather than appending. Appending left two consecutive
      // assistant messages, which breaks the strict user/assistant alternation
      // ChatRequest.history requires: the very next send (resume or otherwise)
      // failed 422 ("unexpected role 'assistant'") and every send after that did
      // too, since the broken pair never leaves local state on its own.
      const history = toApiHistory(messages.slice(1, -1))
      const res = await chatApi.resume(runId, decision, history, crossWorkspace, answer)
      setMessages(prev => [...prev.slice(0, -1), {
        role: 'assistant',
        content: res.response,
        steps: res.steps || [],
        mode: res.mode,
        runId: res.run_id,
      }])
      refreshUsage()
    } catch (err) {
      setMessages(prev => [...prev.slice(0, -1), { role: 'assistant', content: `Error: ${err.message}`, steps: [] }])
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
          <div key={i} className={`chat-fade-in flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
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
                {m.role === 'assistant' ? <Markdown text={m.content} /> : m.content}
              </div>
              {m.role === 'assistant' && (() => {
                const proposalStep = m.steps?.find(s => s.type === 'pending_plan')
                const pendingWrites = m.steps?.filter(s => s.type === 'pending_write') || []
                const pendingQuestion = m.steps?.find(s => s.type === 'pending_question')
                const isLastMsg = i === messages.length - 1
                return (
                  <>
                    <StepTrace steps={m.steps} />
                    {proposalStep && isLastMsg && !loading && (
                      <ProposalCard
                        step={proposalStep}
                        onConfirm={() => sendResume(m.runId, 'approve')}
                        onCancel={() => sendResume(m.runId, 'decline')}
                      />
                    )}
                    {pendingWrites.length > 0 && isLastMsg && !loading && (
                      <>
                        {(() => {
                          const previewStep = pendingWrites.find(s => _DASHBOARD_PREVIEW_TOOLS.has(s.tool))
                          return previewStep ? <DashboardBlockPreview step={previewStep} /> : null
                        })()}
                        <ApprovalCard
                          steps={pendingWrites}
                          onApprove={() => sendResume(m.runId, 'approve')}
                          onDeny={() => sendResume(m.runId, 'decline')}
                        />
                      </>
                    )}
                    {pendingQuestion && isLastMsg && !loading && (
                      <AskUserQuestionCard
                        step={pendingQuestion}
                        onSubmit={(answer) => sendResume(m.runId, undefined, answer)}
                      />
                    )}
                    {m.mode === 'usage_confirm_required' && isLastMsg && !loading && (
                      <UsageConfirmCard
                        onContinue={() => send(null, m.triggerMsg, chatMode, true)}
                        onCancel={() => setMessages(msgs => msgs.map((mm, idx) =>
                          idx === i ? { ...mm, mode: undefined } : mm
                        ))}
                      />
                    )}
                  </>
                )
              })()}
            </div>
          </div>
        ))}
        {loading && (
          <div className="chat-fade-in flex justify-start">
            <div className="w-7 h-7 rounded-full bg-orange-500 flex items-center justify-center text-white text-xs font-bold shrink-0 mr-2 mt-1">L</div>
            <div className="card px-4 py-2.5 rounded-bl-sm">
              <span className="chat-thinking text-sm font-medium">Thinking…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Composer — bordered toolbar (mode/usage/memory) + auto-growing input, boxed together */}
      <div className="shrink-0 pt-2">
        <div className="border border-charcoal-200 dark:border-charcoal-700 rounded-2xl bg-white dark:bg-charcoal-900 p-2 space-y-1.5">
          {/* Toolbar strip */}
          <div className="flex items-center gap-2">
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
                <div className="absolute bottom-full mb-1 left-0 w-72 bg-white dark:bg-charcoal-900 border border-charcoal-200 dark:border-charcoal-700 rounded-xl shadow-lg z-50 overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-charcoal-100 dark:border-charcoal-800">
                    <span className="text-xs font-semibold text-charcoal-500 dark:text-charcoal-400 uppercase tracking-wide">Mode</span>
                    <button
                      onClick={() => setShowModeDrawer(false)}
                      className="text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 text-sm leading-none"
                      aria-label="Close"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="p-3 space-y-3">
                    {[
                      { id: 'approve',  label: '✓ Approve',   desc: 'AI asks before each change' },
                      { id: 'plan',     label: '📋 Plan',      desc: 'AI proposes before acting' },
                      { id: 'auto',     label: '⚡ Auto',     desc: 'AI executes without asking' },
                      { id: 'research', label: '🔍 Research',  desc: 'Read-only analysis and web search' },
                    ].map(m => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => { setChatMode(m.id); setShowModeDrawer(false) }}
                        className="flex items-center justify-between w-full gap-3 text-left group"
                      >
                        <div className="min-w-0">
                          <p className={`text-sm font-medium transition-colors ${chatMode === m.id ? 'text-orange-500' : 'group-hover:text-orange-500'}`}>
                            {m.label}
                          </p>
                          <p className="text-xs text-charcoal-400 dark:text-charcoal-500">{m.desc}</p>
                        </div>
                        <span className={`shrink-0 text-orange-500 ${chatMode === m.id ? '' : 'invisible'}`}>✓</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* AI usage indicator — hidden when the admin hasn't set a cap for this user */}
            {usage && usage.mode !== 'off' && usage.pct !== null && (
              <span
                className={`badge shrink-0 ${
                  usage.pct >= 100
                    ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                    : usage.pct >= 80
                      ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
                      : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                }`}
                title={`AI usage: ${usage.pct}% of your ${usage.period} limit`}
              >
                {usage.pct}%
              </span>
            )}

            <div className="flex-1" />

            {/* Memory pill — collapses workspace-scope + short/long-term links into one popup */}
            <div className="relative" ref={memoryRef}>
              <button
                type="button"
                onClick={() => setShowMemoryPopup(o => !o)}
                title="Memory"
                className={`text-xs px-2.5 py-1 rounded-lg flex items-center gap-1 transition-colors ${
                  crossWorkspace ? 'bg-blue-500 text-white' : 'btn-ghost'
                }`}
              >
                <span>🧠 Memory</span>
                <span className="text-[10px] opacity-60">▾</span>
              </button>
              {showMemoryPopup && (
                <div className="absolute bottom-full mb-1 right-0 w-72 bg-white dark:bg-charcoal-900 border border-charcoal-200 dark:border-charcoal-700 rounded-xl shadow-lg z-50 overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-charcoal-100 dark:border-charcoal-800">
                    <span className="text-xs font-semibold text-charcoal-500 dark:text-charcoal-400 uppercase tracking-wide">Memory</span>
                    <button
                      onClick={() => setShowMemoryPopup(false)}
                      className="text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 text-sm leading-none"
                      aria-label="Close"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="p-3 space-y-3">
                    {hasBothWorkspaces && (
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium">Both workspaces</p>
                          <p className="text-xs text-charcoal-400 dark:text-charcoal-500">
                            {crossWorkspace ? 'Chat sees Personal and Business Brain data' : `Limited to ${workspace === 'business' ? 'Business' : 'Personal'} only`}
                          </p>
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={crossWorkspace}
                          aria-label="Toggle both-workspaces scope"
                          onClick={() => setCrossWorkspace(x => !x)}
                          className={`relative w-9 h-5 rounded-full shrink-0 transition-colors ${crossWorkspace ? 'bg-blue-500' : 'bg-charcoal-300 dark:bg-charcoal-600'}`}
                        >
                          <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${crossWorkspace ? 'translate-x-4' : 'translate-x-0'}`} />
                        </button>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => { setShowMemoryPopup(false); navigate('/brain?file=Short_Term_Memory.md', { state: { from: '/chat' } }) }}
                      className="flex items-center justify-between w-full gap-3 text-left group"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium group-hover:text-orange-500 transition-colors">⏳ Short-term memory</p>
                        <p className="text-xs text-charcoal-400 dark:text-charcoal-500">Recent context the AI keeps handy</p>
                      </div>
                      <span className="text-charcoal-300 dark:text-charcoal-600 shrink-0">→</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => { setShowMemoryPopup(false); navigate('/brain?file=Long_Term_Memory.md', { state: { from: '/chat' } }) }}
                      className="flex items-center justify-between w-full gap-3 text-left group"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium group-hover:text-orange-500 transition-colors">📚 Long-term memory</p>
                        <p className="text-xs text-charcoal-400 dark:text-charcoal-500">Durable facts and preferences</p>
                      </div>
                      <span className="text-charcoal-300 dark:text-charcoal-600 shrink-0">→</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Input row */}
          <form onSubmit={send} className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Ask about your priorities, tasks, goals…"
              rows={1}
              className="input flex-1 resize-none leading-normal"
              style={{ maxHeight: 160, overflowY: 'auto' }}
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="btn-primary px-4 py-2 disabled:opacity-50 shrink-0"
            >
              →
            </button>
          </form>
        </div>
      </div>

      {/* Clears the fixed mobile footer nav so the input row is never hidden behind it */}
      <div className="h-20 md:hidden shrink-0" aria-hidden="true" />

      {/* Saved chats drawer */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-black/40" onClick={() => { setShowHistory(false); setSelectedChat(null) }} />
          <div className="w-80 md:w-96 h-full bg-white dark:bg-charcoal-900 border-l border-charcoal-200 dark:border-charcoal-700 flex flex-col shadow-xl">

            {/* Drawer header */}
            <div className="flex items-center justify-between px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] border-b border-charcoal-200 dark:border-charcoal-700 shrink-0">
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
                        {m.role === 'assistant' ? <Markdown text={m.content} /> : m.content}
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
