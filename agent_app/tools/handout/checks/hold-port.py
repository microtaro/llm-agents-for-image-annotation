# Holds a port as another program would, until the stop file appears or the time runs out.
#   hold-port.py PORT STOP_FILE SECONDS
import os
import socket
import sys
import time

port, stop, seconds = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
held = socket.socket()
held.bind(("127.0.0.1", port))
held.listen(1)
end = time.time() + seconds
while time.time() < end and not os.path.exists(stop):
    time.sleep(0.5)
