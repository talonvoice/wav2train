import argparse
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

def build_lexicon(name, words, nbest=10, spm_path=None):
    if spm_path is None:
        spm_path = name
    sp = spm.SentencePieceProcessor()
    sp.Load(spm_path + '.model')

    exclude = ('<unk>', '<s>', '</s>')
    with open(name + '.tokens', 'w') as o, open(spm_path + '.vocab', 'r') as f:
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
    parser.add_argument('clips', help='path to clips.lst', type=str, nargs='+')
    parser.add_argument('--model', '-m', help='pre-trained sentencepiece model', type=str, default=None)
    parser.add_argument('--nbest', '-n', help='number of word piece samples for lexicon', type=int, default=10)
    args = parser.parse_args()

    name = args.name
    lists = [os.path.abspath(p) for p in args.clips]
    print('[+] Building corpus')
    corpus, words = build_corpus(args.name, lists)
    print('[ ] -> {}'.format(corpus))
    if args.model:
        print('[+] Using existing SentencePieceModel:', args.model)
        # strip .model so we get .vocab too
        model = args.model
        if model.endswith('.model'):
            model = model.rsplit('.', 1)[0]
    else:
        print('[+] Training SentencePieceModel')
        train_spm(args.name, corpus)
        model = args.name
    print('[+] Generating lexicon')
    lexicon = build_lexicon(args.name, words, nbest=args.nbest, spm_path=model)
    print('[ ] -> {}'.format(lexicon))
