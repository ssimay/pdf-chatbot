# db_manager.py
import json
import os
import shutil

DB_INDEX_FILE = 'db_index.json' 
CHROMA_DB_DIR = 'chroma_dbs' 

def load_db_index():
    """Loads the database index from JSON file."""
    if os.path.exists(DB_INDEX_FILE):
        try:
            with open(DB_INDEX_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {DB_INDEX_FILE} is corrupted. Starting with an empty index.")
            return {}
    return {}

def save_db_index(index):
    """Saves the database index to JSON file."""
    with open(DB_INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=4)

def add_pdf_to_index(pdf_name: str, chroma_path: str):
    """Adds a new PDF and its Chroma path to the index."""
    index = load_db_index()
    index[pdf_name] = chroma_path
    save_db_index(index)
    print(f"Added '{pdf_name}' to DB index at '{chroma_path}'")

def remove_pdf_from_index(pdf_name: str):
    """Removes a PDF entry from the index."""
    index = load_db_index()
    if pdf_name in index:
        del index[pdf_name]
        save_db_index(index)
        print(f"Removed '{pdf_name}' from DB index.")

def get_chroma_path_by_pdf_name(pdf_name: str):
    """Retrieves the Chroma path for a given PDF name."""
    index = load_db_index()
    return index.get(pdf_name)

def clear_database_and_index_entry(pdf_name: str):
    """Clears the Chroma database directory and removes its entry from the index."""
    chroma_path = get_chroma_path_by_pdf_name(pdf_name)
    if chroma_path and os.path.exists(chroma_path):
        try:
            print(f"✨ Clearing database at {chroma_path} for '{pdf_name}'...")
            shutil.rmtree(chroma_path)
            print(f"🗑️ Successfully cleared {chroma_path}")
        except PermissionError as e:
            print(f"⚠️ PermissionError: Could not clear {chroma_path}. Another process might be using the files. {e}")
            print("Please ensure no other ChromaDB processes are running or try restarting the application.")
        except Exception as e:
            print(f"❌ Error clearing database at {chroma_path}: {e}")
    else:
        print(f"Database for '{pdf_name}' at {chroma_path} does not exist or path not found in index. No need to clear.")
    
    remove_pdf_from_index(pdf_name) 