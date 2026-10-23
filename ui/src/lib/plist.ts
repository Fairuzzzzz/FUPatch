export class PlistError extends Error {}

function startsWith(bytes: Uint8Array, text: string): boolean {
  if (bytes.length < text.length) return false
  for (let i = 0; i < text.length; i++) {
    if (bytes[i] !== text.charCodeAt(i)) return false
  }
  return true
}

function readUInt(bytes: Uint8Array, offset: number, size: number): number {
  let value = 0
  for (let i = 0; i < size; i++) value = value * 256 + bytes[offset + i]
  return value
}

/** Parse an Apple binary property list (bplist00). */
export function parseBinaryPlist(bytes: Uint8Array): unknown {
  if (bytes.length < 40 || !startsWith(bytes, 'bplist00')) {
    throw new PlistError('not a binary property list')
  }
  const trailer = bytes.length - 32
  const offsetSize = bytes[trailer + 6]
  const refSize = bytes[trailer + 7]
  const numObjects = readUInt(bytes, trailer + 8, 8)
  const topObject = readUInt(bytes, trailer + 16, 8)
  const offsetTable = readUInt(bytes, trailer + 24, 8)
  if (!offsetSize || !refSize || numObjects < 1) {
    throw new PlistError('corrupt binary property list trailer')
  }
  const offsets: number[] = []
  for (let i = 0; i < numObjects; i++) {
    offsets.push(readUInt(bytes, offsetTable + i * offsetSize, offsetSize))
  }
  const cache = new Map<number, unknown>()

  const lengthAt = (offset: number): [number, number] => {
    const low = bytes[offset] & 0x0f
    if (low !== 0x0f) return [low, offset + 1]
    const marker = bytes[offset + 1]
    if (marker >> 4 !== 0x1) throw new PlistError('bad length object')
    const size = 1 << (marker & 0x0f)
    return [readUInt(bytes, offset + 2, size), offset + 2 + size]
  }

  const object = (ref: number): unknown => {
    if (ref < 0 || ref >= numObjects) throw new PlistError('bad object reference')
    if (cache.has(ref)) return cache.get(ref)
    const offset = offsets[ref]
    const marker = bytes[offset]
    const kind = marker >> 4
    const low = marker & 0x0f
    let value: unknown
    if (kind === 0x0) {
      if (low === 0x8) value = false
      else if (low === 0x9) value = true
      else if (low === 0x0) value = null
      else throw new PlistError('unknown simple object')
    } else if (kind === 0x1) {
      const size = 1 << low
      let number = 0
      for (let i = 0; i < size; i++) number = number * 256 + bytes[offset + 1 + i]
      value = number
    } else if (kind === 0x2) {
      const size = 1 << low
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
      value = size === 4 ? view.getFloat32(offset + 1, false) : view.getFloat64(offset + 1, false)
    } else if (kind === 0x3) {
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
      const seconds = view.getFloat64(offset + 1, false)
      value = new Date(Date.UTC(2001, 0, 1) + seconds * 1000)
    } else if (kind === 0x4) {
      const [size, start] = lengthAt(offset)
      value = bytes.slice(start, start + size)
    } else if (kind === 0x5) {
      const [size, start] = lengthAt(offset)
      let text = ''
      for (let i = 0; i < size; i++) text += String.fromCharCode(bytes[start + i])
      value = text
    } else if (kind === 0x6) {
      const [size, start] = lengthAt(offset)
      let text = ''
      for (let i = 0; i < size; i++) {
        text += String.fromCharCode(
          (bytes[start + i * 2] << 8) | bytes[start + i * 2 + 1],
        )
      }
      value = text
    } else if (kind === 0x8) {
      value = { UID: readUInt(bytes, offset + 1, low + 1) }
    } else if (kind === 0x0a || kind === 0x0c) {
      const [size, start] = lengthAt(offset)
      const items: unknown[] = []
      for (let i = 0; i < size; i++) {
        items.push(object(readUInt(bytes, start + i * refSize, refSize)))
      }
      value = items
    } else if (kind === 0x0d) {
      const [size, start] = lengthAt(offset)
      const dict: Record<string, unknown> = Object.create(null)
      for (let i = 0; i < size; i++) {
        const key = object(readUInt(bytes, start + i * refSize, refSize))
        const item = object(
          readUInt(bytes, start + (size + i) * refSize, refSize),
        )
        if (typeof key !== 'string') throw new PlistError('non-string dictionary key')
        dict[key] = item
      }
      value = dict
    } else {
      throw new PlistError('unsupported binary plist object type')
    }
    cache.set(ref, value)
    return value
  }

  return object(topObject)
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

const BASE64 =
  'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

function base64(data: Uint8Array): string {
  let out = ''
  for (let i = 0; i < data.length; i += 3) {
    const a = data[i]
    const b = i + 1 < data.length ? data[i + 1] : 0
    const c = i + 2 < data.length ? data[i + 2] : 0
    out += BASE64[a >> 2]
    out += BASE64[((a & 3) << 4) | (b >> 4)]
    out += i + 1 < data.length ? BASE64[((b & 15) << 2) | (c >> 6)] : '='
    out += i + 2 < data.length ? BASE64[c & 63] : '='
  }
  return out
}

function xmlValue(value: unknown, indent: string): string {
  const inner = indent + '\t'
  if (value === null || value === undefined) return '<string></string>'
  if (typeof value === 'boolean') return value ? '<true/>' : '<false/>'
  if (typeof value === 'number') {
    return Number.isInteger(value)
      ? `<integer>${value}</integer>`
      : `<real>${value}</real>`
  }
  if (typeof value === 'string') {
    return `<string>${escapeXml(value)}</string>`
  }
  if (value instanceof Date) {
    return `<date>${value.toISOString().replace(/\.\d{3}Z$/, 'Z')}</date>`
  }
  if (value instanceof Uint8Array) {
    return `<data>${base64(value)}</data>`
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '<array/>'
    const body = value.map((item) => inner + xmlValue(item, inner)).join('\n')
    return `<array>\n${body}\n${indent}</array>`
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const keys = Object.keys(record).sort()
    if (keys.length === 0) return '<dict/>'
    const body = keys
      .map(
        (key) =>
          `${inner}<key>${escapeXml(key)}</key>\n${inner}${xmlValue(record[key], inner)}`,
      )
      .join('\n')
    return `<dict>\n${body}\n${indent}</dict>`
  }
  throw new PlistError('cannot serialize plist value')
}

/** Serialize a property list as XML. iOS accepts XML and binary Info.plist. */
export function serializePlist(value: unknown): Uint8Array {
  const text =
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ' +
    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n' +
    '<plist version="1.0">\n' +
    xmlValue(value, '') +
    '\n</plist>\n'
  return new TextEncoder().encode(text)
}

export function parsePlist(bytes: Uint8Array): unknown {
  if (startsWith(bytes, 'bplist00')) return parseBinaryPlist(bytes)
  if (startsWith(bytes, '<?xml') || startsWith(bytes, '<plist')) {
    throw new PlistError('XML Info.plist is not supported (binary plist expected)')
  }
  throw new PlistError('unknown Info.plist format')
}
