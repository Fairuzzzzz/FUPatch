import { analyze, extract, findArm64, replaceSlice } from './macho'
import type { MachOInfo } from './macho'
import { parsePlist, serializePlist } from './plist'
import { readIndex, readMember, rewrite } from './zip'
import type { Addition, Part, RandomAccess, Sink } from './zip'

export interface PatchStep {
  id: string
  feature: string
  vaddr: string
  expect: string
  replace: string
  note?: string
}

export interface PatchManifest {
  schema: number
  id: string
  title: string
  app: { bundle_id?: string; executable?: string }
  slice: {
    arch: string
    vaddr_base: string
    source_sha256: string[]
    intermediate_sha256: string[]
    result_sha256: string
  }
  binary_steps: PatchStep[]
  members_remove: { exact?: string[]; globs?: string[] }
  members_add: { name: string; source?: string; data?: string }[]
  info_changes: { set?: Record<string, unknown>; remove?: string[] }
  version: { marker_key?: string }
}

export interface PatchEvent {
  phase: string
  pct: number
  detail: string
}

export interface PatchOptions {
  keepFat?: boolean
  additions?: Record<string, Uint8Array>
  onEvent?: (event: PatchEvent) => void
  isCancelled?: () => boolean
}

export interface PatchResult {
  version: string
  applied: string[]
  skipped: string[]
  removed: string[]
  added: string[]
  binarySha256: string
  members: number
  size: number
  outName: string
}

export class PatchError extends Error {}

const VERSION_RE = /^\d{1,3}(\.\d{1,3}){1,3}$/

function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
  return true
}

function hexToBytes(text: string): Uint8Array {
  if (text.length % 2 !== 0) throw new PatchError('odd hex string')
  const out = new Uint8Array(text.length / 2)
  for (let i = 0; i < out.length; i++) {
    const value = Number.parseInt(text.slice(i * 2, i * 2 + 2), 16)
    if (Number.isNaN(value)) throw new PatchError('bad hex string')
    out[i] = value
  }
  return out
}

function toHex(bytes: Uint8Array): string {
  let out = ''
  for (const byte of bytes) out += byte.toString(16).padStart(2, '0')
  return out
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    bytes as unknown as BufferSource,
  )
  const view = new Uint8Array(digest)
  let out = ''
  for (const byte of view) out += byte.toString(16).padStart(2, '0')
  return out
}

function globToRegExp(pattern: string): RegExp {
  let source = '^'
  for (const char of pattern) {
    if (char === '*') source += '.*'
    else if (char === '?') source += '.'
    else source += char.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }
  return new RegExp(source + '$')
}

function resolveRemovals(
  spec: { exact?: string[]; globs?: string[] } | undefined,
  names: string[],
): Set<string> {
  const exact = new Set(spec?.exact ?? [])
  const globs = (spec?.globs ?? []).map(globToRegExp)
  const out = new Set<string>()
  for (const name of names) {
    if (exact.has(name) || globs.some((pattern) => pattern.test(name))) {
      out.add(name)
    }
  }
  return out
}

function resolveAdditions(
  spec: PatchManifest['members_add'] | undefined,
  present: Set<string>,
  provided: Record<string, Uint8Array>,
): Addition[] {
  const out: Addition[] = []
  for (const item of spec ?? []) {
    if (!item.name) throw new PatchError('members_add entry has no name')
    if (present.has(item.name)) continue
    let data = item.source ? provided[item.source] : undefined
    if (!data && item.data) data = new TextEncoder().encode(item.data)
    if (!data) {
      throw new PatchError('missing member data for ' + item.name)
    }
    out.push({ name: item.name, data })
  }
  return out
}

function patchInfoPlist(
  raw: Uint8Array,
  manifest: PatchManifest,
  version: string,
): Uint8Array {
  const value = parsePlist(raw)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new PatchError('Info.plist is not a dictionary')
  }
  const plist = value as Record<string, unknown>
  for (const key of manifest.info_changes.remove ?? []) delete plist[key]
  for (const [key, item] of Object.entries(manifest.info_changes.set ?? {})) {
    plist[key] = item
  }
  plist.CFBundleShortVersionString = version
  plist.CFBundleVersion = version
  const markerKey = manifest.version.marker_key
  if (markerKey) plist[markerKey] = manifest.id
  return serializePlist(plist)
}

const INFO_PLIST = /^Payload\/[^/]+\.app\/Info\.plist$/

/**
 * Patch an IPA entirely in memory. `source` is random access (a File), `sink`
 * receives the new archive as a sequence of byte chunks and Blobs.
 */
