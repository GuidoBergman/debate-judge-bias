"""Anthropic client + consultant call. One blocking call per invocation."""
import os

from anthropic import Anthropic
from dotenv import load_dotenv


# Local dev reads the key from .env; Heroku injects ANTHROPIC_API_KEY directly
# via `heroku config:set`, in which case load_dotenv is a no-op.
load_dotenv()

MODEL = 'claude-opus-4-5'
TEMPERATURE = 1.0
MAX_TOKENS = 400  # ~100-word replies; small headroom for formatting.

_client = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])


def call_consultant(system_prompt: str, user_prompt: str) -> str:
    resp = _client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    return resp.content[0].text.strip()
