import { deflateSync, inflateSync } from 'fflate'

import { crc32 } from './crc32'

/** Random-access byte source: a File in the browser, a Blob in Node. */
export interface RandomAccess {
  size: number
  read(offset: number, length: number): Promise<Uint8Array>
  /** Optional zero-copy slice used to copy member data without reading it. */
  slice?(offset: number, length: number): Blob
}

export type Part = Uint8Array | Blob
export type Sink = (part: Part) => void | Promise<void>

export interface ZipEntry {
  vmade: number
  vneed: number
  flags: number
  method: number
  mtime: number
  mdate: number
  crc: number
  csize: number
  usize: number
  name: Uint8Array
  nameStr: string
  extra: Uint8Array
  comment: Uint8Array
  dstart: number
  iattr: number
  eattr: number
  off: number
}

export interface ZipIndex {
  entries: ZipEntry[]
  comment: Uint8Array
  size: number
}

export interface Addition {
  name: string
  data: Uint8Array
}

export class ZipError extends Error {}

const EOCD_SIG = 0x06054b50
const CD_SIG = 0x02014b50
const LH_SIG = 0x04034b50
const CD_HEADER = 46
const LH_HEADER = 30

// fixed timestamp so the output is deterministic
const FIXED_DATE = ((2026 - 1980) << 9) | (10 << 5) | 22
const FIXED_TIME = 0

const textDecoder = new TextDecoder('utf-8')
const textEncoder = new TextEncoder()

function dv(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
}

/** Read the EOCD and central directory without extracting the archive. */
export async function readIndex(source: RandomAccess): Promise<ZipIndex> {
  if (source.size < 22) throw new ZipError('not a zip (file too small)')
  const back = Math.min(source.size, 66000)
  const tail = await source.read(source.size - back, back)
  const tdv = dv(tail)
  let pos = -1
  for (let i = tail.length - 22; i >= 0; i--) {
    if (tdv.getUint32(i, true) === EOCD_SIG) {
      pos = i
      break
    }
  }
  if (pos < 0) throw new ZipError('EOCD not found (not a zip?)')
  const disk = tdv.getUint16(pos + 4, true)
  const cddisk = tdv.getUint16(pos + 6, true)
  const nrec = tdv.getUint16(pos + 8, true)
  const ntot = tdv.getUint16(pos + 10, true)
  const cdsize = tdv.getUint32(pos + 12, true)
  const cdoff = tdv.getUint32(pos + 16, true)
  const clen = tdv.getUint16(pos + 20, true)
  if (disk || cddisk || nrec !== ntot) {
    throw new ZipError('multi-disk archives are not supported')
  }
  if (cdoff === 0xffffffff || cdsize === 0xffffffff || nrec === 0xffff) {
    throw new ZipError('ZIP64 archives are not supported')
  }
  const comment = tail.slice(pos + 22, pos + 22 + clen)
  const cd = await source.read(cdoff, cdsize)
  const cddv = dv(cd)
  const entries: ZipEntry[] = []
  let i = 0
  while (i < cd.length) {
    if (i + CD_HEADER > cd.length || cddv.getUint32(i, true) !== CD_SIG) {
      throw new ZipError(`central directory is corrupt at offset ${i}`)
    }
    const vmade = cddv.getUint16(i + 4, true)
    const vneed = cddv.getUint16(i + 6, true)
    const flags = cddv.getUint16(i + 8, true)
    const method = cddv.getUint16(i + 10, true)
    const mtime = cddv.getUint16(i + 12, true)
    const mdate = cddv.getUint16(i + 14, true)
    const crc = cddv.getUint32(i + 16, true)
    const csize = cddv.getUint32(i + 20, true)
    const usize = cddv.getUint32(i + 24, true)
    const fnl = cddv.getUint16(i + 28, true)
    const exl = cddv.getUint16(i + 30, true)
    const cml = cddv.getUint16(i + 32, true)
    const dstart = cddv.getUint16(i + 34, true)
    const iattr = cddv.getUint16(i + 36, true)
    const eattr = cddv.getUint32(i + 38, true)
    const off = cddv.getUint32(i + 42, true)
    const start = i + CD_HEADER
    const end = start + fnl + exl + cml
    if (end > cd.length) throw new ZipError('central directory is truncated')
    if (csize === 0xffffffff || usize === 0xffffffff) {
      throw new ZipError('ZIP64 entries are not supported')
    }
    const name = cd.slice(start, start + fnl)
    entries.push({
      vmade,
      vneed,
      flags,
      method,
      mtime,
      mdate,
      crc,
      csize,
      usize,
      name,
      nameStr: textDecoder.decode(name),
      extra: cd.slice(start + fnl, start + fnl + exl),
      comment: cd.slice(start + fnl + exl, end),
      dstart,
      iattr,
      eattr,
      off,
    })
    i = end
  }
  if (entries.length !== nrec) {
    throw new ZipError(`entry count ${entries.length} != ${nrec} from EOCD`)
  }
  return { entries, comment, size: source.size }
}

