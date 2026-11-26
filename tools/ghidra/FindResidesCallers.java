
// Find callers of the resource filename lookup functions.
//@category MHFU

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class FindResidesCallers extends GhidraScript {

    private static final long[] TARGETS = {
        0x10023D2ACL,
        0x10023CA30L
    };

    private static final String[] NAMES = {
        "ROFS_getFileName",
        "ROFS_getFileNameSplit"
    };

    @Override
    public void run() throws Exception {

        println("=== Resource Filename Callers ===");

        for (int i = 0; i < TARGETS.length; i++) {

            Address target = toAddr(TARGETS[i]);
            Reference[] refs = getReferencesTo(target);

            println("");
            println(NAMES[i] + " @ " + target);
            println("Total references: " + refs.length);

            for (Reference ref : refs) {

                monitor.checkCancelled();

                Address from = ref.getFromAddress();
                Function caller = getFunctionContaining(from);
                Instruction instruction = getInstructionAt(from);

                println("");
                println("  Reference: " + from);
                println("  Type: " + ref.getReferenceType());

                if (caller != null) {
                    println("  Caller: " + caller.getName());
                    println("  Entry: " + caller.getEntryPoint());
                }

                if (instruction != null) {
                    println("  Instruction: " + instruction);
                }
            }
        }

        println("");
        println("=== Complete ===");
    }
}
