import os
import sys
import tempfile
import traceback

def rebase(data_dir):
    clips_path = os.path.abspath(os.path.join(data_dir, 'clips')).encode('utf8')
    if not os.path.exists(clips_path):
        raise Exception('cannot rebase this directory: no clips/')
    for name in os.listdir(data_dir):
        if name.endswith('.lst'):
            path = os.path.join(data_dir, name)
            print('[+]', path)
            o = tempfile.NamedTemporaryFile(delete=False)
            with open(path, 'rb') as f:
                for line in f:
                    parts = line.split(b' ', 3)
                    if os.path.basename(os.path.dirname(parts[1])) == b'clips':
                        parts[1] = os.path.join(clips_path, os.path.basename(parts[1]))
                    line = b' '.join(parts)
                    o.write(line)
            o.close()
            os.rename(path, path + '.tmp')
            try:
                os.rename(o.name, path)
            except Exception:
                traceback.print_exc()
                os.rename(path + '.tmp', path)
                continue
            os.unlink(path + '.tmp')

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print('Usage: wrebase <dir> [dir...]')
        sys.exit(1)

    for d in sys.argv[1:]:
        try: rebase(d)
        except Exception:
            print('Error rebasing:', d)
            traceback.print_exc()
