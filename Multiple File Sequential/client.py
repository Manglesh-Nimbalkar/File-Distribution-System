import socket
import struct
import os
import hashlib
import threading
from tqdm import tqdm
from tkinter import messagebox, simpledialog
from database import fetch_groups
import time


SERVER_PORT = 5002
BUFFER_SIZE = 1024
SERVER_IP = '127.0.0.1'
CLIENT_PORT = 5500

def get_saved_user_id(group_name):
    try:
        with open(f"{group_name}_user_id.txt", 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
    


# Function to send a request to join a group
def send_join_request(group_name):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:

        username = simpledialog.askstring("Input","Enter your username :")

        request = f"JOIN:{username}:{group_name}"
        # sock.sendto(request.encode('utf-8'), (SERVER_IP, SERVER_PORT))
        sock.sendto(request.encode('utf-8'), (SERVER_IP, CLIENT_PORT))

        # Wait for server response
        response, _ = sock.recvfrom(1024)
        response = response.decode('utf-8')

        if response.startswith("APPROVED"):
            user_id = response.split(":")[1]
            messagebox.showinfo("Join Group", f"Join request approved! Your user ID is {user_id}.")
            save_user_id(group_name, user_id)
            return user_id
        else:
            messagebox.showerror("Join Group", "Join request denied by the server.")
            return None
        
# Functionality to save the user ID
def save_user_id(group_name, user_id):
    with open(f"{group_name}_user_id.txt", 'w') as f:
        f.write(user_id)




# Functionality to validate the user ID
def validate_user_id(user_id, group_name):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    validation_request = f"VALIDATE:{user_id}:{group_name}"
    sock.sendto(validation_request.encode('utf-8'), (SERVER_IP, CLIENT_PORT))

    response, _ = sock.recvfrom(1024)
    response = response.decode('utf-8')
    return response == "VALID"


# Functionality to join the multicast group
def join_multicast_group(user_id, group_name):
    if validate_user_id(user_id, group_name):
        GROUPS = fetch_groups()
        multicast_group = GROUPS[group_name]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', SERVER_PORT))
        # sock.bind(('', 5001))

        mreq = struct.pack("4sl", socket.inet_aton(multicast_group), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        print(f"[+] User {user_id} joined multicast group {group_name} ({multicast_group})")
        return sock
    else:
        print("User ID validation failed")
        return None


def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as temp_sock:
        try:
            temp_sock.bind(('', port))
            return True
        except OSError:
            return False


def receive_metadata(multicast_group, user_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', SERVER_PORT))

    mreq = struct.pack("4sl", socket.inet_aton(multicast_group), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print(f"Connected to Server Port : {SERVER_PORT}")

    total_files = 0
    port_received = "FALSE"
    port = 0
    while port_received == "FALSE":
        data, address = sock.recvfrom(4096)
        data = data.decode('utf-8')
        if data.startswith('PORT'):
            command = data.split('<SEPARATOR>')[1:]
            print(f"Command = {command}")
            if command[0] == user_id:
                port = int(command[1])
                total_files = int(command[2])
                if is_port_free(port):
                    port_received = "TRUE"
                    print(f"Received port = {port}")
        response = f"PORT<SEPARATOR>{user_id}<SEPARATOR>{port_received}"
        sock.sendto(response.encode('utf-8'), address)

    for _ in range(total_files):
        receive_file(multicast_group, user_id, port)
        
            



def receive_file(multicast_group, user_id, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', port))

        mreq = struct.pack("4sl", socket.inet_aton(multicast_group), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        print(f"Connected to port : {port}")

        # Validation for meta data
        data, address = sock.recvfrom(4096)

        try:
            metadata = data.decode('utf-8')
            print(metadata)
            filename, filesize, command_str = metadata.split('<SEPARATOR>')
            filesize = int(filesize)
            command = command_str == "True"  
            filename = os.path.basename(filename)
        except UnicodeDecodeError as e:
            print("[-] Error: Received data is not valid metadata.")
            sock.close()
            return
        
        ack = "METADATA<SEPARATOR>True"
        sock.sendto(ack.encode('utf-8'), address)

        

        print(f"[+] Receiving file: {filename} with size: {filesize} bytes")

        total_bytes_received = 0
        buffer = {}  
        expected_sequence_number = 0

        progress_bar = tqdm(total=filesize, unit='B', unit_scale=True, desc="Receiving")

        with open(filename, 'wb') as f:
            while total_bytes_received < filesize:
                data, address = sock.recvfrom(BUFFER_SIZE + 36 + len(user_id))
                seq_number = struct.unpack('I', data[:4])[0]
                checksum_received = data[4:36].decode()
                received_user_id = data[36:36 + len(user_id)].strip().decode()
                file_data = data[36 + len(user_id):]

                # Verify the checksum
                checksum_calculated = hashlib.md5(file_data).hexdigest()
                if checksum_received == checksum_calculated and received_user_id == user_id:
                    # Store the packet in the buffer
                    buffer[seq_number] = file_data

                    # Write packets in order
                    while expected_sequence_number in buffer:
                        f.write(buffer.pop(expected_sequence_number))
                        total_bytes_received += len(file_data)
                        progress_bar.update(len(file_data))
                        expected_sequence_number += 1

                    # Send ACK
                    ack_packet = struct.pack('I', seq_number) + user_id.encode().ljust(36)
                    sock.sendto(ack_packet, address)

        progress_bar.close()

        print(f"[+] File {filename} received successfully.")


        # Send final acknowledgment with user ID and filename
        final_ack = f"ACK_COMPLETE<SEPARATOR>{user_id}<SEPARATOR>{filename}"
        sock.sendto(final_ack.encode('utf-8'), address)

        # Wait for post-transfer command
        if command :
            print("Expecting command from server ...")
            try:
                command_data, address = sock.recvfrom(4096)
                command_metadata = command_data.decode('utf-8')
                print(command_metadata)
                if command_metadata.startswith("COMMAND<SEPARATOR>"):
                    commands = command_metadata.split('<SEPARATOR>')
                    commands.pop(0)
                    for command in commands:
                        print(f"[+] Executing post-transfer command: {command}")
                        os.system(command)
            except UnicodeDecodeError as e:
                print("[-] Error: Received data is not a valid command.")
            except Exception as e:
                print(f"[-] Error executing command: {e}")

        sock.close()
    

    except PermissionError as e:
        print(f"PermissionError: {e}")
        print("Ensure that the port is not being blocked by a firewall or used by another process.")

    except Exception as e:
        print("This is the correct error")
        print(f"Error occurred: {e}")



