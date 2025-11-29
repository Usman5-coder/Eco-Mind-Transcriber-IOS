import sounddevice as sd
import numpy as np
import queue
import wave
import io

#import tkinter as tk
#from tkinter import messagebox




class ChunkRecorder:
    """
    Records from an Aggregate Device that has:
      - BlackHole (system audio) as channels 0–1
      - Microphone as channel 2 (mono) or 2–3 (stereo)

    Provides get_next_chunk() which returns separate WAV byte streams
    for 'system' and 'mic'.
    """

    def __init__(
        self,
        chunk_seconds=1,
        samplerate=48000,
        dtype="int16",
        device_index=None,
        capture_system_audio=True,
        capture_microphone=True,
    ):
        self.chunk_seconds = chunk_seconds
        self.samplerate = samplerate
        self.dtype = dtype
        self.capture_system_audio = capture_system_audio
        self.capture_microphone = capture_microphone

        self.q = queue.Queue()
        self.running = False
        self.stream = None

        # Choose device
        self.device = device_index
        if self.device is None:
            self.device = sd.default.device[0]  # default input

        info = sd.query_devices(self.device)
        self.channels = info["max_input_channels"]
        print(f"Using device index {self.device} ({info['name']}) with {self.channels} channels")
        #messagebox.showinfo("Recorder !!", f"Using device index {self.device} ({info['name']}) with {self.channels} channels")
        

        if self.channels < 2 and self.capture_system_audio:
            print("WARNING: Less than 2 input channels; system audio capture may not work as expected.")
            
        if self.channels < 3 and self.capture_microphone:
            print("WARNING: Less than 3 input channels; mic capture may not work as expected.")
            

    # -------------------------------------------------
    # sounddevice callback
    # -------------------------------------------------
    def _callback(self, indata, frames, time_info, status):
        if status:
            print("Recorder status:", status)
        # Push raw frames into queue
        self.q.put(indata.copy())

    # -------------------------------------------------
    # Start/stop
    # -------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True

        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._callback,
            device=self.device,
        )
        self.stream.start()
        print("Recorder started.")

    def stop(self):
        if not self.running:
            return
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.running = False
        print("Recorder stopped.")

    # -------------------------------------------------
    # Chunk retrieval (blocking, used in worker thread)
    # -------------------------------------------------
    def get_next_chunk(self):
        """
        Blocking method (intended for use in a thread) that collects enough
        frames for one chunk and returns a dict:

          {
            "system": <wav_bytes>  # if capture_system_audio and available
            "mic":    <wav_bytes>  # if capture_microphone and available
          }

        Returns None if no frames could be collected (e.g. on shutdown).
        """
        if not self.running:
            return None

        frames_needed = int(self.samplerate * self.chunk_seconds)
        frames = []
        collected = 0

        # We'll keep trying until we collect enough frames or recorder stops
        while collected < frames_needed and self.running:
            try:
                # Short timeout so thread can notice stop requests
                data = self.q.get(timeout=0.2)
            except queue.Empty:
                if not self.running:
                    return None
                # No new audio yet; keep waiting until chunk is filled
                continue

            frames.append(data)
            collected += data.shape[0]

        if not frames:
            return None

        audio = np.concatenate(frames, axis=0)  # shape: (samples, channels)
        chunk_dict = {}

        # System audio (BlackHole) = channels 0 & 1
        if self.capture_system_audio and audio.shape[1] >= 2:
            system_audio = audio[:, :2]
            chunk_dict["system"] = self.to_wav(system_audio)

        # Mic = channel 2 (mono) or 2–3
        if self.capture_microphone and audio.shape[1] >= 3:
            mic_audio = audio[:, 2:3]
            chunk_dict["mic"] = self.to_wav(mic_audio)

        if chunk_dict:
            return chunk_dict

        return None

    # -------------------------------------------------
    # WAV conversion
    # -------------------------------------------------
    def to_wav(self, samples: np.ndarray) -> bytes:
        """
        Convert numpy samples (samples x channels) to WAV bytes.
        """
        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(samples.shape[1])
            wf.setsampwidth(np.dtype(self.dtype).itemsize)
            wf.setframerate(self.samplerate)
            wf.writeframes(samples.astype(self.dtype).tobytes())
        return bio.getvalue()








