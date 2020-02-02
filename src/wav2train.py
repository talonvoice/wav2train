from multiprocessing.pool import Pool
from tqdm import tqdm
import argparse
import gc
import itertools
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

def align(args):
    size, audio_file, transcript_file, align_dir, jobs, verbose, model = args
    name = os.path.basename(audio_file).rsplit('.', 1)[0]
    tlog = os.path.join(align_dir, name + '.tlog')
    aligned = os.path.join(align_dir, name + '-aligned.json')
    linked_transcript = os.path.join(align_dir, os.path.basename(transcript_file))
    if os.path.exists(aligned):
        return audio_file, aligned, linked_transcript
    with open(linked_transcript, 'w') as o, open(transcript_file, 'r') as f:
        o.write(canonicalize(f.read()))
    argv = ['python', align_exe,
        '--audio-vad-aggressiveness', '2',
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
        logging.debug(line)
    return (audio_file, aligned, linked_transcript)

words_re = re.compile(r"[a-zA-Z']+")

def segment(args):
    audio_file, aligned_path, txt_path, clips_dir = args
    name = os.path.basename(audio_file).split('.')[0]
    skipped = 0
    results = []
    with open(aligned_path, 'r') as f:
        aligned_json = json.load(f)
    with open(txt_path, 'r') as f:
        transcript = f.read()
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

            # skip transcripts that aren't snapped to word boundaries
            text_start, text_end = segment['text-start'], segment['text-end']
            if text_start > 0 and transcript[text_start-1].strip():
                logging.debug('[-] Discarding bad start alignment: {}'.format(repr(transcript[text_start-1:text_start+10])))
                skipped += 1
                continue
            if text_end < len(transcript) and transcript[text_end].strip():
                logging.debug('[-] Discarding bad end alignment: {}'.format(repr(transcript[text_end-1:text_end+10])))
                skipped += 1
                continue

            subname = '{}-{}'.format(name, i)
            clip = '{}/{}.flac'.format(clips_dir, subname)
            if not os.path.exists(clip):
                tf = sox.Transformer()
                tf.trim(start / 1000, end / 1000)
                tf.convert(16000, 1, 16)
                tf.remix()
                tf.build(audio_file, clip)
            duration = round(end - start, 3)
            results.append('{} {} {} {}'.format(subname, clip, duration, text))
        except Exception:
            logging.debug('Error segmenting {}-{}'.format(name, i))
            skipped += 1
    return results

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
    if args.workers is not None:
        stt_jobs = max(1, args.workers)
    else:
        stt_jobs = max(1, threads // args.jobs)

    align_queue = []
    align_args = (align_dir, stt_jobs, args.verbose, model_dir)
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
            align_queue.append((sz, audio_path, txt_path) + align_args)

    align_queue.sort(reverse=True)
    segment_queue = []
    chunksize = max(1, min(4, len(align_queue) // args.jobs))
    gc.collect()
    align_pool = Pool(args.jobs)
    align_iter = align_pool.imap_unordered(align, align_queue, chunksize=chunksize)
    logging.info('[+] Aligning ({}) transcript(s)'.format(len(align_queue)))
    for audio_path, aligned_path, txt_path in tqdm(align_iter, desc='Align', total=len(align_queue)):
        try:
            segment_queue.append((audio_path, aligned_path, txt_path, clips_dir))
        except Exception:
            logging.debug('Failed to align {}'.format(audio_path))
    logging.info('[+] Alignment complete')

    chunksize = max(1, min(4, len(segment_queue) // threads))
    gc.collect()
    segment_pool = Pool(threads)
    segment_iter = segment_pool.imap_unordered(segment, segment_queue, chunksize=chunksize)
    logging.info('[+] Generating segments for ({}) clip(s)'.format(len(segment_queue)))
    with open(clips_lst, 'w') as lst:
        for lines in tqdm(segment_iter, desc='Segment', total=len(segment_queue)):
            lst.write('\n'.join(lines) + '\n')
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
