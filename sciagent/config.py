import os
from pathlib import Path


class Config:
    def __init__(self):
        self.home = Path(os.getenv("SCIAGENT_HOME", "./state")).expanduser().resolve()
        self.db_path = Path(os.getenv("SCIAGENT_DB", str(self.home / "sciagent.sqlite3"))).expanduser().resolve()
        self.artifacts_dir = self.home / "artifacts"
        self.llm_provider = os.getenv("SCIAGENT_LLM", "auto")
        self.model = os.getenv("SCIAGENT_MODEL", "qwen2.5:7b")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self.context_tokens = int(os.getenv("SCIAGENT_CONTEXT_TOKENS", "8000"))
        self.output_reserve = int(os.getenv("SCIAGENT_OUTPUT_RESERVE", "1500"))
        self.arxiv_api_delay = float(os.getenv("SCIAGENT_ARXIV_API_DELAY", "3.0"))
        self.arxiv_browser_delay = float(os.getenv("SCIAGENT_ARXIV_BROWSER_DELAY", "16.0"))
        self.user_agent = os.getenv(
            "SCIAGENT_USER_AGENT",
            "ScientificResearchAgent/0.1 (research use; contact: local-user)",
        )

    def ensure_dirs(self):
        self.home.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
