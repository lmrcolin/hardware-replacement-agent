"""Voice for the agent chat: speech-to-text on this machine, text-to-speech in the browser.

- STT: faster-whisper (https://github.com/SYSTRAN/faster-whisper, MIT) on the CPU, int8.
  Local and free (CLAUDE.md rule 5): the audio never leaves the machine. The model is
  downloaded once on first use (``ADVISOR_WHISPER_MODEL``, default ``small``). Optional extra:
  ``uv sync --extra voice``; without it the microphone is simply not offered.
- TTS: the browser's own ``speechSynthesis`` (Spanish voice when available). No dependency, no
  service. It reads only the agent's final message, which the agent already verified.
Presentation only: the transcript is sent to the agent exactly like typed text.
"""

from __future__ import annotations

import io
import json
import os
import re
import wave
from collections.abc import Callable, Iterable
from functools import cache
from importlib.util import find_spec
from typing import Any

DEFAULT_MODEL = "small"
MODEL_ENV = "ADVISOR_WHISPER_MODEL"


def available() -> bool:
    """True when faster-whisper is installed (``uv sync --extra voice``)."""
    return find_spec("faster_whisper") is not None


@cache
def _model(name: str) -> Any:
    from faster_whisper import WhisperModel  # optional dependency

    return WhisperModel(name, device="cpu", compute_type="int8")


def vocabulary_prompt(part_numbers: Iterable[str]) -> str:
    """Whisper ``initial_prompt``: biases the transcript towards the catalog's spellings."""
    parts = ", ".join(sorted(set(part_numbers)))
    return f"Reemplazo de componentes. Part numbers del catálogo: {parts}." if parts else ""


SAMPLE_RATE = 16_000  # what Whisper expects and what st.chat_input records


def wav_to_float32(audio: bytes) -> Any:
    """Mono float32 samples at 16 kHz from WAV bytes (stdlib + numpy; no ffmpeg/PyAV)."""
    import numpy as np

    with wave.open(io.BytesIO(audio), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError(f"WAV de {8 * width} bits no soportado (se espera PCM de 16 bits)")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and samples.size:
        positions = np.linspace(0, samples.size - 1, int(samples.size * SAMPLE_RATE / rate))
        samples = np.interp(positions, np.arange(samples.size), samples).astype(np.float32)
    return samples


def transcribe(audio: bytes, *, vocabulary: Iterable[str] = ()) -> str:
    """Spanish transcript of a WAV recording (empty string when nothing was said)."""
    model = _model(os.environ.get(MODEL_ENV) or DEFAULT_MODEL)
    segments, _ = model.transcribe(
        wav_to_float32(audio),
        language="es",
        vad_filter=True,
        initial_prompt=vocabulary_prompt(vocabulary) or None,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def message_from(value: Any, transcriber: Callable[[bytes], str] | None) -> tuple[str, bool]:
    """(text, came_by_voice) from a chat_input value: plain str or ChatInputValue."""
    if value is None:
        return "", False
    if isinstance(value, str):
        return value.strip(), False
    text = (getattr(value, "text", "") or "").strip()
    audio = getattr(value, "audio", None)
    if audio is not None and transcriber is not None:
        spoken = transcriber(audio.getvalue())
        if spoken:
            return f"{text} {spoken}".strip(), True
    return text, False


def speech_text(markdown: str, limit: int = 900) -> str:
    """Plain text to read aloud: no markdown symbols, at most ``limit`` characters."""
    text = re.sub(r"[*_`#>|]", "", markdown)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(". ", 1)[0]
    return cut + "."


def speak_html(text: str) -> str:
    """Snippet for ``st.components.v1.html``: reads ``text`` with a Spanish browser voice."""
    # json.dumps quotes the text; escaping "<" keeps "</script>" from closing the tag early.
    payload = json.dumps(speech_text(text)).replace("<", r"\u003c")
    return (
        "<script>(function(){const s=window.parent.speechSynthesis||window.speechSynthesis;"
        "if(!s){return;}const say=()=>{s.cancel();"
        f"const u=new SpeechSynthesisUtterance({payload});u.lang='es-MX';u.rate=1.02;"
        "const v=s.getVoices().find(x=>x.lang&&x.lang.toLowerCase().startsWith('es'));"
        "if(v){u.voice=v;u.lang=v.lang;}s.speak(u);};"
        "if(s.getVoices().length){say();}else{s.onvoiceschanged=say;}})();</script>"
    )
