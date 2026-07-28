import os

def get_dimensions(path):
    with open(path, 'rb') as f:
        data = f.read(1024*1024) # read first 1MB
    
    # Search for 'tkhd'
    idx = 0
    while True:
        idx = data.find(b'tkhd', idx)
        if idx == -1:
            return "tkhd not found"
        
        # Check if version is 0 or 1
        # tkhd starts with 4 bytes size, 4 bytes type ('tkhd'), 1 byte version, 3 bytes flags
        version = data[idx + 4]
        
        # We want to find the width and height which are at the very end of tkhd box.
        # Box size of tkhd is 92 bytes for version 0, 104 bytes for version 1.
        if version == 0:
            # width/height are at offset 76 and 80 relative to start of tkhd box
            w_offset = idx + 76
            h_offset = idx + 80
        elif version == 1:
            w_offset = idx + 88
            h_offset = idx + 92
        else:
            idx += 4
            continue
            
        if h_offset + 4 <= len(data):
            w_bytes = data[w_offset:w_offset+4]
            h_bytes = data[h_offset:h_offset+4]
            
            # Width and height are 16.16 fixed point
            width = int.from_bytes(w_bytes, 'big') / 65536.0
            height = int.from_bytes(h_bytes, 'big') / 65536.0
            
            if width > 0 and height > 0:
                return f"{width}x{height} (version={version})"
        
        idx += 4

for filename in os.listdir('frontend/phase3/assets'):
    if filename.endswith('.mp4'):
        path = os.path.join('frontend/phase3/assets', filename)
        print(f"{filename}: {get_dimensions(path)}")
