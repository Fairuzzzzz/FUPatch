import manifestJson from '../../../patches/mhfu-ios.json'
import storyboard from '../../../assets/LaunchScreen.storyboard?raw'

import type { PatchManifest } from './engine'

export const MANIFEST = manifestJson as unknown as PatchManifest

/** Member contents referenced by ``members_add[].source``. */
export const ADDITIONS: Record<string, Uint8Array> = {
  'assets/LaunchScreen.storyboard': new TextEncoder().encode(storyboard),
}
