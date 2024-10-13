import socket
import os
import struct
import hashlib
import threading
from tkinter import messagebox
import uuid
import tqdm
import time
from threading import Lock
from datetime import datetime
from database import fetch_groups, connect_to_database, create_group_table, add_user_to_group, is_user_id_valid, store_in_database

# Server and networking settings
SERVER_PORT = 5002
BUFFER_SIZE = 1024
TTL = 2  # Time-to-live for multicast packets
ACK_TIMEOUT = 3  # Time to wait for an acknowledgment before retransmitting
WINDOW_SIZE = 5  # Number of packets sent before waiting for ACKs
CLIENT_PORT = 5500

port_lock = Lock()

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
                    send_previous_files(group_name, user_id)

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

pause_event = threading.Event()
abort_event = threading.Event()
pause_event.set() 


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
    


def get_available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as temp_sock:
        temp_sock.bind(('', 0))  
        port = temp_sock.getsockname()[1] 
    return port


def send_metadata(selected_files, group_ip, user_id, command=[]):
    files_to_send = []
    for file in selected_files:
        if not check_if_sent(file, user_id):
            files_to_send.append(file)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
    sock.settimeout(ACK_TIMEOUT)

    total_files = len(files_to_send)
    port = 0
    port_ack = "FALSE"
    with port_lock:
        while port_ack == "FALSE" :
            port = get_available_port()
            port_command = f"PORT<SEPARATOR>{user_id}<SEPARATOR>{port}<SEPARATOR>{total_files}"
            print(f"Port signal sent successfully")
            sock.sendto(port_command.encode('utf-8'), (group_ip, SERVER_PORT))

            try :
                ack, _ = sock.recvfrom(4096)
                ack = ack.decode('utf-8')

                if ack.startswith('PORT'):
                    response = ack.split('<SEPARATOR>')
                    if response[1] == user_id and response[2] == "TRUE":
                        print(f"Port signal received at client side successfully")
                        port_ack = "TRUE"
                        break
            
            except socket.timeout:
                print("Port sending timeout, retrying...")

    print(f"Commands = {command}")
    for file in files_to_send:
        if file == files_to_send[-1]:
            send_file(file, group_ip, user_id, port, command)
        else :
            send_file(file, group_ip, user_id, port)
    