export async function patchIpa(
  source: RandomAccess,
  sink: Sink,
  manifest: PatchManifest,
  options: PatchOptions = {},
): Promise<PatchResult> {
  const emit = (phase: string, pct: number, detail = '') => {
    options.onEvent?.({ phase, pct: Math.max(0, Math.min(100, Math.round(pct))), detail })
  }
  const check = () => {
    if (options.isCancelled?.()) throw new PatchError('cancelled by user')
  }

  emit('inspect', 1, 'reading IPA')
  const index = await readIndex(source)
  const names = index.entries.map((entry) => entry.nameStr)
  const infoEntry = index.entries.find((entry) => INFO_PLIST.test(entry.nameStr))
  if (!infoEntry) throw new PatchError('Info.plist not found inside the IPA')
  const appDir = infoEntry.nameStr.slice(0, infoEntry.nameStr.lastIndexOf('/'))
  const rawPlist = await readMember(source, infoEntry)
  const parsed = parsePlist(rawPlist)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new PatchError('Info.plist is not a dictionary')
  }
  const plist = parsed as Record<string, unknown>
  const executable = plist.CFBundleExecutable
  if (typeof executable !== 'string' || !executable) {
    throw new PatchError('CFBundleExecutable is missing from Info.plist')
  }
  const exeName = appDir + '/' + executable
  const exeEntry = index.entries.find((entry) => entry.nameStr === exeName)
  if (!exeEntry) throw new PatchError('executable not found inside the IPA')

  emit('read', 4, exeName)
  const exeData = await readMember(source, exeEntry)
  let macho: MachOInfo
  try {
    macho = analyze(exeData)
  } catch (error) {
    throw new PatchError(
      'not a Mach-O executable: ' + (error instanceof Error ? error.message : error),
    )
  }
  const arm = findArm64(macho)
  if (!arm) {
    throw new PatchError(
      'IPA has no arm64 slice (found: ' +
        macho.slices.map((slice) => slice.arch).join(', ') +
        ')',
    )
  }
  const slice = extract(exeData, arm)
  const sourceSha = await sha256Hex(slice)
  const known =
    manifest.slice.source_sha256.includes(sourceSha) ||
    manifest.slice.intermediate_sha256.includes(sourceSha)
  if (!known) {
    throw new PatchError(
      'unknown binary (sha ' +
        sourceSha.slice(0, 16) +
        ') — not a supported MHFU IPA',
    )
  }
  emit('verify', 8, 'slice sha ' + sourceSha.slice(0, 16))

  const patched = slice.slice()
  const base = Number.parseInt(manifest.slice.vaddr_base, 16)
  const applied: string[] = []
  const skipped: string[] = []
  const total = manifest.binary_steps.length
  for (let i = 0; i < total; i++) {
    check()
    const step = manifest.binary_steps[i]
    const offset = Number.parseInt(step.vaddr, 16) - base
    const expect = hexToBytes(step.expect)
    const replace = hexToBytes(step.replace)
    if (expect.length !== replace.length) {
      throw new PatchError('step ' + step.id + ' has mismatched lengths')
    }
    if (offset < 0 || offset + expect.length > patched.length) {
      throw new PatchError('step ' + step.id + ' is out of range')
    }
    const current = patched.subarray(offset, offset + expect.length)
    if (bytesEqual(current, replace)) {
      skipped.push(step.id)
    } else if (bytesEqual(current, expect)) {
      patched.set(replace, offset)
      applied.push(step.id)
    } else {
      throw new PatchError(
        'step ' +
          step.id +
          ' at ' +
          offset.toString(16) +
          ' does not match (found: ' +
          toHex(current) +
          ', expected: ' +
          step.expect +
          ')',
      )
    }
    emit('steps', 10 + Math.floor((14 * (i + 1)) / Math.max(1, total)), `${i + 1}/${total}`)
  }
  const resultSha = await sha256Hex(patched)
  if (resultSha !== manifest.slice.result_sha256) {
    throw new PatchError(
      'resulting binary sha mismatch\n  got     : ' +
        resultSha +
        '\n  expected: ' +
        manifest.slice.result_sha256,
    )
  }
  emit('steps', 24, 'binary sha ok')

  const fatOut = Boolean(options.keepFat && macho.kind === 'fat')
  const newExe = fatOut ? replaceSlice(exeData, arm, patched) : patched

  const version =
    typeof plist.CFBundleShortVersionString === 'string'
      ? plist.CFBundleShortVersionString
      : ''
  if (!version) throw new PatchError('source Info.plist has no version')
  if (!VERSION_RE.test(version)) {
    throw new PatchError('invalid version ' + JSON.stringify(version))
  }

  const present = new Set(names)
  const removals = resolveRemovals(manifest.members_remove, names)
  const additions = resolveAdditions(
    manifest.members_add,
    present,
    options.additions ?? {},
  )
  if (!applied.length && !removals.size && !additions.length) {
    throw new PatchError('this IPA is already patched')
  }

  emit('plist', 25, 'version ' + version + ' (unchanged)')
  const newPlist = patchInfoPlist(rawPlist, manifest, version)
  const replacements = new Map<string, Uint8Array>([
    [infoEntry.nameStr, newPlist],
    [exeName, newExe],
  ])

  emit('write', 25, 'starting')
  let lastPct = -1
  const result = await rewrite(
    source,
    index,
    sink,
    replacements,
    removals,
    additions,
    (done, count, writtenBytes, totalBytes) => {
      check()
      const pct = 25 + Math.floor((67 * writtenBytes) / Math.max(1, totalBytes))
      if (pct !== lastPct) {
        lastPct = pct
        emit('write', pct, `${done}/${count} files`)
      }
    },
  )
  emit('verify', 94, 'output ready')
  emit('done', 100, 'complete')
  return {
    version,
    applied,
    skipped,
    removed: [...removals].sort(),
    added: additions.map((item) => item.name),
    binarySha256: resultSha,
    members: result.members,
    size: result.bytes,
    outName: 'MHFU_patched.ipa',
  }
}

export type { Addition, Part, RandomAccess, Sink }
