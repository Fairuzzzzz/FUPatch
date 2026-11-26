
// MHFU iOS 1.00.11 — iPad bottom- and right-edge gesture deferral.
//
// Hook:   0x1003545D0
// Cave:   0x10049EA00
// Return: 0x1003545D4
// Size:   156 bytes
//
// Registers preferredScreenEdgesDeferringSystemGestures
// on RootViewController before UIApplicationMain.
//
// The custom method returns UIRectEdgeBottom | UIRectEdgeRight (12).
//
// All address-dependent instructions are encoded for
// the intended virtual address of this helper.

.text
.p2align 2
.globl _gesture_hook

_gesture_hook:

    // Preserve frame pointer and return address.
    stp     x29, x30, [sp, #-16]!
    mov     x29, sp

    // dlsym(RTLD_DEFAULT, "sel_registerName")
    mov     x0, #-2
    adr     x1, selector_function_name

    // BL 0x100496CF8 (dlsym).
    .inst   0x97ffe0ba

    // Skip registration if lookup failed.
    cbz     x0, done

    // Register the gesture-deferral selector.
    mov     x8, x0
    adr     x0, gesture_selector
    blr     x8
    cbz     x0, done

    // Prepare class_addMethod arguments.
    mov     x1, x0

    // ADRP x0, 0x10069D000.
    .inst   0xf0000fe0

    // RootViewController class object.
    add     x0, x0, #0x158

    // Custom implementation and method type encoding.
    adr     x2, gesture_method
    adr     x3, method_types

    // BL 0x1004969EC (class_addMethod).
    .inst   0x97ffdfec

done:

    // Restore original stack and registers.
    ldp     x29, x30, [sp], #16

    // Reproduce displaced ADRP x8, 0x10069C000.
    .inst   0xd0000fe8

    // Return to original startup at 0x1003545D4.
    .inst   0x17fad6e3

.p2align 2

gesture_method:

    mov     x0, #12
    ret

selector_function_name:
    .asciz "sel_registerName"

gesture_selector:
    .asciz "preferredScreenEdgesDeferringSystemGestures"

method_types:
    .asciz "Q16@0:8"

.p2align 2
