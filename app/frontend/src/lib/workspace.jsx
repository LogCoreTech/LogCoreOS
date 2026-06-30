import { createContext, useContext, useState } from 'react'

const WorkspaceCtx = createContext({ workspace: 'personal', switchWorkspace: () => {} })

export function WorkspaceProvider({ children }) {
  const [workspace, setWorkspace] = useState(
    () => localStorage.getItem('lc_ws') || 'personal'
  )

  function switchWorkspace(next) {
    localStorage.setItem('lc_ws', next)
    setWorkspace(next)
  }

  return (
    <WorkspaceCtx.Provider value={{ workspace, switchWorkspace }}>
      {children}
    </WorkspaceCtx.Provider>
  )
}

export const useWorkspace = () => useContext(WorkspaceCtx)
