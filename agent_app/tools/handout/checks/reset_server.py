# The app's server with every closing connection failing as the log's did (asyncio's proactor
# raised in socket.shutdown and skipped counting the connection out).
import socket


def reset(self, how):
    raise ConnectionResetError(10054, "simulated: reset by the remote host")


socket.socket.shutdown = reset
import agent_app.__main__ as main

main.serve()
