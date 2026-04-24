from google.adk.agents import Agent
from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval
from vertexai.preview import rag
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
CORPUS_ID = os.getenv("VERTEX_RAG_CORPUS_ID")

# Initialize Vertex AI
import vertexai
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Define RAG retrieval tool
ask_rag_retrieval = VertexAiRagRetrieval(
    name='retrieve_telegram_data',
    description=(
        'Gunakan tool ini untuk mengambil informasi relevan dari '
        'corpus chat Telegram untuk menjawab pertanyaan pengguna.'
    ),
    rag_resources=[
        rag.RagResource(
            rag_corpus=f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{CORPUS_ID}"
        )
    ],
    similarity_top_k=10,  # Ambil 10 hasil teratas
    vector_distance_threshold=0.6,  # Filter berdasarkan relevance
)