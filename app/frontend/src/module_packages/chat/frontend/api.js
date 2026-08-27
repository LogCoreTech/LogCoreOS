// Chat's API client — built on the shared request/get/post/patch/del
// helpers exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module.
import { get, post, del } from '../../../lib/api'

export const chat = {
  send:       (chatId, message, history, mode = 'approve', crossWorkspace = false, acceptOverage = false) => post('/chat', { chat_id: chatId, message, history, mode, cross_workspace: crossWorkspace, accept_overage: acceptOverage }),
  // Replays/answers a paused turn (approve/decline a pending write, or answer a
  // question) instead of sending a new message — see docs/MEMORY.md 2026-08-09.
  resume:     (chatId, runId, decision, history, crossWorkspace = false, answer = null) => post('/chat', { chat_id: chatId, history, cross_workspace: crossWorkspace, resume: { run_id: runId, decision, answer } }),
  saveMemory: (history, target = 'short') => post('/chat/save-memory',  { history, target }),
  saveChat:   (history, name = '', filename = '') => post('/chat/save', { history, name, filename }),
  listSaved:  ()                          => get('/chat/saved'),
  deleteSaved: (filename)                 => del(`/chat/saved/${encodeURIComponent(filename)}`),
  // One entry per conversation (status + unread), backing the "Chats" list —
  // see docs/MEMORY.md 2026-08-15 for why this replaced /saved as the
  // sidebar's source.
  sessions:    ()                         => get('/chat/sessions'),
  markSessionRead: (chatId)               => post(`/chat/sessions/${encodeURIComponent(chatId)}/read`),
  // The live pending_write/pending_question/pending_plan card for a
  // conversation (run_id/mode/steps), if it currently has one — re-attached
  // onto the last message when reopening a session whose own status is
  // awaiting_approval/awaiting_answer, since the saved .md archive itself
  // has no structured step data (2026-08-15).
  pending:    (chatId)                    => get(`/chat/pending/${encodeURIComponent(chatId)}`),
  // Tells the server "I'm still looking at this conversation" so a
  // completion/approval notification isn't also sent while it's already
  // visible live — see docs/MEMORY.md 2026-08-15.
  presence:   (chatId)                    => post('/chat/presence', { chat_id: chatId }),
  runs:       ()                          => get('/chat/runs'),
  getRun:     (id)                        => get(`/chat/runs/${id}`),
}
