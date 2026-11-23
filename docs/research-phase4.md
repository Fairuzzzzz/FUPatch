# MHFU UI research — Phase 4: Cockpit rendering paths

Main research record: [docs/research.md](research.md).

**Scope:** Static ARM64 analysis of the Cockpit render dispatcher and direct
rendering helpers. No IPA, executable, manifest, save data, or working game was
modified. Addresses below are unslid Mach-O virtual addresses for the
UUID-verified arm64 executable.

## Runtime observations supplied for this phase

The following are confirmed observations from the user's LLDB session, not
facts independently reproduced in this documentation-only update:

- The Cockpit singleton pointer was `0x10706D500` in that session only.
- `0x10036B960` received that same object pointer.
- `Cockpit + 0x544` read as `0x1000`; `Cockpit + 0x5B7` read as `0`.
- The renderer calculated an X anchor of `24`.
- Its bit-6-clear path called routines using text format strings including
  `"%s"`.
- A confirmed hamburger activation did **not** hit `0x10037D8EC`.

The object pointer and values are session-specific. The accepted-event path at
`0x10037D8EC` is deprioritized for this interaction.

## Render dispatcher

`0x10037EDBC` dispatches on Cockpit state:

1. It examines the byte at `this + 0x11B0`.
2. If that byte is `1`, it reads the selector at `this + 0x11B4`.
3. Selectors `0`–`12` enter the corresponding case below; selectors above
   `12` skip the case dispatch.
4. Afterward, bit 2 of the word at `this + 0x628` gates a shared tail call to
   `0x10036C60C`; otherwise the dispatcher returns.

| Selector | Direct callee | Static classification |
|---:|---:|---|
| 0 | `0x1003A614C` | Helper/state path; not classified as sprite drawing |
| 1 | `0x1003A6A08` | Helper/state path; not classified as sprite drawing |
| 2 | `0x10036B960` | Text-heavy HUD path; runtime confirmed for the Cockpit object |
| 3 | `0x10037F8F0` | Repeated text/layout drawing calls |
| 4 | `0x10037F790` | List/control path; draw responsibility uncertain |
| 5 | `0x10037EF14` | Text/list rendering path |
| 6 | `0x10037F06C` | Mixed UI drawing; includes typed element rendering and text |
| 7 | `0x10036C5F8` | Tail-dispatches to `0x1003AC858` |
| 8 | `0x1003A8024` | Helper called with constants `0x116` and `0x117` |
| 9 | `0x10036A04C` | Mixed element/layout rendering |
| 10 | `0x10037F530` | Text-heavy drawing path |
| 11 | `0x10037FB84` | Text/list drawing path |
| 12 | `0x10037F890` | Text/layout helper |

These labels describe visible control flow and helper use; the binary does not
provide symbols proving the user-facing name or purpose of every case.

## Sprite and element-rendering candidates

### 1. `0x10036A270` — Cockpit element descriptor dispatcher

**Priority: highest.**

- **Caller and condition:** `0x10036B960` calls it at `0x10036BC10` on the
  bit-6-clear path, which matches the supplied runtime value
  `Cockpit + 0x544 = 0x1000`. The other call at `0x10036BAE8` is in the
  bit-6-set path.
- **Evidence:** The function reads a descriptor through `x1`, including a
  type byte at descriptor offset `+0xB` and 16-bit fields at offsets
  `+0`, `+2`, `+4`, and `+6`. It applies display scale and branches on the
  descriptor type. Some branches call the atlas renderer
  `0x10036B42C`; another path calls a quad/primitive helper. It also invokes
  text-related helpers. This is evidence for a mixed, descriptor-driven UI
  renderer, not proof of a hamburger-specific object.
- **Unknown:** Which descriptor represents the hamburger; whether its touch
  target reuses the descriptor's geometry; and which state selector draws it.

**Targeted experiment:** Resolve addresses from the loaded image and stop once
at the descriptor-dispatch entry only when called from the confirmed
`0x10036B960` bit-6-clear callsite:

