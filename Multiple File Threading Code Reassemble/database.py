import mysql.connector

# Database connection
def connect_to_database():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",  # Replace with your MySQL username
            password="manglesh2004",  # Replace with your MySQL password
            database="FileSharingDB"  # Replace with your MySQL database name
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None
    

# Function to create a table for a new group
def create_group_table(group_name):
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        try:
            table_name = f"{group_name.replace(' ', '_')}_users"
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} (user_id VARCHAR(255) PRIMARY KEY)")
            connection.commit()
            print(f"Table '{table_name}' created or already exists.")
        except mysql.connector.Error as err:
            print(f"Failed to create table '{table_name}': {err}")
        finally:
            connection.close()


# Fetch groups from the database
def fetch_groups():
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT group_name, group_address FROM GroupDetails")
        groups = cursor.fetchall()
        connection.close()
        return {group[0]: group[1] for group in groups}
    return {}


# Function to add a user to the group table
def add_user_to_group(user_id, group_name):
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        insert_query = f"INSERT INTO {group_name.replace(' ', '_')}_users (user_id) VALUES (%s)"
        cursor.execute(insert_query, (user_id,))
        connection.commit()
        connection.close()


# Function to check if a user_id is valid for a group
def is_user_id_valid(user_id, group_name):
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        check_query = f"SELECT COUNT(*) FROM {group_name.replace(' ', '_')}_users WHERE user_id = %s"
        cursor.execute(check_query, (user_id,))
        result = cursor.fetchone()[0]
        connection.close()
        return result > 0
    return False


def store_in_database(file_names, group_name, timestamp):
    # Connect to the database
    connection = connect_to_database()
    if connection:
        try:
            cursor = connection.cursor()

            # Insert each file into the 'sharedHistory' table
            for file_name in file_names:
                insert_query = """
                    INSERT INTO sharedHistory (file_name, group_name, timestamp)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(insert_query, (file_name, group_name, timestamp))

            # Commit the transaction
            connection.commit()

            print(f"Successfully inserted {len(file_names)} record(s) into the sharedHistory table.")

        except mysql.connector.Error as err:
            print(f"Database error: {err}")
            connection.rollback()

        finally:
            cursor.close()
            connection.close()

    else:
        print("Failed to connect to the database.")

