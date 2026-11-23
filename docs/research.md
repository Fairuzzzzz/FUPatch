# MHFU iPad — UI Reverse Engineering Research

**Repository:** FUPatch4iPad
**Game:** Monster Hunter Freedom Unite (MH Unite), iOS v1.00.11
**Last updated:** November 22, 2026
**Status:** Ongoing; no hamburger-specific position patch implemented

The separate [Phase 4 Cockpit rendering investigation](research-phase4.md)
contains the render-dispatcher map, sprite-rendering candidates, and focused
LLDB probes.

## 1. Objectives

### Immediate

Move the partially visible hamburger menu button horizontally toward the
physical right edge of the iPad display while preserving:

- Its partial visibility, size, and vertical position.
- Its touchscreen interaction.
- Other UI elements and game behavior.
- The original game, save data, and working baseline.

### Longer-term

Determine whether MHFU has shared UI layout infrastructure that could support
independently configurable HUD positions, control sizes, hitboxes, or
scaling, device-specific layouts, and reusable layout presets. A graphical
layout editor is a possible long-term tool. These capabilities are
possibilities, not confirmed features of the engine.

## 2. Environment and binary conventions

| Component | Details |
|---|---|
| Device | iPad Air 11-inch M2 (`iPad14,8`) |
| OS / game | iPadOS 18.7.3 / MH Unite v1.00.11 |
| Patch profile | `iphone12-14` |
| Device family | `[1,2]` in the working iPad baseline |
| Repository | `E:\Archive\FUPatch4iPad` |
| Working baseline | `E:\Games\MHFU-iPad-baseline.ipa` |
| Debugging | Intel Mac with Xcode/LLDB |
| Executable UUID | `58cc55c760ca3196b5d20c2aeb64b32b` |
| Bundle identifier | `jp.co.capcom.mhp2gwd` |
| Baseline executable SHA-256 | `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4` |

All addresses below are unslid Mach-O virtual addresses unless stated
otherwise. Resolve the loaded image and current ASLR slide for each LLDB
session; previously observed runtime values are session-specific.

Previously observed runtime values included PID `29167`, slide `0x4BC0000`,
and executable base `0x104BC0000`.

Those runtime values are historical only. The working baseline is already a
verified `iphone12-14` result; do not use it as an unpatched source IPA.

## 3. Existing FUPatch coordinate findings

### Safe-area transformation

The previously examined helper is at `0x10049E4B4`. The recorded inset values
were left `141`, right `141`, top `0`, and bottom `63`. The observed horizontal
transform was:

`Xout = L + Xin * (W - L - R) / W`

This is a global coordinate-remapping lead. Its relationship to the hamburger
has not been demonstrated, and changing it could affect other UI elements.

### UI-scale candidates

| Role | Unslid address |
|---|---:|
| Patched instruction | `0x100369584` |
| Containing function entry | `0x10036952C` |
| Caller | `0x100350710` |
| Additional candidate | `0x1003D93FC` |

Breakpoints on these candidates reportedly recorded no hits during the tested
hamburger interactions and transitions. They are not established as
hamburger-specific.

The manifest labels UI-scale and safe-area patch groups, but those labels do
not prove that a patch controls the hamburger.

## 4. UIKit and native touch-input findings

### UIKit entry points

| Function | Unslid address |
|---|---:|
| `touchesBegan:withEvent:` | `0x10046328C` |
| `touchesMoved:withEvent:` | `0x100463478` |
| `touchesEnded:withEvent:` | `0x1004635F8` |
| `getTouchInfoIndex:` | `0x1004637A4` |
| Began location return | `0x100463374` |
| Moved location return | `0x10046354C` |

### Recorded taps

| Measurement | Hamburger tap | Outside tap |
|---|---:|---:|
| UIKit X | 1114.5686 | 891.9585 |
| UIKit Y | 118.4890 | 102.2159 |
| Events | 5 | 5 |
| Menu opened | Yes | No |

Both recordings produced the same generic UIKit sequence:

1. `touchesBegan`
2. `touchLocationBegan`
3. `getTouchInfoIndex`
4. `touchesEnded`
5. `getTouchInfoIndex`

