import os
import tkinter as tk
import threading
import mysql
import re
from tkinter import filedialog, messagebox, simpledialog, font
from datetime import datetime
from tkinter import ttk
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from database import connect_to_database, create_group_table, fetch_groups
from server import start_sending, handle_user_requests


# Function to open the file dialog and select files
def open_file_dialog():
    files = filedialog.askopenfilenames(title="Select Files")
    return files

# Function to create a new group
def create_new_group():
    group_name = simpledialog.askstring("Input", "Enter group name:")
    group_address = simpledialog.askstring("Input", "Enter group address (e.g., 224.1.1.6):")
    if group_name and group_address:
        connection = connect_to_database()
        if connection:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO GroupDetails (group_name, group_address) VALUES (%s, %s)",
                           (group_name, group_address))
            connection.commit()
            connection.close()
            update_group_menu()  # Refresh the dropdown menu
            create_group_table(group_name)
            messagebox.showinfo("Success", "Group created successfully!")
    else:
        messagebox.showwarning("Input Error", "Please enter both group name and address.")

# Function to update the group dropdown menu
def update_group_menu():
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT group_name FROM GroupDetails")
        groups = cursor.fetchall()
        group_menu['menu'].delete(0, 'end')
        for group in groups:
            group_menu['menu'].add_command(label=group[0], command=tk._setit(selected_group_var, group[0]))
        connection.close()

def get_group_tables(connection):
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES LIKE 'group_%_users'")
        tables = cursor.fetchall()
        return [table[0] for table in tables]  # Extract table names
    except mysql.connector.Error as err:
        messagebox.showerror("Database Error", f"Error: {err}")
        return []


def get_group_details(connection):
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT id, group_name, group_address FROM groupdetails")
        group_details = cursor.fetchall()
        return group_details
    except mysql.connector.Error as err:
        messagebox.showerror("Database Error", f"Error: {err}")
        return []

def get_user_counts(connection, tables):
    user_counts = {}
    try:
        cursor = connection.cursor()
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            user_counts[table] = count
        return user_counts
    except mysql.connector.Error as err:
        messagebox.showerror("Database Error", f"Error: {err}")
        return {}


def view_group_details():
    connection = connect_to_database()
    if connection is None:
        messagebox.showerror("Connection Error", "Failed to connect to the database.")
        return

    # Get group tables and user counts for the graph
    tables = get_group_tables(connection)
    if not tables:
        messagebox.showerror("Query Error", "No tables found in the format 'group_n_users'.")
        return

    user_counts = get_user_counts(connection, tables)
    if not user_counts:
        messagebox.showerror("Query Error", "Failed to retrieve user counts.")
        return

    # Get group details for the table
    group_details = get_group_details(connection)
    if not group_details:
        messagebox.showerror("Query Error", "Failed to retrieve group details.")
        return

    # Plot the graph and show the group details table
    plot_graph_and_show_table(user_counts, group_details)


def plot_graph(user_counts):
    # Create a tkinter window
    window = tk.Tk()
    window.title("User Frequency Graph")

    # Data for plotting
    groups = list(user_counts.keys())
    counts = list(user_counts.values())

    # Create a figure and plot
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(groups, counts, color='skyblue')
    ax.set_title('Number of Users in Each Group')
    ax.set_xlabel('Groups')
    ax.set_ylabel('Number of Users')
    plt.xticks(rotation=45, ha='right')

    # Embed the plot into tkinter window
    canvas = FigureCanvasTkAgg(fig, master=window)
    canvas.draw()
    canvas.get_tk_widget().pack()

    # Start the tkinter loop
    window.mainloop()


def fetch_shared_history():
    conn = connect_to_database()
    if conn is None:
        return []

    cursor = conn.cursor()
    cursor.execute("SELECT id, file_name, group_name, timestamp FROM sharedHistory")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return data


def clear_active_users():
    groups = fetch_groups()

    for group in groups :
        path = f"./{group.replace(' ', '_')}_active_users.txt"
        if os.path.exists(path):
            with open(path, 'w') as f:
                pass


