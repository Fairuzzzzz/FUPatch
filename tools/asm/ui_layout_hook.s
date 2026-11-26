
// MHFU iOS 1.00.11 — iPad hamburger and shared button layout.
//
// Hook:   0x1003A35D0
// Cave:   0x10049E900
// Return: 0x1003A35D4
// Size:   200 bytes
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
.globl _ui_layout_hook

_ui_layout_hook:

    // The hamburger path keeps its Phase 12 stores and return address.
    ldr     w8, [x20, #0x00]
    cmp     w8, #8
    b.ne    Lshared_button

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

Lshared_button:
    // w8 still holds the full compact identifier. 8 << 12 is 0x8000.
    cmp     w8, #8, lsl #12
    b.ne    original
    ldr     w8, [x20, #0x04]
    cmp     w8, #556
    b.ne    original
    ldr     w8, [x20, #0x08]
    cmp     w8, #556
    b.ne    original
    ldr     w8, [x4]
    cmp     w8, #105
    b.ne    original

    // Index 35 shares this geometry signature. Its control is unidentified.
    ldr     w8, [x20, #0x0c]
    cmp     w8, #25
    b.eq    Lextend_height
    cmp     w8, #26
    b.eq    Lextend_height
    cmp     w8, #27
    b.eq    Lextend_height
    cmp     w8, #35
    b.ne    original

Lextend_height:
    movz    w8, #0x4300, lsl #16    // 128.0f
    str     w8, [x4, #0x24]
    str     w8, [x4, #0x54]
    str     w8, [x20, #0x24]
    b       original
