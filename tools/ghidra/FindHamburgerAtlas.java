import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class FindHamburgerAtlas extends GhidraScript {

    @Override
    public void run() throws Exception {

        long base = 0x10072E0FCL;
        long start = 0x10072F9B8L - 8;
        long end = 0x10072FD9CL - 8;

        int[][] targets = {
            {890, 593, 102, 142},
            {1544, 324, 43, 60},
            {556, 745, 84, 84},
            {1856, 4, 60, 60}
        };

        String[] names = {
            "Large hamburger",
            "Small hamburger",
            "Large arrow background",
            "Small arrow button"
        };

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

            for (int i = 0; i < targets.length; i++) {

                int[] t = targets[i];

                boolean overlaps =
                    px < t[0] + t[2] &&
                    px + pw > t[0] &&
                    py < t[1] + t[3] &&
                    py + ph > t[1];

                if (overlaps) {
                    println(String.format(
                        "%s | Index %d | Address 0x%X | " +
                        "Atlas (%d,%d,%d,%d) | " +
                        "Pixels (%d,%d,%d,%d)",
                        names[i], index, addr,
                        x, y, w, h,
                        px, py, pw, ph
                    ));
                }
            }
        }

        println("Search complete.");
    }
}
