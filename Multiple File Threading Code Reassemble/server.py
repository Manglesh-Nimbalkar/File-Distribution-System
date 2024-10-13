import socket
import os
import struct
import hashlib
import threading
from tkinter import messagebox
import uuid
import tqdm
import time
from datetime import datetime
from database import fetch_groups, connect_to_database, create_group_table, add_user_to_group, is_user_id_valid, store_in_database 


# Server and networking settings
SERVER_PORT = 5002
BUFFER_SIZE = 1024
TTL = 3  # Time-to-live for multicast packets
ACK_TIMEOUT = 3  # Time to wait for an acknowledgment before retransmitting
WINDOW_SIZE = 5  # Number of packets sent before waiting for ACKs
CLIENT_PORT = 55000

def send_file_to_client(sock, packet, group_ip):
    sock.sendto(packet, (group_ip, SERVER_PORT))


def handle_user_requests():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', CLIENT_PORT))

    while True:
        try:
            data, address = sock.recvfrom(1024)
            request = data.decode('utf-8')
            username = ""
            received_list = []
            received_list = request.split(':')
            action = ""
            group_name = ""
            # action, username, group_name = request.split(':')
            if (len(received_list) == 3) :
                action = received_list[0]
                username = received_list[1]
                group_name = received_list[2]
            else :
                action = received_list[0]
                group_name = received_list[1]

            if action == "JOIN":
                # Simulate approval process (you can add more logic here)
                approve = messagebox.askyesno("Group Join Request", f"Approve user '{username}' to join '{group_name}'?")
                
                if approve:
                    create_group_table(group_name)  # Ensure the group's table exists
                    user_id = str(uuid.uuid4())
                    add_user_to_group(user_id, group_name)
                    response = f"APPROVED:{user_id}"
                    add_active_user(user_id, group_name)
                    # send_previous_files(group_name, user_id)
                else:
                    response = "DENIED"

                sock.sendto(response.encode('utf-8'), address)

            elif action == "VALIDATE":
                user_id = username
                group_name = group_name
                if is_user_id_valid(user_id, group_name):
                    response = "VALID"
                    add_active_user(user_id, group_name)
                    # send_previous_files(group_name, user_id)
                else:
                    response = "INVALID"
                sock.sendto(response.encode('utf-8'), address)

            elif action == "UPDATE" :
                user_id = username
                group_name = group_name
                # response = ""
                file_update = update_required(group_name, user_id)
                if file_update > 0 :
                    response = f"UPDATE NEEDED:{file_update}"
                else :
                    response = "UPDATED"
                    
                sock.sendto(response.encode('utf-8'), address)
                time.sleep(1)
                if file_update > 0 :
                    threading.Thread(target=send_previous_files, args=(group_name, user_id)).start()
                    # send_previous_files(group_name, user_id)

        except Exception as e:
            print(f"Error occurred: {e}")


