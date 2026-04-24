import os
import asyncio
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from agent import telegram_agent

# Load environment variables
load_dotenv()

APP_NAME = "telegram-bot-test"
USER_ID = "test-user-001"
SESSION_ID = "test-session-001"


async def main() -> None:
    """Menguji telegram_agent menggunakan ADK Runner."""
    print("Menginisialisasi ADK Runner...")

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    runner = Runner(
        agent=telegram_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    pertanyaan = "Berikan saya ringkasan atau cari informasi tentang tiket INC48124542."
    print(f"\nPertanyaan: {pertanyaan}\n")

    content = types.Content(
        role="user",
        parts=[types.Part(text=pertanyaan)],
    )

    print("--- Jawaban Agen AI ---")
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=content,
    ):
        # Hanya tampilkan event final dari agen
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(part.text)


if __name__ == "__main__":
    asyncio.run(main())