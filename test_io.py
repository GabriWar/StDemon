#!/usr/bin/env python3
"""
Test script to demonstrate I/O monitoring with stdutil.py
This script writes to stdout at regular intervals and reads from stdin.
"""

import sys
import time
import random
import datetime
import select
import os

def main():
    """
    Main function that runs an infinite loop:
    - Writing timestamps to stdout every few seconds
    - Reading any available input from stdin
    """
    print("Starting I/O test script...")
    print("This script will output a timestamp every few seconds.")
    print("It will also echo back any input it receives.")
    print("Press Ctrl+C to exit.")
    print("-" * 50)
    
    # Counter for messages
    counter = 1
    
    try:
        while True:
            # Write a timestamp to stdout
            timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
            message = f"[{counter}] Output message at {timestamp}"
            print(message, flush=True)
            
            # Check if there's any input available
            if select.select([sys.stdin], [], [], 0)[0]:
                user_input = sys.stdin.readline().strip()
                if user_input:
                    echo_time = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    print(f"[{counter}] Received input at {echo_time}: {user_input}", flush=True)
            
            # Sleep for a random time between 1-5 seconds
            sleep_time = random.uniform(1, 5)
            counter += 1
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\nExiting test script.")
        sys.exit(0)

if __name__ == "__main__":
    # Set stdout to line-buffered mode
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    else:
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
    
    main()