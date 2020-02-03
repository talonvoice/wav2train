from pydub import AudioSegment
from tqdm import tqdm
import itertools
import multiprocessing
import os
import subprocess
import sys

base_path = os.path.join(os.path.dirname(__file__), '..')
align_path = os.path.realpath(os.path.join(base_path, 'DSAlign', 'align'))
sys.path.append(align_path)

from text import levenshtein as distance
import wav2letter
 
encoder = None
def init_w2l(path):
    global encoder
    loader = wav2letter.W2lLoader(path)
    encoder = loader.load_encoder()

def file_lines(clips_lst):
    with open(clips_lst, 'r') as f:
        return f.read().strip().split('\n')

def collapse_letters(text):
    last_c = None
    out = []
    for c in text:
        if c == last_c:
            continue
        last_c = c
        out.append(c)
    return ''.join(out)

def test_job(line):
    name, clip_path, length, txt = line.strip().split(' ', 3)
    txt = collapse_letters(txt)
    audio = (AudioSegment.from_file(clip_path)
             .set_channels(1)
             .set_frame_rate(16000))
    transcript = encoder.emit(audio.get_array_of_samples())
    ter = distance(txt, transcript) / len(txt)
    return line, transcript, ter

def wfilter_libw2l(w2l_path, clips_lst, threshold):
    pool = multiprocessing.Pool(initializer=init_w2l, initargs=(w2l_path,))
    lines = file_lines(clips_lst)
    for (line, transcript, ter) in tqdm(pool.imap_unordered(test_job, lines), desc='Filter', total=len(lines)):
        if ter < threshold:
            print(line.strip())

def wfilter_batch(w2l_path, clips_lst, threshold):
    lookup = {}
    for line in file_lines(clips_lst):
        name, clip_path, length, txt = line.strip().split(' ', 3)

    Test = os.path.join(w2l_path, 'Test')
    am = os.path.join(w2l_path, 'acoustic.bin')
    tokens = os.path.join(w2l_path, 'tokens.txt')
    lexicon = os.path.join(w2l_path, 'empty.txt')
    if not os.path.exists(lexicon):
        with open(lexicon, 'w') as f: pass

    devnull = open(os.devnull, 'w+')
    p = subprocess.Popen(['Test', '--am', am, '--tokens', tokens, '--lexicon', lexicon, '--test', clips_lst,
                          '--maxload', '-1', '--show', '--maxisz=900000000', '--minisz=25', '--mintsz=1'],
                         stdin=devnull, stdout=subprocess.PIPE, stderr=devnull)
    for line in p.stdout:
        if line.startswith('[sample:'):
            print('sample!')
        print('stdout', line)

def wfilter(w2l_path, clips_lst, threshold):
    if os.path.exists(os.path.join(w2l_path, 'Test')):
        wfilter_batch(w2l_path, clips_lst, threshold)
    else:
        wfilter_libw2l(w2l_path, clips_lst, threshold)

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print('Usage: wfilter w2l_dir/ clips.lst 0.5 > filtered.lst')
        sys.exit(1)
    wfilter(sys.argv[1], sys.argv[2], float(sys.argv[3]))
