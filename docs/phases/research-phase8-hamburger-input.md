# Phase 8 — Right-edge placement and touch responsiveness

November 24, 2026. Session PID 30509, ASLR slide `0x404000`. All runtime pointers below are historical; never reuse them after relaunch. No persistent executable modification was made during these experiments.

## Geometry and layout

The shared geometry record 1 (+0x10 float X offset, runtime `0x106504870`) was originally -51. Earlier -426 test proved relocation. Later 0 moved right; +50 was excessive, +42 reached the edge, +35 (`0x420C0000`) was preferable but responsiveness remained intermittent. The previously suspected X clamp is not established. At +35 A/B/C were `(2303,169,81,129)` before expansion. A/B visual geometry, B rendering/interpolation read at runtime `0x1007A7D40`; C is actual input geometry. Preserve width, height and Y during placement.

Cockpit `0x1064F9500`, menu byte +0x11B5, layout ID +0x12E0, active array +0x12E8, count +0x15A4. Runtime array stride 0x70; source stride 0x40; geometry stride 0x80. Menu transitions replace descriptors. Layout source pointer array `0x100B34AE8`.

| Layout | Source base | Hamburger index | Compact record | Width field | X offset field |
|---|---|---:|---|---|---|
| 21 open | 0x10650C720 | 11 | 0x10650C9E0 | 0x10650CA00 | 0x10650CA10 |
| 23 closed | 0x10650CCA0 | 18 | 0x10650D120 | 0x10650D140 | 0x10650D150 |

Both records contain identifier 8, atlas indices 527/527, geometry index 1 and flags 0x00010001. Original compact width 51, height 81, offsets X/Y 0. Experiments set both widths to 91 (`0x42B60000`), X offsets to -40 (`0xC2200000`). C derived from A plus scaled offset and dimensions. Open converter and closed handler confirmed expanded bounds `(2239,169,145,129)` / endpoints `(2239,169,2384,298)`; A/B unchanged in converter. Proposed -20 offset was not confirmed applied. Later bounds still showed -40 expansion. Original width bits `0x424C0000`, offset `0x00000000`. Shared geometry original -51 bits `0xC24C0000`. Restore through full restart, not historical pointer writes.

## Input path

| Routine / instruction | Unslid | Runtime |
|---|---|---|
| Button handler | 0x1003BCD34 | 0x1007C0D34 |
| Read C rectangle | 0x1003BCDE0 | 0x1007C0DE0 |
| Initial search call | 0x1003BCE14 | 0x1007C0E14 |
| Search return | 0x1003BCE18 | 0x1007C0E18 |
| Touch search | 0x100460CB4 | 0x100864CB4 |
| Inclusive rectangle predicate | 0x100460BD0 | 0x100864BD0 |
| Existing touch validation | 0x100460C2C | 0x100864C2C |
| Button action dispatch function | 0x1003BDBC8 | 0x1007C1BC8 |
| Display update of touch records | 0x1004606CC | 0x1008646CC |
| Reset one touch record | 0x1004607E8 | 0x1008647E8 |
| Touch initialization | 0x100460A24 | 0x100864A24 |
| UIKit begin handler | 0x10046328C | 0x10086728C |

Watchpoint on C width identified handler, x27 descriptor, x25 index. At search call x0 manager, x1 int32 bounds (left/top/right/bottom). Search scans five records at manager+0x60, stride 0x60. Requires +0x3C==0, X>=0, +0x34!=0, then inclusive coordinate predicate. Increments +0x48 on successful selection, returns index or -1. Return stored in descriptor +0x00; negative means unassigned. Previous successful tap `(2327.28809,193.243896)` returned 0 and opened menu. Captured failed tap `(2343.48,239.01)` inside expanded bounds had +0x34=1, +0x3C=1, +0x48=0; step over confirmed w0=0xffffffff. This proves rejection of that sample, not root cause of normal-use delay.

## Touch lifecycle

UIKit begin handler passes 1 and 0 to initializer, which writes +0x30=1 and +0x38/+0x3C=0. Main-thread display update promotes +0x30 to +0x34 at runtime 0x100864724; promotes +0x38 to +0x3C at 0x100864788. Watchpoint 10 caught +0x3C transition 0→1 after release and reset at 0x100864844 (PC following instruction 0x100864848). Reset called from display update 0x1008647B4, CADisplayLink stack. It clears flags and sets coordinate vectors to -1. +0x50 is cleanup counter, reset occurs when end registered and counter >=1. +0x4C participates in begin flag lifetime. +0x54 compared with 13, sets +0x40 periodically, but initial search does not consult either. Exact event semantics outside observed paths remain provisional. UIKit and display update run on main thread, button search on thread 13. The record may retain coordinates after begin flag clears; nonnegative X does not imply currently held. Multiple retained records with both begin/end flags set were observed during interrupted tests.

## Responsiveness and ruled-out leads

User reported quick taps often failed, tapping slightly left helped, holding hamburger for approximately two seconds opened it while held, and holding an unrelated finger for a while made the second finger's hamburger tap respond immediately. No controlled baseline exists. Explicit optional button delay checks bit 26 of descriptor flags and increments +0x44 counter up to 2; closed hamburger flags 0x00010001, counter 0, so this delay is disabled. Upstream enable bit 0 set, optional bit 7 gate disabled. No explicit hold time in initial search. Polling experiment at C read with conditional auto-continue breakpoint produced 38 idle hits and 55 additional held-finger hits over roughly five seconds each; debugger overhead, imprecise intervals and interrupt race invalidate quantitative inference. Do not treat shared wake-up, throttling, edge gestures, multitouch bug or missed begin window as established. Do not bypass touch-end eligibility globally.

Safe-area helper unslid 0x10049E4B4 (runtime 0x1008A24B4) constants 141/141/0/63 at runtime 0x1008A251C; breakpoint did not hit during tested tap. No patch to helper. Earlier stale allocation tests and read watchpoint overlap were confounds, not proof of a clamp or nonexistent input consumer.

## Session close and restart plan

Breakpoints 1–9 disabled at last reported state; watchpoint 10 disabled for behavioral testing, older watchpoints presumed disabled but not all independently verified. Process reported running. User requested detach; commands `process detach` and `quit` supplied, execution not reported. Detach alone does not restore memory. Fully quit and relaunch game without debugger; ordinary baseline hamburger taps first. Then attach only if needed, refresh slide, pointer identities and layout, apply geometry-only +35 test, retest. Avoid complex finger choreography and repeated stopping breakpoints; one or two commands per iteration. Keep geometry and input experiments separate. Locate original geometry backing data and check sharing before permanent patch. No final placement, exclusive input region, baseline responsiveness or restart persistence established.