def send_file(filename, group_ip, user_id, port, post_transfer_command=[]):
    print(f"Inside send file function")
    filesize = os.path.getsize(filename)
    num_packets = (filesize + BUFFER_SIZE - 1) // BUFFER_SIZE
    ack_file_path = os.path.join(os.getcwd(), f"{filename}_acknowledgments.txt")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
    sock.settimeout(ACK_TIMEOUT)


    command = bool(post_transfer_command)
    acknowledged_metadata = False
    retry_count = 0

    while not acknowledged_metadata:
        file_info = f"{os.path.basename(filename)}<SEPARATOR>{filesize}<SEPARATOR>{command}"
        sock.sendto(file_info.encode('utf-8'), (group_ip, port))

        try:
            ack, _ = sock.recvfrom(4096)
            if ack.decode('utf-8').split('<SEPARATOR>')[1] == "True":
                acknowledged_metadata = True
        except socket.timeout:
            retry_count += 1
            if retry_count >= 5:
                print("Failed to send metadata after 5 retries.")
                return

    
    sequence_number = 0
    sent_packets = {}  # Buffer to hold sent but unacknowledged packets
    acknowledged_packets = set()
    progress_bar = tqdm.tqdm(total=num_packets, desc=f"Sending {filename} to {user_id}")

    with open(filename, 'rb') as f:
        while True:
            pause_event.wait()
            if abort_event.is_set():
                print(f"[-] File transfer aborted for {user_id}.")
                progress_bar.close()
                return

            window_packets = []
            for _ in range(WINDOW_SIZE):
                bytes_read = f.read(BUFFER_SIZE)
                if not bytes_read:
                    break

                checksum = hashlib.md5(bytes_read).hexdigest()
                header = struct.pack('I', sequence_number) + checksum.encode() + user_id.encode().ljust(36)
                packet = header + bytes_read
                sent_packets[sequence_number] = packet
                window_packets.append(packet)
                sequence_number += 1

            # Send all packets in the current window
            for packet in window_packets:
                sock.sendto(packet, (group_ip, port))

            # Check buffer and resend unacknowledged packets
            for seq_num, packet in list(sent_packets.items()):
                try:
                    ack, _ = sock.recvfrom(1024)
                    ack_num, ack_user_id = struct.unpack('I', ack[:4])[0], ack[4:].strip().decode()

                    if ack_num == seq_num and ack_user_id == user_id:
                        acknowledged_packets.add(seq_num)
                        del sent_packets[seq_num]  # Remove from buffer
                        progress_bar.update(1)

                except socket.timeout:
                    # Resend unacknowledged packets
                    for seq_num, packet in sent_packets.items():
                        if seq_num not in acknowledged_packets:
                            sock.sendto(packet, (group_ip, port))

            # Break the loop if the file has been completely sent
            if not bytes_read:
                break

    # Final check to ensure all packets are acknowledged
    while sent_packets:
        for seq_num, packet in list(sent_packets.items()):
            try:
                ack, _ = sock.recvfrom(1024)
                ack_num, ack_user_id = struct.unpack('I', ack[:4])[0], ack[4:].strip().decode()

                if ack_num == seq_num and ack_user_id == user_id:
                    acknowledged_packets.add(seq_num)
                    del sent_packets[seq_num]  # Remove from buffer
                    progress_bar.update(1)

            except socket.timeout:
                # Resend unacknowledged packets
                for seq_num, packet in sent_packets.items():
                    if seq_num not in acknowledged_packets:
                        sock.sendto(packet, (group_ip, port))

    progress_bar.close()
    print(f"[+] File {filename} sent successfully to {user_id}.")

    try:
        while True:
            ack_data, _ = sock.recvfrom(4096)
            ack_message = ack_data.decode('utf-8')
            if ack_message.startswith("ACK_COMPLETE<SEPARATOR>"):
                ack_user_id, ack_filename = ack_message.split('<SEPARATOR>')[1:3]
                if ack_filename == os.path.basename(filename) and ack_user_id == user_id:
                    with open(ack_file_path, 'a') as ack_file:
                        ack_file.write(f"{user_id}\n")
                    print(f"[+] Received final acknowledgment from user {user_id} for file {filename}.")
                    break
    except socket.timeout:
        print(f"[-] Timeout while waiting for final acknowledgment from user {user_id} for {filename}.")
    except Exception as e:
        print(f"[-] Error receiving final acknowledgment: {e}")


    if post_transfer_command:
        commands = "<SEPARATOR>".join(post_transfer_command)
        command_info = f"COMMAND<SEPARATOR>{commands}"
        sock.sendto(command_info.encode('utf-8'), (group_ip, port))



# Function that initiates the sending process
def start_sending(selected_files, selected_group, post_transfer_command, schedule_time):
    if not selected_files:
        messagebox.showwarning("No Files Selected", "Please select at least one file.")
        return

    if selected_group == "Select a group":
        messagebox.showwarning("No Group Selected", "Please select a group.")
        return

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
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT group_address FROM GroupDetails WHERE group_name = %s", (selected_group,))
        result = cursor.fetchone()
        if result:
            group_ip = result[0]
            cursor.execute(f"SELECT user_id FROM {selected_group.replace(' ', '_')}_users")
            user_ids = [row[0] for row in cursor.fetchall()]

            with open(f"{selected_group.replace(' ', '_')}_active_users.txt", 'r') as f:
                active_users = [line.strip() for line in f.readlines()]

            send_list = [user for user in active_users if user in user_ids]

            for file in selected_files:
                written = False

                if not os.path.exists(f"{selected_group.replace(' ', '_')}_sent_files.txt"):
                    with open(f"{selected_group.replace(' ', '_')}_sent_files.txt", 'w') as f:
                        pass

                files = open(f"{selected_group.replace(' ', '_')}_sent_files.txt", 'r').readlines()
                files = [f.strip() for f in files]
                for f in files:
                    if file == f:
                        written = True
                        break

                if not written :
                    with open(f"{selected_group.replace(' ', '_')}_sent_files.txt", 'a') as ack_file:
                        ack_file.write(f"{file}\n")
                

            threads = []

            for user_id in send_list:
                th = threading.Thread(target=send_metadata, args=(selected_files, group_ip, user_id, post_transfer_command))
                th.start()
                threads.append(th)

            for thread in threads:
                thread.join()
                

            # store_in_database(selected_files, selected_group, timestamp)

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

    print(f"Previous files remaining to send = {previous_files}")
    if len(previous_files) > 0 : 
        # for f in previous_files :
            # print(f"Sending file {f}")
            send_metadata(previous_files, groups[group_name], user_id)
            time.sleep(1)