def plot_graph_and_show_table(user_counts, group_details):
    window = tk.Toplevel()
    window.title("User Frequency Graph and Group Details")

    window.state('zoomed')

    # Root frame to contain everything
    root_frame = tk.Frame(window, padx=10, pady=10, bg="#f0f0f0")
    root_frame.pack(fill="both", expand=True)

    # Left Frame - Shared History
    history_frame = tk.Frame(root_frame, bg="#ffffff", relief="sunken", borderwidth=2)
    history_frame.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')

    history_label = tk.Label(history_frame, text="Shared History", font=("Arial", 16, "bold"), bg="#ffffff")
    history_label.pack(pady=10)

    history_columns = ('ID', 'File Name', 'Group Name', 'Timestamp')
    history_table = ttk.Treeview(history_frame, columns=history_columns, show='headings', height=8)

    # Defining column headings and widths
    history_table.heading('ID', text='ID')
    history_table.column('ID', width=50, anchor='center')

    history_table.heading('File Name', text='File Name')
    history_table.column('File Name', width=200, anchor='center')

    history_table.heading('Group Name', text='Group Name')
    history_table.column('Group Name', width=100, anchor='center')

    history_table.heading('Timestamp', text='Timestamp')
    history_table.column('Timestamp', width=150, anchor='center')

    # Inserting data into the table
    shared_history_data = fetch_shared_history()
    for row in reversed(shared_history_data):
        history_table.insert('', 'end', values=row)

    history_table.pack(fill='both', expand=True)

    # Right Frame - Graph and Table
    right_frame = tk.Frame(root_frame, bg="#ffffff", relief="sunken", borderwidth=2)
    right_frame.grid(row=0, column=1, padx=10, pady=10, sticky='nsew')

    # Graph Section
    graph_frame = tk.Frame(right_frame, bg="#ffffff")
    graph_frame.pack(padx=10, pady=10, fill='x')

    # Rename groups from 'group_n_users' to 'Group n'
    groups = []
    counts = []
    for group_name in user_counts.keys():
        match = re.search(r'(\d+)', group_name)
        if match:
            numeric_part = match.group(1)
            formatted_group_name = f"Group {numeric_part}"
            groups.append(formatted_group_name)
            counts.append(user_counts[group_name])

    # Plotting the graph
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(groups, counts, color='blue')
    ax.set_title('Number of Users in Each Group', fontsize=14)
    # ax.set_xlabel('Groups', fontsize=12)
    ax.set_ylabel('Number of Users', fontsize=12)
    # plt.xticks(rotation=45, ha='right')

    canvas = FigureCanvasTkAgg(fig, master=graph_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill='x')

    # Table Section
    table_frame = tk.Frame(right_frame, bg="#ffffff")
    table_frame.pack(padx=10, pady=10, fill='both', expand=True)

    table_label = tk.Label(table_frame, text="Group Details", font=("Arial", 16, "bold"), bg="#ffffff")
    table_label.pack(pady=10)

    columns = ('ID', 'Group Name', 'Group Address')
    table = ttk.Treeview(table_frame, columns=columns, show='headings', height=8)

    # Defining column headings and widths
    table.heading('ID', text='ID')
    table.column('ID', width=50, anchor='center')

    table.heading('Group Name', text='Group Name')
    table.column('Group Name', width=150, anchor='center')

    table.heading('Group Address', text='Group Address')
    table.column('Group Address', width=200, anchor='center')

    # Inserting data into the table
    for row in group_details:
        table.insert('', 'end', values=row)

    table.pack(fill='both', expand=True)

    # Configure row/column weights for resizing
    root_frame.grid_rowconfigure(0, weight=1)
    root_frame.grid_columnconfigure(0, weight=1)
    root_frame.grid_columnconfigure(1, weight=2)


