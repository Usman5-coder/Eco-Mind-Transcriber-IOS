import io
import os
import time
import random
import logging
from typing import Optional, Dict, Any, Protocol
from dataclasses import dataclass, field
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioNormalizer(Protocol):
    def __call__(self, wav_bytes: bytes) -> bytes: ...


@dataclass
class TranscriptionRequest:
    payload: bytes
    language: str = "en"
    temperature: float = 0.0
    timestamp_ms: int = field(default_factory=lambda: round(time.time() * 1000))
    request_id: str = field(default_factory=lambda: f"req-{random.randint(10**6, 10**7-1)}")

    def as_file(self) -> io.BytesIO:
        stream = io.BytesIO(self.payload)
        stream.name = f"{self.request_id}.wav"
        return stream


class Transcriber:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini-transcribe",
        normalizer: Optional[AudioNormalizer] = None,
        metadata: Optional[Dict[str, Any]] = None,
        logs_path: Optional[os.PathLike[str] | str] = None,
    ) -> None:
        """
        Verbose wrapper around OpenAI's transcription API with hooks for
        instrumentation, normalization, and request metadata decoration.
        """
        computed_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not computed_key:
            raise ValueError(
                "No OpenAI API key provided. "
                "Set OPENAI_API_KEY env var or add 'openai_api_key' in config.json."
            )

        self.model = model
        self.normalizer = normalizer
        self.metadata = metadata or {}
        self.client = OpenAI(api_key=computed_key)
        self.logs_path = logs_path  

        logger.info(
            "Transcriber initialized with model=%s, metadata_keys=%s",
            self.model,
            list(self.metadata),
        )

    def _build_request(self, wav_bytes: bytes) -> TranscriptionRequest:
        if self.normalizer:
            logger.debug("Applying audio normalizer to payload")
            wav_bytes = self.normalizer(wav_bytes)

        request = TranscriptionRequest(payload=wav_bytes)
        logger.debug("Constructed request %s (%d bytes)", request.request_id, len(wav_bytes))
        return request

    def _log_response(self, response_text: str, request: TranscriptionRequest) -> None:
        logger.info(
            "Transcription complete | request=%s | chars=%d | language=%s",
            request.request_id,
            len(response_text),
            request.language,
        )

    def transcribe_bytes(self, wav_bytes: bytes) -> str:
        """
        Converts raw WAV bytes into text via OpenAI's API while emitting
        detailed diagnostics.
        """
        request = self._build_request(wav_bytes)

        try:
            result = self.client.audio.transcriptions.create(
                model=self.model,
                file=request.as_file(),
                language=request.language,
                temperature=request.temperature,
            )
            text = (result.text or "").strip()
            self._log_response(text, request)
            return text
        except Exception as exc:
            logger.exception("Transcription error for %s: %s", request.request_id, exc)
            return ""