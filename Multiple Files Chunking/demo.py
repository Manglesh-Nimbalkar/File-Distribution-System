import os

chunk_info = {'E:/TY/BIDA/Lab/Assignment 2/demo.mp4' : 10}

for filename, chunk_count in chunk_info.items():
    filename = os.path.basename(filename)
    with open(filename, 'wb') as output_file:
        for chunk_index in range(1, chunk_count + 1):
            chunk_filename = f"{filename}_part{chunk_index}"
            with open(chunk_filename, 'rb') as chunk_file:
                output_file.write(chunk_file.read())
            os.remove(chunk_filename)  