```lldb
script t=lldb.debugger.GetSelectedTarget(); m=next(t.GetModuleAtIndex(i) for i in range(t.GetNumModules()) if t.GetModuleAtIndex(i).GetFileSpec().GetFilename()=="MH Unite"); assert m.GetUUIDString().replace("-","").lower()=="58cc55c760ca3196b5d20c2aeb64b32b"; rt=lambda a:m.ResolveFileAddress(a).GetLoadAddress(t); err=lldb.SBError(); cockpit=t.GetProcess().ReadPointer(rt(0x100732fc0),err); assert err.Success(); bp=t.BreakpointCreateByAddress(rt(0x10036a270)); bp.SetCondition("((unsigned long long)$x0 == 0x%X) && ((unsigned long long)$x30 == 0x%X)"%(cockpit,rt(0x10036bc14))); bp.SetOneShot(True); print("bp",bp.GetID(),"Cockpit",hex(cockpit))
```

At the stop, record `x1`–`x5`, the backtrace, and the descriptor bytes. The
condition compares against the runtime singleton pointer, not the historical
`0x10706D500` value.

### 2. `0x10036B42C` — atlas-sprite quad renderer

**Priority: high; nested under candidate 1.**

- **Caller and condition:** `0x10036A270` calls it at `0x10036A310` for
  selected descriptor-type masks. Those branches pass atlas index `0x40` or
  `0x9E` in `x6`.
- **Evidence:** The function indexes a 12-byte record table at
  `0x10072E0FC` using `x6`, reads source-region fields, scales destination
  coordinates, builds multiple quad/strip commands, and submits them through
  `0x10037662C`, `0x100377E34`, `0x100375FD4`, and `0x100377D80`. This is
  strong evidence for atlas-based sprite rendering.
- **Unknown:** The visual identity of atlas entries `0x40` and `0x9E`, and
  whether either one is the hamburger.

**Targeted experiment:** Stop once at the sprite renderer entry only when it
is called from the sprite branch in `0x10036A270`, and only for the two atlas
indices seen in that branch:

```lldb
script bp2=t.BreakpointCreateByAddress(rt(0x10036b42c)); bp2.SetCondition("((unsigned long long)$x0 == 0x%X) && ((unsigned long long)$x30 == 0x%X) && (((unsigned int)$w6 == 0x40) || ((unsigned int)$w6 == 0x9e))"%(cockpit,rt(0x10036a314))); bp2.SetOneShot(True); print("bp",bp2.GetID())
```

At the stop, record `x1`–`x6` and `bt 8`. `x1`–`x4` are the candidate
destination rectangle; `x6` is the atlas selector. A hit identifies an
atlas-sprite draw in the observed Cockpit branch, not necessarily the hamburger.

### Deprioritized alternate panel path (not in the priority list)

`0x10037A9B0` is a fixed multi-part atlas/panel renderer. It uses a separate
table based at `0x10072E7D8` and emits several quads. Its typed dispatcher is
`0x1003736E4`: descriptor type `4` reaches `0x37A9B0`; types `0`/`2` and
`1`/`3` reach `0x36B42C` with different atlas indices. The descriptor
dispatcher is called in other render states, including cases routed through
`0x37F06C` and `0x37FB84`. This looks more like panel/skin artwork than a
hamburger glyph, so it is not in the first two probes.

The helper `0x100377A84` constructs a generic render-queue quad and submits it
through `0x1001F56A8`; no specific hamburger asset or selector was identified.
It remains a possible background/primitive path, not a prioritized icon
candidate.

## Shared layout and remaining uncertainty

The strongest static link is that the confirmed text-heavy renderer
`0x10036B960` passes its Cockpit `this` pointer and layout data to
`0x10036A270`, which can route typed descriptors into `0x10036B42C`. The
sprite renderer consumes position/size arguments and atlas source-region data.
This supports a shared Cockpit element-rendering pipeline.

No evidence yet shows that the hamburger uses this descriptor, atlas entry, or
the same coordinates for hit-testing. The user-reported accepted-event
breakpoint miss at `0x10037D8EC` further deprioritizes that generic transition
path; it does not rule out other event dispatchers.

**Success criterion for the next capture:** identify a descriptor/atlas
selector and destination rectangle that correspond visually to the
half-visible hamburger, then determine whether the touch path references that
same element or geometry. Do not infer identity from the shared Cockpit object
alone, and do not patch until this link is demonstrated.
