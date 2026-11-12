"""Gemini model wrapper with automatic model selection, retries and fallback."""
import time

from google import genai
from google.genai import errors

# Preferred models, best first. The first one available to the API key is used.
PREFERRED_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


class LLM:
    def __init__(self, api_key, model=None, log=None):
        if not api_key:
            raise ValueError("A Gemini API key is required.")
        self.client = genai.Client(api_key=api_key)
        self.log = log or (lambda msg: None)
        self._available = None
        self.model = model or self.pick_model()

    # ------------------------------------------------------------------ models
    def available_models(self):
        """Names of models that this key can use for text generation."""
        if self._available is None:
            names = []
            try:
                for m in self.client.models.list():
                    name = (m.name or "").split("/")[-1]
                    actions = getattr(m, "supported_actions", None) or []
                    if actions and "generateContent" not in actions:
                        continue
                    if name.startswith("gemini"):
                        names.append(name)
            except Exception as exc:  # listing is optional; fall back to the preference list
                self.log(f"Could not list models ({exc}); using defaults.")
            self._available = names
        return self._available

    def pick_model(self):
        avail = set(self.available_models())
        for name in PREFERRED_MODELS:
            if not avail or name in avail:
                return name
        flash = sorted(n for n in avail if "flash" in n and "image" not in n and "tts" not in n
                       and "live" not in n and "audio" not in n)
        return flash[-1] if flash else PREFERRED_MODELS[0]

    def _next_model(self):
        avail = set(self.available_models())
        order = [m for m in PREFERRED_MODELS if not avail or m in avail]
        if self.model in order and order.index(self.model) + 1 < len(order):
            return order[order.index(self.model) + 1]
        return None

    # ---------------------------------------------------------------- generate
    def generate(self, contents, config, max_retries=4):
        """Call the model, retrying on rate limits and switching model if one is unavailable."""
        delay = 5
        for attempt in range(max_retries + 1):
            try:
                return self.client.models.generate_content(model=self.model, contents=contents, config=config)
            except errors.ClientError as exc:
                code = getattr(exc, "code", None)
                if code == 429 and attempt < max_retries:
                    self.log(f"Rate limit reached on {self.model}; waiting {delay}s and retrying.")
                    time.sleep(delay)
                    delay = min(delay * 2, 40)
                    continue
                if code in (400, 403, 404) and ("not found" in str(exc).lower() or "not supported" in str(exc).lower()
                                                or "permission" in str(exc).lower() or code == 404):
                    nxt = self._next_model()
                    if nxt:
                        self.log(f"Model {self.model} is not available for this key; switching to {nxt}.")
                        self.model = nxt
                        continue
                raise
            except errors.ServerError:
                if attempt < max_retries:
                    self.log(f"Model server busy; retrying in {delay}s.")
                    time.sleep(delay)
                    delay = min(delay * 2, 40)
                    continue
                raise
