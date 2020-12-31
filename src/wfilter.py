from multiprocessing import Pool
from tempfile import NamedTemporaryFile
from tqdm import tqdm
import argparse
import cffi
import itertools
import os
import re
import subprocess
import sys

# start miniflac
flac_ffi = cffi.FFI()
flac_ffi.cdef(r'''
typedef struct {
    uint32_t blocksize;
} FLAC__FrameHeader;

void *FLAC__stream_decoder_new();
int FLAC__stream_decoder_init_file(
    void *decoder,
    const char *filename,
    void *write_callback,
    void *metadata_callback,
    void *error_callback,
    void *client_data
);
void FLAC__stream_decoder_delete(void *);
bool FLAC__stream_decoder_process_until_end_of_stream(void *);
uint32_t FLAC__stream_decoder_get_sample_rate(void *);
uint32_t FLAC__stream_decoder_get_channels(void *);
uint32_t FLAC__stream_encoder_get_state(void *);
''')
try:
    flac_lib = flac_ffi.dlopen('libFLAC.so')
except Exception:
    flac_lib = None

@flac_ffi.callback('int (void *, FLAC__FrameHeader *, void *, size_t *)')
def miniflac_stream_read(decoder, frame, buf, samples_out):
    samples_out[0] += frame.blocksize
    return 0

@flac_ffi.callback('void ()')
def miniflac_stream_error():
    return 0

def miniflac_read_file(path):
    sample_count = flac_ffi.new('size_t *')
    decoder = flac_lib.FLAC__stream_decoder_new()
    try:
        status = flac_lib.FLAC__stream_decoder_init_file(
                decoder, path.encode('utf8'), miniflac_stream_read, flac_ffi.NULL, miniflac_stream_error, sample_count)
        if status:
            err = flac_lib.FLAC__stream_encoder_get_state(decoder)
            raise RuntimeError('FLAC decode init failed: {}'.format(err))
        if not flac_lib.FLAC__stream_decoder_process_until_end_of_stream(decoder):
            raise RuntimeError('FLAC decode failed')
        sample_rate = flac_lib.FLAC__stream_decoder_get_sample_rate(decoder)
        channels    = flac_lib.FLAC__stream_decoder_get_channels(decoder)
        return sample_count[0] / sample_rate, channels
    finally:
        flac_lib.FLAC__stream_decoder_delete(decoder)
# end miniflac

def srange(desc):
    if not desc:
        return range(0, sys.maxsize)
    rmin, rmax = map(int, desc.split('-', 1))
    return range(rmin, rmax+1)

