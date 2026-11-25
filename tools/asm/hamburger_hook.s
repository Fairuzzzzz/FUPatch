
// MHFU iOS 1.00.11 — iPad hamburger geometry and hitbox hook.
//
// Hook:   0x1003A35D0
// Cave:   0x10049E900
// Return: 0x1003A35D4
// Size:   100 bytes
//
// Registers at entry:
//   x19: Destination descriptor
//   x20: Compact layout record
//   x21: Geometry table base
//   x4:  Selected geometry record
//
// Only w8 is used as a scratch register.
// The displaced instruction restores x8 before returning.

.text
.p2align 2
.globl _hamburger_hook

_hamburger_hook:

    // Verify compact record type.
    ldr     w8, [x20, #0x00]
    cmp     w8, #8
    b.ne    original

    // Verify both atlas indices.
    ldr     w8, [x20, #0x04]
    cmp     w8, #527
    b.ne    original

    ldr     w8, [x20, #0x08]
    cmp     w8, #527
    b.ne    original

    // Verify geometry index.
    ldr     w8, [x20, #0x0c]
    cmp     w8, #1
    b.ne    original

    // Verify geometry type.
    ldr     w8, [x4]
    cmp     w8, #99
    b.ne    original

    // Geometry X = 12.5.
    movz    w8, #0x4148, lsl #16
    str     w8, [x4, #0x10]

    // Geometry and hitbox width = 76.5.
    movz    w8, #0x4299, lsl #16
    str     w8, [x4, #0x20]
    str     w8, [x20, #0x20]

    // Geometry and hitbox height = 121.5.
    movz    w8, #0x42f3, lsl #16
    str     w8, [x4, #0x24]
    str     w8, [x20, #0x24]

original:

    // Displaced original instruction.
    ldrsw   x8, [x4]

    // Branch from 0x10049E960 to 0x1003A35D4.
    .inst   0x17fc131d
