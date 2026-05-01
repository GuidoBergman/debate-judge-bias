"""LLM clients for the jury app: Anthropic Claude + Google Gemini.

Clients are lazy-initialized so importing this module never requires API keys
(useful for tests / scripts that read prompts.py through the package). Each
call is blocking; failures bubble up so the page can surface them to the
human judge rather than silently dropping a turn.
"""
import os
import warnings

from anthropic import Anthropic
from dotenv import load_dotenv

from .prompts import MODEL_CLAUDE, MODEL_GEMINI


load_dotenv()

TEMPERATURE = 1.0
# Both models are prompted to keep turns to ~50 words but neither
# strictly enforces the cap, and Claude in particular happily runs to
# 100+ words when it decides to elaborate. We give a generous margin so
# the visible reply is never truncated mid-sentence.
MAX_TOKENS_CLAUDE = 1000
# Gemini 2.5 Flash has built-in "thinking" tokens that count toward
# max_output_tokens but are NOT returned in response.text. With a tight
# cap the visible reply gets truncated mid-sentence (the model burns the
# budget thinking, then cuts off the answer). The legacy
# google-generativeai SDK doesn't expose thinking_config, so the only
# lever we have is a generous overall budget. 2000 tokens is plenty for
# any chain-of-thought + the 50-word visible reply.
MAX_TOKENS_GEMINI = 2000


_anthropic_client: Anthropic | None = None
_gemini_configured = False


def _get_anthropic() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    return _anthropic_client


def _ensure_gemini_configured():
    global _gemini_configured
    if not _gemini_configured:
        # The package emits a FutureWarning on import; we keep using it
        # because google-genai (its replacement) isn't installed in the
        # environment. The deprecated package still works for our needs.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', FutureWarning)
            import google.generativeai as genai
            genai.configure(api_key=os.environ['GOOGLE_API_KEY'])
        _gemini_configured = True


def call_claude(system_prompt: str, user_prompt: str) -> str:
    resp = _get_anthropic().messages.create(
        model=MODEL_CLAUDE,
        max_tokens=MAX_TOKENS_CLAUDE,
        temperature=TEMPERATURE,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    return resp.content[0].text.strip()


def call_gemini(system_prompt: str, user_prompt: str) -> str:
    _ensure_gemini_configured()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', FutureWarning)
        import google.generativeai as genai
        model = genai.GenerativeModel(
            model_name=MODEL_GEMINI,
            system_instruction=system_prompt,
        )
        resp = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=TEMPERATURE,
                max_output_tokens=MAX_TOKENS_GEMINI,
            ),
        )
    return (resp.text or '').strip()


def call_llm(model_id: str, system_prompt: str, user_prompt: str) -> str:
    if model_id == MODEL_CLAUDE:
        return call_claude(system_prompt, user_prompt)
    if model_id == MODEL_GEMINI:
        return call_gemini(system_prompt, user_prompt)
    raise ValueError(f'Unknown model id: {model_id!r}')
