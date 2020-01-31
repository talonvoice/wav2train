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

def main(src, dst):
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
            flac_path = json_path.rsplit('.', 1)[0] + '.flac'

            book_meta = j['book_meta']
            url_text = book_meta['url_text_source']
            url = urlparse(url_text)
            if url_text and url.hostname and url.hostname.endswith('gutenberg.org'):
                match = book_id_re.search(url.path)
                if match:
                    spk_id = j['speaker']
                    lv_id = j['book_meta']['id']
                    gut_id = match.group(1)
                    id_str = '{}_{}_{}'.format(spk_id, lv_id, gut_id)
                    nonce = name_nonces[id_str]
                    name_nonces[id_str] += 1
                    name = '{}-{}'.format(id_str, nonce)

                    dst_name = os.path.join(dst, name)
                    book_path = get_book(dst, gut_id)
                    try: os.link(book_path, dst_name + '.txt')
                    except FileExistsError: pass
                    try: os.link(flac_path, dst_name + '.flac')
                    except FileExistsError: pass
        except Exception:
            print('Error at', json_path)
            traceback.print_exc()

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: librilight-prep <input> <output>')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
