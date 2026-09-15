import os
import json
import logging
import re
import anthropic
from django.conf import settings
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """
    Base class for all AI agents in the system.
    Handles API client initialization, error handling, and common utilities.
    """

    def __init__(self):
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
        self.max_tokens = getattr(settings, 'AI_MAX_TOKENS', 4096)
        self.temperature = getattr(settings, 'AI_TEMPERATURE', 0.7)

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY is not set in settings.")

        # Honor ANTHROPIC_API_BASE_URL (e.g. custom/proxy endpoints) just like
        # the chat service does — without it a proxy-only key fails auth.
        client_kwargs = {'api_key': self.api_key}
        base_url = getattr(settings, 'ANTHROPIC_API_BASE_URL', '')
        if base_url:
            client_kwargs['base_url'] = base_url
        self.client = anthropic.Anthropic(**client_kwargs)

    def generate(self, prompt, system_prompt=None, temperature=None, max_tokens=None):
        """
        Generate content using the Anthropic API.

        Args:
            prompt (str): The user prompt
            system_prompt (str): Optional system prompt to set context
            temperature (float): Optional override for temperature
            max_tokens (int): Optional override for max tokens

        Returns:
            str: The generated content
        """
        try:
            kwargs = {
                "model": self.model,
                # `or` swallows falsy values like temperature=0 — use is None
                "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
                "temperature": self.temperature if temperature is None else temperature,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            # Join all text blocks (don't assume content[0] is text)
            text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return text or response.content[0].text

        except anthropic.APIError as e:
            logger.error(f"Anthropic API Error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in AI generation: {str(e)}")
            raise

    def generate_json(self, prompt, system_prompt=None):
        """
        Generate structured JSON content.
        Forces the model to output JSON and parses the result.
        """
        json_prompt = f"{prompt}\n\nPlease respond with valid JSON only, without any markdown formatting or explanations."

        response_text = self.generate(json_prompt, system_prompt, temperature=0.2)

        try:
            # Prefer the first {...} block — robust against preamble text,
            # ```json fences, and trailing explanations.
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise json.JSONDecodeError('no JSON object found', response_text, 0)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {response_text}")
            raise ValueError(f"AI did not return valid JSON: {str(e)}")

    @abstractmethod
    def process_request(self, request_data):
        """
        Abstract method to be implemented by specific agents.
        """
        pass
