"""Adapter for the Qwen-7B model behind an OpenAI-compatible chat endpoint.

On the laptop this is llama.cpp's llama-server running the GGUF file. A hosted GPU server (vLLM, or
llama-server on Kaggle/Colab behind an authenticated tunnel) works the same way: set MODEL_BASE_URL and
MODEL_API_KEY. The React app never talks to the model directly.
"""
import json
import re
from pathlib import Path

import httpx

from app.core.config import Settings
from app.validators.mcq_format import build_input

# Same system prompt the LoRA model was fine-tuned with; changing it changes the model's behaviour.
MCQ_SYSTEM = ("You are a B.Tech exam setter. From the context, write ONE multiple-choice question of the requested difficulty. "
              "Exactly one option is correct; the three wrong options must be different from each other, plausible and clearly wrong. "
              "Check any calculation before answering. Reply in exactly this format: question: <question> options: (A) <option> "
              "(B) <option> (C) <option> (D) <option> answer: <letter> explanation: <one or two sentences>")

NOTES_SYSTEM = "You are a B.Tech lecturer who writes accurate, compact study notes."
ASPECTS_USER = ("List {n} different subtopics of \"{topic}\" (subject: {subject}) that a B.Tech exam could test. "
                "Write one short subtopic per line, with no numbering and no other text.")
NOTES_USER = ("Write study notes on \"{aspect}\" for the topic \"{topic}\" in {subject}. Write one paragraph of about 140 words "
              "with precise definitions, key facts, and any standard formula with a small worked number example if the "
              "subtopic has one. Do not write questions.")

FEWSHOT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "fewshot_examples.json"


class ModelError(Exception):
    """Base class; message is safe to show to users."""


class ModelUnavailable(ModelError):
    pass


class ModelTimeout(ModelError):
    pass


class ModelBadResponse(ModelError):
    pass


class ModelService:
    def __init__(self, settings: Settings):
        self.s = settings
        headers = {"Content-Type": "application/json"}
        if settings.model_api_key:
            headers["Authorization"] = f"Bearer {settings.model_api_key}"
        self.client = httpx.Client(base_url=settings.model_base_url.rstrip("/"), headers=headers,
                                   timeout=httpx.Timeout(settings.model_timeout_s, connect=10.0))
        self.fewshot = json.loads(FEWSHOT_PATH.read_text(encoding="utf-8")) if settings.model_variant == "base" else []

    # ---------- transport ----------

    def chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> str:
        body = {"model": self.s.model_name, "messages": messages,
                "temperature": self.s.temperature if temperature is None else temperature,
                "top_p": self.s.top_p, "max_tokens": max_tokens or self.s.max_tokens}
        try:
            r = self.client.post("/v1/chat/completions", json=body)
        except httpx.TimeoutException as e:
            raise ModelTimeout(f"The model did not answer within {self.s.model_timeout_s:.0f} seconds.") from e
        except httpx.HTTPError as e:
            raise ModelUnavailable(f"Cannot reach the model service at {self.s.model_base_url}. Is it running?") from e
        if r.status_code in (401, 403):
            raise ModelUnavailable("The model service refused the API key (check MODEL_API_KEY).")
        if r.status_code >= 400:
            raise ModelBadResponse(f"The model service returned HTTP {r.status_code}.")
        try:
            return r.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ModelBadResponse("The model service sent a response in an unexpected format.") from e

    def health(self) -> tuple[str, str | None]:
        try:
            r = self.client.get("/health", timeout=5.0)
        except httpx.HTTPError:
            return "unreachable", f"No model service at {self.s.model_base_url}. Start llama-server with the GGUF model (see README)."
        if r.status_code == 200:
            return "ok", None
        if r.status_code == 503:
            return "error", "The model service is still loading the model."
        return "error", f"The model service health check returned HTTP {r.status_code}."

    # ---------- prompts ----------

    def mcq_messages(self, subject: str, topic: str, difficulty: str, context: str, branch: str | None = None) -> list[dict]:
        user = build_input(branch or self.s.default_branch, subject, topic, difficulty, context)
        msgs = [{"role": "system", "content": MCQ_SYSTEM}]
        for ex in self.fewshot:                       # untrained base model: two worked examples first
            msgs += [{"role": "user", "content": ex["input_text"]}, {"role": "assistant", "content": ex["target_text"]}]
        return msgs + [{"role": "user", "content": user}]

    def generate_mcq_text(self, subject, topic, difficulty, context) -> str:
        return self.chat(self.mcq_messages(subject, topic, difficulty, context))

    def generate_aspects(self, subject: str, topic: str, n: int) -> list[str]:
        text = self.chat([{"role": "system", "content": NOTES_SYSTEM},
                          {"role": "user", "content": ASPECTS_USER.format(n=n, topic=topic, subject=subject)}],
                         temperature=0.3, max_tokens=200)
        lines = [re.sub(r"^[\s\-*•\d.)]+", "", l).strip() for l in text.splitlines()]
        seen, out = set(), []
        for l in lines:
            if 3 <= len(l) <= 120 and l.lower() not in seen:
                seen.add(l.lower()); out.append(l)
        return out[:n]

    def generate_notes(self, subject: str, topic: str, aspect: str) -> str:
        text = self.chat([{"role": "system", "content": NOTES_SYSTEM},
                          {"role": "user", "content": NOTES_USER.format(aspect=aspect, topic=topic, subject=subject)}],
                         temperature=0.3, max_tokens=320)
        return " ".join(text.split())

    def close(self):
        self.client.close()
