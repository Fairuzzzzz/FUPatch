
// Locate fixed-size loading glyph atlas records.
//@category MHFU

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class FindLoadingAtlas extends GhidraScript {

    private static final String[] GLYPHS = {
        "N", "O", "W", "L", "A", "D", "I", "G"
    };

    private static final int GRID_X = 0;
    private static final int GRID_Y = 1088;
    private static final int CELL_WIDTH = 96;
    private static final int CELL_HEIGHT = 96;

    private static final int RECORD_SIZE = 12;

    private static final int[] MULTIPLIERS = {
        1, 2, 4, 8
    };

    private static final int TOLERANCE = 8;

    private static int u16(byte[] data, int offset) {
        return (data[offset] & 0xff)
            | ((data[offset + 1] & 0xff) << 8);
    }

    private static boolean near(int actual, int expected) {
        return Math.abs(actual - expected) <= TOLERANCE;
    }

    private static boolean matchesGlyph(
            byte[] data,
            int offset,
            int multiplier,
            int glyphIndex) {

        if (offset < 0 ||
            offset > data.length - RECORD_SIZE) {
            return false;
        }

        int x = u16(data, offset) * multiplier;
        int y = u16(data, offset + 2) * multiplier;
        int w = u16(data, offset + 4) * multiplier;
        int h = u16(data, offset + 6) * multiplier;

        int expectedX = GRID_X + glyphIndex * CELL_WIDTH;

        return near(x, expectedX)
            && near(y, GRID_Y)
            && near(w, CELL_WIDTH)
            && near(h, CELL_HEIGHT);
    }

    @Override
    public void run() throws Exception {

        Memory memory = currentProgram.getMemory();

        int matches = 0;
        int sequences = 0;

        println("=== Loading Glyph Grid Discovery ===");
        println("Program: " + currentProgram.getName());

        println(String.format(
            "Grid origin: (%d,%d)",
            GRID_X, GRID_Y
        ));

        println(String.format(
            "Cell size: %d x %d",
            CELL_WIDTH, CELL_HEIGHT
        ));

        println("Tolerance: " + TOLERANCE + " pixels");
        println("");

        for (MemoryBlock block : memory.getBlocks()) {

            if (!block.isInitialized()) {
                continue;
            }

            if (block.getSize() < RECORD_SIZE ||
                block.getSize() > Integer.MAX_VALUE) {
                continue;
            }

            monitor.checkCancelled();

            byte[] data = new byte[(int) block.getSize()];
            memory.getBytes(block.getStart(), data);

            println("Scanning: " + block.getName()
                + " @ " + block.getStart()
                + " (" + data.length + " bytes)");

            for (int offset = 0;
                 offset <= data.length - RECORD_SIZE;
                 offset += 2) {

                if ((offset & 0xffff) == 0) {
                    monitor.checkCancelled();
                }

                int flags = u16(data, offset + 8);
                int resource = u16(data, offset + 10);

                for (int multiplier : MULTIPLIERS) {

                    for (int i = 0; i < GLYPHS.length; i++) {

                        if (!matchesGlyph(
                                data, offset, multiplier, i)) {
                            continue;
                        }

                        int x = u16(data, offset);
                        int y = u16(data, offset + 2);
                        int w = u16(data, offset + 4);
                        int h = u16(data, offset + 6);

                        Address address =
                            block.getStart().add(offset);

                        println(String.format(
                            "MATCH %s @ %s | %dx | " +
                            "raw=(%d,%d,%d,%d) | " +
                            "pixels=(%d,%d,%d,%d) | " +
                            "flags=0x%04X | resource=%d",
                            GLYPHS[i],
                            address,
                            multiplier,
                            x, y, w, h,
                            x * multiplier,
                            y * multiplier,
                            w * multiplier,
                            h * multiplier,
                            flags,
                            resource
                        ));

                        matches++;

                        // Check for consecutive glyph records.
                        int count = 1;

                        for (int j = i + 1;
                             j < GLYPHS.length;
                             j++) {

                            int nextOffset =
                                offset + (j - i) * RECORD_SIZE;

                            if (!matchesGlyph(
                                    data,
                                    nextOffset,
                                    multiplier,
                                    j)) {
                                break;
                            }

                            int nextFlags =
                                u16(data, nextOffset + 8);

                            int nextResource =
                                u16(data, nextOffset + 10);

                            if (nextFlags != flags ||
                                nextResource != resource) {
                                break;
                            }

                            count++;
                        }

                        if (count >= 3) {

                            StringBuilder sequence =
                                new StringBuilder();

                            for (int j = i; j < i + count; j++) {
                                sequence.append(GLYPHS[j]);
                            }

                            println(String.format(
                                "  SEQUENCE %s | " +
                                "%d consecutive records | " +
                                "stride=%d",
                                sequence.toString(),
                                count,
                                RECORD_SIZE
                            ));

                            sequences++;
                        }
                    }
                }
            }
        }

        println("");
        println("Total individual matches: " + matches);
        println("Total sequence matches: " + sequences);
        println("=== Discovery Complete ===");
    }
}
