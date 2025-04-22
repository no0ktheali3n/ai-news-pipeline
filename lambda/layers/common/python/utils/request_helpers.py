import time
import random

def random_delay(min_seconds=0.1, max_seconds=1.5):
    duration = random.uniform(min_seconds, max_seconds)
    print(f"Sleeping for {duration:.2f} seconds...")
    time.sleep(duration)