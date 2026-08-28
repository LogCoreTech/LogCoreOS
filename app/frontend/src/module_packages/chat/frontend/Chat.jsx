import { useState, useRef, useEffect } from 'react'
import HelpButton from '../../../components/HelpButton'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { chat as chatApi } from './api'
import { suggestions as sugApi, brain as brainApi, aiUsage as aiUsageApi } from '../../../lib/api'
import { dashboards as dashboardsApi } from '../../dashboard/frontend/api'
import { useAuth } from '../../../lib/auth'
import { useWorkspace } from '../../../lib/workspace'
import DashboardGrid from '../../../components/dashboard/DashboardGrid'
import { BLOCK_REGISTRY } from '../../../components/dashboard/blockRegistry'

const _DASHBOARD_PREVIEW_TOOLS = new Set(['add_dashboard_block', 'update_dashboard_block'])

// Client-only pointer to the chat_id last on screen — NOT a cache of the
// conversation itself (that always loads fresh from the server via
// GET /chat/sessions + the archive file). Lets a page reload reopen the same
// conversation without keeping the Chat module "running" in the background.
// "New Chat" mints a fresh id and writes it here too, but since no session
// exists server-side until the first message is actually sent, a reload
// right after clicking New Chat (with nothing sent yet) finds no matching
// session below and correctly lands on a blank chat — matching the app's own
// "New Chat then reopen should start fresh" rule for free, with no separate
// "is this fresh" flag to keep in sync.
//
// Keyed per workspace (2026-08-15): a chat_id/session belongs to exactly one
// workspace's own Chats/ folder, so personal and business each need their
// own last-open pointer — switching workspaces should restore THAT
// workspace's last conversation, not always land on a blank one.
function lastChatKey(ws) {
  return `lc_chat_last_id_${ws}`
}

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
      const url = match[2]
      // Only render as a real link when the scheme is safe (http/https/mailto)
      // or it's an in-app relative path (e.g. /help#finance). Anything else —
      // javascript:, data:, etc — renders as plain text instead, since this
      // text can echo back web-search results or Brain content the AI read,
      // not just the model's own trusted output.
      const safe = /^(https?:|mailto:)/i.test(url) || url.startsWith('/')
      if (!safe) {
        out.push(match[1])
      } else {
        const external = /^https?:\/\//i.test(url)
        out.push(
          <a key={k} href={url} className="text-orange-500 hover:underline" {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
            {match[1]}
          </a>
        )
      }
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
  // A message with no text (e.g. a turn that was pure tool-call, no prose)
  // must render as empty, not crash the whole page — 2026-08-16, real
  // crash: "undefined is not an object (evaluating 'e.split')" the first
  // time a dashboard resize/move was requested.
  const lines = (text || '').split('\n')
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
    // step.input.layout is the agent's own optional size override (2026-08-15)
    // — preview it accurately rather than always showing the default size.
    const w = step.input.layout?.w || meta?.defaultLayout?.w || 12
    const h = step.input.layout?.h || meta?.defaultLayout?.h || 9
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
    previewBlocks = rendered.blocks.map(b => {
      if (b.id !== step.input.block_id) return b
      // step.input.layout is the agent's own optional position/size override
      // (2026-08-15) — x/w only change on lg (mobile stays full-width at
      // x=0), height changes on both, mirroring agent_service.py's own
      // _apply_layout_override so the preview matches what will actually
      // be saved.
      const override = step.input.layout
      const layout = override
        ? {
            lg: {
              ...b.layout.lg,
              ...(override.x != null ? { x: override.x } : {}),
              ...(override.y != null ? { y: override.y } : {}),
              ...(override.w ? { w: override.w } : {}),
              ...(override.h ? { h: override.h } : {}),
            },
            sm: { ...b.layout.sm, ...(override.h ? { h: override.h } : {}) },
          }
        : b.layout
      return { ...b, config: step.input.config || {}, layout, ok: false, locked_reason: 'pending_approval' }
    })
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

// sendResume's own history — deliberately NOT toApiHistory. messages.slice(1,
// -1) at the moment a turn is paused always ends with the *user* message
// that triggered the still-pending assistant reply (a normal alternating
// conversation always has a user turn directly before an assistant one) —
// toApiHistory's trailing-pop assumes a dangling non-assistant entry is
// leftover cruft to discard, so it silently dropped that real, current user
// message every single time a turn was resumed. The server then archived
// `history + [resumed reply]` with that user turn missing, leaving two
// assistant entries adjacent in the saved .md file — invisible in the same
// live session (local `messages` state itself stayed fine), but the next
// time that archive was reloaded (a page remount, switching workspaces and
// back, reopening from the Chats drawer — all now more frequent since the
// 2026-08-15 background-multi-chat work), the corrupted pair loaded straight
// into `messages`, and the very next real send 422'd with "History message N
// has unexpected role 'assistant'" (found 2026-08-15, reported as "chat
// breaks after accepting an approval card").
function toResumeHistory(msgs) {
  const h = msgs.filter(m => !m._proactive).map(m => ({ role: m.role, content: m.content }))
  while (h.length && h[0].role !== 'user') h.shift()
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

function greeting(user) {
  return {
    role: 'assistant',
    content: `Hi, ${user?.name?.split(' ')[0] || 'there'}, what can I help you with today?`,
    steps: [],
  }
}

export default function Chat() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const hasBothWorkspaces = (user?.workspaces?.length ?? 0) > 1
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  // Stable per-conversation id (background execution + multi-conversation UI,
  // 2026-08-15) — minted the moment a genuinely new conversation starts, sent
  // with every /chat call for it, and used as the primary key for the "Chats"
  // list (GET /chat/sessions) instead of a raw filename. A ref mirrors the
  // state so async response handlers can tell, once a request finally
  // resolves, whether the user is STILL looking at the conversation it
  // belongs to (state closures capture the value at call time; the ref
  // always reads live) — if not, the reply is simply not applied to
  // `messages` here, since the server has already durably saved it and
  // indexed it as unread; reopening that conversation later picks it up.
  const [chatId, setChatId] = useState(() => {
    try {
      return localStorage.getItem(lastChatKey(workspace)) || crypto.randomUUID()
    } catch {
      return crypto.randomUUID()
    }
  })
  const chatIdRef = useRef(chatId)
  chatIdRef.current = chatId
  const [messages, setMessages] = useState([greeting(user)])
  const [input, setInput] = useState('')
  // Which chat_ids currently have a request in flight — scoped per-
  // conversation (not one global boolean) so switching to a different, idle
  // conversation is never blocked by another one still generating.
  const [loadingIds, setLoadingIds] = useState(() => new Set())
  const loading = loadingIds.has(chatId)
  // chat_ids whose "Thinking…" state came from restoring a session that's
  // still `status: "running"` server-side (reopened after a reload, or
  // opened from the drawer/a deep link) rather than from this tab's own
  // in-flight send()/sendResume() call — those already know when they
  // finish via their own awaited promise; this is for the case where nobody
  // in this tab is actually waiting on anything (owner report, 2026-08-17:
  // "the chat bubble should stay displayed when the agent is running, but
  // it doesn't save" — the Thinking bubble is pure local state, so it never
  // reappeared on reopening a conversation that was genuinely still running).
  const [restoredRunningIds, setRestoredRunningIds] = useState(() => new Set())
  const [chatMode, setChatMode] = useState('approve')
  const [crossWorkspace, setCrossWorkspace] = useState(false)
  const [showModeDrawer, setShowModeDrawer] = useState(false)
  const [showMemoryPopup, setShowMemoryPopup] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [sessions, setSessions] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [usage, setUsage] = useState(null) // { mode, pct } — null until loaded
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const modeRef = useRef(null)
  const memoryRef = useRef(null)

  function setLoadingFor(id, isLoading) {
    setLoadingIds(prev => {
      const next = new Set(prev)
      if (isLoading) next.add(id)
      else next.delete(id)
      return next
    })
  }

  function refreshUsage() {
    aiUsageApi.me().then(setUsage).catch(() => {})
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
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

  // Poll a restored-as-running conversation until the server-side status
  // actually moves off "running" — nothing else in this tab is watching it
  // (no live channel exists, same reasoning as the presence-ping design
  // elsewhere), so without this the Thinking bubble would stay stuck
  // forever, or the finished reply would only ever show up after a manual
  // reload. Reuses openSession() to pick up the final content once done —
  // that call re-derives everything (paused card, plain completion, etc.)
  // the normal way, so this doesn't need its own completion-handling logic.
  useEffect(() => {
    if (restoredRunningIds.size === 0) return
    const interval = setInterval(async () => {
      let list
      try {
        list = await chatApi.sessions()
      } catch {
        return // keep trying next tick
      }
      for (const id of restoredRunningIds) {
        const found = (list || []).find(s => s.chat_id === id)
        if (found && found.status === 'running') continue
        setRestoredRunningIds(prev => {
          const next = new Set(prev)
          next.delete(id)
          return next
        })
        setLoadingFor(id, false)
        if (chatIdRef.current === id && found) openSession(found)
      }
    }, 4000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restoredRunningIds])

  // Presence — pings the server so a completion/approval notification isn't
  // also sent for this chat while it's already visible live (2026-08-15,
  // owner ask: "only send a notification... when the user is not on that
  // module"). Pings immediately on mount and whenever chatId changes
  // (switching conversations, workspace switch, opening a session), then
  // every 20s while the tab stays open and visible — deliberately no ping
  // on backgrounding/leaving: presence just goes stale on its own (see
  // agent_service.is_chat_present's 45s window), no explicit "I left" call
  // needed. Pure server-side bookkeeping, no UI of its own — safe to add
  // without touching layout.
  useEffect(() => {
    function ping() {
      if (document.visibilityState === 'visible') chatApi.presence(chatId).catch(() => {})
    }
    ping()
    const interval = setInterval(ping, 20000)
    document.addEventListener('visibilitychange', ping)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', ping)
    }
  }, [chatId])

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

  // Workspace switch reopens THAT workspace's own last conversation (falls
  // back to a fresh blank one if it never had a session) — a chat_id/session
  // belongs to exactly one workspace's own Chats/ folder (see agent_service
  // .py's _sessions_path), so continuing to type into what's on screen would
  // silently create a same-id session in the new workspace disconnected from
  // what the user's actually looking at. Also clears crossWorkspace and
  // refreshes the sessions list if the drawer's open. Deliberately
  // workspace-only: showHistory is read as a gate, not a trigger — opening/
  // closing the drawer on its own shouldn't reset the conversation.
  //
  // Guarded to skip its very first run: a `useEffect` with a dependency array
  // still fires once after the initial render, not just on later changes —
  // unguarded, this reset ran on every single mount and clobbered the
  // restored chatId/messages below before they ever reached the screen
  // (bug: Chat never reopened the last conversation, always looked "New").
  const isFirstWorkspaceRun = useRef(true)
  useEffect(() => {
    if (isFirstWorkspaceRun.current) {
      isFirstWorkspaceRun.current = false
      return
    }
    setCrossWorkspace(false)
    // Previously always minted a fresh chat_id and blank greeting here — so
    // switching workspace and switching back never reopened what was there,
    // it always looked "New" (reported 2026-08-15). restoreForWorkspace does
    // the same lookup the initial mount does, just for the workspace being
    // switched TO.
    restoreForWorkspace(workspace)
    if (showHistory) {
      chatApi.sessions().then(list => setSessions(list || [])).catch(() => setSessions([]))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace])

  // Persist which chat_id is on screen so a reload — or switching back to
  // this workspace later — reopens the same conversation. A plain pointer,
  // not a cache of the conversation itself (see lastChatKey above).
  useEffect(() => {
    try {
      localStorage.setItem(lastChatKey(workspace), chatId)
    } catch {
      /* ignore (private-browsing/storage-full) */
    }
  }, [chatId, workspace])

  // Look up the real content for a workspace's restored chatId (mount, or a
  // workspace switch). If it has no server-side session yet (a brand new/
  // never-sent chat_id, including right after "New Chat"), there's nothing
  // to load — land on a fresh blank chat for that workspace instead.
  async function restoreForWorkspace(ws) {
    let stored
    try {
      stored = localStorage.getItem(lastChatKey(ws))
    } catch {
      stored = null
    }
    if (!stored) {
      setChatId(crypto.randomUUID())
      setMessages([greeting(user)])
      return
    }
    try {
      const list = await chatApi.sessions()
      const found = (list || []).find(s => s.chat_id === stored)
      if (found) {
        await openSession(found)
        return
      }
    } catch {
      /* fall through to a blank chat under the stored id below */
    }
    setChatId(stored)
    setMessages([greeting(user)])
  }

  // On first mount only, restore the current workspace's last conversation.
  // Skipped when a `?chat_id=` deep link is present; that effect below owns
  // loading in that case.
  useEffect(() => {
    if (searchParams.get('chat_id')) return
    restoreForWorkspace(workspace)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Deep link (?chat_id=<id>) — the notification bell's "View →" on a chat
  // reply/approval-needed push lands here. Loads that conversation directly,
  // same as clicking it in the drawer (openSession below) — no separate
  // preview step, matching how every other module's own deep link works.
  useEffect(() => {
    const target = searchParams.get('chat_id')
    if (!target) return
    searchParams.delete('chat_id')
    setSearchParams(searchParams, { replace: true })
    chatApi.sessions().then(list => {
      const found = (list || []).find(s => s.chat_id === target)
      if (found) openSession(found)
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  async function send(e, overrideMsg, modeOverride, acceptOverage) {
    e?.preventDefault()
    const msg = overrideMsg ?? input.trim()
    if (!msg || loading) return

    // Captured now, not read live later — if the user switches to a
    // different conversation (or a brand new one) before this resolves, the
    // response below must not land in whatever's currently on screen. The
    // request itself is never cancelled by switching (no AbortController),
    // and the server durably saves + indexes the result either way — this
    // guard only decides whether THIS component still shows it live.
    const sendingChatId = chatId
    const userMsg = { role: 'user', content: msg, steps: [] }
    const updated = [...messages, userMsg]
    setMessages(updated)
    if (!overrideMsg) setInput('')
    setLoadingFor(sendingChatId, true)

    try {
      const history = toApiHistory(updated.slice(1, -1))
      const res = await chatApi.send(sendingChatId, msg, history, modeOverride || chatMode, crossWorkspace, acceptOverage)
      if (chatIdRef.current === sendingChatId) {
        setMessages([...updated, {
          role: 'assistant',
          content: res.response,
          steps: res.steps || [],
          mode: res.mode,
          runId: res.run_id,
          triggerMsg: msg,
        }])
        chatApi.markSessionRead(sendingChatId).catch(() => {})
      }
      refreshUsage()
    } catch (err) {
      if (chatIdRef.current === sendingChatId) {
        setMessages([...updated, { role: 'assistant', content: `Error: ${err.message}`, steps: [] }])
      }
    } finally {
      setLoadingFor(sendingChatId, false)
      if (chatIdRef.current === sendingChatId) inputRef.current?.focus()
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
    const sendingChatId = chatId
    setLoadingFor(sendingChatId, true)
    try {
      // The pending turn (the message carrying the pending_write/pending_question/
      // pending_plan step) IS this same assistant turn, not a separate one —
      // replace it in place rather than appending. Appending left two consecutive
      // assistant messages, which breaks the strict user/assistant alternation
      // ChatRequest.history requires.
      // Use toResumeHistory, NOT toApiHistory — see its own comment above.
      // This array correctly ends in the user message whose reply is pending;
      // toApiHistory's trailing-pop is built for send()'s different shape and
      // would silently discard that message here.
      const history = toResumeHistory(messages.slice(1, -1))
      const res = await chatApi.resume(sendingChatId, runId, decision, history, crossWorkspace, answer)
      if (chatIdRef.current === sendingChatId) {
        setMessages(prev => [...prev.slice(0, -1), {
          role: 'assistant',
          content: res.response,
          steps: res.steps || [],
          mode: res.mode,
          runId: res.run_id,
        }])
        chatApi.markSessionRead(sendingChatId).catch(() => {})
      }
      refreshUsage()
    } catch (err) {
      if (chatIdRef.current === sendingChatId) {
        setMessages(prev => [...prev.slice(0, -1), { role: 'assistant', content: `Error: ${err.message}`, steps: [] }])
      }
    } finally {
      setLoadingFor(sendingChatId, false)
      if (chatIdRef.current === sendingChatId) inputRef.current?.focus()
    }
  }

  function newChat() {
    setChatId(crypto.randomUUID())
    setMessages([greeting(user)])
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

  // Opens a conversation directly into the main pane — no intermediate
  // preview/"Continue →" step (owner: keep the Chats button, but make it
  // open on click instead of a preview page). Works both from a drawer row
  // click and from the ?chat_id= deep link above.
  async function openSession(session) {
    setHistoryLoading(true)
    try {
      const file = await brainApi.getFile(`Chats/${session.filename}`)
      let parsed = parseSavedChat(file.content)
      // The archive itself only ever stores plain role/content turns, so a
      // conversation left mid-approval/question/plan reloaded the assistant's
      // prompt text fine but lost the actual interactive card — the user
      // could see "I need your approval..." but had no button to act on it
      // (reported 2026-08-15). If this session is still paused, re-fetch the
      // live pending-turn record and re-attach steps/mode/runId onto the
      // last (assistant) message, same shape a live pause response already
      // carries in send()/sendResume() above.
      if (
        (session.status === 'awaiting_approval' || session.status === 'awaiting_answer') &&
        parsed.length &&
        parsed[parsed.length - 1].role === 'assistant'
      ) {
        try {
          const pending = await chatApi.pending(session.chat_id)
          if (pending) {
            parsed = [
              ...parsed.slice(0, -1),
              { ...parsed[parsed.length - 1], steps: pending.steps || [], mode: pending.mode, runId: pending.run_id },
            ]
          }
        } catch {
          /* the plain text still loaded fine above — just no interactive card */
        }
      }
      setChatId(session.chat_id)
      setMessages(parsed.length ? [greeting(user), ...parsed] : [greeting(user)])
      setShowHistory(false)
      chatApi.markSessionRead(session.chat_id).catch(() => {})
      setSessions(prev => prev.map(s => (s.chat_id === session.chat_id ? { ...s, unread: false } : s)))
      // Still genuinely running server-side (this tab isn't the one that
      // started it, or it survived a reload) — show the Thinking bubble and
      // start polling for it to finish, instead of silently looking idle.
      if (session.status === 'running') {
        setLoadingFor(session.chat_id, true)
        setRestoredRunningIds(prev => new Set(prev).add(session.chat_id))
      }
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' }), 50)
    } catch {
      alert('Failed to load that chat.')
    } finally {
      setHistoryLoading(false)
    }
  }

  async function deleteSession(session, e) {
    e.stopPropagation()
    try {
      await chatApi.deleteSaved(session.filename)
      setSessions(prev => prev.filter(s => s.chat_id !== session.chat_id))
      // Deleting the conversation currently on screen leaves nothing sensible
      // to keep showing — start fresh rather than displaying orphaned messages
      // a future send would try to (and fail to) re-save under a gone chat_id.
      if (session.chat_id === chatId) newChat()
    } catch (err) {
      alert(err.message || 'Failed to delete chat')
    }
  }

  async function openHistory() {
    setShowHistory(true)
    setHistoryLoading(true)
    try {
      const list = await chatApi.sessions()
      setSessions(list || [])
    } catch {
      setSessions([])
    } finally {
      setHistoryLoading(false)
    }
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

  return (
    <>
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


      <div className="flex-1 min-h-0 space-y-4 pb-4 overflow-y-auto">
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

      {/* Composer — bordered toolbar (mode/usage/memory) + auto-growing input, boxed together.
          Plain flow (not sticky/fixed — an earlier same-day sticky attempt
          broke this and Notes both, reverted). No JS keyboard-avoidance code
          at all (attempt 8) — relies entirely on Safari's native focus-scroll
          plus index.html's interactive-widget=resizes-content. */}
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
    </div>

      {/* Saved chats drawer — kept as a sibling of the page container above,
          not a descendant: a `fixed inset-0` element nested inside a
          transformed ancestor renders relative to that ancestor instead of
          the true viewport (the same CSS trap found with the image lightbox
          earlier this session — see docs/MEMORY.md). The page container has
          no transform applied today, but keeping this structure costs
          nothing and avoids re-introducing the trap if one ever is. */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-black/40" onClick={() => setShowHistory(false)} />
          <div className="w-80 md:w-96 h-full bg-white dark:bg-charcoal-900 border-l border-charcoal-200 dark:border-charcoal-700 flex flex-col shadow-xl">

            {/* Drawer header */}
            <div className="flex items-center justify-between px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] border-b border-charcoal-200 dark:border-charcoal-700 shrink-0">
              <h3 className="text-sm font-semibold">Chats</h3>
              <button
                onClick={() => setShowHistory(false)}
                className="text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 text-lg leading-none"
              >
                ✕
              </button>
            </div>

            {/* Drawer body — clicking a row opens it directly, no preview step */}
            <div className="flex-1 min-h-0 overflow-y-auto">
              {historyLoading ? (
                <div className="flex items-center justify-center h-24">
                  <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : sessions.length === 0 ? (
                <p className="text-sm text-charcoal-400 dark:text-charcoal-500 text-center py-10">No chats yet.</p>
              ) : (
                <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800">
                  {sessions.map(session => (
                    <div
                      key={session.chat_id}
                      className="flex items-center gap-2 px-4 py-3 hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors group"
                    >
                      <button
                        onClick={() => openSession(session)}
                        className="flex-1 text-left min-w-0 flex items-center gap-2"
                      >
                        {session.status === 'running' ? (
                          <span
                            className="w-2 h-2 rounded-full bg-orange-500 shrink-0 animate-pulse"
                            title="Still working…"
                          />
                        ) : session.unread ? (
                          <span
                            className="w-2 h-2 rounded-full bg-orange-500 shrink-0"
                            title={session.status === 'awaiting_approval' || session.status === 'awaiting_answer' ? 'Needs your input' : 'Unread'}
                          />
                        ) : (
                          <span className="w-2 h-2 shrink-0" />
                        )}
                        <span className="min-w-0 flex-1">
                          <p className={`text-sm truncate ${session.unread ? 'font-semibold text-charcoal-900 dark:text-white' : 'font-medium text-charcoal-800 dark:text-charcoal-100'}`}>
                            {session.title || fmtFilename(session.filename)}
                          </p>
                          <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-0.5 truncate">
                            {session.status === 'awaiting_approval' || session.status === 'awaiting_answer'
                              ? 'Needs your input'
                              : session.last_message_preview || fmtFilename(session.filename)}
                          </p>
                        </span>
                      </button>
                      <button
                        onClick={e => deleteSession(session, e)}
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
    </>
  )
}
