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

bbox = bmp.getbbox()
data = bmp.getdata()
bands = [data.getband(i) for i in range(num_bands)]

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
            if abs(decoded[i] - (source[i] >> 3)) > tolerance:
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
        for x in range(0,bbox[2]):
            pixel = band[y*bbox[2]+x] >> 3
            if fill_cmd:
                cmd <<= 5
                cmd += pixel
                cmd_idx += 1
                if cmd_idx == 6:
                    cmd += 0xC0000000
                    data.append(cmd)
                    reset()
            elif run_length[idx] < 33 and abs(pixel_value[idx] - pixel) <= tolerance:
                run_length[idx] += 1
            else: 
                if run_length[idx] == 0:
                    pixel_value[idx] = pixel
                    run_length[idx] = 1
                elif run_length[idx] == 1:
                    last_pixel = pixel_value[idx]
                    handle_partial_run(data)

                    fill_cmd = True
                    cmd <<= 5
                    cmd += last_pixel
                    cmd_idx += 1
                    if cmd_idx == 6:
                        cmd += 0xC0000000
                        data.append(cmd)
                        reset()
                        pixel_value[idx] = pixel
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
                    pixel_value[idx] = pixel
                    run_length[idx] = 1
        if not fill_cmd:
            if run_length[idx] != 1:
                if run_length[idx] > 1:
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
                last_pixel = pixel_value[idx]
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
            source_data.append(band[offset+i])

        decode_and_compare(data, source_data, tolerance)
        return data

for y in range(bbox[3]):
    data = []
    tolerance = [0,0,0]
    for b in range(num_bands):
        data.append(encode_band(bands[b], y*bbox[2], 0))
    print("%d %d %d" % (len(data[0]), len(data[1]), len(data[2])))
    while sum([len(d) for d in data]) > 220:
        index_max = max(range(num_bands), key=[len(data[i]) - 100*tolerance[i] for i in range(num_bands)].__getitem__)
        tolerance[index_max] += 1
        data[index_max] = encode_band(bands[index_max], y*bbox[2], tolerance[index_max])
        print("  %d(%d) %d(%d) %d(%d)" % (len(data[0]), tolerance[0], len(data[1]), tolerance[1], len(data[2]), tolerance[2]))
    len_cmd = len(data[0])
    if num_bands == 3:
        len_cmd += len(data[1]) << 10
        len_cmd += len(data[2]) << 20
    else:
        len_cmd +=  0x80000000
    out_file.write(struct.pack('<I', len_cmd))
    for b in range(num_bands):
        for cmd in data[b]:
            out_file.write(struct.pack('<I', cmd))