export function findEntry(index: ZipIndex, name: string): ZipEntry | undefined {
  return index.entries.find((entry) => entry.nameStr === name)
}

async function dataOffset(source: RandomAccess, entry: ZipEntry): Promise<number> {
  const head = await source.read(entry.off, LH_HEADER)
  if (dv(head).getUint32(0, true) !== LH_SIG) {
    throw new ZipError('local header is corrupt for ' + JSON.stringify(entry.nameStr))
  }
  const lfnl = dv(head).getUint16(26, true)
  const lexl = dv(head).getUint16(28, true)
  return entry.off + LH_HEADER + lfnl + lexl
}

/** Read and decompress one member. */
export async function readMember(
  source: RandomAccess,
  entry: ZipEntry,
): Promise<Uint8Array> {
  const start = await dataOffset(source, entry)
  const raw = await source.read(start, entry.csize)
  if (entry.method === 0) return raw
  if (entry.method === 8) {
    const out = inflateSync(raw)
    if (out.length !== entry.usize) {
      throw new ZipError('member size mismatch for ' + JSON.stringify(entry.nameStr))
    }
    return out
  }
  throw new ZipError(
    `member ${JSON.stringify(entry.nameStr)} uses unsupported compression ${entry.method}`,
  )
}

interface Written {
  vmade: number
  vneed: number
  flags: number
  method: number
  mtime: number
  mdate: number
  crc: number
  csize: number
  usize: number
  name: Uint8Array
  extra: Uint8Array
  comment: Uint8Array
  dstart: number
  iattr: number
  eattr: number
  offset: number
}

function localHeader(entry: Written): Uint8Array {
  const out = new Uint8Array(LH_HEADER + entry.name.length + entry.extra.length)
  const view = dv(out)
  view.setUint32(0, LH_SIG, true)
  view.setUint16(4, entry.vneed, true)
  view.setUint16(6, entry.flags, true)
  view.setUint16(8, entry.method, true)
  view.setUint16(10, entry.mtime, true)
  view.setUint16(12, entry.mdate, true)
  view.setUint32(14, entry.crc, true)
  view.setUint32(18, entry.csize, true)
  view.setUint32(22, entry.usize, true)
  view.setUint16(26, entry.name.length, true)
  view.setUint16(28, entry.extra.length, true)
  out.set(entry.name, LH_HEADER)
  out.set(entry.extra, LH_HEADER + entry.name.length)
  return out
}

function centralHeader(entry: Written): Uint8Array {
  const out = new Uint8Array(
    CD_HEADER + entry.name.length + entry.extra.length + entry.comment.length,
  )
  const view = dv(out)
  view.setUint32(0, CD_SIG, true)
  view.setUint16(4, entry.vmade, true)
  view.setUint16(6, entry.vneed, true)
  view.setUint16(8, entry.flags, true)
  view.setUint16(10, entry.method, true)
  view.setUint16(12, entry.mtime, true)
  view.setUint16(14, entry.mdate, true)
  view.setUint32(16, entry.crc, true)
  view.setUint32(20, entry.csize, true)
  view.setUint32(24, entry.usize, true)
  view.setUint16(28, entry.name.length, true)
  view.setUint16(30, entry.extra.length, true)
  view.setUint16(32, entry.comment.length, true)
  view.setUint16(34, entry.dstart, true)
  view.setUint16(36, entry.iattr, true)
  view.setUint32(38, entry.eattr, true)
  view.setUint32(42, entry.offset, true)
  let at = CD_HEADER
  out.set(entry.name, at)
  at += entry.name.length
  out.set(entry.extra, at)
  at += entry.extra.length
  out.set(entry.comment, at)
  return out
}

