#!/usr/bin/env python3

# Replace this with your actual API key
api_key = "YOUR_OPENAI_API_KEY_HERE"

with open('.env', 'w', encoding='utf-8') as f:
    f.write(f"OPENAI_API_KEY={api_key}\n")

print("✅ .env file created successfully!")
print("API Key length:", len(api_key)) 