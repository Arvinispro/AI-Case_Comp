"""Simple Gemini API call with Python.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# Always load the workspace .env, even if the process starts from another directory.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)
api_key = os.getenv("GEMINI_API_KEY")
ai_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not api_key:
    print("Missing GEMINI_API_KEY. Put it in your .env file.")
    sys.exit(1)

client = genai.Client(api_key=api_key)

#Examples of using prompts
response = client.models.generate_content(
    model=ai_model,
    contents="Are you there?",
)
print(response.text)

response = client.models.generate_content_stream(
    model=ai_model,
    contents="What is Gaussian Distribution?",
)
for stream in response:
  print(stream.text)
  
#Example of having a chat
chat = client.chats.create(model=ai_model)

while True:
    msg = input(">")
    if msg == 'exit':
        break
    response = chat.send_message(msg)
    print(response.text)

# Example of sending files
uploaded_file = client.files.upload(file = "A2_handout.pdf")

response = client.models.generate_content(
    model = ai_model,
    contents = ["Summarize this assignment", uploaded_file]
)

print(response.text)
