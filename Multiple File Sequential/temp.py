import mysql.connector
import hashlib


# Connect to MySQL database
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


# Function to hash the password using SHA-256
def hash_password(password):
    sha256_hash = hashlib.sha256(password.encode()).hexdigest()
    return sha256_hash


# Function to insert hashed password into the database
def insert_admin_credentials(username, password):
    connection = connect_to_database()
    if connection:
        try:
            cursor = connection.cursor()
            hashed_password = hash_password(password)
            query = "INSERT INTO admin_credentials (username, hashed_password) VALUES (%s, %s)"
            cursor.execute(query, (username, hashed_password))
            connection.commit()
            print("Admin credentials inserted successfully.")
        except mysql.connector.Error as err:
            print(f"Error: {err}")
        finally:
            connection.close()


if __name__ == "__main__":
    # Input username and password
    username = input("Enter admin username: ")
    password = input("Enter admin password: ")

    # Insert the hashed password into the database
    insert_admin_credentials(username, password)