def add_active_user(user_id, group_name):
    path = f"./{group_name.replace(' ', '_')}_active_users.txt"
    present = False
    
    if os.path.exists(path):
        with open(path, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if user_id == line.strip():
                    present = True
                    break

    if not present:
        with open(path, 'a') as f:
            f.write(user_id + "\n")


def check_if_sent(file_name, user_id) :
    ack_file_path = os.path.join(os.getcwd(), f"{file_name}_acknowledgments.txt")

    if not os.path.exists(ack_file_path):
        with open(ack_file_path, 'w') as ack_file:
            ack_file.write("")


    with open(ack_file_path, 'r') as ack_file:
        acknowledged_users = set(line.strip() for line in ack_file.readlines())

    if user_id in acknowledged_users :
        print(f"Skipping user id = {user_id} for file = {file_name}")
        return True
    else :
        return False
    

def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as temp_sock:
        try:
            temp_sock.bind(('', port))
            return True
        except OSError:
            return False

def get_available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as temp_sock:
        temp_sock.bind(('', 0))  
        port = temp_sock.getsockname()[1] 
    return port


def print_running_threads():
    threads = threading.enumerate()
    print(f"Number of active threads: {len(threads)}")
    for thread in threads:
        print(f"Thread name: {thread.name}")


def send_metadata(selected_group, selected_files, group_ip, user_id, command=[]):
    files_to_send = []
    for file in selected_files:
        if not check_if_sent(file, user_id):
            files_to_send.append(file)

    total_files = len(files_to_send)
    if total_files == 0: return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
    sock.settimeout(ACK_TIMEOUT)

    retry_count = 0
    status = "FALSE"
    command_status = "FALSE" if len(command) == 0 else "TRUE"
    while status == "FALSE":
        control_signal = f"TOTALFILES<SEPARATOR>{user_id}<SEPARATOR>{total_files}<SEPARATOR>{command_status}"
        sock.sendto(control_signal.encode('utf-8'), (group_ip, SERVER_PORT))

        try:
            ack, _ = sock.recvfrom(4096)
            response = ack.decode('utf-8').split('<SEPARATOR>')
            if response[1] == user_id and response[2] == "TRUE":
                print(f"Control signal sent successfully to user_id {user_id}")
                status = "TRUE"
        except socket.timeout:
            if retry_count < 3:
                print(f"Control signal retransmitting for user_id {user_id}")
                retry_count += 1
            else:
                break

    threads = []

    index = 0
    for file in files_to_send:
        filesize = os.path.getsize(file)
        file_port = get_available_port()

        retry_count = 0
        acknowledged_metadata = False

        while not acknowledged_metadata:
            file_info = f"METADATA<SEPARATOR>{index}<SEPARATOR>{user_id}<SEPARATOR>{os.path.basename(file)}<SEPARATOR>{filesize}<SEPARATOR>{file_port}"
            sock.sendto(file_info.encode('utf-8'), (group_ip, SERVER_PORT))

            try:
                ack, _ = sock.recvfrom(4096)
                response = ack.decode('utf-8').split('<SEPARATOR>')
                if len(response) > 2:
                    if int(response[1]) == index and response[2] == user_id:
                        print(f"Metadata received at client id {user_id} side successfully for file {file}")
                        acknowledged_metadata = True
            except socket.timeout:
                if retry_count < 3:
                    print("Metadata Ack timeout occurred, retrying...")
                    retry_count += 1
                else:
                    break

        th = threading.Thread(target=send_file, args=(index, file, filesize, group_ip, user_id, file_port))
        threads.append(th)

        index += 1

        if not os.path.exists(f"{selected_group.replace(' ', '_')}_sent_files.txt"):
            with open(f"{selected_group.replace(' ', '_')}_sent_files.txt", 'w') as ack_file:
                ack_file.write("")

        written = False
        files = open(f"{selected_group.replace(' ', '_')}_sent_files.txt", 'r').readlines()
        files = [f.strip() for f in files]
        for f in files:
            if file == f:
                written = True

        if not written:
            with open(f"{selected_group.replace(' ', '_')}_sent_files.txt", 'a') as ack_file:
                ack_file.write(f"{file}\n")

    time.sleep(1)
    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()
    
    time.sleep(1)

    if len(command) != 0:
        commands = ""
        print("Command Sent from server")
        for i in command :
            commands += f"<SEPARATOR>{i}"
        command_info = f"COMMAND{commands}"
        sock.sendto(command_info.encode('utf-8'), (group_ip, SERVER_PORT))

    
        

        
def send_file(file_id, filename, filesize, group_ip, user_id, server_port):
    num_packets = (filesize + BUFFER_SIZE - 1) // BUFFER_SIZE
    
    # Create the UDP socket with dynamic port allocation
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
    sock.settimeout(ACK_TIMEOUT)
 
    sequence_number = 0
    sent_packets = {}
    progress_bar = tqdm.tqdm(total=num_packets, desc=f"Sending {filename} to {user_id}")
    total_packet_loss = {}

    with open(filename, 'rb') as f:
        while True:
            window_packets = []
            for _ in range(WINDOW_SIZE):
                bytes_read = f.read(BUFFER_SIZE)
                if not bytes_read:
                    break

                checksum = hashlib.md5(bytes_read).hexdigest()
                header = str(file_id).encode().ljust(36) + struct.pack('I', sequence_number) + checksum.encode() + user_id.encode().ljust(36) 
                packet = header + bytes_read
                sent_packets[sequence_number] = packet
                window_packets.append(packet)

                sequence_number += 1

            # Send packets in the current window
            for packet in window_packets:
                sock.sendto(packet, (group_ip, server_port))

            # Wait for ACKs and handle retransmissions
            for packet in window_packets:
                seq_num = struct.unpack('I', packet[36:40])[0]  
                try:
                    ack, _ = sock.recvfrom(1024)
                    ack_file_id = ack[:36].strip().decode()
                    ack_num, ack_user_id = struct.unpack('I', ack[36:40])[0], ack[40:].strip().decode()

                    if ack_num in sent_packets and ack_user_id == user_id and ack_file_id == str(file_id):
                        del sent_packets[ack_num]
                        progress_bar.update(1)
                except socket.timeout:
                    # print(f"[-] No ACK from {user_id} for packet {seq_num}, retransmitting...")
                    total_packet_loss[seq_num] = packet
                    for _ in range(5):
                        sock.sendto(packet, (group_ip, server_port))

            if not bytes_read:
                break
        
    progress_bar.close()

    print(f"[+] File {filename} sent successfully to {user_id}.")

    print(f"Total Packets Lost = {len(total_packet_loss.keys())}")

    ack_file_path = os.path.join(os.getcwd(), f"{filename}_acknowledgments.txt")

    # Listen for final acknowledgment from the client
    try:
        while True:
            ack_data, _ = sock.recvfrom(4096)
            ack_message = ack_data.decode('utf-8')
            if ack_message.startswith("ACK_COMPLETE<SEPARATOR>"):
                print(f"ACK = {ack_message}")
                ack_user_id, ack_filename = ack_message.split('<SEPARATOR>')[1:3]
                if ack_filename == os.path.basename(filename) and ack_user_id == user_id:
                    file = open(ack_file_path, 'r').readlines()
                    file = [f.strip() for f in file]
                    if (ack_user_id not in file):
                        with open(ack_file_path, 'a') as ack_file:
                            ack_file.write(f"{user_id}\n")

                    final_msg = f"FILETRANSFERCOMPLETE<SEPARATOR>{file_id}<SEPARATOR>{user_id}"
                    sock.sendto(final_msg.encode('utf-8'), (group_ip, server_port))
                    
                    print(f"[+] \n\nReceived final acknowledgment from user {user_id} for file {filename}.")
                    break

    except socket.timeout:
        print(f"[-] \n\nTimeout while waiting for final acknowledgment from user {user_id} for {filename}.")

    except Exception as e:
        print(f"[-] Error receiving final acknowledgment: {e}")



def start_sending(selected_files, selected_group, post_transfer_command = None, schedule_time = None):

    print(f"Post transfer commands = {post_transfer_command}")

    if not selected_files:
        messagebox.showwarning("No Files Selected", "Please select at least one file.")
        return

    if selected_group == "Select a group":
        messagebox.showwarning("No Group Selected", "Please select a group.")
        return

    # Check if a valid schedule time is set
    if schedule_time:
        now = datetime.now()
        scheduled_datetime = datetime.combine(now.date(), schedule_time)
        
        if scheduled_datetime < now:
            messagebox.showwarning("Invalid Schedule Time", "The scheduled time is in the past. File transfer will not execute.")
            return 

        delay_seconds = (scheduled_datetime - now).total_seconds()

        if delay_seconds > 0:
            messagebox.showinfo("Scheduled", f"File transfer scheduled to start at {schedule_time}. Waiting...")
            time.sleep(delay_seconds)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Proceed with file sending
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT group_address FROM GroupDetails WHERE group_name = %s", (selected_group,))
        result = cursor.fetchone()
        if result:
            group_ip = result[0]

            # Fetch the user_ids of active users in the group
            cursor.execute(f"SELECT user_id FROM {selected_group.replace(' ', '_')}_users")
            user_ids = [row[0] for row in cursor.fetchall()]

            with open(f"{selected_group.replace(' ', '_')}_active_users.txt", 'r') as f:
                active_users = [line.strip() for line in f.readlines()]

            # Compare and filter only the active users who are also in the user_ids list
            send_list = [user for user in active_users if user in user_ids]

            print(send_list)
            
            threads = []
           
            for user_id in send_list :
                if user_id == send_list[-1] :
                    thread = threading.Thread(target=send_metadata, args=(selected_group, selected_files, group_ip, user_id, post_transfer_command))
                    threads.append(thread)
                else :
                    thread = threading.Thread(target=send_metadata, args=(selected_group, selected_files, group_ip, user_id))
                    threads.append(thread)
            
            store_in_database(selected_files, selected_group, timestamp)

            for thread in threads:
                thread.start()
            
                
            for thread in threads :
                thread.join()

            
        else:
            messagebox.showerror("Error", "Selected group not found in the database.")
        connection.close()



def update_required(group_name, user_id) :
    if not os.path.exists(f"{group_name.replace(' ', '_')}_sent_files.txt"):
        return False
    
    # groups = fetch_groups()
    with open(f"{group_name.replace(' ', '_')}_sent_files.txt", 'r') as f :
        sent_files = f.readlines()
        sent_files = [file.replace("\n","") for file in sent_files]
        # print(sent_files)
        send_file = 0
        for file in sent_files :
            if not os.path.exists(f"{file}_acknowledgments.txt"):
                send_file += 1
                continue        

            present = False
            with open(f"{file}_acknowledgments.txt", 'r') as id:
                
                ids = id.readlines()
                ids = [i.strip() for i in ids]
                
                for i in ids :
                    if user_id == i :
                        present = True
            
            if not present : send_file += 1

        print(f"Total files = {send_file}")
        if send_file != 0 : return send_file
        else : return send_file


def send_previous_files(group_name, user_id) :

    print("Previous files are being sent")
    previous_files = []
    groups = fetch_groups()
    with open(f"{group_name.replace(' ', '_')}_sent_files.txt", 'r') as f :
        sent_files = f.readlines()
        # print(sent_files)
        sent_files = [file.replace("\n","") for file in sent_files]
        for file in sent_files :

            if not os.path.exists(f"{file}_acknowledgments.txt"):
                previous_files.append(file)
                continue

            present = False
            with open(f"{file}_acknowledgments.txt", 'r') as id:
                
                ids = id.readlines()
                ids = [i.strip() for i in ids]
                for i in ids :
                    if user_id == i :
                        present = True
                    
            if not present : previous_files.append(file)

    groups = fetch_groups()

    print(f"Previous files remaining to send = {previous_files}")
    if len(previous_files) > 0 : 
        send_metadata(group_name, previous_files, groups[group_name], user_id)
        time.sleep(2)
