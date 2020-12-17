import os
import sys

def all_words(name, lists, raw=False):
    words = set()
    for lst in lists:
        with open(lst, 'r') as f:
            for line in f:
                if raw:
                    text = line.strip()
                else:
                    text = line.split(' ', 3)[-1].strip()
                for word in text.strip().split():
                    if word: words.add(word)
    return words

def leters(word, ctc=False):
    if word.startswith("'") and word.endswith("'"):
        word = word[1:-1].strip()
    if ctc:
        return ' '.join(word)
    out = []
    last = None
    for c in word:
        if c != last: out.append(c)
        last = c
    return ' '.join(out)

def build_lexicon(name, words, nbest=10, ctc=False):
    lexicon_path = name + '.lexicon'
    with open(lexicon_path, 'w') as o:
        for word in sorted(words):
            if not word.strip("'"):
                continue
            o.write('{} {}\n'.format(word, leters(word, ctc=ctc)))
    return lexicon_path

def usage():
    print('Usage: wlexicon [--ctc] [--raw] <name> <clips.lst> [clips.lst...]')
    sys.exit(1)

if __name__ == '__main__':
    ctc = '--ctc' in sys.argv
    raw = '--raw' in sys.argv
    if ctc: sys.argv.remove('--ctc')
    if raw: sys.argv.remove('--raw')
    if len(sys.argv) < 2:
        usage()

    name = sys.argv[1]
    lists = [os.path.abspath(p) for p in sys.argv[2:]]
    print('[+] Finding words')
    words = all_words(name, lists, raw=raw)
    print('[+] Generating lexicon')
    lexicon = build_lexicon(name, words, ctc=ctc)
    print('[ ] -> {}'.format(lexicon))
