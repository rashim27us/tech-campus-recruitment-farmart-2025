import os
import sys
import time
import re
import mmap
import multiprocessing
from datetime import datetime
from functools import partial


def extract_from_chunk(chunk_data, target_date, chunk_index):
    
    date_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})T')
    
    matching_logs = []
    count = 0

    lines = chunk_data.split('\n')

    start_idx = 1 if chunk_index > 0 else 0
    
    for line in lines[start_idx:]:
        if not line:
            continue
            
        match = date_pattern.match(line)
        if match and match.group(1) == target_date:
            matching_logs.append(line)
            count += 1
    
    return matching_logs, count


def extract_logs_parallel(file_path, target_date, output_path, num_processes=None):
    start_time = time.time()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    file_size = os.path.getsize(file_path)
    print(f"Log file size: {file_size / (1024**3):.2f} GB")

    if num_processes is None:
        num_processes = multiprocessing.cpu_count()
    
    print(f"Using {num_processes} parallel processes")
    chunk_size = min(100 * 1024 * 1024, file_size // num_processes)
    num_chunks = file_size // chunk_size + (1 if file_size % chunk_size else 0)
    
    print(f"Dividing file into {num_chunks} chunks of ~{chunk_size/(1024*1024):.2f} MB each")
    
    total_count = 0
    matching_logs = []
    
    try:
        with open(file_path, 'r') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            
            # Process chunks in parallel
            with multiprocessing.Pool(processes=num_processes) as pool:
                process_chunk = partial(extract_from_chunk, target_date=target_date)
                chunk_boundaries = []
                for i in range(1, num_chunks):
                    pos = i * chunk_size
                    mm.seek(pos)
                    while pos < file_size:
                        if mm[pos:pos+1] == b'\n':
                            break
                        pos += 1
                    chunk_boundaries.append(pos + 1)

                chunk_boundaries = [0] + chunk_boundaries + [file_size]
                chunks = []
                for i in range(len(chunk_boundaries) - 1):
                    start = chunk_boundaries[i]
                    end = chunk_boundaries[i+1]
                    
                    mm.seek(start)
                    chunk_data = mm.read(end - start).decode('utf-8', errors='replace')
                    chunks.append((chunk_data, target_date, i))  # Pass target_date here
                print(f"Starting parallel processing with {len(chunks)} chunks")
                results = pool.starmap(extract_from_chunk, chunks)  # Directly call extract_from_chunk

                for logs, count in results:
                    matching_logs.extend(logs)
                    total_count += count
                
                print(f"Parallel processing complete, found {total_count} matching log entries")
            
            mm.close()
    
    except ValueError as e:
        print(f"Memory mapping failed: {e}")
        print("Falling back to line-by-line processing")
        return extract_logs_streaming(file_path, target_date, output_path)

    with open(output_path, 'w') as output_file:
        for log in matching_logs:
            output_file.write(log + '\n')
    
    elapsed_time = time.time() - start_time
    print(f"Extraction completed in {elapsed_time:.2f} seconds")
    print(f"Found {total_count} log entries for date {target_date}")
    
    return total_count


def extract_logs_streaming(file_path, target_date, output_path, buffer_size=8*1024*1024):
    start_time = time.time()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    file_size = os.path.getsize(file_path)
    
    date_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})T')
    
    count = 0
    processed_bytes = 0
    last_progress = 0
    
    with open(file_path, 'r') as log_file, open(output_path, 'w') as output_file:
        leftover = ""
        
        while True:
            data = log_file.read(buffer_size)
            if not data:
                break
                
            processed_bytes += len(data)
        
            progress = int((processed_bytes / file_size) * 100)
            if progress >= last_progress + 5:
                print(f"Progress: {progress}% ({processed_bytes / (1024**3):.2f} GB)")
                last_progress = progress
            data = leftover + data
            lines = data.split('\n')
            leftover = lines.pop() if data[-1] != '\n' else ""
            for line in lines:
                match = date_pattern.match(line)
                if match and match.group(1) == target_date:
                    output_file.write(line + '\n')
                    count += 1
                    if count % 100000 == 0:
                        print(f"Found {count} matching log entries so far...")
        if leftover:
            match = date_pattern.match(leftover)
            if match and match.group(1) == target_date:
                output_file.write(leftover + '\n')
                count += 1
    
    elapsed_time = time.time() - start_time
    print(f"Extraction completed in {elapsed_time:.2f} seconds")
    print(f"Found {count} log entries for date {target_date}")
    
    return count


def validate_date(date_string):
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def main():
    if len(sys.argv) != 3:
        print("Usage: python extract_logs.py YYYY-MM-DD")
        sys.exit(1)
    log_file_path = sys.argv[1]
    target_date = sys.argv[2]
    
    
    if not validate_date(target_date):
        print("Error: Date must be in YYYY-MM-DD format")
        sys.exit(1)
    
    
    # Path for the output file
    output_file_path = f"output/output_{target_date}.txt"
    
    try:
        print(f"Extracting logs for date: {target_date}")
        num_logs = extract_logs_parallel(log_file_path, target_date, output_file_path)
        
        print(f"Successfully extracted {num_logs} logs to {output_file_path}")
    except FileNotFoundError:
        print(f"Error: Log file not found at {log_file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()