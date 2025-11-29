import asyncio
import json
from pathlib import Path
import datetime
import io
import wave
import logging 
from logging.handlers import RotatingFileHandler
import re

from fastapi import FastAPI, WebSocket
import uvicorn

import numpy as np


from recorder import ChunkRecorder
from transcriber import Transcriber
#from transcriber.transcriber import Transcriber

# ---------------------------------------------------
# Config & paths  (always use HOME, not cwd)
# ---------------------------------------------------
CONFIG_DIR = Path.home() / ".echomind"
CONFIG_PATH = CONFIG_DIR / "config.json"
LOGS_DIR = CONFIG_DIR / "logs"
TRANSCRIPT_LOGS_DIR = CONFIG_DIR / ".transcript.json"


def load_config():
    # Always ensure base dirs exist
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        default = {
            "chunk_duration": 2,
            "control_port": 8766,
            "websocket_port": 8765,
            "openai_api_key": "",  
            "log_level": "info",
            "capture_system_audio": True,
            "capture_microphone": True,
            "input_device_index": None,
        }
        CONFIG_PATH.write_text(json.dumps(default, indent=2))

    return json.loads(CONFIG_PATH.read_text())


config = load_config()
print("Loaded config:", config)

# ---------------------------------------------------
# Logging
# ---------------------------------------------------
# main log file
log_file = LOGS_DIR / "echomind.log"

logger = logging.getLogger("EchoMind")
logger.setLevel(getattr(logging, config.get("log_level", "info").upper(), logging.INFO))

handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
logger.addHandler(handler)

if not TRANSCRIPT_LOGS_DIR.exists():
    TRANSCRIPT_LOGS_DIR.parent.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_LOGS_DIR.write_text(json.dumps({"junk": ""}))



handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
logger.addHandler(handler)

logger.info("EchoMind service starting...")

# ---------------------------------------------------
# FastAPI app & globals
# ---------------------------------------------------
app = FastAPI()

recorder = ChunkRecorder(
    chunk_seconds=config.get("chunk_duration", 1),
    device_index=config.get("input_device_index"),
    capture_system_audio=config.get("capture_system_audio", True),
    capture_microphone=config.get("capture_microphone", True),
)

transcriber = Transcriber(
    api_key=config.get("openai_api_key") or None,
    logs_path=TRANSCRIPT_LOGS_DIR,
)

clients = set()
running = False
transcription_task: asyncio.Task | None = None


# ---------------------------------------------------
# Audio helpers
# ---------------------------------------------------
def wav_to_samples(wav_bytes: bytes) -> np.ndarray:
    """Convert WAV bytes to float64 numpy array."""
    bio = io.BytesIO(wav_bytes)
    with wave.open(bio, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float64)


def calculate_rms(wav_bytes: bytes) -> float:
    samples = wav_to_samples(wav_bytes)
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples ** 2)))


def is_silence(
    wav_bytes: bytes,
    rms_threshold: float = 900,
    peak_threshold: float = 2500,
) -> bool:
    """
    Return True if this chunk is essentially silence/background noise.
    Thresholds are intentionally conservative to avoid random junk.
    """
    try:
        samples = wav_to_samples(wav_bytes)
        if len(samples) == 0:
            return True

        rms = float(np.sqrt(np.mean(samples ** 2)))
        peak = float(np.max(np.abs(samples)))
        return (rms < rms_threshold and peak < peak_threshold)
    except Exception as e:
        logger.error(f"Silence detection error: {e}")
        return True


# ---------------------------------------------------
# Text helpers
# ---------------------------------------------------
def looks_like_noise(text: str) -> bool:
    """
    Heuristic to drop obvious garbage like "Kijl." / "Nevi." etc.
    - Very short strings
    - Single 'word' with no vowels
    """
    t = text.strip()
    if not t:
        return True

    # Very short
    if len(t) <= 2:
        return True

    words = t.split()
    if len(words) == 1:
        core = re.sub(r"[^a-zA-Z]", "", words[0]).lower()
        if len(core) >= 3:
            vowels = sum(1 for c in core if c in "aeiou")
            if vowels == 0:
                return True

    return False


