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

# Mở CORS hoàn toàn để giao diện từ Vercel/Local có thể gọi tới thoải mái
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Hệ thống tự động đọc API Key từ biến môi trường bảo mật (Environment Variable)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

SILENCE_DURATION = 0.3 
print("🚀 SERVER ONLINE LITE SẴN SÀNG DEPLOY LÊN RENDER!")

def process_audio_via_groq(audio_bytes):
    """Chuyển đổi byte audio thành file WAV ảo trong RAM và gửi lên Groq API"""
    try:
        if not GROQ_API_KEY:
            print("⚠️ Cảnh báo: Chưa có GROQ_API_KEY! Hệ thống không thể gọi API.")
            return "Chưa cấu hình API Key", "API Key Error"

        client = Groq(api_key=GROQ_API_KEY)
        start_time = time.time()
        
        # Tạo file WAV ảo lưu trong RAM để tiết kiệm tài nguyên hệ thống
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)      # 16-bit
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(audio_bytes)
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        # 1. Gọi Groq Whisper bóc băng bản Large-v3 khôn nhất hiện tại (< 0.3s)
        transcription = client.audio.transcriptions.create(
            file=wav_io,
            model="whisper-large-v3",
            response_format="json"
        )
        original_text = transcription.text.strip()
        
        if not original_text or len(original_text) < 2:
            return "", ""
            
        print(f"🎤 [Groq STT] ({time.time() - start_time:.2f}s): {original_text}")

        # 2. Gọi siêu máy tính Llama 3 70B dịch thuật thời gian thực
        translate_start = time.time()
        prompt = f"""You are a professional, direct bilingual interpreter. 
        Task: Translate the text accurately between English and Vietnamese.
        Rules: Output ONLY the final translation, no explanations, no notes, no quotes.
        
        Text to translate: {original_text}"""
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-70b-8192",
            temperature=0.0,
        )
        translated_text = chat_completion.choices[0].message.content.strip()
        print(f"🤖 [Groq LLM] Dịch xong ({time.time() - translate_start:.2f}s): {translated_text}")
        
        return original_text, translated_text
    except Exception as e:
        print(f"❌ Lỗi xử lý API: {e}")
        return "Lỗi xử lý", "API Error"

async def process_audio_pipeline(audio_data, websocket: WebSocket):
    # Đẩy việc gọi API sang Thread riêng để không làm lag luồng nhận WebSocket âm thanh
    original, translated = await asyncio.to_thread(process_audio_via_groq, audio_data)
    if original:
        try:
            await websocket.send_json({
                "type": "result",
                "original": original,
                "translated": translated
            })
        except Exception as e:
            print(f"❌ Không thể gửi kết quả về Client: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Client Online đã kết nối thành công!")
    audio_buffer = bytearray()
    silence_start_time = None
    speech_start_time = None
    is_speaking = False
    
    ambient_noise = 100.0
    dynamic_threshold = 180.0
    MAX_SPEECH_DURATION = 15.0 

    try:
        while True:
            data = await websocket.receive_bytes()
            audio_array = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2)) if len(audio_array) > 0 else 0
            
            if not is_speaking:
                if rms < 400:
                    ambient_noise = (ambient_noise * 0.95) + (rms * 0.05)
                    dynamic_threshold = max(160, ambient_noise + 60)
            
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
        print("❌ Client ngắt kết nối.")
    except Exception as e:
        print(f"❌ Lỗi WebSocket: {e}")

if __name__ == '__main__':
    import uvicorn
    # 🌟 ĐỘC CHIÊU CHO RENDER: Tự động bắt đúng cổng hệ thống cấp, chạy local thì mặc định 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)