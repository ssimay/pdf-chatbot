# ingest.py 
import argparse
import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.schema.document import Document
from get_embedding_function import get_embedding_function
from langchain_chroma import Chroma
from tqdm import tqdm
import time

def ingest_pdf_to_chroma(pdf_filepath: str, chroma_target_path: str):
    """
    Ingests a single PDF file into a specified Chroma database path.
    """
    print(f"✨ Starting ingestion for {pdf_filepath} into {chroma_target_path}...")

    documents = load_single_pdf(pdf_filepath)
    chunks = split_documents(documents)
    add_to_chroma(chunks, chroma_target_path)
    print(f"✅ Ingestion complete for {pdf_filepath}.")


def load_single_pdf(pdf_filepath: str):
    """Loads a single PDF document from the given path."""
    loader = PyPDFLoader(pdf_filepath)
    return loader.load()

def split_documents(documents: list[Document]):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        length_function=len,
        is_separator_regex=False,
    )
    return text_splitter.split_documents(documents)

def calculate_chunk_ids(chunks):
    last_page_id = None
    current_chunk_index = 0

    for chunk in chunks:
        source = os.path.basename(chunk.metadata.get("source", ""))
        page = chunk.metadata.get("page")
        
        if not isinstance(page, (int, str)):
            page = "unknown_page"
        if not isinstance(source, str) or not source:
            source = "unknown_source.pdf"

        current_page_id = f"{source}:{page}"

        if current_page_id == last_page_id:
            current_chunk_index += 1
        else:
            current_chunk_index = 0

        chunk.metadata["id"] = f"{current_page_id}:{current_chunk_index}"
        last_page_id = current_page_id

    return chunks

def add_to_chroma(chunks: list[Document], chroma_target_path: str):
    db = Chroma(
        persist_directory=chroma_target_path,
        embedding_function=get_embedding_function()
    )

    chunks_with_ids = calculate_chunk_ids(chunks)

    existing_items = db.get(include=[])
    existing_ids = set(existing_items["ids"])
    print(f"🔎 Existing documents in DB ({chroma_target_path}): {len(existing_ids)}")

    new_chunks = [chunk for chunk in chunks_with_ids if chunk.metadata["id"] not in existing_ids]

    if new_chunks:
        print(f"➕ Adding new documents: {len(new_chunks)}")
        for chunk in tqdm(new_chunks, desc=f"📦 Embedding chunks into {chroma_target_path}"):
             db.add_documents([chunk], ids=[chunk.metadata["id"]])

        del db
    else:
        print("✅ No new documents to add")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_file", type=str, help="Path to the PDF file to ingest.")
    parser.add_argument("--chroma_path", type=str, default="chroma_temp_upload",
                        help="Path where the Chroma DB for this PDF will be stored.")
    parser.add_argument("--reset", action="store_true", help="Reset the database before ingestion.")
    args = parser.parse_args()

    if args.reset and os.path.exists(args.chroma_path):
        import shutil
        shutil.rmtree(args.chroma_path)
        print(f"Cleared {args.chroma_path}")


    ingest_pdf_to_chroma(args.pdf_file, args.chroma_path)