import socket
import threading

SERVER_PORT = 5002
BUFFER_SIZE = 1024
TTL = 1  # Time-to-live for multicast packets
ACK_TIMEOUT = 3  # Time to wait for an acknowledgment before retransmitting
WINDOW_SIZE = 5  # Number of packets sent before waiting for ACKs

def is_port_free(port):
   
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as temp_sock:
        try:
            temp_sock.bind(('', port))
            return True
        except OSError:
            return False
        
def get_available_port():
    # Create a temporary socket to find an available port
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as temp_sock:
        temp_sock.bind(('', 0))  # Bind to port 0 to let the OS assign an available port
        port = temp_sock.getsockname()[1]  # Retrieve the port number assigned
    return port

def create_socket(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
    sock.settimeout(ACK_TIMEOUT)
    sock.bind(('', port))

    print(f"Port bind successful")

port = get_available_port()

print(f"Port = {port}")
print(f"Response = {is_port_free(port)}")

th = threading.Thread(target=create_socket, args=(port,))
th.start()

th.join()
