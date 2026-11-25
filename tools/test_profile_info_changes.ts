/// <reference path="../ui/node_modules/@types/node/index.d.ts" />

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { profileInfoChanges } from '../ui/src/lib/engine'
import type { PatchManifest } from '../ui/src/lib/engine'

const manifest = JSON.parse(
  readFileSync('patches/mhfu-ios.json', 'utf8'),
) as PatchManifest

const profiles = manifest.profiles ?? []

const ipad = profiles.find(
  (profile) => profile.id === 'ipad-air-m2',
)

assert.ok(ipad, 'Production iPad profile is missing')

test('iPad profile enables native iPad support', () => {
  const changes = profileInfoChanges(manifest, ipad)

  assert.deepEqual(changes.set?.UIDeviceFamily, [1, 2])
})

test('existing profiles retain their original configuration', () => {
  const base = profileInfoChanges(manifest, null)

  for (const profile of profiles) {
    if (profile.id === 'ipad-air-m2') continue

    const changes = profileInfoChanges(manifest, profile)

    assert.deepEqual(changes, base, profile.id)
    assert.deepEqual(changes.set?.UIDeviceFamily, [1])
  }
})

test('iPad profile preserves common plist settings', () => {
  const base = profileInfoChanges(manifest, null)
  const changes = profileInfoChanges(manifest, ipad)

  assert.deepEqual(changes, {
    set: {
      ...base.set,
      UIDeviceFamily: [1, 2],
    },
    remove: base.remove,
  })
})

test('profile removals override base assignments', () => {
  const changes = profileInfoChanges(manifest, {
    ...ipad,
    info_changes: {
      remove: ['UIDeviceFamily'],
    },
  })

  assert.equal(
    Object.hasOwn(changes.set ?? {}, 'UIDeviceFamily'),
    false,
  )

  assert.ok(changes.remove?.includes('UIDeviceFamily'))
})

test('profile assignments override base removals', () => {
  const changes = profileInfoChanges(manifest, {
    ...ipad,
    info_changes: {
      set: {
        UILaunchImageFile: 'CustomLaunchImage',
      },
    },
  })

  assert.equal(
    changes.set?.UILaunchImageFile,
    'CustomLaunchImage',
  )

  assert.ok(!changes.remove?.includes('UILaunchImageFile'))
})

test('resolver does not mutate the manifest', () => {
  const before = JSON.stringify(manifest)

  for (const profile of profiles) {
    profileInfoChanges(manifest, profile)
  }

  assert.equal(JSON.stringify(manifest), before)
})

test('repeated profile resolution is deterministic', () => {
  assert.deepEqual(
    profileInfoChanges(manifest, ipad),
    profileInfoChanges(manifest, ipad),
  )
})
