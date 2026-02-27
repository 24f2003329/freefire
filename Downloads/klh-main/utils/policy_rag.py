import os
import json
import re
import hashlib
import google.generativeai as genai
import chromadb
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")
os.makedirs(CHROMA_DIR, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)


from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-en-v1.5")

def get_embedding(text):
    return model.encode(text, normalize_embeddings=True)


def sanitize_collection_name(name):
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if len(name) < 3:
        name = name + "_col"
    if len(name) > 63:
        name = name[:63]
    if not name[0].isalpha():
        name = "c_" + name
    return name


def get_collection(policy_id):
    col_name = sanitize_collection_name(f"pol_{policy_id}")
    return chroma_client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"}
    )


def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages.append({"page_number": i + 1, "text": text.strip()})
    return pages


def chunk_text(text, page_number, chunk_size=500, overlap=100):
    chunks = []
    words = text.split()
    if len(words) <= chunk_size:
        return [{"text": text, "page_number": page_number}]

    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_str = " ".join(words[start:end])
        chunks.append({"text": chunk_str, "page_number": page_number})
        if end >= len(words):
            break
        start += chunk_size - overlap
    return chunks


def ingest_policy(pdf_path, policy_name):
    policy_id = hashlib.md5(f"{policy_name}_{os.path.basename(pdf_path)}".encode()).hexdigest()[:16]
    collection = get_collection(policy_id)

    if collection.count() > 0:
        return {
            "policy_id": policy_id, "policy_name": policy_name,
            "chunks": collection.count(), "status": "already_ingested"
        }

    pages = extract_text_from_pdf(pdf_path)
    if not pages:
        return {
            "policy_id": policy_id, "policy_name": policy_name,
            "chunks": 0, "status": "error",
            "message": "No text extracted from PDF."
        }

    all_chunks = []
    for page in pages:
        all_chunks.extend(chunk_text(page["text"], page["page_number"]))

    ids = []
    embeddings = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(all_chunks):
        ids.append(f"{policy_id}_c{i}")
        documents.append(chunk["text"])
        metadatas.append({
            "page_number": chunk["page_number"],
            "chunk_index": i,
            "policy_name": policy_name,
            "policy_id": policy_id
        })
        embeddings.append(get_embedding(chunk["text"]))

    batch_size = 40
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        collection.add(
            ids=ids[i:end],
            embeddings=embeddings[i:end],
            documents=documents[i:end],
            metadatas=metadatas[i:end]
        )

    return {
        "policy_id": policy_id, "policy_name": policy_name,
        "chunks": len(all_chunks), "pages": len(pages), "status": "success"
    }


def query_policy(policy_id, question, n_results=5):
    collection = get_collection(policy_id)

    if collection.count() == 0:
        return {
            "answer": "No policy data found. Please upload a policy first.",
            "verdict": "UNKNOWN", "citations": [],
            "confidence": "Low", "retrieved_chunks": []
        }

    q_embedding = get_embedding(question)
    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(n_results, collection.count())
    )

    context_parts = []
    retrieved_chunks = []

    for i in range(len(results["documents"][0])):
        doc = results["documents"][0][i]
        meta = results["metadatas"][0][i]
        context_parts.append(f"[Source {i+1} - Page {meta['page_number']}]:\n{doc}")
        retrieved_chunks.append({
            "source_number": i + 1,
            "page_number": meta["page_number"],
            "text_snippet": doc[:300] + "..." if len(doc) > 300 else doc,
            "full_text": doc
        })

    context = "\n\n---\n\n".join(context_parts)

    model = genai.GenerativeModel("gemini-3-flash-preview")

    prompt = f"""You are an expert insurance policy analyst. Answer the customer's question based ONLY on the policy excerpts below.

POLICY EXCERPTS:
{context}

CUSTOMER QUESTION: {question}

Return a valid JSON object (no markdown, no code blocks):

{{
    "verdict": "string - COVERED / NOT COVERED / PARTIALLY COVERED / UNCLEAR",
    "answer": "string - clear simple explanation in 2-4 sentences",
    "detailed_explanation": "string - detailed explanation with policy terms",
    "conditions": ["list of conditions/waiting periods that apply"],
    "exclusions": ["list of relevant exclusions"],
    "limits": "string - coverage limits or 'Not specified'",
    "citations": [
        {{
            "source_number": "number",
            "page_number": "number",
            "relevant_quote": "string - exact quote from excerpt"
        }}
    ],
    "confidence": "High / Medium / Low",
    "follow_up_suggestions": ["2-3 related questions"]
}}

Rules: Only use info from excerpts. Cite page numbers. Use simple language. If info is insufficient, say UNCLEAR."""

    response = model.generate_content(prompt)

    try:
        text = response.text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
    except (json.JSONDecodeError, Exception):
        result = {
            "verdict": "UNCLEAR",
            "answer": response.text if response else "Analysis failed",
            "detailed_explanation": "",
            "conditions": [], "exclusions": [],
            "limits": "Not specified",
            "citations": [], "confidence": "Low",
            "follow_up_suggestions": []
        }

    result["retrieved_chunks"] = retrieved_chunks
    return result


def list_policies():
    policies = []
    try:
        collections = chroma_client.list_collections()
        for col_name in collections:
            name = col_name if isinstance(col_name, str) else (col_name.name if hasattr(col_name, 'name') else str(col_name))
            if name.startswith("pol_"):
                collection = chroma_client.get_collection(name)
                count = collection.count()
                if count > 0:
                    sample = collection.peek(1)
                    policy_name = "Unknown Policy"
                    policy_id = name.replace("pol_", "")
                    if sample and sample.get("metadatas") and len(sample["metadatas"]) > 0:
                        policy_name = sample["metadatas"][0].get("policy_name", "Unknown")
                        policy_id = sample["metadatas"][0].get("policy_id", policy_id)
                    policies.append({
                        "policy_id": policy_id,
                        "policy_name": policy_name,
                        "chunks": count,
                        "collection_name": name
                    })
    except Exception as e:
        print(f"Error listing policies: {e}")
    return policies


def delete_policy(policy_id):
    col_name = sanitize_collection_name(f"pol_{policy_id}")
    try:
        chroma_client.delete_collection(col_name)
        return True
    except Exception:
        return False