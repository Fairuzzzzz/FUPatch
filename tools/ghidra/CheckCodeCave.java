
// Check zero-filled code-cave candidates and incoming references.
//@category MHFU

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class CheckCodeCave extends GhidraScript {

    @Override
    public void run() throws Exception {

        Address start = askAddress(
            "Code Cave",
            "Starting address (inclusive):"
        );

        int size = askInt(
            "Code Cave",
            "Region size in bytes:"
        );

        if (size <= 0) {
            printerr("Region size must be positive.");
            return;
        }

        Address end = start.addNoWrap(size - 1L);

        int nonZeroBytes = 0;
        int totalRefs = 0;
        int nonExecutableBytes = 0;

        println("Scanning: " + start + " - " + end);
        println("Requested size: " + size + " bytes");
        println("");

        monitor.initialize(size);

        for (int i = 0; i < size; i++) {

            monitor.checkCancelled();
            monitor.setProgress(i + 1);

            Address addr = start.add(i);

            MemoryBlock block =
                currentProgram.getMemory().getBlock(addr);

            if (block == null || !block.isInitialized()) {
                printerr("Uninitialized or unmapped memory: " + addr);
                printerr("Scan aborted.");
                return;
            }

            if (!block.isExecute()) {
                nonExecutableBytes++;
            }

            byte value = currentProgram.getMemory().getByte(addr);

            if (value != 0) {
                nonZeroBytes++;

                println(String.format(
                    "NONZERO: %s = 0x%02X",
                    addr,
                    value & 0xFF
                ));
            }

            ReferenceIterator refs =
                currentProgram.getReferenceManager()
                    .getReferencesTo(addr);

            while (refs.hasNext()) {

                Reference ref = refs.next();
                totalRefs++;

                println(
                    "REFERENCE: " +
                    ref.getFromAddress() + " -> " +
                    ref.getToAddress() + " | " +
                    ref.getReferenceType()
                );
            }
        }

        println("");
        println("===== SUMMARY =====");
        println("Bytes scanned: " + size);
        println("Nonzero bytes: " + nonZeroBytes);
        println("References: " + totalRefs);
        println("Non-executable bytes: " + nonExecutableBytes);

        if (nonZeroBytes == 0 &&
            totalRefs == 0 &&
            nonExecutableBytes == 0) {

            println("Result: CANDIDATE PASSED");

        } else {

            println("Result: CANDIDATE REQUIRES REVIEW");
        }

        println("===================");
        println("Indirect references may remain undetected.");
    }
}
