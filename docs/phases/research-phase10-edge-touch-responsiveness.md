# Phase 10 — Screen-Edge Touch Responsiveness

**Project:** FUPatch4iPad  
**Date:** 2026-11-24  
**Status:** Runtime fix successfully tested; permanent implementation pending

## 1. Objective

Resolve the unreliable touch response near the right screen edge without changing MHFU's internal input-processing logic or compromising the hamburger geometry finalized in Phase 9.

## 2. Evidence and diagnosis

The original hamburger responded normally after a clean restart. In PID 30733, changing only the shared geometry X offset reproduced the responsiveness problem near the edge:

| X offset | Observed response |
|---:|---|
| -51 (original) | Normal taps worked |
| 0 | Every click worked |
| +20 | Every click worked |
| +35 | Sustained presses needed |

Earlier experiments also showed that holding a second finger could improve response, and that a failed touch could have valid coordinates but an already registered touch-end flag (`+0x3C = 1`). Those observations did not establish a defect in the game's touch lifecycle. The explicit per-button delay flag (bit 26 of `0x00010001`) was disabled.

The position-dependent failure, including ignored taps around the screen edge, motivated investigation of UIKit system gesture arbitration. The successful intervention below strongly supports that diagnosis. The precise OS gesture recognizer and timing mechanism were not independently traced.

## 3. Static inspection

From a separate Mac terminal:

```bash
strings "$HOME/Code/FUPatch4iPad-analysis/MH Unite" | grep -iE 'preferredScreenEdges|DeferringSystemGestures|delaysTouches|GestureRecognizer|touchesCancelled'
```

Observed output:

```text
touchesCancelled:withEvent:
```

No gesture-deferral selector was found by this search. This is supporting evidence, not proof of the absence of every possible gesture-related implementation.

## 4. Successful LLDB runtime experiment

### 4.1 Environment

- Game: MH Unite, iOS ARM64 (project baseline 1.00.11).
- Device: iPad Air M2, iPadOS 18.7.3 (previously recorded project environment).
- PID: `30733`.
- ASLR slide: `0x4E6C000`.
- Root controller instance: `0x10B43A4E0` (session-specific).
- Controller class: `RootViewController`.

The Phase 9 geometry and hitbox modifications were already active. Diagnostic breakpoints had been disabled for functional testing.

### 4.2 Identify the controller and baseline preference

With the process stopped:

```lldb
expression -l objc++ -O -- (id)[(id)[(id)[UIApplication sharedApplication] keyWindow] rootViewController]
```

Observed:

```text
<RootViewController: 0x10b43a4e0>
```

```lldb
expression -l objc++ -- (unsigned long)[(id)0x10B43A4E0 preferredScreenEdgesDeferringSystemGestures]
```

Observed: `(unsigned long) $3 = 0`.

The controller requested no screen-edge system gesture deferral.

### 4.3 Install the override

The initial attempt failed to compile because `IMP` was undeclared. Importing the Objective-C runtime module resolved that issue:

```lldb
expression -l objc++ -- @import ObjectiveC;
expression -l objc++ -- (bool)class_addMethod((Class)NSClassFromString(@"RootViewController"), @selector(preferredScreenEdgesDeferringSystemGestures), (IMP)imp_implementationWithBlock(^unsigned long(id self) { return 8UL; }), "Q@:")
```

Observed: `(bool) $4 = true`.

This adds a class-local implementation returning `8`, corresponding to `UIRectEdgeRight`. It does not replace the superclass implementation or patch the game's touch-search functions.

### 4.4 Refresh UIKit's preference and test

The following commands were supplied for verification and refresh:

```lldb
expression -l objc++ -- (unsigned long)[(id)0x10B43A4E0 preferredScreenEdgesDeferringSystemGestures]
expression -l objc++ -- (void)[(id)0x10B43A4E0 setNeedsUpdateOfScreenEdgesDeferringSystemGestures]
continue
```

Expected getter value: `8`. The individual verification and refresh command outputs were not pasted into the conversation, so they are not recorded as independently observed results.

