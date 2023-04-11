import os
import sys

def all_words(name: str, lists: list[str], raw: bool=False) -> dict[str, str]:
    words = {}
    for lst in lists:
        with open(lst, 'r') as f:
            for line in f:
                if raw:
                    text = line.strip()
                    if ' ' in text:
                        word, spoken = text.split(' ', 1)
                    else:
                        word = spoken = text
                    if word: words[word] = spoken
                else:
                    text = line.split(' ', 3)[-1].strip()
                    for word in text.strip().split():
                        if word: words[word] = word
    return words

def leters(word: str, ctc: bool=False, cap_tokens: bool=False) -> str:
    if cap_tokens:
        tokens = []
        chunk_size = 1
        for i, c in enumerate(word):
            if c == c.lower():
                chunk_size += 1
            else:
                chunk_size = 1
            next_upper = i < len(word) - 1 and word[i + 1].isupper()
            # english hack!
            if (c == 'U' or c == 'u' and i == 0) and next_upper:
                tokens += 'you'
            else:
                tokens.append(c)
            if next_upper and chunk_size in (0, 1):
                tokens += ['|']
        if '|' in tokens:
            print(word, ''.join(tokens))
        word = ''.join(tokens)
    word = word.lower()
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

def build_lexicon(name: str, words: dict[str, str], nbest: int=10, ctc: bool=False) -> str:
    lower_words = {word.lower() for word in words if word != word.upper()}
    lexicon_path = name + '.lexicon'
    with open(lexicon_path, 'w') as o:
        for word, spoken in sorted(words.items()):
            if not word.strip("'"):
                continue
            if spoken == word:
                lword = word.lower()
                cap_tokens = (word != lword and lword in lower_words)
                spoken = leters(word, ctc=ctc, cap_tokens=cap_tokens)
                if not cap_tokens and (word.isupper() and len(word) <= 4):
                    spoken2 = leters(word, ctc=ctc, cap_tokens=True)
                    o.write('{} {} |\n'.format(word, spoken2))
            else:
                spoken = ' '.join('|'.join(spoken.split())).lower()
            o.write('{} {} |\n'.format(word, spoken))
    return lexicon_path

def usage() -> None:
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
