import sys
import struct

if len(sys.argv) < 2:
    print("Supply filename without extension as argument")
    sys.exit(1)

fname = sys.argv[1]

out_file = open(fname + ".huf", "wb")

for i in range((64 * 6) // 8):
    out_file.write(struct.pack("=B", 0))

out_bits = 0
out_bit_len = 0
bytes_written = 0

def add_bits(bits, bit_len):
    global out_bits, out_bit_len
    assert(bits.bit_length() <= bit_len)
    out_bits <<= bit_len
    out_bits |= bits
    out_bit_len += bit_len

def write_bits(align):
    global out_bits, out_bit_len, out_file, bytes_written
    while out_bit_len >= 8:
        out_bit_len -= 8
        out_byte = out_bits >> out_bit_len
        out_bits &= (1 << (out_bit_len)) - 1
        out_file.write(struct.pack("=B", out_byte))
        bytes_written += 1
    if align and out_bit_len > 0:
        out_bits <<= 8 - out_bit_len
        out_file.write(struct.pack("=B", out_bits))
        out_bit_len = 0
        out_bits = 0
        bytes_written += 1


for i in range(720):
    bytes_written = 0
    out_bits = 0
    out_bit_len = 0

    for b in range(3):
        add_bits(64, 13)
        add_bits(0xC0000000, 32)
        add_bits(0xC0000000, 32)

    write_bits(True)

    # Word align
    if (bytes_written & 3) != 0:
        for i in range(bytes_written & 3,4):
            out_file.write(struct.pack('=B', 0))


