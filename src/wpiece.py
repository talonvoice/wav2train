import os
import sentencepiece as spm
import sys

def build_corpus(name, lists):
    words = set()
    corpus_path = name + '.corpus'
    with open(corpus_path, 'w') as o:
        for lst in lists:
            with open(lst, 'r') as f:
                for line in f:
                    text = line.split(' ', 3)[-1].strip()
                    for word in text.strip().split():
                        if word: words.add(word)
                    o.write(text + '\n')
    return corpus_path, words

def train_spm(name, corpus_path, vocab_size=10000):
    spm_args = ('--input={} --model_prefix={} --vocab_size={} --hard_vocab_limit=false '
                '--character_coverage=1.0 --normalization_rule_name=nmt_nfkc').format(
                    corpus_path, name, int(vocab_size))
    spm.SentencePieceTrainer.Train(spm_args)

def build_lexicon(name, words, nbest=10):
    sp = spm.SentencePieceProcessor()
    sp.Load(name + '.model')

    exclude = ('<unk>', '<s>', '</s>')
    with open(name + '.tokens', 'w') as o, open(name + '.vocab', 'r') as f:
        for line in f:
            tok = line.strip().split('\t', 1)[0]
            if tok not in exclude:
                o.write(tok.replace('\u2581', '_') + '\n')

    lexicon_path = name + '.lexicon'
    with open(lexicon_path, 'w') as o:
        for word in sorted(words):
            wps = sp.NBestEncodeAsPieces(word, nbest)
            for wp in wps:
                wpstr = ' '.join([w.replace('\u2581', '_') for w in wp])
                o.write('{}\t{}\n'.format(word, wpstr))
    return lexicon_path

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: wpiece <name> <clips.lst> [clips.lst...]')
        sys.exit(1)

    name = sys.argv[1]
    lists = [os.path.abspath(p) for p in sys.argv[2:]]
    print('[+] Building corpus')
    corpus, words = build_corpus(name, lists)
    print('[ ] -> {}'.format(corpus))
    print('[+] Training SentencePieceModel')
    train_spm(name, corpus)
    print('[+] Generating lexicon')
    lexicon = build_lexicon(name, words)
    print('[ ] -> {}'.format(lexicon))
