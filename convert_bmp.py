from operator import itemgetter
import sys
import struct
from PIL import Image

if len(sys.argv) < 2:
    print("Supply filename without extension as argument")
    sys.exit(1)

fname = sys.argv[1]
num_bands = 3
if len(sys.argv) > 2 and sys.argv[2] == "-g":
    num_bands = 1

bmp = Image.open(fname + ".bmp")

out_file = open(fname + ".dat", "wb")

line_len = bmp.size[0]
if bmp.getbbox() is not None:
    bbox = (bmp.getbbox()[0], 0, bmp.getbbox()[2], bmp.size[1])
else:
    bbox = (0, 0, 0, bmp.size[1])
if bbox[2] - bbox[0] < 6: bbox = (bbox[0], 0, bbox[0] + 6, bmp.size[1])
print(bbox)
data = bmp.getdata()
bands = [data.getband(i) for i in range(num_bands)]

dither = (0, 4, 1, 5, 
          6, 2, 7, 3,
          1, 5, 0, 4,
          7, 3, 6, 2)

def add_dither(x, y, pixel):
    return min(pixel + dither[(x & 3) + 4*(y & 3)], 255)

def add_to_frequency(freq, data):
    for d in data:
        if (d >> 30) == 3: f = freq[0]
        else: f = freq[1]
        for i in range(0,21,10):
            s = (d >> i) & 0x3ff
            if s not in f: f[s] = 1
            else: f[s] += 1

def decode_and_compare(data, source, tolerance):
    decoded = []
    for d in data:
        if d >> 30 == 3:
            for i in range(25,-1,-5):
                decoded.append((d >> i) & 0x1f)
        else:
            if d >> 30 != 1: 
                print("Error: %08X" % d)
                print([hex(i)[2:] for i in data])
                sys.exit(3)
            for i in range(20,-1,-10):
                for j in range(2 + ((d >> i) & 0x1f)):
                    decoded.append((d >> (i + 5) & 0x1f))

    if len(decoded) < len(source) or len(decoded) > len(source) + 5:
        print("Length mismatch %d %d" % (len(source), len(decoded)))
        print([hex(i>>3)[2:] for i in source])
        print([hex(i)[2:] for i in decoded])
        sys.exit(3)

    match = True
    fail_idx = 0
    for i in range(len(decoded)):
        if i < len(source):
            source_pixel = add_dither(i, y, source[i])
            if abs(decoded[i] - (source_pixel >> 3)) > tolerance:
                match = False
                fail_idx = i
                break
        elif decoded[i] != 0:
            match = False
            fail_idx = i
            break

    if not match:
        print("Data mismatch at idx %d (%d != %d)" % (fail_idx, source[i] if i < len(source) else 0, decoded[i]))
        print([hex(i>>3)[2:] for i in source])
        print([hex(i)[2:] for i in decoded])
        sys.exit(3)


cmd = 0
run_length = [0, 0, 0]
pixel_value = [-1, -1, -1]
idx = 0
fill_cmd = False
cmd_idx = 0

def reset():
    global cmd, run_length, pixel_value, idx, fill_cmd, cmd_idx
    cmd = 0
    run_length = [0, 0, 0]
    pixel_value = [-256, -256, -256]
    idx = 0
    fill_cmd = False
    cmd_idx = 0

