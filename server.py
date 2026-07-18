import asyncio
import numpy as np
import os
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import wave
import io
from groq import Groq 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

# 🌟 BỘ LỌC CHỐNG SPAM MỚI
SILENCE_DURATION = 1.2  # Đợi im lặng 1.2 giây mới chốt câu (Tránh bị cắt vụn chữ)
MIN_AUDIO_LENGTH = 16000 * 2 * 0.5  # Âm thanh phải dài trên 0.5 giây mới gửi đi (lọc tiếng ho, tiếng quạt)

# Ép flush=True để Render nhả Log ra ngay lập tức
print("🚀 SERVER LITE v4 - CHỐNG SPAM API READY!", flush=True)

def process_audio_via_groq(audio_bytes):
    try:
        if not GROQ_API_KEY:
            print("⚠️ Lỗi: Chưa cấu hình GROQ_API_KEY", flush=True)
            return "Chưa cấu hình API Key", "Vui lòng thêm KEY vào Render"

        # LỌC RÁC: Nếu file âm thanh bé hơn 0.5s, bỏ qua luôn, không gọi API
        if len(audio_bytes) < MIN_AUDIO_LENGTH:
            print("💤 [Bỏ qua] Âm thanh quá ngắn, chỉ là tiếng ồn", flush=True)
            return "", ""

        client = Groq(api_key=GROQ_API_KEY)
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_bytes)
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        # Bóc băng
        start_time = time.time()
        transcription = client.audio.transcriptions.create(
            file=wav_io,
            model="whisper-large-v3",
            response_format="json"
        )
        original_text = transcription.text.strip()
        
        if not original_text or len(original_text) < 2:
            return "", ""
            
        print(f"🎤 [Groq STT] ({time.time() - start_time:.2f}s): {original_text}", flush=True)

        # Dịch thuật
        translate_start = time.time()
        prompt = f"""You are a professional, direct bilingual interpreter. 
        Translate the text accurately between English and Vietnamese.
        Rules: Output ONLY the final translation, no notes.
        Text: {original_text}"""
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",  # Model quốc dân không bị lỗi
            temperature=0.0,
        )
        translated_text = chat_completion.choices[0].message.content.strip()
        print(f"🤖 [Groq LLM] Dịch: {translated_text}", flush=True)
        
        return original_text, translated_text

    except Exception as e:
        # BẮT ĐÚNG TẬN GỐC LỖI VÀ IN LÊN RENDER
        error_msg = str(e)
        print(f"❌ Lỗi Groq API Đỏ: {error_msg}", flush=True)
        
        # Nếu bị khóa vì Spam, thông báo thẳng ra màn hình Web
        if "429" in error_msg or "Rate limit" in error_msg:
            return "Hệ thống bị khóa tạm thời do SPAM", "Đợi 1 phút rồi nói tiếp..."
            
        return "Lỗi xử lý", error_msg

async def process_audio_pipeline(audio_data, websocket: WebSocket):
    original, translated = await asyncio.to_thread(process_audio_via_groq, audio_data)
    if original:
        try:
            await websocket.send_json({
                "type": "result",
                "original": original,
                "translated": translated
            })
        except Exception as e:
            print(f"❌ Lỗi gửi WebSocket: {e}", flush=True)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Client đã kết nối!", flush=True)
    audio_buffer = bytearray()
    silence_start_time = None
    speech_start_time = None
    is_speaking = False
    ambient_noise = 100.0
    dynamic_threshold = 200.0  # Nâng mốc nhận diện lên để mic bớt nhạy với tiếng ồn nhỏ
    MAX_SPEECH_DURATION = 15.0 

    try:
        while True:
            data = await websocket.receive_bytes()
            audio_array = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2)) if len(audio_array) > 0 else 0
            
            if not is_speaking and rms < 400:
                ambient_noise = (ambient_noise * 0.95) + (rms * 0.05)
                dynamic_threshold = max(200, ambient_noise + 80)
            
            if rms > dynamic_threshold: 
                if not is_speaking:
                    is_speaking = True
                    speech_start_time = time.time()
                silence_start_time = None
                audio_buffer.extend(data)  
            else:
                if is_speaking:
                    audio_buffer.extend(data)  
                    if silence_start_time is None:
                        silence_start_time = time.time()
            
            if is_speaking:
                current_duration = time.time() - speech_start_time
                if (silence_start_time and (time.time() - silence_start_time > SILENCE_DURATION)) or (current_duration > MAX_SPEECH_DURATION):
                    audio_data_to_process = bytes(audio_buffer)
                    audio_buffer.clear()
                    is_speaking = False
                    silence_start_time = None
                    speech_start_time = None
                    asyncio.create_task(process_audio_pipeline(audio_data_to_process, websocket))
    except WebSocketDisconnect:
        print("❌ Client ngắt kết nối.", flush=True)
    except Exception as e:
        print(f"❌ Lỗi Endpoint: {e}", flush=True)

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