# import sounddevice as sd
# import numpy as np
# import queue
# import wave
# import io


# class ChunkRecorder:
#     """
#     Records from an Aggregate Device that has:
#       - BlackHole (system audio) as channels 0–1
#       - Microphone as channel 2 (mono) or 2–3 (stereo)

#     Splits each chunk into separate WAV byte streams for 'system' and 'mic'.
#     """

#     def __init__(
#         self,
#         chunk_seconds=1,
#         samplerate=48000,
#         dtype="int16",
#         device_index=None,
#         capture_system_audio=True,
#         capture_microphone=True,
#     ):
#         self.chunk_seconds = chunk_seconds
#         self.samplerate = samplerate
#         self.dtype = dtype
#         self.capture_system_audio = capture_system_audio
#         self.capture_microphone = capture_microphone

#         self.q = queue.Queue()
#         self.running = False
#         self.stream = None

#         # Choose device
#         self.device = device_index
#         if self.device is None:
#             self.device = sd.default.device[0]  # default input

#         info = sd.query_devices(self.device)
#         self.channels = info["max_input_channels"]
#         print(f"Using device index {self.device} ({info['name']}) with {self.channels} channels")

#         if self.channels < 2 and self.capture_system_audio:
#             print("WARNING: Less than 2 input channels; system audio capture may not work as expected.")
#         if self.channels < 3 and self.capture_microphone:
#             print("WARNING: Less than 3 input channels; mic capture may not work as expected.")

#     def _callback(self, indata, frames, time_info, status):
#         if status:
#             print("Recorder status:", status)
#         self.q.put(indata.copy())

    
#     def start(self):
#         if self.running:
#             return
#         self.running = True

#         self.stream = sd.InputStream(
#             samplerate=self.samplerate,
#             channels=self.channels,
#             dtype=self.dtype,
#             callback=self._callback,
#             device=self.device,
#         )
#         self.stream.start()
#         print("Recorder started.")

#     def stop(self):
#         if not self.running:
#             return
#         if self.stream is not None:
#             self.stream.stop()
#             self.stream.close()
#             self.stream = None
#         self.running = False
#         print("Recorder stopped.")

#     def chunks(self):
#         """
#         Generator that yields dicts:
#           {
#             "system": <wav_bytes>  # if capture_system_audio and available
#             "mic":    <wav_bytes>  # if capture_microphone and available
#           }
#         """
#         frames_needed = int(self.samplerate * self.chunk_seconds)

#         while self.running:
#             frames = []
#             collected = 0

#             while collected < frames_needed and self.running:
#                 try:
#                     data = self.q.get(timeout=3)
#                 except queue.Empty:
#                     break
#                 frames.append(data)
#                 collected += data.shape[0]

#             if not frames:
#                 continue

#             audio = np.concatenate(frames, axis=0)  # shape: (samples, channels)
#             chunk_dict = {}

#             # System audio (BlackHole) = channels 0 & 1
#             if self.capture_system_audio and audio.shape[1] >= 2:
#                 system_audio = audio[:, :2]
#                 chunk_dict["system"] = self.to_wav(system_audio)

#             # Mic = channel 2 (mono)
#             if self.capture_microphone and audio.shape[1] >= 3:
#                 mic_audio = audio[:, 2:3]
#                 chunk_dict["mic"] = self.to_wav(mic_audio)

#             if chunk_dict:
#                 yield chunk_dict

#     def to_wav(self, samples: np.ndarray) -> bytes:
#         """
#         Convert numpy samples (samples x channels) to WAV bytes.
#         """
#         bio = io.BytesIO()
#         with wave.open(bio, "wb") as wf:
#             wf.setnchannels(samples.shape[1])
#             wf.setsampwidth(np.dtype(self.dtype).itemsize)
#             wf.setframerate(self.samplerate)
#             wf.writeframes(samples.astype(self.dtype).tobytes())
#         return bio.getvalue()