def valid_audio_fn(line):
    parts = line.split(' ', 3)
    if len(parts) != 4:
        return
    path = parts[1]
    try:
        # double check flacs
        is_flac = path.endswith('.flac')
        if is_flac and flac_lib:
            length, channels = miniflac_read_file(path)
            length *= 1000
            if channels != 1:
                return None
        elif is_flac:
            subprocess.check_call(['flac', '-ts', path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            out = subprocess.check_output(['metaflac', '--show-total-samples', '--show-sample-rate', path])
            total_samples, sample_rate = map(int, out.strip().split(b'\n'))
            length = (total_samples / sample_rate) * 1000
        else:
            argv = ['ffprobe', '-i', path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()
            length = float(out.strip()) * 1000
    except Exception:
        return None
    if length > 1.0 and abs(length - float(parts[2])) < 1.0:
        return line
    return None

def filter_lines(lines):
    return (line for line in lines
            if line.count(' ') >= 3)

def filter_audio_length(lines, audio_range):
    for line in lines:
        audio_length = int(float(line.split(' ', 3)[2]))
        if audio_length in audio_range:
            yield line

def filter_char_length(lines, char_range):
    for line in lines:
        text = line.split(' ', 3)[3]
        if len(text) in char_range:
            yield line

def filter_regex(lines, regex):
    for line in lines:
        text = line.split(' ', 3)[3]
        if regex.match(text):
            yield line

def filter_valid_audio(lines):
    pool = Pool()
    for line in pool.imap_unordered(valid_audio_fn, lines):
        if line:
            yield line

def filter_test(args, lines, desc):
    lookup = {}
    for line in lines:
        try:
            name, clip_path, length, txt = line.strip().split(' ', 3)
        except Exception:
            continue
        lookup[name] = line

    with NamedTemporaryFile('w', suffix='.txt') as lexicon, NamedTemporaryFile('w', suffix='.lst') as tmp_lst:
        tmp_lst.write('\n'.join(lines) + '\n')
        tmp_lst.flush()

        p = subprocess.Popen([args.w2l_test, '--am', args.am, '--tokens', args.tokens, '--lexicon', lexicon.name, '--test', tmp_lst.name,
                              '--maxload', '-1', '--show', '--uselexicon=false',
                              '--minisz=25', '--maxisz=900000000', '--mintsz=1', '--maxtsz=900000000',
                              '--datadir=', '--tokensdir=', '--rundir=', '--archdir=', '--emission_dir='],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def sample_iter():
            for line in p.stdout:
                line = line.decode('utf8').strip()
                if line.startswith('[sample:'):
                    yield line

        for line in tqdm(sample_iter(), desc='{} (w2l)'.format(desc), total=len(lines)):
            parts = line.split(' ')
            WER = float(parts[3].strip(',%')) / 100
            TER = float(parts[5].strip(',%')) / 100
            if (not args.LER or TER <= args.LER) and (not args.WER or WER <= args.WER):
                name = parts[1].strip(',')
                if name in lookup:
                    yield lookup[name]

class Stats:
    def __init__(self, total):
        self.total = total
        self.counts = {}
        self.order = []
        self.minisz = self.minlsz = self.minwsz = sys.maxsize
        self.maxisz = self.maxlsz = self.maxwsz = 0

    def wrap(self, name, lines):
        self.order.append(name)
        def wrapper(lines):
            n = 0
            for line in lines:
                n += 1
                yield line
            self.counts[name] = n
        return wrapper(lines)

    def line(self, line):
        name, path, length, text = line.split(' ', 3)
        wcount = text.count(' ') + 1 if text else 0
        length = float(length)
        self.minisz = min(self.minisz, length)
        self.maxisz = max(self.maxisz, length)
        self.minlsz = min(self.minlsz, len(text))
        self.maxlsz = max(self.maxlsz, len(text))
        self.minwsz = min(self.minwsz, wcount)
        self.maxwsz = max(self.maxwsz, wcount)

    def dump(self):
        eprint = lambda *args: print(*args, file=sys.stderr)
        name_pad = max(len(name) for name in self.order) + 1

        steps = []
        last_count = self.total
        for name in self.order:
            count = self.counts[name]
            text = '{} ({:,})'.format(name, count - last_count)
            steps.append(text)
            last_count = count
        eprint('| pipeline: input={} > {}'.format(self.total, ' > '.join(steps)))
        audio_stats = 'audio (min={}ms max={}ms)'.format(int(self.minisz), int(self.maxisz))
        char_stats = 'chars (min={} max={})'.format(self.minlsz, self.maxlsz)
        word_stats = 'words (min={} max={})'.format(self.minwsz, self.maxwsz)
        eprint('| stats:    {} {} {}'.format(audio_stats, char_stats, word_stats))

def wfilter(args):
    w2l_args = (args.w2l_test, args.am)
    w2l_fargs = (args.LER, args.WER)
    if any(w2l_args + w2l_fargs) and not (all(w2l_args) and any(w2l_fargs)):
        raise ValueError('Must provide all of (--w2l_test --am) and at least one of (--LER --WER)')

    with open(args.lst, 'r') as f:
        lines = f.read().strip().split('\n')
    total = len(lines)
    lines = filter_lines(lines)

    stats = Stats(total)
    if args.audio:
        audio_range = srange(args.audio)
        lines = filter_audio_length(lines, audio_range)
        lines = stats.wrap('audio', lines)

    if args.chars:
        chars_range = srange(args.chars)
        lines = filter_char_length(lines, chars_range)
        lines = stats.wrap('chars', lines)

    if args.regex:
        regex = re.compile(args.regex) if args.regex else re.compile(r'')
        lines = filter_regex(lines, regex)
        lines = stats.wrap('regex', lines)

    if args.valid:
        lines = filter_valid_audio(lines)
        lines = stats.wrap('valid', lines)

    line_iter = tqdm(lines, desc=args.desc, total=total)
    if all(w2l_args):
        lines = list(line_iter)
        line_iter = filter_test(args, lines, args.desc)
        line_iter = stats.wrap('w2l_test', line_iter)

    for line in line_iter:
        print(line)
        stats.line(line)

    stats.dump()

if __name__ == '__main__':
    example = '''
    Example: wfilter clips.lst --valid --audio 35-33000 --chars 1-600 > clips-filter.lst
    Example: wfilter clips.lst --w2l_test ~/wav2letter/build/Test --am acoustic.bin --tokens tokens.txt --LER 0.5 > clips-filter.lst
    '''.rstrip()
    parser = argparse.ArgumentParser()
    parser.add_argument('lst',        help='input lst dataset file', type=str)
    parser.add_argument('--w2l_test', help='path to wav2letter Test binary', type=str)
    parser.add_argument('--am',       help='path to wav2letter acoustic model', type=str)
    parser.add_argument('--tokens',   help='path to wav2letter tokens', type=str)
    parser.add_argument('--LER',      help='minimum Letter Error Rate', type=float)
    parser.add_argument('--WER',      help='minimum Word Error Rate', type=float)
    parser.add_argument('--desc',     help='description (for progress bar)', type=str)
    parser.add_argument('--audio',    help='filter on audio length range (range MIN-MAX milliseconds)', type=str)
    parser.add_argument('--chars',    help='filter on char count (range MIN-MAX chars)', type=str)
    parser.add_argument('--regex',    help="filter transcripts not matching regex e.g. --transcript \"^[a-zA-Z' ]+$\"", type=str)
    parser.add_argument('--valid',    help='filter broken audio files', action='store_true')
    try:
        args = parser.parse_args()
    except SystemExit:
        print(example, file=sys.stderr)
        raise
    wfilter(args)
