from multiprocessing.pool import ThreadPool
from tqdm import tqdm
import argparse
import json
import logging
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

can_re = re.compile(r'[,\.-?"]')
def canonicalize(text):
    text = text.replace("’", "'")
    text = can_re.sub(' ', text)
    return text

def align(audio_file, transcript_file, align_dir, jobs=1, verbose=False, model=None):
    linked_transcript = os.path.join(align_dir, os.path.basename(transcript_file))
    with open(linked_transcript, 'w') as o, open(transcript_file, 'r') as f:
        o.write(canonicalize(f.read()))

    name    = os.path.basename(audio_file).rsplit('.', 1)[0]
    aligned = os.path.join(align_dir, name + '-aligned.json')
    tlog    = os.path.join(align_dir, name + '.tlog')
    if os.path.exists(aligned):
        return audio_file, aligned
    argv = ['python', align_exe,
        '--stt-workers',    str(jobs),
        '--output-max-cer', '25',
        '--audio',   audio_file,
        '--script',  linked_transcript,
        '--aligned', aligned,
        '--tlog',    tlog,
        '--force',
    ]
    if model is not None:
        argv += ['--stt-model-dir', model]
    if verbose:
        print(' '.join(argv))
        p = subprocess.Popen(argv, stdin=devnull)
    else:
        argv += ['--no-progress']
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

            aligned = segment['aligned'].strip().lower()
            text = ' '.join(words_re.findall(text.lower()))
            if aligned != text:
                logging.debug('[-] Discarding Alignment:')
                logging.debug('a|{}'.format(segment['aligned']))
                logging.debug('r|{}'.format(segment['aligned-raw']))
                logging.debug('t|{}'.format(text))
                skipped += 1
                continue

            subname = '{}-{}'.format(name, i)
            clip = '{}/{}.flac'.format(clips_dir, subname)
            if not os.path.exists(clip):
                tf = sox.Transformer()
                tf.trim(start / 1000, end / 1000)
                tf.build(audio_file, clip)
            duration = round(sox.file_info.duration(clip) * 1000, 3)
            yield '{} {} {} {}'.format(subname, clip, duration, text)
        except Exception:
            logging.debug('Error segmenting {}-{}'.format(name, i))
            skipped += 1

    if skipped:
        logging.debug('[-] Clip {}: skipped {}/{} segments due to bad alignment'.format(name, skipped, len(aligned_json)))

def wav2train(args):
    logfile = os.path.abspath('align.log')
    logging.basicConfig(filename=logfile, level=logging.DEBUG)
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    logging.getLogger().addHandler(stream)

    indir     = os.path.abspath(args.input_dir)
    outdir    = os.path.abspath(args.output_dir)
    align_dir = os.path.join(outdir, 'align')
    clips_dir  = os.path.join(outdir, 'clips')
    clips_lst = os.path.join(outdir, 'clips.lst')

    logging.info('[+] Starting new alignment.')
    logging.info('[+] Input: {}'.format(indir))
    logging.info('[+] Output: {}'.format(outdir))

    model_dir = None
    if args.model:
        model_dir = os.path.abspath(args.model)

    os.makedirs(align_dir, exist_ok=True)
    os.makedirs(clips_dir, exist_ok=True)
    os.chdir(dsalign_dir)

    threads = multiprocessing.cpu_count()
    align_pool   = ThreadPool(args.jobs)
    segment_pool = ThreadPool(threads)
    if args.workers is not None:
        stt_jobs = max(1, args.workers)
    else:
        stt_jobs = max(1, threads // args.jobs)

    align_queue = []
    logging.info('[+] Collecting files to align')
    seen_exts   = set()
    unseen_exts = {'flac', 'wav', 'mp3', 'ogg', 'sph', 'aac', 'wma', 'alac'}
    for ent in os.scandir(indir):
        if ent.name.endswith('.txt'):
            txt_path = ent.path
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
            sz = ent.stat(follow_symlinks=True).st_size
            audio_path = n_path
            align_queue.append((sz, audio_path, txt_path))

    align_queue.sort(reverse=True)
    segment_queue = []
    logging.info('[+] Aligning ({}) transcript(s)'.format(len(align_queue)))
    align_fn = lambda t: align(t[1], t[2], align_dir, jobs=stt_jobs, verbose=args.verbose, model=model_dir)
    for audio_path, aligned_json in tqdm(align_pool.imap(align_fn, align_queue), desc='Align', total=len(align_queue)):
        try:
            with open(aligned_json, 'r') as f:
                j = json.load(f)
            segment_queue.append((audio_path, j))
        except Exception:
            logging.debug('Failed to align {}'.format(audio_path))
    logging.info('[+] Alignment complete')

    segment_fn = lambda t: segment(t[0], t[1], clips_dir)
    logging.info('[+] Generating segments for ({}) clip(s)'.format(len(segment_queue)))
    with open(clips_lst, 'w') as lst:
        for lines in tqdm(segment_pool.imap(segment_fn, segment_queue), desc='Segment', total=len(segment_queue)):
            for line in lines: 
                lst.write(line + '\n')
    logging.info('[+] Generated segments. All done.')

if __name__ == '__main__':
    logging.getLogger('sox').setLevel(logging.ERROR)

    parser = argparse.ArgumentParser()
    parser.add_argument('input_dir')
    parser.add_argument('output_dir')
    parser.add_argument('--model',   '-m', help='directory containing speech model', type=str)
    parser.add_argument('--jobs',    '-j', help='alignments to run in parallel', type=int, default=1)
    parser.add_argument('--workers', '-w', help='number parallel transcription workers per job', type=int)
    parser.add_argument('--verbose', '-v', help='print verbose output', action='store_true')
    args = parser.parse_args()
    wav2train(args)
