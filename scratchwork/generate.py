import threading
import random
from gensim import models
from heapq import nsmallest
import json
import datetime
import os

print("Initializing")
KV = models.KeyedVectors.load_word2vec_format(
    "GoogleNews-vectors-negative300.bin", binary=True #, limit=600_000
)
print("Loaded word2vec")

allowed_words = []
with open("words_alpha.txt") as fi:
    for line in fi:
        allowed_words.append(line.rstrip().lower())
allowed_words_set = set(allowed_words)

#names_set = set()
#with open('names.txt', 'r') as ifs:
#    for name in ifs:
#        name = name.strip().lower()
#        names_set.add(name)

base_common_words = set()
with open('base_common_words.txt', 'r') as ifs:
    for word in ifs:
        base_common_words.add(word.strip().lower())

#names_set = names_set - base_common_words

common_words = list()
#for fname in ["common_words.txt"]:
#    with open(fname) as fi:
#        for line in fi:
#            word = line.strip().lower()
#            if word in names_set:
#                continue
#            common_words.append(word)

common_words = base_common_words

class WordScore:
    def __init__(self, idx, score):
        self.word = None
        self.score = round((1 - score) * 100, 1)
        self.topn = None
        self.idx = idx

    def set_word(self, word):
        self.word = word

    def set_topn(self, topn):
        self.topn = topn

    def format(self):
        return f'`{self.word}` (#{self.topn+1}, {self.score:.1f})'

    def format_find(self):
        return f'`{self.word}` found! #{self.topn+1} ({self.score:.1f})'


fnames = os.listdir('words')
for fname in fnames:
    f = fname.split('.')[0]
    if not f in common_words:
        os.remove(f'words/{fname}')


for secret_word in sorted(common_words):
    secret_word = secret_word.lower()
    print(secret_word)
    if not secret_word in allowed_words_set:
        print(f'Illegal word: {secret_word}')
        continue

    if os.path.exists(f'words/{secret_word}.json'):
        continue
    try:
        if len(secret_word) <= 3 or not KV.key_to_index[secret_word]:
            print(f'Word is too short or not found: {secret_word}')
            continue
    except:
        print(f'Word not found in KV: {secret_word}')
        continue

    print(datetime.datetime.now().isoformat())
    print(f'Working on word {secret_word}')

    distance_arr = KV.distances(secret_word)
    items = nsmallest(5000, (WordScore(idx=i, score=v) for i, v in enumerate(distance_arr) if KV.index_to_key[i] != secret_word and KV.index_to_key[i] in allowed_words_set), key = lambda x: (-1*x.score, x.idx))
    if len(items) < 4000:
        print(f'Not enough related words ({len(ltems)}) found for {secret_word}')
        continue

    with open(f'words/{secret_word}.json', 'w') as ofs:
        json.dump(
            {
                "word": secret_word,
                "top_words": [
                    {
                        "word": KV.index_to_key[ws.idx],
                        "n": i,
                        "score": ws.score
                    }
                    for i, ws in enumerate(items)
                ]
            },
            fp=ofs
        )

