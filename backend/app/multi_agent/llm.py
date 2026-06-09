"""Shared LLM client for all specialist agents."""
from __future__ import annotations

import json
import logging
import re

from app.database import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def parse_llm_json(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


class AgentLLM:
    def __init__(self) -> None:
        self._gemini = None
        self._groq_client = None
        if settings.gemini_api_key and settings.llm_provider != "groq":
            try:
                import google.generativeai as genai

                genai.configure(api_key=settings.gemini_api_key)
                self._gemini = genai.GenerativeModel(settings.gemini_model)
            except Exception as exc:
                logger.warning("Gemini client init failed: %s", exc)
        if settings.groq_api_key:
            try:
                from groq import Groq

                self._groq_client = Groq(api_key=settings.groq_api_key)
            except Exception as exc:
                logger.warning("Groq client init failed: %s", exc)

    @property
    def available(self) -> bool:
        return bool(self._gemini or self._groq_client)

    async def complete(self, prompt: str, temperature: float = 0.35, json_mode: bool = False) -> str | None:
        providers = (
            ("groq", self._groq_client),
            ("gemini", self._gemini),
        )
        if settings.llm_provider == "gemini":
            providers = (("gemini", self._gemini), ("groq", self._groq_client))

        for name, client in providers:
            if not client:
                continue
            if name == "gemini":
                try:
                    kwargs: dict = {}
                    if json_mode:
                        kwargs["generation_config"] = {"response_mime_type": "application/json"}
                    r = self._gemini.generate_content(prompt, **kwargs)
                    if r.text:
                        return r.text
                except Exception as exc:
                    logger.warning("Gemini request failed: %s", exc)
                continue
            if name == "groq":
                try:
                    groq_kwargs: dict = {
                        "model": getattr(settings, "groq_model", "llama-3.3-70b-versatile"),
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                    }
                    if json_mode:
                        groq_kwargs["response_format"] = {"type": "json_object"}
                    r = self._groq_client.chat.completions.create(**groq_kwargs)
                    content = r.choices[0].message.content
                    if content:
                        return content
                except Exception as exc:
                    logger.warning("Groq request failed: %s", exc)
        return None

    async def json_prompt(self, prompt: str) -> dict | None:
        raw = await self.complete(prompt, json_mode=True)
        if not raw:
            raw = await self.complete(prompt)
        return parse_llm_json(raw or "")

    async def text_prompt(self, prompt: str) -> str | None:
        return await self.complete(prompt)


llm = AgentLLM()
