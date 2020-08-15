import argparse
import os
import sentencepiece as spm
import sys

def build_corpus(name, lists=(), corpora=()):
    words = set()
    if not lists and len(corpora) == 1:
        # fast path for using an existing text corpus
        with open(corpora[0], 'r') as f:
            for line in f:
                for word in line.strip().split():
                    # TODO: use an alphabet whitelist like wav2train?
                    if word: words.add(word.lower())
        return corpora[0], words

    corpus_path = name + '.corpus'
    with open(corpus_path, 'w') as o:
        for lst in lists:
            with open(lst, 'r') as f:
                for line in f:
                    text = line.split(' ', 3)[-1].strip()
                    for word in text.strip().split():
                        if word: words.add(word)
                    o.write(text + '\n')
        for text in corpora:
            with open(text, 'r') as f:
                for line in f:
                    for word in line.strip().split():
                        # TODO: use an alphabet whitelist like wav2train?
                        if word: words.add(word.lower())
                    o.write(line.rstrip() + '\n')
    return corpus_path, words

def train_spm(name, corpus_path, vocab_size=10000, nthread=1):
    spm_args = ('--input={} --model_prefix={} --vocab_size={} --num_threads={} '
                '--hard_vocab_limit=false '
                '--character_coverage=1.0 '
                '--normalization_rule_name=nmt_nfkc').format(
                    corpus_path, name, int(vocab_size), int(nthread))
    spm.SentencePieceTrainer.Train(spm_args)

def build_lexicon(name, words, nbest=10, spm_path=None):
    if spm_path is None:
        spm_path = name
    model_path = spm_path + '.model'
    vocab_path = spm_path + '.vocab'
    if os.path.isfile(spm_path) and not os.path.isfile(model_path):
        model_path = spm_path
    sp = spm.SentencePieceProcessor()
    sp.Load(model_path)

    if not os.path.exists(vocab_path):
        print('[-] spm vocab file ({}) not found, skipping token generation'.format(vocab_path))
    else:
        exclude = ('<unk>', '<s>', '</s>')
        with open(name + '.tokens', 'w') as o, open(vocab_path, 'r') as f:
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
    parser = argparse.ArgumentParser()
    parser.add_argument('name', help='model name prefix', type=str)
    parser.add_argument('--text', help='path to corpus text file(s)', type=str, nargs='*')
    parser.add_argument('--list',  help='w2l clips.lst file(s)', type=str, nargs='*')
    parser.add_argument('--model',   '-m', help='pre-trained sentencepiece model', type=str, default=None)
    parser.add_argument('--nbest',   '-n', help='number of word piece samples for lexicon', type=int, default=10)
    parser.add_argument('--ntoken',  '-w', help='number of tokens in vocabulary to train', type=int, default=10000)
    parser.add_argument('--nthread', '-j', help='number of threads to use for training', type=int, default=1)
    args = parser.parse_args()

    if not (args.text or args.list):
        print('Error: you must provide --text or --list')
        parser.print_help()
        sys.exit(1)

    name = args.name
    lists = [os.path.abspath(p) for p in args.list or ()]
    corpora = [os.path.abspath(p) for p in args.text or ()]
    print('[+] Processing corpus')
    corpus, words = build_corpus(args.name, lists=lists, corpora=corpora)
    print('[ ] -> {}'.format(corpus))
    if args.model:
        print('[+] Using existing SentencePieceModel:', args.model)
        # strip .model so we get .vocab too
        model = args.model
        if model.endswith('.model'):
            model = model.rsplit('.', 1)[0]
    else:
        print('[+] Training SentencePieceModel')
        train_spm(args.name, corpus, vocab_size=args.ntoken, nthread=args.nthread)
        model = args.name
    print('[+] Generating lexicon')
    lexicon = build_lexicon(args.name, words, nbest=args.nbest, spm_path=model)
    print('[ ] -> {}'.format(lexicon))
