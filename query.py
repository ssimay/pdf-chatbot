# query.py 
import argparse
import os
from groq import Groq
from dotenv import load_dotenv
import requests
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate
from get_embedding_function import get_embedding_function
from sentence_transformers import CrossEncoder
from huggingface_hub import login 


PROMPT_TEMPLATE = """
You are a helpful tutor that answers questions concisely and factually, based only on the provided context and conversation history. Do not add made-up examples, fictional scenarios, or unrelated commentary.

Context:
{context}

Conversation History:
{history}

User's Question:
{question}

Answer the question based on the above context.
"""
load_dotenv()

hf_token = os.environ.get("HUGGINGFACE_TOKEN")
if hf_token:
    login(token=hf_token)
else:
    print("HUGGINGFACE_TOKEN not found in .env. Model downloads might fail.")

reranker = CrossEncoder("BAAI/bge-reranker-large")

def rerank_chunks(query: str, docs: list) -> list:
    pairs = [(query, doc.page_content) for doc in docs]
    scores = reranker.predict(pairs)

    scored = list(zip(docs, scores))
    scored.sort(key=lambda x: x[1], reverse=True)  
    return [doc for doc, _ in scored]

def call_groq_api(prompt: str) -> str:
    client = Groq(
        api_key=os.environ.get("GROQ_API_KEY"),
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model="gemma2-9b-it",
        temperature=0.7,
        max_completion_tokens=1024,
        top_p=1,
        stop=None,
    )

    return chat_completion.choices[0].message.content

def query_rag(query_text: str, history=None, use_history=False, chroma_path: str = None):
    if not chroma_path:
        return "No PDF has been loaded. Please upload a PDF to start."

    db = Chroma(
        persist_directory=chroma_path, 
        embedding_function=get_embedding_function()
    )

    question_variants = generate_question_variants(query_text)

    retrieved_docs = []
    seen_ids = set()

    for variant in question_variants:
        variant_results = db.similarity_search_with_score(variant, k=3)
        for doc, score in variant_results:
            doc_id = doc.metadata.get("id")
            if doc_id and doc_id not in seen_ids:
                retrieved_docs.append((doc, score))
                seen_ids.add(doc_id)

    retrieved_docs.sort(key=lambda x: x[1])
    docs_only = [doc for doc, _ in retrieved_docs]
    top_k_docs = rerank_chunks(query_text, docs_only)[:5]

    context_text = "\n\n---\n\n".join([doc.page_content for doc in top_k_docs])
    sources = [doc.metadata.get("id", None) for doc in top_k_docs]

    if use_history and history:
        formatted_history = ""
        max_messages = 6
        limited_history = history[-max_messages:]
        for msg in limited_history:
            role = "User" if msg['sender'] == 'user' else "Assistant"
            formatted_history += f"{role}: {msg['message']}\n"
    else:
        formatted_history = "No prior conversation."

    prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
    prompt = prompt_template.format(
        context=context_text,
        history=formatted_history,
        question=query_text
    )

    response_text = call_groq_api(prompt)
    formatted_response = f"{response_text}\n\nSources: {sources}"

    return response_text

def generate_question_variants(original_question: str) -> list[str]:
    return [
        original_question,
        f"Explain in detail: {original_question}",
        f"What are the steps involved in: {original_question}?",
        f"Can you describe: {original_question}?",
        f"Break down: {original_question}"
    ]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query_text", type=str, help="The query text.")
    parser.add_argument("--chroma_path", type=str, default="chroma", 
                        help="Path to the Chroma DB to query from.")
    args = parser.parse_args()
    print(query_rag(args.query_text, chroma_path=args.chroma_path))