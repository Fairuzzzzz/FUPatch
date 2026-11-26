
// Inspect system texture pointer table and surrounding data.
//@category MHFU

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Data;
import ghidra.program.model.mem.Memory;

public class FindResidesReferences extends GhidraScript {

    private static final long TABLE = 0x1006F4ED0L;
    private static final int RANGE = 0x100;

    @Override
    public void run() throws Exception {

        Memory memory = currentProgram.getMemory();

        println("=== System Resource Table Inspection ===");
        println("");

        for (int offset = -RANGE;
             offset <= RANGE;
             offset += 8) {

            monitor.checkCancelled();

            Address address = toAddr(TABLE + offset);

            long value = memory.getLong(address);

            String description = "";

            if (value != 0) {
                try {
                    Address target = toAddr(value);

                    if (memory.contains(target)) {
                        Data data = getDataAt(target);

                        if (data != null &&
                            data.getValue() instanceof String) {

                            description = " -> \"" +
                                data.getValue() + "\"";

                        } else {
                            description = " -> " + target;
                        }
                    }
                } catch (Exception ignored) {
                    // Not a valid mapped pointer.
                }
            }

            println(String.format(
                "%s | %+5d | 0x%016X%s%s",
                address,
                offset,
                value,
                description,
                offset == 0 ? "  <-- ENGLISH RESIDES" : ""
            ));

            Reference[] refs = getReferencesTo(address);

            for (Reference ref : refs) {

                Address from = ref.getFromAddress();
                Function function = getFunctionContaining(from);

                println("    XREF: " + from
                    + " | " + ref.getReferenceType()
                    + (function != null
                        ? " | " + function.getName()
                        + " @ " + function.getEntryPoint()
                        : ""));
            }
        }

        println("");
        println("=== Complete ===");
    }
}
