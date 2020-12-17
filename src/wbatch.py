from tempfile import NamedTemporaryFile
import argparse
import os
import subprocess

base = os.path.dirname(__file__)
wfilter = os.path.join(base, '..', 'wfilter')

def batch_filter(outdir, set_name, lists, argv, merge=False):
    if not lists:
        return ''
    print('[+] {}'.format(set_name))
    if merge:
        lstname = '{}.lst'.format(set_name)
        outlst = os.path.join(outdir, lstname)
        with NamedTemporaryFile('w', suffix='.lst') as tmp:
            for lst in lists:
                with open(lst, 'r') as f:
                    tmp.write(f.read().strip() + '\n')
            tmp.flush()
            with open(outlst, 'w') as out:
                subprocess.check_call([wfilter, tmp.name, '--desc', lstname] + argv, stdout=out)
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
    flags['--train'] = batch_filter(outdir, 'train', train_set, argv, merge=args.merge)
    flags['--test']  = batch_filter(outdir, 'test',  test_set,  argv)
    flags['--valid'] = batch_filter(outdir, 'valid', valid_set, argv)
    flags['--datadir'] = outdir

    with open(os.path.join(outdir, 'flagsfile'), 'w') as f:
        for k, v in flags.items():
            f.write('{}={}\n'.format(k, v))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--flagsfile', help='input flagsfile path', type=str, required=True)
    parser.add_argument('--output',    help='output directory', type=str, required=True)
    parser.add_argument('--merge',     help='merge train into one list', action='store_true')

    args, unknown = parser.parse_known_args()
    main(args, unknown)
