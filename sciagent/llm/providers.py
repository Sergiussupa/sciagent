import json
import re

import requests


class LLMError(RuntimeError):
    pass


class BaseLLM:
    name = "base"

    def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        raise NotImplementedError


class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: int = 600):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            r = requests.get(
                self.base_url + "/api/tags",
                timeout=3,
            )
            return r.ok
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        system: str = "",
        json_mode: bool = False,
    ) -> str:

        messages = []

        if system:
            messages.append(
                {
                    "role": "system",
                    "content": system,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,

            # Для нашего pipeline reasoning наружу
            # сейчас не нужен.
            "think": False,

            "options": {
                "temperature": 0.1,
                "num_ctx": 8192,
            },
        }

        if json_mode:
            payload["format"] = "json"

        response = requests.post(
            self.base_url + "/api/chat",
            json=payload,
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()

        message = data.get("message") or {}

        text = (
            message.get("content") or ""
        ).strip()

        # Некоторые Qwen/Ollama combinations
        # кладут structured output сюда.
        if not text:
            text = (
                message.get("thinking") or ""
            ).strip()

        if not text:
            raise LLMError(
                "Ollama returned empty answer. "
                "response keys=%s message keys=%s"
                % (
                    sorted(data.keys()),
                    sorted(message.keys()),
                )
            )

        return text


class ExtractiveLLM(BaseLLM):
    name = "extractive-fallback"

    def generate(
        self,
        prompt: str,
        system: str = "",
        json_mode: bool = False,
    ) -> str:

        abstract = ""

        marker = "[ABSTRACT]"

        if marker in prompt:
            abstract = prompt.split(
                marker,
                1,
            )[1]

            next_marker = re.search(
                r"\n\n\[[A-Z0-9_]+\]\n",
                abstract,
            )

            if next_marker:
                abstract = abstract[
                    :next_marker.start()
                ]

        abstract = abstract.strip()

        if json_mode:
            return json.dumps(
                {
                    "summary": abstract[:2200],
                    "research_question": "",
                    "method": "",
                    "datasets": [],
                    "baselines": [],
                    "main_results": [],
                    "limitations": [],
                    "evidence": [],
                },
                ensure_ascii=False,
            )

        return abstract[:3000]


def make_llm(
    provider: str,
    model: str,
    ollama_url: str,
) -> BaseLLM:

    if provider == "extractive":
        return ExtractiveLLM()

    ollama = OllamaLLM(
        ollama_url,
        model,
    )

    if provider == "ollama":
        if not ollama.available():
            raise LLMError(
                "Ollama is not reachable at %s"
                % ollama_url
            )

        return ollama

    if provider == "auto":
        if ollama.available():
            return ollama

        return ExtractiveLLM()

    raise LLMError(
        "Unknown LLM provider: %s"
        % provider
    )
