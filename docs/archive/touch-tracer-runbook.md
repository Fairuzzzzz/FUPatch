# Archived: MHFU LLDB Touch Tracer Runbook

This runbook is retained for historical reproducibility. The current
hamburger-specific hitbox remains unresolved; see [research.md](../research.md).

This script records touch-entry registers, selected `CGPoint` return registers,
thread IDs, and shallow call stacks. Its optional native hit-test mode traces
the input subsystem's point-in-rectangle predicate without enabling the UIKit
touch breakpoints. It does not read target memory or modify the game.
Breakpoint callbacks auto-continue; no system-wide functions such as
`objc_msgSend` are instrumented.

## Prerequisites

- A Mac with Xcode/LLDB and a USB-paired iPad.
- Developer Mode enabled on the iPad (`Settings → Privacy & Security →
  Developer Mode`) and the Mac trusted.
- LLDB must be permitted to attach to the installed app. A development-signed
  app with `get-task-allow` allowed by its provisioning profile is normally
  required. The entitlement in the IPA before Sideloadly signs it does not
  establish the final installed signature.
- Use the already-running app first. Do not reinstall or replace the working
  app just to run this tracer.

Apple’s current Xcode device-support table lists Xcode 26.6 for iOS 15 and
later, which includes iPadOS 18.7.3. See
[Xcode system requirements](https://developer.apple.com/xcode/system-requirements/),
[Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device),
and [development provisioning profiles](https://developer.apple.com/help/account/provisioning-profiles/create-a-development-provisioning-profile/).

## Attach and trace one tap

Attach Xcode to the running **MH Unite** process. In Xcode, use **Debug →
Attach to Process**, or use the LLDB console already attached to the app:

```lldb
command script import /path/to/mhfu_touch_trace.py
mhfu-touch-start hamburger --path ~/Desktop/mhfu-touch.jsonl --max-events 100
```

Tap the visible hamburger portion once, then stop:

```lldb
mhfu-touch-stop
mhfu-touch-show hamburger 20
```

Record a nearby control tap using a separate label:

```lldb
mhfu-touch-start outside --path ~/Desktop/mhfu-touch.jsonl --max-events 100
```

Tap just outside the hamburger, then:

```lldb
mhfu-touch-stop
mhfu-touch-compare hamburger outside
mhfu-touch-remove
```

The default capture includes `touchesBegan`, `touchesMoved`, `touchesEnded`,
`getTouchInfoIndex`, plus breakpoints immediately after `locationInView:` in
the began/moved handlers to capture `d0/d1` as candidate CGPoint values.
Coordinate-conversion helpers are optional:

```lldb
mhfu-touch-start hamburger --include-conversion --max-events 80 --move-interval 0.1
```

`--include-conversion` adds the known point-conversion/copy routines. This may
produce more events; the tracer rate-limits moved events and caps each session.
Use `--no-points` to omit the post-`locationInView:` samples.

## Optional native rectangle-test experiment

Static ARM64 analysis shows `touchesBegan:` calls `0x100460A24` to transfer a
scaled point into one of five records in the C++ `hx::system::Input` singleton;
`touchesMoved:` calls `0x10046085C` to update the record. `0x100461C0C` is a
two-float copy helper. The records have a `0x60`-byte stride. A downstream
helper at `0x100460D44` reads a record point and compares it with four integer
rectangle bounds, returning a slot or a negative status. Its direct caller is
`0x100007720` (callsite `0x100007874`), which iterates 20-byte touch-control
records. This is an evidence-backed native rectangle-test candidate, but the
static path does **not** establish that it is the menu's hamburger hit-test.

The optional mode installs only two narrow breakpoints: predicate entry
`0x100460D44` (input object, bounds pointer, slot index, return address) and
its shared return path `0x100460D98` (return code in `x0`). It records pointer
values but does not dereference them. Entries and returns are independently
rate-limited by `--native-interval` (default 0.10 seconds), and remain bounded
by `--max-events`.

```lldb
mhfu-touch-start hamburger-native --native-hit-test --native-interval 0.1 --max-events 80 --stack-depth 12 --path ~/Desktop/mhfu-touch.jsonl
```

Tap the hamburger once, then inspect and stop:

```lldb
mhfu-touch-stop
mhfu-touch-show hamburger-native 40
```

Repeat with `outside-native` while tapping the same nearby outside point:

```lldb
mhfu-touch-start outside-native --native-hit-test --native-interval 0.1 --max-events 80 --stack-depth 12 --path ~/Desktop/mhfu-touch.jsonl
```

Then:

```lldb
mhfu-touch-stop
mhfu-touch-compare hamburger-native outside-native
mhfu-touch-remove
```

The result event's `x0` is the native predicate result (low 32 bits interpreted
as signed: a slot index or a negative status). Compare the caller stacks,
slot index, and result across the two labels. A hit at this function is not by
itself proof of a hamburger hit; if it is not reached, or its caller remains
the touch-control mapper, the menu-specific consumer still needs to be found.

The JSONL file is appended to, with session-start, event, and session-end
records. Labels remain available to `mhfu-touch-show` and
`mhfu-touch-compare` only for the lifetime of the LLDB script session.
`mhfu-touch-status` reports the active event count while recording and retains
the last stopped session's count afterward.

## Address and safety behavior

The tracer locates the loaded `MH Unite` module, checks its UUID against the
known arm64 build, resolves each unslid address through LLDB, and derives the
current slide. It never hardcodes a prior session’s slide. The supplied touch
entry addresses are unslid Mach-O virtual addresses:

| Function | Address |
|---|---:|
| `touchesBegan:withEvent:` | `0x10046328C` |
| `touchesMoved:withEvent:` | `0x100463478` |
| `touchesEnded:withEvent:` | `0x1004635F8` |
| `getTouchInfoIndex:` | `0x1004637A4` |
| `touchesBegan` location return | `0x100463374` |
| `touchesMoved` location return | `0x10046354C` |
| Optional touch conversion | `0x100460A24`, `0x10046085C`, `0x100461C0C` |
| Native rectangle predicate entry/return | `0x100460D44`, `0x100460D98` |

If the module UUID differs, the tracer refuses to install breakpoints. It reads
register values only; pointer values are logged, never dereferenced. Run
`mhfu-touch-stop` to disable recording and `mhfu-touch-remove` to delete only
the tracer-created breakpoints.

## Interpretation limits

The point samples are UIKit `locationInView:` results, not proven hamburger
hitbox coordinates. Static analysis establishes transfer into the native input
records and a generic rectangle predicate, but no menu-specific hit-test or
hamburger state transition has yet been attributed. The tracer reports call
stacks and differences between labels; it does not label a tap as “hamburger
hit” or infer a rendering path. Runtime caller/rectangle evidence or a
menu-state transition is still needed before making that attribution.
