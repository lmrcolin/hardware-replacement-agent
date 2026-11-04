"""Voice helpers (app/components/voice.py): no model is loaded here."""

from __future__ import annotations

import io
import json
import math
import struct
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from components import voice


def _wav(seconds: float, rate: int, channels: int = 1) -> bytes:
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) * channels
        for i in range(int(seconds * rate))
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buffer.getvalue()


def test_wav_is_decoded_to_mono_16k_float() -> None:
    pytest.importorskip("numpy")
    same = voice.wav_to_float32(_wav(0.5, 16_000))
    assert same.dtype.name == "float32" and len(same) == 8_000 and abs(same).max() <= 1.0
    resampled = voice.wav_to_float32(_wav(0.5, 8_000, channels=2))
    assert len(resampled) == 8_000  # stereo 8 kHz -> mono 16 kHz


def test_message_from_typed_text_and_dictation() -> None:
    assert voice.message_from("  hola ", None) == ("hola", False)
    assert voice.message_from(None, None) == ("", False)
    audio = SimpleNamespace(getvalue=lambda: b"wav")
    dictated = SimpleNamespace(text="", audio=audio)
    assert voice.message_from(dictated, lambda b: "Necesito reemplazar la USB-2627") == (
        "Necesito reemplazar la USB-2627",
        True,
    )
    assert voice.message_from(dictated, lambda b: "") == ("", False)  # silence
    assert voice.message_from(dictated, None) == ("", False)  # voice extra not installed
    typed = SimpleNamespace(text="Busco una GPU", audio=None)
    assert voice.message_from(typed, lambda b: "x") == ("Busco una GPU", False)


def test_vocabulary_prompt_lists_catalog_parts_once() -> None:
    prompt = voice.vocabulary_prompt(["USB-2627", "E810-CQDA2", "USB-2627"])
    assert prompt.count("USB-2627") == 1 and "E810-CQDA2" in prompt
    assert voice.vocabulary_prompt([]) == ""


def test_speech_reads_plain_text_and_is_safely_embedded() -> None:
    text = "**USB-2633** — compatible; 879.00 USD.\n\n- condición `x`"
    assert voice.speech_text(text) == "USB-2633 — compatible; 879.00 USD. - condición x"
    long = "Frase uno. " * 200
    assert len(voice.speech_text(long)) <= 900 and voice.speech_text(long).endswith(".")
    tricky = '</script><script>alert(1)</script> "comillas"'
    html = voice.speak_html(tricky)
    payload = html.split("SpeechSynthesisUtterance(", 1)[1].split(");u.lang", 1)[0]
    assert json.loads(payload) == voice.speech_text(tricky)
    assert html.count("</script") == 1  # the payload cannot close the script tag
    assert "<" not in payload