# ---------------------------------------------------
# Main transcription loop
#   NOTE: all blocking audio work happens in a thread via run_in_executor,
#   so FastAPI's event loop stays responsive even when there's silence.
# ---------------------------------------------------

async def transcription_loop():
    global running

    loop = asyncio.get_event_loop()

    # Ensure recorder is fresh
    if recorder.running:
        recorder.stop()
        await asyncio.sleep(0.2)

    recorder.start()
    logger.info("Transcription loop started")

    try:
        while running:
            # This call blocks in a thread, NOT the event loop
            chunk = await loop.run_in_executor(None, recorder.get_next_chunk)

            if not running:
                break

            if not chunk:
                # No chunk ready yet (e.g., silence / no frames).
                # Yield back to the event loop briefly.
                await asyncio.sleep(0.01)
                continue

            sys_bytes = chunk.get("system")
            mic_bytes = chunk.get("mic")

            sys_rms = calculate_rms(sys_bytes) if sys_bytes else 0.0
            mic_rms = calculate_rms(mic_bytes) if mic_bytes else 0.0

            active_sources = []

            if sys_bytes and mic_bytes:
                margin = 150.0

                if sys_rms >= mic_rms + margin and sys_rms > 600:
                    active_sources = [("system", sys_bytes)]
                elif mic_rms >= sys_rms + margin and mic_rms > 570:
                    active_sources = [("mic", mic_bytes)]
                else:
                    if sys_rms > 600:
                        active_sources = [("system", sys_bytes)]
                    else:
                        # both too quiet
                        continue

            elif sys_bytes:
                if sys_rms > 600:
                    active_sources = [("system", sys_bytes)]
                else:
                    continue

            elif mic_bytes:
                if mic_rms > 570:
                    active_sources = [("mic", mic_bytes)]
                else:
                    continue
            else:
                continue

            for source, wav_bytes in active_sources:
                if is_silence(wav_bytes):
                    continue

                # Run Whisper-style transcription in a thread
                text = await loop.run_in_executor(
                    None, transcriber.transcribe_bytes, wav_bytes
                )

                if not text or looks_like_noise(text):
                    continue

                payload = {
                    "text": text,
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "source": source,  # "mic" or "system"
                }

                logger.info(f"[{source.upper()}] {text}")

                # Broadcast to websocket clients
                disconnected = []
                for ws in list(clients):
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        disconnected.append(ws)

                for ws in disconnected:
                    clients.discard(ws)

    except asyncio.CancelledError:
        logger.info("Transcription loop cancelled")
    except Exception as e:
        logger.error(f"Error in transcription loop: {e}")
    finally:
        recorder.stop()
        logger.info("Transcription loop stopped")


# ---------------------------------------------------
# HTTP API
# ---------------------------------------------------
@app.post("/start")
async def start_service():
    global running, transcription_task

    if running:
        return {"status": "already_running"}

    running = True
    transcription_task = asyncio.create_task(transcription_loop())
    logger.info("Service started via API")
    return {"status": "started"}
    


@app.post("/stop")
async def stop_service():
    global running, transcription_task

    if not running:
        return {"status": "already_stopped"}

    running = False
    recorder.stop()
    if transcription_task:
        transcription_task.cancel()
        transcription_task = None

    logger.info("Service stopped via API")
    return {"status": "stopped"}


@app.post("/restart")
async def restart_service():
    await stop_service()
    return await start_service()


@app.get("/status")
def status():
    return {
        "running": running,
        "clients": len(clients),
        "control_port": config.get("control_port", 8766),
        "websocket_port": config.get("websocket_port", 8765),
    }


# ---------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(clients)}")

    try:
        while True:
            # Keep connection alive; we don't need incoming messages.
            await websocket.receive_text()
    except Exception:
        clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(clients)}")


# ---------------------------------------------------
# Entrypoint
# ---------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "service:app",
        host="0.0.0.0",
        port=config.get("control_port", 8766),
        reload=False,
    )



