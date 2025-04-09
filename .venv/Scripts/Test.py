import zmq

context = zmq.Context()
router_socket = context.socket(zmq.ROUTER)
router_socket.bind("tcp://*:5555")
print("Minimal-Server (ROUTER) lauscht auf Port 5555")

while True:
    message = router_socket.recv_multipart()
    print(f"Empfangen: {message}")