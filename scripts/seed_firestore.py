import sys
import os

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sync_orchestrator import update_firestore_cache

if __name__ == "__main__":
    print("Seeding Firestore Cache...")
    update_firestore_cache()
    print("Done!")