The user reported: **“Amazing it works”** after the above instructions, confirming a successful functional test of the edge-touch fix. No quantified latency, repeated-trial count, or other-edge regression test was recorded.

## 5. Preserve Phase 9 configuration

The gesture experiment did not require further geometry or hitbox changes.

| Parameter | Original | Approved runtime value | Float bits |
|---|---:|---:|---|
| Geometry X offset | -51 | 12.5 | `0x41480000` |
| Geometry Y offset | 106 | 106 | `0x42D40000` |
| Visual width | 51 | 76.5 | `0x42990000` |
| Visual height | 81 | 121.5 | `0x42F30000` |
| Horizontal/vertical scale | 1 | 1 | `0x3F800000` |
| Hitbox width (both layouts) | 51 | 76.5 | `0x42990000` |
| Hitbox height (both layouts) | 81 | 121.5 | `0x42F30000` |

Session-specific addresses:

- Shared geometry record: `0x10AF6C860`; X/Y at `+0x10/+0x14`, width/height at `+0x20/+0x24`.
- Compact hamburger record A: `0x10AF6F7E0`; hitbox dimensions at `0x10AF6F800` and `0x10AF6F804`.
- Compact hamburger record B: `0x10AF749E0`; hitbox dimensions at `0x10AF74A00` and `0x10AF74A04`.
- Measured final rectangles (second converted layout): primary visual, secondary visual and touch hitbox each `(2267, 169, 122, 194)` in internal coordinates.

Both compact records were modified and menu operation was successfully tested. Only the second layout's final calculated rectangle was independently read back. Internal coordinates are not a verified direct mapping to screenshot pixels.

## 6. Permanent implementation requirements

The intended Objective-C behavior is:

```objc
- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures {
    return UIRectEdgeRight;
}
```

When installing or changing the preference dynamically, request an update on the relevant view controller on the main thread:

```objc
[self setNeedsUpdateOfScreenEdgesDeferringSystemGestures];
```

This is a semantic reference, not an implemented permanent binary patch. Choose an integration mechanism appropriate to the project's existing executable patching and signing workflow. A class-local runtime registration during initialization or an equivalent native method implementation are candidate approaches, not validated implementations. Preserve right-edge-only scope; do not defer all edges unnecessarily. Gesture deferral requests priority for app interaction and does not imply complete disabling of system navigation.

For compatibility, check API availability if supporting OS versions before this UIKit API was introduced. Ensure the override is installed before the relevant preference is evaluated, or request a refresh afterward. Do not hardcode session-specific heap addresses. Verify the expected executable identity and original data before applying any permanent geometry changes. Make repeated installation safe and handle an existing class-local method explicitly rather than assuming `class_addMethod` always succeeds.

## 7. Validation checklist

- [x] Original hamburger works in a clean runtime.
- [x] Position-dependent touch failure reproduced with geometry-only changes.
- [x] Root controller baseline gesture preference read as zero.
- [x] Right-edge-only runtime method added successfully.
- [x] User reported successful edge-touch behavior after intervention.
- [ ] Independently record getter value after override installation.
- [ ] Independently verify the other layout's calculated hitbox.
- [ ] Locate permanent backing data for finalized geometry and compact records.
- [ ] Implement persistent geometry, hitbox and gesture-deferral changes.
- [ ] Verify normal opening and closing after a full restart without LLDB.
- [ ] Verify taps on the visible rightmost portion and ordinary controls elsewhere.
- [ ] Check system navigation gestures and other screen edges for unintended effects.
- [ ] Verify rotation and supported device/OS configurations as applicable.

## 8. Resume point

Preserve the current successful runtime configuration while planning the permanent patch. The underlying gesture-arbitration explanation is strongly supported by the targeted intervention, but the precise OS timing mechanism remains unconfirmed. There is no current evidence that bypassing the game's legitimate touch-end eligibility checks is necessary.

All modifications described here remain temporary until implemented in a persistent patch and verified after restart. The next milestone is permanent implementation, not further geometry tuning or global touch-filter modification.

Suggested commit:

```text
docs: document right-edge gesture deferral fix
```
