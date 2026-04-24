from google.adk.agents import Agent
from rag import ask_rag_retrieval

# Define agent
telegram_agent = Agent(
    model='gemini-3-flash-preview',
    name='telegram_data_agent',
    instruction="""
    Anda adalah assistant yang membantu pengguna menemukan informasi dari 
    chat Telegram. Gunakan retrieval tool untuk menemukan konteks relevan 
    dan berikan jawaban yang akurat dan bermanfaat.
    
    Selalu:
    1. Gunakan retrieval tool untuk mencari informasi
    2. Sertakan sumber/konteks dari chat
    3. Jika tidak menemukan info, beri tahu pengguna dengan jelas
    """,
    tools=[ask_rag_retrieval]
)