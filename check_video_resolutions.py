import struct
import os

def find_dims(file_path):
    with open(file_path, 'rb') as f:
        data = f.read(5 * 1024 * 1024) # 5MB
    
    # Let's search for 'tkhd' atom
    pos = 0
    tkhd_offsets = []
    while True:
        pos = data.find(b'tkhd', pos)
        if pos == -1:
            break
        tkhd_offsets.append(pos)
        pos += 4
        
    for tkhd_pos in tkhd_offsets:
        # Check size of tkhd atom
        atom_size = int.from_bytes(data[tkhd_pos-4:tkhd_pos], 'big')
        version = data[tkhd_pos+4]
        # End of tkhd atom has width and height as 16.16 fixed point
        # width is at tkhd_pos + atom_size - 12 (or similar)
        # For version 0, size is 92. width at 76, height at 80
        # For version 1, size is 104. width at 88, height at 92
        if version == 0:
            w_pos = tkhd_pos + 76
            h_pos = tkhd_pos + 80
        else:
            w_pos = tkhd_pos + 88
            h_pos = tkhd_pos + 92
            
        if h_pos + 4 <= len(data):
            w_val = int.from_bytes(data[w_pos:w_pos+4], 'big') / 65536.0
            h_val = int.from_bytes(data[h_pos:h_pos+4], 'big') / 65536.0
            if 100 < w_val < 5000 and 100 < h_val < 5000:
                return f"{int(w_val)}x{int(h_val)}"
    return "Unknown"

for name in os.listdir('frontend/phase3/assets'):
    if name.endswith('.mp4'):
        p = os.path.join('frontend/phase3/assets', name)
        print(f"{name}: {find_dims(p)}")
