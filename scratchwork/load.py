import os
import json
import time
t = time.time()
with open('mess.json', 'r') as ofs:
    for line in ofs:
        try:
            json.loads(line)
        except:
            print('oops')

print(time.time() - t)