export interface RewriteResult {
  members: number
  bytes: number
}

/**
 * Write a new ZIP: keep members as-is (raw compressed bytes), replace, drop
 * and add members. Deterministic output.
 */
export async function rewrite(
  source: RandomAccess,
  index: ZipIndex,
  sink: Sink,
  replacements: Map<string, Uint8Array>,
  removals: Set<string>,
  additions: Addition[],
  onProgress?: (
    done: number,
    total: number,
    writtenBytes: number,
    totalBytes: number,
  ) => void,
): Promise<RewriteResult> {
  const kept = index.entries.filter((entry) => !removals.has(entry.nameStr))
  const totalBytes =
    kept.reduce((sum, entry) => sum + entry.usize, 0) +
    additions.reduce((sum, item) => sum + item.data.length, 0)
  const totalMembers = kept.length + additions.length
  let done = 0
  let writtenBytes = 0
  let offset = 0
  const written: Written[] = []

  for (const entry of kept) {
    const replacement = replacements.get(entry.nameStr)
    let method = entry.method
    let crc = entry.crc
    let csize = entry.csize
    let usize = entry.usize
    let data: Part
    if (replacement) {
      const compressed = deflateSync(replacement)
      data = compressed
      method = 8
      crc = crc32(replacement)
      csize = compressed.length
      usize = replacement.length
    } else {
      const start = await dataOffset(source, entry)
      data = source.slice
        ? source.slice(start, entry.csize)
        : await source.read(start, entry.csize)
    }
    const item: Written = {
      vmade: entry.vmade,
      vneed: entry.vneed,
      flags: entry.flags & ~0x08,
      method,
      mtime: entry.mtime,
      mdate: entry.mdate,
      crc,
      csize,
      usize,
      name: entry.name,
      extra: entry.extra,
      comment: entry.comment,
      dstart: entry.dstart,
      iattr: entry.iattr,
      eattr: entry.eattr,
      offset,
    }
    const header = localHeader(item)
    await sink(header)
    offset += header.length
    await sink(data)
    offset += csize
    written.push(item)
    done += 1
    writtenBytes += usize
    onProgress?.(done, totalMembers, writtenBytes, totalBytes)
  }

  for (const addition of additions) {
    const compressed = deflateSync(addition.data)
    const name = textEncoder.encode(addition.name)
    const item: Written = {
      vmade: 0x031e,
      vneed: 20,
      flags: 0,
      method: 8,
      mtime: FIXED_TIME,
      mdate: FIXED_DATE,
      crc: crc32(addition.data),
      csize: compressed.length,
      usize: addition.data.length,
      name,
      extra: new Uint8Array(0),
      comment: new Uint8Array(0),
      dstart: 0,
      iattr: 0,
      eattr: 0,
      offset,
    }
    const header = localHeader(item)
    await sink(header)
    offset += header.length
    await sink(compressed)
    offset += compressed.length
    written.push(item)
    done += 1
    writtenBytes += addition.data.length
    onProgress?.(done, totalMembers, writtenBytes, totalBytes)
  }

  const cdStart = offset
  for (const item of written) {
    const header = centralHeader(item)
    await sink(header)
    offset += header.length
  }
  const cdSize = offset - cdStart
  const eocd = new Uint8Array(22 + index.comment.length)
  const view = dv(eocd)
  view.setUint32(0, EOCD_SIG, true)
  view.setUint16(4, 0, true)
  view.setUint16(6, 0, true)
  view.setUint16(8, written.length, true)
  view.setUint16(10, written.length, true)
  view.setUint32(12, cdSize, true)
  view.setUint32(16, cdStart, true)
  view.setUint16(20, index.comment.length, true)
  eocd.set(index.comment, 22)
  await sink(eocd)
  offset += eocd.length
  return { members: written.length, bytes: offset }
}
