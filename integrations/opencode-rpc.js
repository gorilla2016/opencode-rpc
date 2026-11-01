// opencode-rpc plugin: launch the Discord RPC daemon when opencode starts.
// Install to ~/.config/opencode/plugins/opencode-rpc.js (global) or
// .opencode/plugins/opencode-rpc.js (project).
//
// The daemon self-terminates when opencode closes (exit_when_closed), so it
// only runs while opencode is open.

import { spawn } from "node:child_process"
import os from "node:os"
import path from "node:path"
import fs from "node:fs"

function alive(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function launch(cmds, i, script) {
  if (i >= cmds.length) return
  const child = spawn(cmds[i], [script], {
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  })
  child.on("error", () => launch(cmds, i + 1, script))
  child.unref()
}

export const OpenCodeRpc = async () => {
  try {
    const home = os.homedir()
    const stateDir = path.join(home, ".opencode-rpc")
    const pidFile = path.join(stateDir, "daemon.pid")

    // already running?
    try {
      const pid = parseInt(fs.readFileSync(pidFile, "utf8").trim(), 10)
      if (pid && alive(pid)) return {}
    } catch {}

    const script =
      process.env.OPENCODE_RPC_SCRIPT ||
      path.join(home, "opencode-rpc", "opencode-rpc.py")
    if (!fs.existsSync(script)) return {}

    const cmds =
      process.platform === "win32" ? ["pythonw", "python"] : ["python3", "python"]
    launch(cmds, 0, script)
  } catch {}
  return {}
}
