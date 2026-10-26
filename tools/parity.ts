/**
 * Parity check: run the browser engine under Node on the real IPA.
 *
 *   ui/node_modules/.bin/esbuild tools/parity.ts --bundle --platform=node \
 *     --format=esm --outfile=/tmp/opencode/parity.mjs
 *   node /tmp/opencode/parity.mjs original.ipa /tmp/opencode/js.ipa [profile]
 */
import { createReadStream, openAsBlob, readFileSync } from 'node:fs'
import { open } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { once } from 'node:events'

import { patchIpa } from '../ui/src/lib/engine'
import type { PatchManifest } from '../ui/src/lib/engine'
import type { RandomAccess } from '../ui/src/lib/zip'

const ipa = process.argv[2]
const out = process.argv[3]
const profile = process.argv[4]
if (!ipa || !out) {
  console.error('usage: parity.mjs <original.ipa> <out.ipa> [profile]')
  process.exit(2)
}

const manifest = JSON.parse(
  readFileSync(resolve(process.cwd(), 'patches/mhfu-ios.json'), 'utf8'),
) as PatchManifest
const storyboard = readFileSync(resolve(process.cwd(), 'assets/LaunchScreen.storyboard'), 'utf8')

const blob = await openAsBlob(ipa)
const source: RandomAccess = {
  size: blob.size,
  read: async (offset, length) =>
    new Uint8Array(await blob.slice(offset, offset + length).arrayBuffer()),
  slice: (offset, length) => blob.slice(offset, offset + length),
}

const handle = await open(out, 'w')
let lastPrint = -1
const started = Date.now()
const result = await patchIpa(
  source,
  async (part) => {
    if (part instanceof Uint8Array) await handle.write(part)
    else await handle.write(new Uint8Array(await part.arrayBuffer()))
  },
  manifest,
  {
    profile,
    additions: {
      'assets/LaunchScreen.storyboard': new TextEncoder().encode(storyboard),
    },
    onEvent: (event) => {
      if (event.pct !== lastPrint && (event.pct % 5 === 0 || event.pct === 100)) {
        lastPrint = event.pct
        console.log(
          `${String(event.pct).padStart(3)}% ${event.phase}${event.detail ? ' · ' + event.detail : ''}`,
        )
      }
    },
  },
)
await handle.close()

const hash = createHash('sha256')
const stream = createReadStream(out)
stream.on('data', (chunk) => hash.update(chunk))
await once(stream, 'end')

console.log(
  JSON.stringify(
    { ...result, seconds: Number(((Date.now() - started) / 1000).toFixed(1)) },
    null,
    2,
  ),
)
console.log('output sha256:', hash.digest('hex'))
