from multiprocessing import Pool
from pydub import AudioSegment
from tqdm import tqdm
import os
import sys

def valid_fn(line):
    parts = line.split(' ', 3)
    if len(parts) != 4:
        return
    path = parts[1]
    try:
        audio = AudioSegment.from_file(path)
    except Exception:
        return None
    l = len(audio)
    if l > 1.0 and abs(l - float(parts[2])) < 1.0:
        return line
    return None

def valid(lst_path):
    with open(lst_path, 'r') as f:
        lines = f.read().strip().split('\n')

    pool = Pool()
    for line in tqdm(pool.imap_unordered(valid_fn, lines), total=len(lines)):
        if line:
            print(line)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: wvalid <clips.lst>')
        sys.exit(1)
    valid(sys.argv[1])
