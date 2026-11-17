# ABC1600 boot ROM

`ABC1600ROM.bin` is the unchanged 16384-byte image supplied by the user from
`/Users/mattis_lind/Downloads/ABC1600ROM.bin` on 2026-11-17. This binary is
target data, not firmware source; no additional license is asserted for it.

| Identifier | Value |
| --- | --- |
| CRC32 | `9372f6f2` |
| SHA-1 | `86f0681f7ef8dd190b49eda5e781881582e0c2a4` |
| SHA-256 | `15bfe1427e0ebd982be73af8d3f82d95f0ac726f9b82b4d2ecfc351bad7319de` |
| Reset SSP | `$00040000` |
| Reset PC | `$00000046` |

CRC32/SHA-1 match the `boot 6490356-04.1f` entry in the
[MAME ABC1600 MMU reference](https://github.com/mamedev/mame/blob/master/src/mame/luxor/abc1600_mmu.cpp).
The [ABC1600 bring-up guide](../../docs/abc1600.md) describes loading this image,
the five-instruction trace, the minimal cause-register fixture and the
remaining machine behavior to implement.
