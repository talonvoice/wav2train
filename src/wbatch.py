from multiprocessing import Pool
from tempfile import NamedTemporaryFile
import argparse
import hashlib
import os
import subprocess
import itertools

from tqdm import tqdm

base = os.path.dirname(__file__)
wfilter = os.path.join(base, '..', 'wfilter')

def cache_one(args):
    line, cache_dir = args
    length = len(line)
    line = line.strip()
    if not line:
        return ''
    _id, path, duration, text = line.split(' ', 3)
    with open(path, 'rb') as f:
        data = f.read()
        h = hashlib.sha256(data).hexdigest()
        cache_base1 = os.path.join(cache_dir, h[:2])
        cache_base2 = os.path.join(cache_base1, h[2:4])
        ext = path.rsplit('.', 1)[1]
        cache_path = os.path.join(cache_base2, f"{h}.{ext}")
        with open(cache_path, 'wb') as o:
            o.write(data)
    return _id, cache_path, duration, text, length

def batch_filter(outdir, set_name, lists, argv, merge=False, cache=None):
    if not lists:
        return ''
    print('[+] {}'.format(set_name))
    if merge:
        lstname = '{}.lst'.format(set_name)
        outlst = os.path.join(outdir, lstname)
        with NamedTemporaryFile('w', suffix='.lst') as tmp:
            count = 0
            for lst in tqdm(lists, desc='copy lists'):
                with open(lst, 'r') as f:
                    data = f.read().strip() + '\n'
                    count += data.count('\n')
                    tmp.write(data)
            tmp.flush()
            if cache is None:
                with open(outlst, 'w') as out:
                    subprocess.check_call([wfilter, tmp.name, '--desc', lstname] + argv, stdout=out)
            else:
                with NamedTemporaryFile('w+', suffix='.lst') as tmp2:
                    subprocess.check_call([wfilter, tmp.name, '--desc', lstname] + argv, stdout=tmp2)
                    tmp2.seek(0, os.SEEK_END)
                    size = tmp2.tell()
                    tmp2.seek(0, os.SEEK_SET)

                    with open(outlst, 'w') as out:
                        pool_iter = pool.imap(cache_one, zip(tmp2, itertools.repeat(cache)), chunksize=8)
                        for _id, path, duration, text, length in tqdm(pool_iter, desc='cache', total=count):
                            out.write(f"{_id} {path} {duration} {text}\n")
        return lstname

    datadir = os.path.commonprefix(lists)
    names = []
    for lst in lists:
        lstname = os.path.relpath(lst, datadir)
        lstname = lstname.rsplit('.', 1)[0].replace(os.sep, '-') + '.lst'
        names.append(lstname)
        outlst = os.path.join(outdir, lstname)
        with open(outlst, 'w') as out:
            subprocess.check_call([wfilter, lst, '--desc', lstname] + argv, stdout=out)
    print()
    return ','.join(names)

def main(args, argv):
    flagsfile = os.path.realpath(args.flagsfile)
    outdir = os.path.realpath(args.output)

    flags = {}
    with open(flagsfile, 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                flags[key] = value

    flagsdir = os.path.dirname(flagsfile)
    datadir = os.path.realpath(flags.get('--datadir', flagsdir))
    train_set = flags.get('--train', '').split(',')
    test_set  = flags.get('--test', '').split(',')
    valid_set = flags.get('--valid', '').split(',')
    train_set = [os.path.join(datadir, lst) for lst in train_set if lst]
    test_set  = [os.path.join(datadir, lst) for lst in test_set  if lst]
    valid_set = [os.path.join(datadir, lst) for lst in valid_set if lst]

    os.makedirs(outdir, exist_ok=True)
    if args.cache:
        cache = args.cache
        os.makedirs(cache, exist_ok=True)
        for a in tqdm(range(256), desc='cache dirs'):
            for b in range(256):
                try:
                    os.mkdir(os.path.join(cache, f"{a:02x}", f"{b:02x}"))
                except FileExistsError:
                    pass

    flags['--train'] = batch_filter(outdir, 'train', train_set, argv, merge=args.merge, cache=args.cache)
    flags['--test']  = batch_filter(outdir, 'test',  test_set,  argv, cache=args.cache)
    flags['--valid'] = batch_filter(outdir, 'valid', valid_set, argv, cache=args.cache)
    flags['--datadir'] = outdir

    with open(os.path.join(outdir, 'flagsfile'), 'w') as f:
        for k, v in flags.items():
            f.write('{}={}\n'.format(k, v))

if __name__ == '__main__':
    pool = Pool()

    parser = argparse.ArgumentParser()
    parser.add_argument('--flagsfile', help='input flagsfile path', type=str, required=True)
    parser.add_argument('--output',    help='output directory', type=str, required=True)
    parser.add_argument('--merge',     help='merge train into one list', action='store_true')
    parser.add_argument('--cache',     help='cache audio to this directory', type=str, default=None)

    args, unknown = parser.parse_known_args()
    main(args, unknown)
