import os
import random
import sys

def split(lst_path):
    with open(lst_path, 'rb') as f:
        lines = f.read().strip().split(b'\n')
    random.shuffle(lines)

    if len(lines) < 3:
        raise Exception('cannot split dataset with fewer than 3 clips')
    split_size = max(2, min(int(len(lines) * 0.20), 20000))
    dev_size = split_size // 2
    test_size = split_size - dev_size
    train_size = len(lines) - split_size
    print('[+] dev   {}/{}'.format(dev_size,   len(lines)))
    print('[+] test  {}/{}'.format(test_size,  len(lines)))
    print('[+] train {}/{}'.format(train_size, len(lines)))

    train_lines, lines      = lines[:train_size], lines[train_size:]
    dev_lines,   test_lines = lines[:dev_size], lines[dev_size:]

    base = os.path.dirname(lst_path)
    with open(os.path.join(base, 'train.lst'), 'wb') as f:
        for line in train_lines:
            f.write(line + b'\n')
    with open(os.path.join(base, 'dev.lst'), 'wb') as f:
        for line in dev_lines:
            f.write(line + b'\n')
    with open(os.path.join(base, 'test.lst'), 'wb') as f:
        for line in test_lines:
            f.write(line + b'\n')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: wsplit <clips.lst>')
        sys.exit(1)
    split(sys.argv[1])