# Function to create the GUI
def create_gui():
    global group_menu  # Declare as global to use in update_group_menu()
    global selected_group_var  # Declare as global to use in update_group_menu()

    root = tk.Tk()
    root.title("File Sharing System")
    root.geometry("500x700+300+25")  # Increased window size to accommodate new options
    root.config(bg="#783CB4")
    root.attributes('-alpha', 1)

    custom_font = font.Font(family="Helvetica", size=12, weight='bold')

    # Style options
    button_bg = "green"
    button_fg = "white"
    frame_bg = "#783CB4"
    label_fg = "#783CB4"
    entry_bg = "black"

    # File selection frame
    file_frame = tk.Frame(root, padx=10, pady=10, bg="#783CB4")
    file_frame.pack(pady=0)

    tk.Label(file_frame, text="Selected Files:", font=custom_font, fg="white", bg="#783CB4").pack()

    selected_files = []

    def select_files():
        files = filedialog.askopenfilenames()
        if files:
            for file in files:
                if file not in selected_files:
                    selected_files.append(file)
            selected_files_label.config(text="\n".join(selected_files))

    def clear_selection():
        selected_files.clear()
        selected_files_label.config(text="")


    # Label to display selected files
    selected_files_label = tk.Label(file_frame, text="", font=custom_font, justify=tk.CENTER, fg="white" , bg="#783CB4")
    selected_files_label.pack()

    # Button frame for the browse and clear buttons
    button_frame = tk.Frame(root, padx=10, pady=10, bg="#783CB4")
    button_frame.pack(pady=0)

    # Button to browse and select files
    select_files_btn = tk.Button(button_frame, text="Browse Files", font=custom_font,justify=tk.CENTER, command=select_files)
    select_files_btn.pack(side=tk.LEFT, padx=5)

    # Button to clear the selection
    clear_btn = tk.Button(button_frame, text="Clear Selection", font=custom_font,justify=tk.CENTER, command=clear_selection)
    clear_btn.pack(side=tk.LEFT, padx=5)

    # Group management frame
    group_frame = tk.Frame(root, padx=10, pady=10, bg="#783CB4")
    group_frame.pack(pady=0)

    tk.Label(group_frame, text="Select Group:", font=custom_font, fg="white", bg="#783CB4").pack(anchor="center")

    selected_group_var = tk.StringVar(value="Select a group")

    group_menu = tk.OptionMenu(group_frame, selected_group_var, "Loading...")  # Placeholder
    group_menu.config(font=custom_font, width=20)
    group_menu.pack(pady=15)

    create_group_btn = tk.Button(group_frame, text="Create New Group", font=custom_font,bg=button_bg, fg=button_fg, command=create_new_group)
    create_group_btn.pack(pady=0, side=tk.LEFT, padx=5)

    update_group_menu()  # Initial call to populate the dropdown

    # Time scheduling frame
    schedule_frame = tk.Frame(root, padx=10, pady=10, bg=frame_bg)
    schedule_frame.pack(pady=10, fill="x")

    tk.Label(schedule_frame, text="Set Transfer Start Time (HH:MM:SS):", font=custom_font, fg="white", bg="#783CB4").pack()

    send_time_set = False  # Local variable to track if the time has been set

    time_frame = tk.Frame(schedule_frame, bg=frame_bg)
    time_frame.pack()

    current_time = datetime.now()
    formatted_time = current_time.strftime("%H:%M:%S")

    hour_var = tk.StringVar(value=formatted_time.split(":")[0])
    min_var = tk.StringVar(value=formatted_time.split(":")[1])
    sec_var = tk.StringVar(value=formatted_time.split(":")[2])

    hour_entry = tk.Entry(time_frame, textvariable=hour_var, width=3, font=custom_font, bg="white")
    hour_entry.pack(side=tk.LEFT)
    tk.Label(time_frame, text=":", font=custom_font, fg=label_fg, bg=frame_bg).pack(side=tk.LEFT)
    min_entry = tk.Entry(time_frame, textvariable=min_var, width=3, font=custom_font, bg="white")
    min_entry.pack(side=tk.LEFT)
    tk.Label(time_frame, text=":", font=custom_font, fg=label_fg, bg=frame_bg).pack(side=tk.LEFT)
    sec_entry = tk.Entry(time_frame, textvariable=sec_var, width=3, font=custom_font, bg="white")
    sec_entry.pack(side=tk.LEFT)

    def set_time():
        nonlocal send_time_set
        send_time_set = True
        messagebox.showinfo("Time Set", "Send time has been set.")
        return send_time_set
    
    def clear_time():
        nonlocal send_time_set
        send_time_set = False

    set_send_time = tk.Button(time_frame, text="Set Send Time", font=custom_font,bg=button_bg, fg=button_fg, command=set_time)
    set_send_time.pack(side=tk.LEFT, pady=5, padx=5)

    set_send_time = tk.Button(time_frame, text="Reset Time", font=custom_font,bg=button_bg, fg=button_fg, command=clear_time)
    set_send_time.pack(side=tk.LEFT, pady=5, padx=5)

    def get_schedule_time():
        try:
            if send_time_set:
                set_time = datetime.strptime(f"{hour_var.get()}:{min_var.get()}:{sec_var.get()}", "%H:%M:%S").time()
                current_time = datetime.now().time()
                
                if set_time <= current_time:
                    messagebox.showerror("Invalid Time", "The set time must be in the future.")
                    return None
                return set_time
            else:
                return None
        except ValueError:
            messagebox.showerror("Invalid Time", "Please enter a valid time.")
            return None

    # Post-transfer command frame
    command_frame = tk.Frame(root, padx=10, pady=10, bg=frame_bg)
    command_frame.pack(pady=10, fill="x")

    tk.Label(command_frame, text="Post-Transfer Commands (one per line):", font=custom_font, padx=10, fg="white", bg="#783CB4").pack()

    # Use a Text widget to allow multiple lines of input
    command_text = tk.Text(command_frame, font=custom_font, width=40, height=3)
    command_text.pack(pady=5)

    def get_commands():
        commands = command_text.get("1.0", tk.END).strip().splitlines()
        print(commands)  
        return commands

    def send_and_clear():
        threading.Thread(target=start_sending, args=(selected_files, selected_group_var.get(), get_commands(), get_schedule_time())).start()
        clear_time()

    # Button to start sending files
    send_btn = tk.Button(root, text="Send Files", font=custom_font,bg="#E74C3C", fg=button_fg,
                         command=send_and_clear)
    send_btn.pack(pady=10)

    # View Details button
    view_details_btn = tk.Button(group_frame, text="View Details", font=custom_font, bg=button_bg, fg=button_fg,
                                 command=view_group_details)
    view_details_btn.pack(pady=15, side=tk.LEFT, padx=5)

    root.mainloop()



if __name__ == "__main__":
    clear_active_users()
    threading.Thread(target=handle_user_requests).start()  
    create_gui()