The outside tap was approximately 222.61 coordinate units left and 16.27
units above the successful tap. These points are not a close hitbox-boundary
pair, and the UIKit coordinates are not established as game UI coordinates.
The generic stacks do not identify the menu-specific handler.

### Native coordinate transfer

| Function | Unslid address |
|---|---:|
| Touch-began conversion | `0x100460A24` |
| Touch-moved conversion | `0x10046085C` |
| Two-float copy helper | `0x100461C0C` |

Static analysis indicates scaled coordinates are transferred into the
`hx::system::Input` singleton, in five records with a `0x60`-byte stride.
This establishes native touch processing, not the hamburger hit-test.

### Rectangle-test candidate: deprioritized

| Role | Unslid address |
|---|---:|
| Predicate entry | `0x100460D44` |
| Return path | `0x100460D98` |
| Direct caller / callsite | `0x100007720` / `0x100007874` |

The predicate tests a recorded point against rectangle bounds; the direct
caller iterates 20-byte touch-control records. It was a generic candidate, not
a confirmed menu test.

| Session | Events | Successful hamburger activation confirmed |
|---|---:|---|
| `hamburger-native` | 0 | No |
| `hamburger-native-2` | 0 | No |
| `hamburger-confirmed` | 0 | Yes; the menu opened |

The first two sessions did not reliably confirm activation. For the confirmed
session, the tracer recorded zero events, but a separate breakpoint-ID hit
count was not captured. This strongly deprioritizes the tested predicate pair;
it does not rule out another native hit-test or dispatch mechanism.

## 5. Latest Cockpit runtime observations

The following values were reported from a confirmed LLDB session:

- The Cockpit singleton pointer was `0x10706D500` (session-specific).
- `0x10036B960` executed during interaction with Quest Info and received the
  same object pointer.
- `Cockpit + 0x544` was `0x1000`.
- `Cockpit + 0x5B7` was `0`.
- The renderer's X-anchor calculation was verified as `504 - 2 * 240 = 24`.
- With bit 6 clear, the observed path included text-format calls using `"%s"`.
- A confirmed hamburger activation did not hit the accepted-event branch at
  `0x10037D8EC` (resolved breakpoint, zero hits).

These observations confirm that the routine is used by Cockpit during Quest
Info interaction and that the tested accepted-event path did not run during
hamburger activation. They do **not** identify `0x10036B960` or its anchor as
the hamburger renderer or position.

### Historical static UI-event path

Earlier static analysis recorded the event-dispatch chain:

`0x10037D718` → `0x10037D87C` → `0x10037FFF4`

The accepted-event branch at `0x10037D8EC` was inferred to require all of:

- Dispatcher result bit 13 set.
- Dispatcher result bit 3 clear.
- The pending-transition field at `x19 + 0x12C4` equal to zero.

The branch changes per-object state around `x19 + 0x11B0`, `x19 + 0x544`, and
`x19 + 0x628`. `0x10037D934` is a follow-up state-application site.

These are generic static event/state findings, not a confirmed hamburger
handler. In the later confirmed activation, the resolved breakpoint at
`0x10037D8EC` had zero hits.

## 6. Cockpit rendering candidates

Static ARM64 analysis of the render dispatcher at `0x10037EDBC` shows that,
when `this + 0x11B0 == 1`, a selector at `this + 0x11B4` dispatches to one of
13 rendering/helper paths. Selector `2` calls `0x10036B960`, the text-heavy
routine observed at runtime.

The Phase 4 document maps all dispatcher branches and details two higher
priority sprite-path candidates:

- `0x10036A270`: descriptor-driven Cockpit element renderer, called by
  `0x10036B960`; some descriptor types route to an atlas-sprite helper.
- `0x10036B42C`: atlas-sprite quad renderer using a 12-byte source-region
  table and destination coordinates.

An alternate panel/skin path at `0x10037A9B0` is lower priority. None of these
functions or assets has been confirmed as the hamburger. No shared touch
hitbox or coordinate source has yet been demonstrated.

Earlier static analysis also marked `0x10036BA00` (`w8`) and `0x10036BA2C`
(`w27`) as candidate X/Y coordinate stores within the `0x10036B960` drawing
path. They have not been shown to store the hamburger's position.

