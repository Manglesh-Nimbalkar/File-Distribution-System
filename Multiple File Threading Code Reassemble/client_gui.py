import socket
import tkinter as tk
from tkinter import messagebox, font
# import threading
from database import fetch_groups
from client import receive_metadata, get_saved_user_id, validate_user_id, send_join_request

SERVER_PORT = 5002
BUFFER_SIZE = 1024
SERVER_IP = '127.0.0.1'
CLIENT_PORT = 55000

def create_gui():
    root = tk.Tk()
    root.title("File Receiver")
    root.geometry("300x300")  # Increased height to accommodate the new button and username entry
    root.config(bg="#783CB4")

    custom_font = font.Font(family="Helvetica", size=12, weight='bold')

    # Create a frame for the group selection
    group_frame = tk.Frame(root, padx=10, pady=10, bg="#783CB4")
    group_frame.pack(pady=0)

    tk.Label(group_frame, text="Select Group:", font=custom_font, fg="white", bg="#783CB4").pack()

    # Fetch groups from the database
    groups = fetch_groups()
    if not groups:
        messagebox.showerror("Error", "Unable to fetch group details from the database.")
        root.destroy()
        return

    # Define the list of groups for the dropdown menu
    group_options = list(groups.keys())
    group_options.append("Select a group")  # Placeholder for default value

    selected_group_var = tk.StringVar(value="Select a group")  # Set default value

    # Create the OptionMenu widget
    group_menu = tk.OptionMenu(group_frame, selected_group_var, *group_options)
    group_menu.config(font=custom_font, width=20)
    group_menu.pack(pady=5)

    # Create a frame for the username input
    username_frame = tk.Frame(root, padx=10, pady=10)
    username_frame.pack(pady=10)

    # Create a button to join the group
    join_group_btn = tk.Button(root, text="Join Group", font=custom_font, command=lambda: join_group(selected_group_var.get(), groups))
    join_group_btn.pack(pady=10)

    # Check for any updates
    get_updates_btn = tk.Button(root, text="Get Updates", font=custom_font, command=lambda: get_updates(selected_group_var.get()))
    get_updates_btn.pack(pady=10)

    # Create a button to start receiving files
    receive_btn = tk.Button(root, text="Receive File", font=custom_font, command=lambda: start_receiving(selected_group_var.get(), groups))
    receive_btn.pack(pady=10)

    root.mainloop()



def get_updates(selected_group) :
    if not selected_group or selected_group == "Select a group":
        messagebox.showwarning("No Group Selected", "Please select a group.")
        return
    
    group_add = fetch_groups()[selected_group]
    user_id = get_saved_user_id(selected_group)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    validation_request = f"UPDATE:{user_id}:{selected_group}"
    sock.sendto(validation_request.encode('utf-8'), (SERVER_IP, CLIENT_PORT))

    response, _ = sock.recvfrom(1024)
    response = response.decode('utf-8')
    if response.startswith("UPDATE NEEDED") :
        messagebox.showinfo("Update Details", "Updates are Required. Updating ...")
        receive_metadata(group_add, user_id)


        messagebox.showinfo("Update Details", "Updates Done Successfully")
    elif response == "UPDATED" :
        messagebox.showinfo("Update Details", "No Required Updates")


def join_group(selected_group, username):
    if not selected_group or selected_group == "Select a group":
        messagebox.showwarning("No Group Selected", "Please select a group.")
        return

    group_name = selected_group
    if not username:
        messagebox.showwarning("No Username", "Please enter a username.")
        return

    user_id = get_saved_user_id(group_name)

    if user_id:
        # Validate the existing user ID
        if validate_user_id(user_id, group_name):
            messagebox.showinfo("Validation Successful", f"User ID is valid for group {group_name}.")
        else:
            messagebox.showerror("Validation Failed", "User ID is invalid. Requesting a new one.")
            request_new_user_id(group_name)
    else:
        # No user ID saved, request to join the group
        request_new_user_id(group_name)

def request_new_user_id(group_name):
    user_id = send_join_request(group_name)
    if user_id:
        messagebox.showinfo("Join Successful", f"Joined group {group_name} with User ID: {user_id}.")
    else:
        messagebox.showerror("Join Failed", f"Failed to join group {group_name}.")

def start_receiving(selected_group, groups):
    if not selected_group or selected_group == "Select a group":
        messagebox.showwarning("No Group Selected", "Please select a group.")
        return

    user_id = get_saved_user_id(selected_group)
    if not user_id or not validate_user_id(user_id, selected_group):
        messagebox.showerror("Not Joined", f"You must join the group {selected_group} before receiving files.")
        return

    group_ip = groups[selected_group]
    
    # while True:
    receive_metadata(group_ip, user_id)



if __name__ == "__main__":
    create_gui()
