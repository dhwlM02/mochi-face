# Mochi brain

Mochi's brain runs on your Mac with Ollama. It gives Mochi conversation, a personality and memory, and it also serves Mochi's face to your phone.

## Start it

```bash
cd ~/Code/mochi-brain
chmod +x start.sh
./start.sh
```

The first run checks Ollama, downloads `llama3.2:3b` if you have no chat model yet (about 2 GB), and makes an HTTPS certificate for your Mac's Wi-Fi address. Then it prints an address like `https://192.168.1.20:8765`.

## Open it on the phone

1. Connect the phone to the same Wi-Fi as the Mac.
2. Open the printed address in Chrome.
3. Chrome says the connection isn't private, because the certificate is your Mac's own. Tap **Advanced → Proceed**. You only do this once.
4. Tap to wake Mochi and allow the camera and microphone.
5. Say **"Hey Mochi"**, then talk.

## Files

| File | What it is |
|---|---|
| `server.py` | The brain. Python standard library only, no installs. |
| `start.sh` | Checks Ollama, makes the certificate, starts the brain. |
| `index.html` | Mochi's face, the same page as GitHub Pages. |
| `memory.json` | What Mochi remembers. Created on first chat and kept private on your Mac. |

## Settings

- **Use a different model:** `MOCHI_MODEL=qwen2.5:7b ./start.sh`
- **Use a different port:** `MOCHI_PORT=9000 ./start.sh`
- **Wipe memory:** tap "Forget everything" in Mochi's ⚙ panel, or delete `memory.json`.

## How the parts fit

- **Phone (face, eyes, ears):** wake word and speech-to-text through Chrome's speech recognition, face tracking with MediaPipe, and speech through the phone's voice.
- **Mac (`server.py` + Ollama):** Mochi's personality and memory. Each reply comes back with a mood (which the face shows) and an action like `wiggle`, `nod` or `come_closer`.
- **Robot body (later):** the face passes every action to `window.mochi.onAction`, so the Android app can forward it to the ESP32 over Bluetooth.

## Notes

- Anyone on your Wi-Fi can open this address and chat with Mochi, so only run it on your home network.
- Chrome's speech recognition sends audio to Google to turn it into text. The thinking and memory stay on your Mac.
