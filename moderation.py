import discord
from faster_whisper import WhisperModel
import wave, asyncio, io, re, time, scipy.signal
import numpy as np

# Initialize the Whisper model
whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")

# Initilize the bot with a list of slurs
def load_slurs():
    with open("slurs.txt", "r", encoding="utf-8") as f:
        return {
            line.strip().lower() for line in f if line.strip()
        }

SLURS = load_slurs()

# Check to receuive audio packets from users in voice channels
voice_audio = {}
voice_last_spoke = {}
transcription_lock = asyncio.Lock()

def on_voice_packet(user, data):
    if user is None or not data.pcm:
        return

    user_id = user.id

    if user_id not in voice_audio:
        voice_audio[user_id] = bytearray()

    voice_audio[user_id].extend(data.pcm)

    # Calculate the volume of this audio packet
    audio_samples = np.frombuffer(data.pcm, dtype=np.int16)

    if audio_samples.size == 0:
        return

    rms = np.sqrt(np.mean(audio_samples.astype(np.float32) ** 2))

    if rms >= 150:
        voice_last_spoke[user_id] = time.monotonic()

# Helper to transcribe each recieved audio packet
async def transcribe_voice_loop(bot):
    while True:
        await asyncio.sleep(0.2)

        if not voice_audio:
            continue

        for user_id, audio in list(voice_audio.items()):
            if not audio:
                continue

            last_spoke = voice_last_spoke.get(user_id)

            if last_spoke is None:
                continue

            silence_duration = time.monotonic() - last_spoke

            # Wait until the user has been silent for 1sec
            if silence_duration < 1.0:
                continue

            # Take the current audio and start a fresh buffer
            audio_chunk = bytes(audio)
            voice_audio[user_id] = bytearray()
            voice_last_spoke.pop(user_id, None)

            audio_samples = np.frombuffer(audio_chunk, dtype=np.int16)

            if audio_samples.size == 0:
                continue

            # Ignore extremely short audio chunks
            duration = audio_samples.size / (48000 * 2)

            if duration < 0.5:
                continue

            rms = np.sqrt(np.mean(audio_samples.astype(np.float32) ** 2))

            if rms < 150:
                continue

            print(
                f"[VOICE] User {user_id} | "
                f"duration={duration:.2f}s | "
                f"rms={rms:.0f}"
            )

            try:
                # Create an in-memory wav file
                audio_samples = np.frombuffer(
                    audio_chunk,
                    dtype=np.int16
                )

                # Make sure we have complete stereo samples
                if audio_samples.size < 2:
                    continue

                if audio_samples.size % 2 != 0:
                    audio_samples = audio_samples[:-1]

                # Discord audio is stereo: split the two channels
                stereo = audio_samples.reshape(-1, 2)

                # Convert stereo to mono
                mono = stereo.mean(axis=1).astype(np.int16)

                # Resample 48 kHz -> 16 kHz
                mono_16k = scipy.signal.resample_poly(mono, 1, 3).astype(np.int16)

                wav_buffer = io.BytesIO()

                with wave.open(wav_buffer, "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(16000)
                    wav_file.writeframes(mono_16k.tobytes())

                wav_buffer.seek(0)

                # Whisper expects a file-like object or path
                async with transcription_lock:
                    segments, info = await asyncio.to_thread(
                        whisper_model.transcribe,
                        wav_buffer,
                        language="en",
                        vad_filter=True,
                        vad_parameters={
                            "min_silence_duration_ms": 500,
                            "speech_pad_ms": 200,
                            "threshold": 0.6,
                        },
                        condition_on_previous_text=False,
                        temperature=0.0,
                        beam_size=5,
                        no_speech_threshold=0.6,
                    )

                text = " ".join(
                    segment.text.strip()
                    for segment in segments
                ).strip()

                if text:
                    username = f"User {user_id}"

                    for guild in bot.guilds:
                        member = guild.get_member(user_id)

                        if member:
                            username = member.display_name
                            break

                    print(
                        f"Transcription from {username}: {text}"
                    )

                matched_slur = next(( slur for slur in SLURS if re.search( rf"\b{re.escape(slur)}\b", text.lower() ) ), None)

                if matched_slur:
                    print(
                        f"Blocked word detected from {user_id}: "
                        f"{matched_slur}"
                    )

                    # Find the Discord member in the guild
                    for guild in bot.guilds:
                        member = guild.get_member(user_id)

                        if member:
                            # Announce in the channel
                            channel = member.voice.channel if member.voice else None

                            if channel:
                                await channel.send(
                                    f"{member.mention} has been removed from "
                                    f"voice chat for using the word '{matched_slur}'"
                                )

                                # Disconnect them from voice
                                await member.move_to(None)

                            break

            except Exception as e:
                print(
                    f"Voice transcription error for {user_id}: {e}"
                )


# Check for slurs in the message content
async def moderate_message(message):
    if message.author.bot:
        return

    message_content = message.content.lower()

    matched_slur = next((slur for slur in SLURS if slur in message_content), None)

    if matched_slur:
        print(
            f"Blocked word detected from "
            f"{message.author} in #{message.channel}: {matched_slur}"
        )

        await message.channel.send(f"@everyone Guys get a load of this guy -> {message.author.mention} he said {matched_slur}, what a loser!")

        if message.author.voice:
            await message.author.move_to(None)