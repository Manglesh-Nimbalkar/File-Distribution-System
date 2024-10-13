import socket
import struct
import os
import hashlib
import threading
import json
from tqdm import tqdm
from tkinter import messagebox, simpledialog
from database import fetch_groups


SERVER_PORT = 5002
BUFFER_SIZE = 1024
SERVER_IP = '127.0.0.1'
CLIENT_PORT = 5001
# CHUNK_SIZE = 100*1024*1024  
CHUNK_SIZE = 5*1024*1024  

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
    sock.sendto(validation_request.encode('utf-8'), (SERVER_IP, 5001))

    response, _ = sock.recvfrom(1024)
    response = response.decode('utf-8')
    return response == "VALID"



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

    print(f"Connected to port : {SERVER_PORT}")

    total_files = 0
    received_total_files = "FALSE"

    while received_total_files == "FALSE":
        
        data, address = sock.recvfrom(4096)

        msg = data.decode('utf-8').split('<SEPARATOR>')
        id = msg[1]
        total_files = int(msg[2])
        command_status = msg[3]

        if user_id == id:
            received_total_files = "TRUE"
            print(f"Total files = {total_files}")
        else:
            received_total_files = "FALSE"
        
        response = f"STATUS<SEPARATOR>{user_id}<SEPARATOR>{received_total_files}"
        sock.sendto(response.encode('utf-8'), address)

  

    threads = [None] * total_files
    index = 0
    while index < total_files:
        while True:
            data, address = sock.recvfrom(4096)
            try:
                metadata = data.decode('utf-8')
                file_id, id, filename, filesize, file_port = metadata.split('<SEPARATOR>')
                file_id = int(file_id)
                filesize = int(filesize)
                file_port = int(file_port)
                filename = os.path.basename(filename)
                print(f"Metadata = {metadata}")
            except UnicodeDecodeError as e:
                print("[-] Error: Received data is not valid metadata.")
                sock.close()
                return
            
            if is_port_free(file_port):
                if threads[file_id] is None and id == user_id and file_id == index:
                    print(f"Allocated port = {file_port}")
                    ack = f"METADATA<SEPARATOR>{file_id}<SEPARATOR>{user_id}"
                    sock.sendto(ack.encode('utf-8'), address)
                    th = threading.Thread(target=receive_file, args=(index, filename, filesize, file_port, multicast_group, user_id))
                    threads[file_id] = th
                    break
            else:
                print(f"[-] Port {file_port} is already in use. Cannot start file transfer for {filename}.")
        
        index += 1


    for thread in threads:
        if thread is not None:
            thread.start()

    for thread in threads:
        if thread is not None:
            thread.join()

    chunk_info = {}
    while len(chunk_info) == 0:
        response = ""
        data, address = sock.recvfrom(4096)
        data = data.decode('utf-8')
        if data.startswith('CHUNKINFO'):
            data = data.split('<SEPARATOR>')[1]
            print(f"Received chunk info = {data}")
            chunk_info = json.loads(data)
            response = "ACK<SEPARATOR>TRUE"
        else:
            response = "ACK<SEPARATOR>TRUE"
        sock.sendto(response.encode('utf-8'), address)
    

    # Reassemble chunks after receiving all parts
    for filename, chunk_count in chunk_info.items():
        filename = os.path.basename(filename)
        with open(filename, 'wb') as output_file:
            for chunk_index in range(1, chunk_count + 1):
                chunk_filename = f"{filename}_part{chunk_index}"
                with open(chunk_filename, 'rb') as chunk_file:
                    output_file.write(chunk_file.read())
                os.remove(chunk_filename)  # Remove the temporary chunk file

        print(f"[+] File {filename} reassembled successfully.")



    if command_status != "FALSE":
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





def receive_file(file_id, filename, filesize, file_port, multicast_group, user_id):
    try:
        print(f"[+] Preparing to receive file: {filename} with size: {filesize} bytes on port {file_port}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', file_port))

        mreq = struct.pack("4sl", socket.inet_aton(multicast_group), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        total_bytes_received = 0
        progress_bar = tqdm(total=filesize, unit='B', unit_scale=True, desc=f"Receiving {filename}")

        with open(filename, 'wb') as f:
            while total_bytes_received < filesize:
                data, address = sock.recvfrom(BUFFER_SIZE + 72 + len(user_id))

                received_file_id = data[:36].strip().decode()
                seq_number = struct.unpack('I', data[36:40])[0]
                checksum_received = data[40:72].decode()
                received_user_id = data[72:72 + len(user_id)].strip().decode()
                file_data = data[72 + len(user_id):]

                checksum_calculated = hashlib.md5(file_data).hexdigest()
                if checksum_received == checksum_calculated and received_user_id == user_id and int(received_file_id) == file_id:
                    f.write(file_data)
                    total_bytes_received += len(file_data)
                    progress_bar.update(len(file_data))

                    ack_packet = received_file_id.encode().ljust(36) + struct.pack('I', seq_number) + user_id.encode().ljust(36)
                    sock.sendto(ack_packet, address)

        progress_bar.close()
        print(f"[+] File {filename} received successfully on port {file_port}.")

        final_ack = f"ACK_COMPLETE<SEPARATOR>{user_id}<SEPARATOR>{filename}"
        while True:
            try:
                sock.sendto(final_ack.encode('utf-8'), address)
                final_msg, address = sock.recvfrom(4096)
                
                final_msg = final_msg.decode('utf-8')
                if final_msg.startswith("FILETRANSFERCOMPLETE<SEPARATOR>"):
                    response = final_msg.split('<SEPARATOR>')
                    if int(response[1]) == file_id and response[2] == user_id:
                        break
            except socket.timeout:
                print(f"Retransmitting final ack for file {filename}")

        sock.close()

    except PermissionError as e:
        print(f"PermissionError: {e}")
        print("Ensure that the port is not being blocked by a firewall or used by another process.")

    except Exception as e:
        print("This is the correct error")
        print(f"Error occurred: {e}")



