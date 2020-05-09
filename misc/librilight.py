from collections import defaultdict
from tqdm import tqdm
from urllib.parse import urlparse
import json
import os
import re
import requests
import sys
import traceback

book_id_re = re.compile(r'/(\d+)(/|$)')

name_nonces = defaultdict(int)

def get_book(dst, gut_id):
    book_path = os.path.join(dst, str(gut_id) + '.txt')
    if os.path.exists(book_path):
        return book_path
    file_url = 'http://www.gutenberg.org/files/{}/'.format(gut_id)
    resp = requests.get(file_url)
    submatch = re.search(r'\b{}[\w-]*\.txt\b'.format(gut_id), resp.text)
    if submatch:
        submatch = submatch.group(0)
        resp = requests.get(file_url + submatch)
        with open(book_path, 'w') as f:
            f.write(resp.text)
        return book_path
    raise Exception('could not find book url')

def main(src, audio_src, dst):
    os.makedirs(dst, exist_ok=True)

    queue = []
    for root, dirs, names in os.walk(src):
        for name in names:
            if name.endswith('.json'):
                queue.append(os.path.join(root, name))

    for json_path in tqdm(queue, desc='Finding Books'):
        try:
            with open(json_path, 'r', encoding='utf8') as f:
                j = json.load(f)
            pathname = os.path.basename(json_path).rsplit('.', 1)[0]
            json_dir = os.path.dirname(json_path)

            if pathname.endswith('_speaker_data'):
                continue

            audio_files = []
            if pathname.endswith('_metadata'):
                pathname = pathname.rsplit('_', 1)[0]
                # partial mp3 path
                book_meta = j
                speaker_data_path = os.path.join(json_dir, pathname) + '_speaker_data.json'
                with open(speaker_data_path, 'r') as f:
                    speaker_data = json.load(f)

                speakers = dict(zip([name.rsplit('_', 1)[0] for name in speaker_data['names']],
                                    [reader[0] for reader in speaker_data['readers'] if reader]))
                mp3_dir = os.path.join(audio_src, pathname)
                for entry in os.scandir(mp3_dir):
                    if entry.path.endswith(('.mp3', '.flac')):
                        reader = speakers.get(entry.name.rsplit('_', 1)[0], '0')
                        audio_files.append((reader, entry.path))
            else:
                # flac prepared path
                audio_path = os.path.join(json_dir, pathname + '.flac')
                if not os.path.exists(audio_path):
                    continue
                book_meta = j['book_meta']
                audio_files = [(j['speaker'], audio_path)]

            txt_path = os.path.join(json_dir, pathname) + '_text.txt'
            book_path = ''
            if os.path.exists(txt_path):
                book_path = txt_path
            else:
                url_text = book_meta['url_text_source']
                url = urlparse(url_text)
                if url_text and url.hostname and url.hostname.endswith('gutenberg.org'):
                    match = book_id_re.search(url.path)
                    if match:
                        gut_id = match.group(1)
                        book_path = get_book(dst, gut_id)

            if book_path:
                for spk_id, audio_file in sorted(audio_files):
                    lv_id = book_meta['id']
                    id_str = '{}_{}'.format(spk_id, lv_id)
                    nonce = name_nonces[id_str]
                    name_nonces[id_str] += 1
                    name = '{}-{}'.format(id_str, nonce)

                    dst_name = os.path.join(dst, name)
                    try: os.link(book_path, dst_name + '.txt')
                    except FileExistsError: pass
                    try: os.link(audio_file, dst_name + '.' + audio_file.rsplit('.', 1)[1])
                    except FileExistsError: pass
        except Exception:
            print('Error at', json_path)
            traceback.print_exc()

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: librilight-prep <input> [<audio_dir>] <output>')
        sys.exit(1)
    if len(sys.argv) == 4:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        main(sys.argv[1], sys.argv[1], sys.argv[2])
