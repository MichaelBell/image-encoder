import struct
import sys

if len(sys.argv) < 2:
    print("Supply filename without extension as argument")
    sys.exit(1)

fname = sys.argv[1]

class Decoder:
    def __init__(self, huf_file):
        self.huf_file = huf_file
        self.huf_data = 0
        self.huf_bit_len = 0
        self.huf_bytes_read = 0
        self.band_len = 0
        self.pixel_table = [[], [], []]
        self.rle_table = [[], [], []]
        self.read_table()

    def get_bits(self, bit_len):
        while self.huf_bit_len < bit_len:
            next_byte = struct.unpack("=B", self.huf_file.read(1))[0]
            self.huf_data <<= 8
            self.huf_data |= next_byte
            self.huf_bit_len += 8
        self.huf_bit_len -= bit_len
        self.band_len -= bit_len
        result = self.huf_data >> self.huf_bit_len
        assert(result.bit_length() <= bit_len)
        self.huf_data &= (1 << self.huf_bit_len) - 1
        return result

    def read_table(self):
        for b in range(3):
            for i in range(64):
                self.pixel_table[b].append(self.get_bits(10))
            for i in range(64):
                self.rle_table[b].append(self.get_bits(10))

    def read_line(self):
        cmd_list = [0]
        total_bits = 0
        for b in range(3):
            self.band_len = self.get_bits(13)
            total_bits += 13 + self.band_len
            cmds = 0
            while self.band_len > 0:
                cmd_type = self.get_bits(1)
                if cmd_type == 1:
                    cmd = 0xC0000000
                    table = self.pixel_table[b]
                else:
                    cmd = 0x40000000
                    table = self.rle_table[b]

                for i in range(3):
                    shift = 20 - (i * 10)
                    symbol_type = self.get_bits(1)
                    if symbol_type == 1:
                        cmd |= self.get_bits(10) << shift
                    else:
                        cmd |= table[self.get_bits(6)] << shift
                cmd_list.append(cmd)
                cmds += 1
            assert(self.band_len == 0)
            cmd_list[0] |= cmds << (10 * b)
        if (total_bits & 0x1f) != 0:
            self.get_bits(32 - (total_bits & 0x1f))
        return cmd_list

dat_file = open(fname + ".dat", "rb")
huf_file = open(fname + ".huf", "rb")

decoder = Decoder(huf_file)

line_count = 0

while True:
    try:
        cmds = decoder.read_line()
    except struct.error:
        break

    count = 0
    fail_count = 0
    for cmd in cmds:
        dat_cmd = struct.unpack("<I", dat_file.read(4))[0]
        if cmd != dat_cmd: 
            fail_count += 1
            print("%3d %3d %08X %08X" % (line_count, count, cmd, dat_cmd))
            print("  FAIL")
        if fail_count == 5: sys.exit(3)
        count += 1
    line_count += 1

