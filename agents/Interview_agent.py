from base_agent import SARBaseAgent
from PyPDF2 import PdfReader
import openai
import os
import json

class InterviewAnalystAgent(SARBaseAgent):
    def __init__(self, name, role, system_message, input_text):
        super().__init__(name, role, system_message)
        self.input_text = input_text

    def extract_interview_transcript(self, filename):
        reader = PdfReader(filename)
        text = ''
        for page in reader.pages:
            text += page.extract_text()
            print(text)

    openai.api_key = os.getenv("OPENAI_API_KEY")


    def ask_chatgpt(self, prompt):
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response['choices'][0]['message']['content']


    def assign_confidence_rating(self, section: str):
        confidence = {
            "think": 1, "maybe": 1, "might": 1, "unsure": 1, "not sure": 1, "can't remember": 1, "sort of": 1, "I guess": 1,
            "probably": 2, "possibly": 2, "presumably": 2, "perhaps": 2, "I believe": 2, "I assume": 2, "around": 2, "about": 2,
            "definitely": 3, "absolutely": 3, "exactly": 3, "certainly": 3, "for sure": 3, "no doubt": 3, "I saw": 3, "I know": 3
        }
        confidence_score = 0
        for x, y in confidence.items():
            if x in section.lower():
                confidence_score += y


        if confidence_score in range(0, 4):
            confidence_level = "low"
        if confidence_score in range(4, 7):
            confidence_level = "mid"
        if confidence_score >= 7:
            confidence_level = "high"

        result_dicts = {
            "section": section,
            "confidence_score": confidence_score,
            "confidence_level": confidence_level
        }
        return result_dicts

    def extract_entities(self, sections):
        extracted_data = []

        for section in sections:
            prompt = (
                "Extract the names of people, places, and time references from the following interview section. "
                "Respond in JSON format with keys: people, places, times.\n\n"
                f"{section}"
            )
            response = self.ask_chatgpt(prompt)

            try:
                entities = json.loads(response)
            except json.JSONDecodeError:
                entities = {"people": [], "places": [], "times": []}

            extracted_data.append({
                "section": section,
                "entities": entities
            })

        return extracted_data

    def parse_sections(self):
        sections = []
        raw_sections = self.input_text.split('\n\n')  # split by double line breaks
        for s in raw_sections:
            cleaned = s.strip()
            if cleaned:
                sections.append(cleaned)
        return sections




















