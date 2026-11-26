import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class FindSortAtlas extends GhidraScript {

    @Override
    public void run() throws Exception {
	println("FindSortAtlas started.");
        long base = 0x10072E0FCL;
        long start = 0x10072F9B8L - 8;
        long end = 0x10072FD9CL - 8;

        int[] target = {576, 580, 308, 160};

        int matches = 0;

        for (long addr = start; addr <= end; addr += 12) {

            Address a = toAddr(addr);

            int x = getShort(a) & 0xffff;
            int y = getShort(a.add(2)) & 0xffff;
            int w = getShort(a.add(4)) & 0xffff;
            int h = getShort(a.add(6)) & 0xffff;
            int flags = getShort(a.add(8)) & 0xffff;
            int resource = getShort(a.add(10)) & 0xffff;

            if (flags != 0x8004 || resource != 11)
                continue;

            long index = (addr - base) / 12;

            int px = x * 4;
            int py = y * 4;
            int pw = w * 4;
            int ph = h * 4;

            boolean overlaps =
                px < target[0] + target[2] &&
                px + pw > target[0] &&
                py < target[1] + target[3] &&
                py + ph > target[1];

            if (overlaps) {

                matches++;

                println(String.format(
                    "Sort candidate | Index %d (0x%X) | " +
                    "Address 0x%X | " +
                    "Atlas (%d,%d,%d,%d) | " +
                    "Pixels (%d,%d,%d,%d)",
                    index, index, addr,
                    x, y, w, h,
                    px, py, pw, ph
                ));
            }
        }

        println("Search complete.");
        println("Total candidates: " + matches);
    }
}