**New runtime validation (Phase 4):** LLDB traced the closed-menu `"  Menu"`
rendering path through `0x1003A5904`, `0x10036C870`, `0x100379100`,
`0x1003788B8`, and `0x100378D6C`. A targeted, repeating breakpoint
changed the X argument from 1822 to 1622 for the atlas-564 draw call.
The user visually confirmed that the circular background behind the
**left navigation arrow** moved; the hamburger did not. This verifies
independent runtime repositioning of that specific graphic call, not
hamburger identification or movement of its touch target. See Phase 4
for the callsite condition, atlas record, and reversal procedure.

See [Phase 4 Cockpit rendering paths](research-phase4.md) for the branch
conditions, direct callees, static evidence, unknowns, and targeted LLDB
experiments. The menu-transition path at `0x10037D8EC` is deprioritized after
the confirmed zero-hit activation.

## 7. LLDB tracer and workflow

Tracer files:

- `tools/mhfu_touch_trace.py`
- `tools/mhfu_touch_trace.md`
- `tests/test_mhfu_touch_trace.py`

The tracer validates executable UUID, resolves unslid addresses against the
loaded module, captures UIKit registers and shallow stacks, and writes bounded
JSONL logs. Its optional `--native-hit-test` mode only covers the rectangle
candidate at `0x100460D44` and `0x100460D98`; it does not automate the newer
Cockpit rendering or accepted-event probes.

The tracer's seven helper tests were reported passing on Windows. Generic
UIKit tracing was exercised live on the Mac. The optional rectangle mode
recorded zero events during the confirmed menu activation.

The Mac LLDB environment previously required importing the script from
`/Users/kolynlin/lldb-scripts/` due to Desktop privacy restrictions. LLDB
Python module reloads required:

```lldb
settings set interpreter.require-overwrite false
command script import --allow-reload /Users/kolynlin/lldb-scripts/mhfu_touch_trace.py
```

Those paths and prior logs are user-reported operational notes. Confirm the
copy being imported and preserve existing JSONL evidence.

A separate copy may exist at `/Users/kolynlin/Desktop/FUPatch/`. Previously
used log files include `/Users/kolynlin/mhfu-touch.jsonl` and
`/Users/kolynlin/mhfu-native-touch.jsonl`.

The Mac's LLDB Python bindings also rejected parameterless
`SBFileSpec.GetPath()`. The tracer now uses compatible path retrieval and
validates the loaded executable UUID before installing its unslid-address
breakpoints.

## 8. Other unconfirmed leads

| Candidate | Unslid address |
|---|---:|
| Generic `glScissor` path | `0x10045CEE0` |
| OpenGL stub | `0x1004965E4` |
| `hxUICockpit.cpp` string | `0x1006027F1` |
| `hxUICockpitLobby.cpp` string | `0x100602A0C` |

These are static-analysis leads only; none is confirmed as the hamburger
renderer. Broad GL and Objective-C message-send breakpoints remain unsuitable
without a specific call-path hypothesis.

## 9. Remaining unknowns and research rules

Still unknown:

- The hamburger's exact drawing function, asset, and UI object.
- Its layout-coordinate source and actual touch hitbox.
- The menu-specific event handler and visibility state.
- Whether rendering and hit-testing share geometry or can be adjusted
  independently.
- Whether the game has reusable per-element layout infrastructure.

Research rules:

1. Separate runtime observations, static-analysis findings, and hypotheses.
2. Resolve the current slide; never hardcode a prior session's runtime base.
3. Prefer targeted high-level breakpoints over broad GL or Objective-C hooks.
4. Preserve the original IPA, working baseline, saves, and existing changes.
5. Do not patch until the hamburger element and its interaction are attributed.
6. Validate any eventual change on a separate experimental build.

## 10. Current conclusion

UIKit touch delivery and native input transfer are partially reconstructed.
The rectangle-test candidate did not fire during a confirmed activation.
The Cockpit descriptor/atlas rendering path has been confirmed at runtime,
and an atlas-564 call was visually identified as the left navigation arrow
background. The hamburger itself has not been identified.

The next milestone is to capture a descriptor/atlas draw that can be matched
visually to the hamburger and determine whether its touch target uses the same
layout data. A configurable HUD layout system remains a future possibility,
not a demonstrated engine capability.
