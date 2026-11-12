# Plain requests, each on its own connection, closed after the answer.
import sys
import urllib.request

for _ in range(int(sys.argv[2])):
    urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health").read()
print("asked", sys.argv[2])
