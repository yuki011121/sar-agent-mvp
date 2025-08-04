from autogen import AssistantAgent
from abc import ABC, abstractmethod

class SARBaseAgent(AssistantAgent):
    def __init__(self, name, role, system_message, knowledge_base=None):
        super().__init__(
            name=name,
            system_message=system_message,
            llm_config={
                "temperature": 0.7,
                "request_timeout": 600,
                "seed": 42,
                "config_list": self.get_config_list()
            }
        )
        self.role = role
        self.kb = knowledge_base
        self.mission_status = "standby"

    def get_config_list(self):
        """Load configuration from environment variables"""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        return [{
            "model": "gpt-4",
            "api_key": os.getenv("OPENAI_API_KEY"),
            "deployment_name": os.getenv("DEPLOYMENT_NAME")
        }]

@abstractmethod
def process_request(self, message):
    """Process incoming requests - must be implemented by specific agents"""
    pass

def update_status(self, status):
    """Update agent's mission status"""
    self.mission_status = status
    return {"status": "updated", "new_status": status}

def get_status(self):
    """Return current status"""
    return self.mission_status