export interface SliceInfo {
  arch: string
  cputype: number
  cpusubtype: number
  offset: number
  size: number
  cryptid: number | null
  cryptoff: number | null
  encrypted: boolean
}

export interface MachOInfo {
  kind: 'fat' | 'thin'
  slices: SliceInfo[]
  size: number
}

export class MachOError extends Error {}

const FAT_MAGIC = 0xcafebabe
const FAT_MAGIC_64 = 0xcafebabf
const MH_MAGIC_64 = 0xfeedfacf
const MH_MAGIC = 0xfeedface
const LC_ENCRYPTION_INFO = 0x21
const LC_ENCRYPTION_INFO_64 = 0x2c
const CPU_TYPE_ARM64 = 0x0100000c

function archName(cputype: number, cpusubtype: number): string {
  const sub = cpusubtype & 0xff
  if (cputype === CPU_TYPE_ARM64) return sub === 2 ? 'arm64e' : 'arm64'
  if (cputype === 0x0000000c) {
    return sub === 11 ? 'armv7s' : sub === 12 ? 'armv7k' : 'armv7'
  }
  return 'cpu-' + (cputype >>> 0).toString(16)
}

function thinSlice(
  view: DataView,
  offset: number,
  magic: number,
  cputype?: number,
  cpusubtype?: number,
): SliceInfo {
  const length = view.byteLength
  if (offset + 32 > length) {
    throw new MachOError('truncated slice at offset ' + offset)
  }
  const header = magic === MH_MAGIC_64 ? 32 : magic === MH_MAGIC ? 28 : 0
  if (!header) throw new MachOError('unknown Mach-O magic')
  const cpu = cputype ?? view.getUint32(offset + 4, true)
  const sub = cpusubtype ?? view.getUint32(offset + 8, true)
  const ncmds = view.getUint32(offset + 16, true)
  let at = offset + header
  let cryptid: number | null = null
  let cryptoff: number | null = null
  for (let i = 0; i < ncmds; i++) {
    if (at + 8 > length) throw new MachOError('truncated load command')
    const cmd = view.getUint32(at, true)
    const size = view.getUint32(at + 4, true)
    if (size < 8) throw new MachOError('corrupt load command')
    if (cmd === LC_ENCRYPTION_INFO || cmd === LC_ENCRYPTION_INFO_64) {
      cryptoff = view.getUint32(at + 8, true)
      cryptid = view.getUint32(at + 16, true)
    }
    at += size
  }
  return {
    arch: archName(cpu, sub),
    cputype: cpu,
    cpusubtype: sub,
    offset,
    size: 0,
    cryptid,
    cryptoff,
    encrypted: Boolean(cryptid),
  }
}

export function analyze(data: Uint8Array): MachOInfo {
  if (data.length < 8) throw new MachOError('file is too short')
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  const be = view.getUint32(0, false)
  if (be === FAT_MAGIC || be === FAT_MAGIC_64) {
    const count = view.getUint32(4, false)
    if (count === 0 || count > 16) {
      throw new MachOError('unreasonable fat slice count: ' + count)
    }
    const wide = be === FAT_MAGIC_64
    const entry = wide ? 32 : 20
    const slices: SliceInfo[] = []
    for (let i = 0; i < count; i++) {
      const base = 8 + i * entry
      if (base + entry > data.length) throw new MachOError('truncated fat header')
      const cpu = view.getUint32(base, false)
      const sub = view.getUint32(base + 4, false)
      let start: number
      let size: number
      if (wide) {
        start = Number(view.getBigUint64(base + 8, false))
        size = Number(view.getBigUint64(base + 16, false))
      } else {
        start = view.getUint32(base + 8, false)
        size = view.getUint32(base + 12, false)
      }
      if (start + size > data.length) {
        throw new MachOError('slice ' + i + ' runs past the end of the file')
      }
      const sliceView = new DataView(
        data.buffer,
        data.byteOffset + start,
        size,
      )
      let slice: SliceInfo
      try {
        const magic = sliceView.getUint32(0, true)
        slice = thinSlice(sliceView, 0, magic, cpu, sub)
      } catch (error) {
        if (!(error instanceof MachOError)) throw error
        slice = {
          arch: archName(cpu, sub),
          cputype: cpu,
          cpusubtype: sub,
          offset: start,
          size,
          cryptid: null,
          cryptoff: null,
          encrypted: false,
        }
      }
      slice.offset = start
      slice.size = size
      slices.push(slice)
    }
    return { kind: 'fat', slices, size: data.length }
  }
  const le = view.getUint32(0, true)
  if (le === MH_MAGIC_64 || le === MH_MAGIC) {
    const slice = thinSlice(view, 0, le)
    slice.size = data.length
    return { kind: 'thin', slices: [slice], size: data.length }
  }
  throw new MachOError('not a Mach-O file')
}

export function findArm64(info: MachOInfo): SliceInfo | null {
  let fallback: SliceInfo | null = null
  for (const slice of info.slices) {
    if (slice.arch === 'arm64') return slice
    if (slice.arch === 'arm64e' && !fallback) fallback = slice
  }
  return fallback
}

export function extract(data: Uint8Array, slice: SliceInfo): Uint8Array {
  return data.slice(slice.offset, slice.offset + slice.size)
}

export function replaceSlice(
  data: Uint8Array,
  slice: SliceInfo,
  next: Uint8Array,
): Uint8Array {
  if (next.length !== slice.size) {
    throw new MachOError(
      `new slice size ${next.length} != ${slice.size}`,
    )
  }
  const out = data.slice()
  out.set(next, slice.offset)
  return out
}