def handle_partial_run(data):
    global cmd, run_length, pixel_value, idx, fill_cmd, cmd_idx
    if idx == 2:
        assert(pixel_value[0] >= 0)
        assert(pixel_value[1] >= 0)
        if run_length[0] >= 4:
            assert(run_length[1] >= 2)
            cmd = pixel_value[0] << 25
            cmd += pixel_value[0] << 15
            cmd += (run_length[0] - 4) << 10
            cmd += pixel_value[1] << 5
            cmd += (run_length[1] - 2)
            cmd += 0x40000000
            data.append(cmd)
            reset()
        elif run_length[1] >= 4:
            assert(run_length[0] >= 2)
            cmd = pixel_value[0] << 25
            cmd += (run_length[0] - 2) << 20
            cmd += pixel_value[1] << 15
            cmd += pixel_value[1] << 5
            cmd += run_length[1] - 4
            cmd += 0x40000000
            data.append(cmd)
            reset()
        else:
            for i in range(run_length[0]):
                cmd <<= 5
                cmd += pixel_value[0]
                cmd_idx += 1
            for i in range(run_length[1]):
                cmd <<= 5
                cmd += pixel_value[1]
                cmd_idx += 1
            if cmd_idx == 6:
                cmd += 0xC0000000
                data.append(cmd)
                reset()
    elif idx == 1:
        assert(pixel_value[0] >= 0)
        if run_length[0] >= 6:
            cmd = pixel_value[0] << 25
            cmd += pixel_value[0] << 15
            cmd += pixel_value[0] << 5
            cmd += run_length[0] - 6
            cmd += 0x40000000
            data.append(cmd)
            reset()
        else:
            for i in range(run_length[0]):
                cmd <<= 5
                cmd += pixel_value[0]
                cmd_idx += 1

