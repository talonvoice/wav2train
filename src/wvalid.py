from multiprocessing import Pool
from tqdm import tqdm
import os
import subprocess
import sys

devnull = open(os.devnull, 'w+')

def valid_fn(line):
    parts = line.split(' ', 3)
    if len(parts) != 4:
        return
    path = parts[1]
    try:
        argv = ['ffprobe', '-i', path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']
        p = subprocess.Popen(argv, stdin=devnull, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        length = float(out.strip()) * 1000
    except Exception:
        return None
    if length > 1.0 and abs(length - float(parts[2])) < 1.0:
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
