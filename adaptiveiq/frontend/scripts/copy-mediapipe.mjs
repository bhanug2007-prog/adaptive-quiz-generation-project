// Copies the MediaPipe face detector's WebAssembly files from node_modules into public/, so the browser loads
// them from this site (no third-party CDN, no video leaves the computer). Runs after `npm install` and before
// `npm run dev` / `npm run build`. The ~9 MB files are not committed (see .gitignore).
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = join(root, 'node_modules', '@mediapipe', 'tasks-vision', 'wasm')
const dst = join(root, 'public', 'mediapipe', 'wasm')
if (!existsSync(src)) {
  console.warn('copy-mediapipe: @mediapipe/tasks-vision is not installed; camera face detection will not load.')
  process.exit(0)
}
mkdirSync(dst, { recursive: true })
let n = 0
for (const f of readdirSync(src)) {
  const a = join(src, f), b = join(dst, f)
  if (!existsSync(b) || statSync(b).size !== statSync(a).size) { copyFileSync(a, b); n++ }
}
if (n) console.log(`copy-mediapipe: copied ${n} file(s) to public/mediapipe/wasm`)