def encode_band(band, offset, tolerance):
        global cmd, run_length, pixel_value, idx, fill_cmd, cmd_idx
        reset()
        data = []
        pixel_avg = -256
        pixel_min = -256
        pixel_max = -256
        for x in range(0,bbox[2]):
            if x < bbox[0]: pixel = 0
            else: pixel = add_dither(x, y, band[offset + x]) >> 3
            this_tolerance = max(tolerance - run_length[idx] // 6, 1)
            if fill_cmd:
                cmd <<= 5
                cmd += pixel
                cmd_idx += 1
                if cmd_idx == 6:
                    cmd += 0xC0000000
                    data.append(cmd)
                    reset()
            elif run_length[idx] < 33 and max(pixel_max, pixel) - min(pixel_min, pixel) <= this_tolerance:
                pixel_avg = (pixel_avg * run_length[idx] + pixel) / (run_length[idx] + 1)
                pixel_min = min(pixel_min, pixel)
                pixel_max = max(pixel_max, pixel)
                run_length[idx] += 1
            else: 
                if run_length[idx] == 0:
                    run_length[idx] = 1
                    pixel_avg = pixel_min = pixel_max = pixel
                elif run_length[idx] == 1:
                    last_pixel = int(pixel_avg)
                    handle_partial_run(data)

                    fill_cmd = True
                    cmd <<= 5
                    cmd += last_pixel
                    cmd_idx += 1
                    if cmd_idx == 6:
                        cmd += 0xC0000000
                        data.append(cmd)
                        reset()
                        pixel_avg = pixel_min = pixel_max = pixel
                        run_length[idx] = 1
                    else:
                        cmd <<= 5
                        cmd += pixel
                        cmd_idx += 1
                        if cmd_idx == 6:
                            cmd += 0xC0000000
                            data.append(cmd)
                            reset()
                else:
                    pixel_value[idx] = int(pixel_avg)
                    idx += 1
                    if idx == 3:
                        assert(pixel_value[0] >= 0)
                        assert(pixel_value[1] >= 0)
                        assert(pixel_value[2] >= 0)
                        assert(run_length[0] >= 2)
                        assert(run_length[1] >= 2)
                        assert(run_length[2] >= 2)
                        cmd = pixel_value[0] << 25
                        cmd += (run_length[0] - 2) << 20
                        cmd += pixel_value[1] << 15
                        cmd += (run_length[1] - 2) << 10
                        cmd += pixel_value[2] << 5
                        cmd += (run_length[2] - 2)
                        cmd += 0x40000000
                        data.append(cmd)
                        reset()
                    pixel_avg = pixel_min = pixel_max = pixel
                    run_length[idx] = 1
        if not fill_cmd:
            if run_length[idx] != 1:
                if run_length[idx] > 1:
                    pixel_value[idx] = int(pixel_avg)
                    idx += 1
                if idx == 3:
                    cmd = pixel_value[0] << 25
                    cmd += (run_length[0] - 2) << 20
                    cmd += pixel_value[1] << 15
                    cmd += (run_length[1] - 2) << 10
                    cmd += pixel_value[2] << 5
                    cmd += (run_length[2] - 2)
                    cmd += 0x40000000
                    data.append(cmd)
                    reset()
                else:
                    handle_partial_run(data)
                    if cmd_idx != 0: fill_cmd = True
            else:
                last_pixel = int(pixel_avg)
                handle_partial_run(data)
                fill_cmd = True
                cmd <<= 5
                cmd += last_pixel
                cmd_idx += 1
                if cmd_idx == 6:
                    cmd += 0xC0000000
                    data.append(cmd)
                    reset()

        if fill_cmd:
            cmd <<= (5 * (6 - cmd_idx))
            cmd += 0xC0000000
            data.append(cmd)

        source_data = []
        for i in range(bbox[2]):
            if i < bbox[0]: source_data.append(0)
            else: source_data.append(band[offset + i])

        decode_and_compare(data, source_data, tolerance)
        return data

frequency = [[{},{}],[{},{}],[{},{}]]

for y in range(bbox[3]):
    data = []
    tolerance = [1,1,1]
    for b in range(num_bands):
        data.append(encode_band(bands[b], y*line_len, tolerance[b]))
    #print("%d %d %d" % (len(data[0]), len(data[1]), len(data[2])))
    while sum([len(d) for d in data]) > 135:
        index_max = max(range(num_bands), key=[len(data[i]) - 100*tolerance[i] for i in range(num_bands)].__getitem__)
        tolerance[index_max] += 1
        data[index_max] = encode_band(bands[index_max], y*line_len, tolerance[index_max])
    print("%s: %d  %d(%d) %d(%d) %d(%d)" % (fname, y,len(data[0]), tolerance[0], len(data[1]), tolerance[1], len(data[2]), tolerance[2]))
    len_cmd = len(data[0])
    add_to_frequency(frequency[0], data[0])
    if num_bands == 3:
        len_cmd += len(data[1]) << 10
        len_cmd += len(data[2]) << 20
        add_to_frequency(frequency[1], data[1])
        add_to_frequency(frequency[2], data[2])
    else:
        len_cmd +=  0x80000000
    out_file.write(struct.pack('<I', len_cmd))
    for b in range(num_bands):
        for cmd in data[b]:
            out_file.write(struct.pack('<I', cmd))

out_file.close()

if False:
  for b in range(num_bands):
    for i in range(2):
        print("%s %s frequency distribution:" % (("Red", "Green", "Blue")[b], ("pixel","rle")[i]))
        sorted_freq = sorted(frequency[b][i].values(), reverse=True)
        uncompressed_size = sum(sorted_freq) * 10
        print("Uncompressed size: %d" % uncompressed_size)
        for i in range(4,8):
            compress_n = 1 << i
            compress_size = i + 1
            other_size = 11
            total_size = 0
            for j in range(len(sorted_freq)):
                if j < compress_n: total_size += compress_size * sorted_freq[j]
                else: total_size += other_size * sorted_freq[j]
            print("Compress first %d: %d (%.2f%%)" % (compress_n, total_size, 100.0 * (total_size / uncompressed_size)))
            total_size = 0
            for j in range(len(sorted_freq)):
                if j < compress_n: total_size += compress_size * sorted_freq[j]
                elif j < 511 + compress_n: total_size += 10 * sorted_freq[j]
                else: total_size += 20 * sorted_freq[j]
            print("Compress scheme 1 (%s): %d (%.2f%%)" % ("OK" if len(sorted_freq) < 511 + compress_size else "No", total_size, 100.0 * (total_size / uncompressed_size)))
            total_size = 0
            for j in range(len(sorted_freq)):
                if j < compress_n: total_size += compress_size * sorted_freq[j]
                elif j < 255 + compress_n: total_size += 9 * sorted_freq[j]
                else: total_size += 19 * sorted_freq[j]
            print("Compress scheme 2 (%s): %d (%.2f%%)" % ("OK" if len(sorted_freq) < 255 + compress_size else "No", total_size, 100.0 * (total_size / uncompressed_size)))


        total_size = 0
        for j in range(len(sorted_freq)):
            if j < 16: total_size += 6 * sorted_freq[j]
            elif j < 16 + 64: total_size += 8 * sorted_freq[j]
            else: total_size += 11 * sorted_freq[j]
        print("Compress scheme n: %d (%.2f%%)" % (total_size, 100.0 * (total_size / uncompressed_size)))
    

in_file = open(fname + ".dat", "rb")
out_file = open(fname + ".huf", "wb")
out_bits = 0
out_bit_len = 0
bytes_written = 0
disable_compression = False

def read_word():
    global in_file
    return struct.unpack("<I", in_file.read(4))[0]

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

pixel_table = [[], [], []]
rle_table = [[], [], []]
for b in range(num_bands):
    pixel_table[b] = [f[0] for f in sorted(frequency[b][0].items(), key=itemgetter(1), reverse=True)[:64]]
    rle_table[b] = [f[0] for f in sorted(frequency[b][1].items(), key=itemgetter(1), reverse=True)[:64]]

    out_bits = 0
    out_bit_len = 0
    for i in range(64):
        try:
            add_bits(pixel_table[b][i], 10)
        except IndexError:
            add_bits(0, 10)
    for i in range(64):
        try:
            add_bits(rle_table[b][i], 10)
        except IndexError:
            add_bits(0, 10)
    write_bits(True)

while True:
    try:
        lens = read_word()
    except struct.error:
        break
    bytes_written = 0
    out_bits = 0
    out_bit_len = 0
    start_band_bit_len = 0
    start_band_remaining_bits = 0

    for b in range(num_bands):
        shift = 10 * b
        band_len = (lens >> shift) & 0x3ff

        for i in range(band_len):
            cmd = read_word()
            if cmd & 0x80000000:
                # Raw pixels
                add_bits(1, 1)

                can_compress = (i != band_len - 1) and not disable_compression
                for shift in range(20,-1,-10):
                    two_pixels = (cmd >> shift) & 0x3ff
                    if two_pixels not in pixel_table[b]: 
                        can_compress = False
                        break
                
                if can_compress:
                    add_bits(0, 1)
                    for shift in range(20,-1,-10):
                        two_pixels = (cmd >> shift) & 0x3ff
                        symbol = pixel_table[b].index(two_pixels)
                        add_bits(symbol, 6)
                else:
                    add_bits(1, 1)
                    add_bits(cmd & 0x3FFFFFFF, 30)

            else:
                # RLE
                add_bits(0, 1)

                can_compress = (i != band_len - 1) and not disable_compression
                for shift in range(20,-1,-10):
                    rle = (cmd >> shift) & 0x3ff
                    if rle not in rle_table[b]: 
                        can_compress = False
                        break
                
                if can_compress:
                    add_bits(0, 1)
                    for shift in range(20,-1,-10):
                        rle = (cmd >> shift) & 0x3ff
                        symbol = rle_table[b].index(rle)
                        add_bits(symbol, 6)
                else:
                    add_bits(1, 1)
                    add_bits(cmd & 0x3FFFFFFF, 30)

        assert(out_bit_len.bit_length() <= 13)
        out_bits |= ((start_band_remaining_bits << 13) | out_bit_len) << out_bit_len
        out_bit_len += 13 + start_band_bit_len
        write_bits(b == num_bands - 1)
        start_band_bit_len = out_bit_len
        start_band_remaining_bits = out_bits
        out_bits = 0
        out_bit_len = 0

    # Word align
    if (bytes_written & 3) != 0:
        for i in range(bytes_written & 3,4):
            out_file.write(struct.pack('=B', 0))

