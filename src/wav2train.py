from multiprocessing.pool import ThreadPool
from pathlib import Path
from tqdm import tqdm
import json
import multiprocessing
import os
import re
import sox
import subprocess
import sys
import traceback

basedir = os.path.dirname(os.path.realpath(os.path.dirname(__file__)))
dsalign_dir = os.path.join(basedir, 'DSAlign')
align_exe = 'align/align.py'
# align_exe = os.path.join(basedir, 'DSAlign', 'bin', 'align.sh')

devnull = open(os.devnull, 'w+')

def align(audio_file, transcript_file, align_dir):
    linked_transcript = os.path.join(align_dir, os.path.basename(transcript_file))
    try:
        os.link(transcript_file, linked_transcript)
    except FileExistsError:
        pass

    name    = os.path.basename(audio_file).rsplit('.', 1)[0]
    aligned = os.path.join(align_dir, name + '-aligned.json')
    tlog    = os.path.join(align_dir, name + '.tlog')
    argv = ['python', align_exe,
        '--stt-workers',    '1',
        '--output-max-cer', '25',
        '--audio',   audio_file,
        '--script',  linked_transcript,
        '--aligned', aligned,
        '--tlog',    tlog,
        '--no-progress',
        '--force',
    ]
    # print(argv)
    p = subprocess.Popen(argv, stdin=devnull, stdout=devnull, stderr=subprocess.PIPE)
    _, err = p.communicate()
    err = (err or b'').strip().decode('utf8')
    for line in err.split('\n'):
        if line.startswith(('TensorFlow: v', 'DeepSpeech: v')):
            continue
        if line.startswith('Warning: reading entire model'):
            continue
        if 'Your CPU supports instructions' in line:
            continue
    return (audio_file, aligned)

words_re = re.compile(r"[a-zA-Z']+")

def segment(audio_file, aligned_json, clips_dir):
    name = os.path.basename(audio_file).split('.')[0]
    skipped = 0
    for i, segment in enumerate(aligned_json):
        # TODO: use a g2p style normalizer to fix numbers? would probably want to do it pre alignment.
        # numbers are one of the main reasons for `aligned != aligned_raw`
        try:
            text = segment['aligned-raw']
            start = segment['start']
            end = segment['end']

            aligned = segment['aligned'].lower()
            text = ' '.join(words_re.findall(text.lower()))
            if aligned != text:
                print('[-] Discarding Alignment:')
                print('a|', segment['aligned'])
                print('r|', segment['aligned-raw'])
                print('t|', text)
                print()
                skipped += 1
                continue

            subname = '{}-{}'.format(name, i)
            clip = '{}/{}.flac'.format(clips_dir, subname)
            if not os.path.exists(clip):
                tf = sox.Transformer()
                tf.trim(start / 1000, end / 1000)
                tf.build(audio_file, clip)
            duration = sox.file_info.duration(clip) * 1000
            yield '{} {} {} {}'.format(subname, clip, duration, text)
        except Exception:
            print('Error segmenting {}-{}'.format(name, i))
            traceback.print_exc()
            skipped += 1

    if skipped:
        print('[-] Clip {}: skipped {}/{} segments due to bad alignment'.format(name, skipped, len(aligned_json)))

def wav2train(indir, outdir):
    indir     = os.path.abspath(indir)
    outdir    = os.path.abspath(outdir)
    align_dir = os.path.join(outdir, 'align')
    clips_dir  = os.path.join(outdir, 'clips')
    clips_lst = os.path.join(outdir, 'clips.lst')

    os.makedirs(align_dir, exist_ok=True)
    os.makedirs(clips_dir, exist_ok=True)
    os.chdir(dsalign_dir)

    jobs = multiprocessing.cpu_count()
    pool = ThreadPool(jobs)

    align_queue = []
    print('[+] Collecting files to align')
    seen_exts   = set()
    unseen_exts = {'flac', 'wav', 'mp3', 'ogg', 'sph', 'aac', 'wma', 'alac'}
    for p in Path(indir).iterdir():
        if p.name.endswith('.txt'):
            txt_path = str(p.resolve())
            name = txt_path.rsplit('.', 1)[0]
            ext = ''
            n_path = ''
            # little dance to find the right file extension without doing way too many stats
            for ext in seen_exts:
                n_ext = name + '.' + ext
                n_path = os.path.join(indir, n_ext)
                if os.path.exists(n_path):
                    break
            else:
                for ext in unseen_exts:
                    n_ext = name + '.' + ext
                    n_path = os.path.join(indir, n_ext)
                    if os.path.exists(n_path):
                        break
                else:
                    continue
                seen_exts.add(ext)
                unseen_exts.remove(ext)
            audio_path = n_path
            align_queue.append((audio_path, txt_path))

    segment_queue = []
    align_fn = lambda t: align(t[0], t[1], align_dir)
    print('[+] Aligning ({}) transcript(s)'.format(len(align_queue)))
    for audio_file, aligned_json in tqdm(pool.imap(align_fn, align_queue), desc='Align', total=len(align_queue)):
        try:
            with open(aligned_json, 'r') as f:
                j = json.load(f)
            segment_queue.append((audio_file, j))
        except Exception:
            print('Failed to align {}'.format(audio_file))
            traceback.print_exc()
    print('[+] Alignment complete')

    segment_fn = lambda t: segment(t[0], t[1], clips_dir)
    print('[+] Generating segments for ({}) clip(s)'.format(len(segment_queue)))
    with open(clips_lst, 'w') as lst:
        for lines in tqdm(pool.imap(segment_fn, segment_queue), desc='Segment', total=len(segment_queue)):
            for line in lines: 
                lst.write(line + '\n')

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: wav2train <input_dir> <output_dir>')
        sys.exit(1)
    wav2train(sys.argv[1], sys.argv[2])
