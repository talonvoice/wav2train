import os
import sys

def all_words(name, lists):
    words = set()
    for lst in lists:
        with open(lst, 'r') as f:
            for line in f:
                text = line.split(' ', 3)[-1].strip()
                for word in text.strip().split():
                    if word: words.add(word)
    return words

def leters(word):
    if word.startswith("'") and word.endswith("'"):
        word = word[1:-1].strip()
    out = []
    last = None
    for c in word:
        if c != last: out.append(c)
        last = c
    return ' '.join(out)

def build_lexicon(name, words, nbest=10):
    lexicon_path = name + '.lexicon'
    with open(lexicon_path, 'w') as o:
        for word in sorted(words):
            o.write('{} {}\n'.format(word, leters(word)))
    return lexicon_path

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: wlexicon <name> <clips.lst> [clips.lst...]')
        sys.exit(1)

    name = sys.argv[1]
    lists = [os.path.abspath(p) for p in sys.argv[2:]]
    print('[+] Finding words')
    words = all_words(name, lists)
    print('[+] Generating lexicon')
    lexicon = build_lexicon(name, words)
    print('[ ] -> {}'.format(lexicon))
