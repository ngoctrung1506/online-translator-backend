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
# ⚡ KHÔI PHỤC TỐC ĐỘ 0.3S SIÊU NHẠY THEO YÊU CẦU
SILENCE_DURATION = 0.3 

print("🚀 SERVER BUSINESS V6 - TECH/FINANCE/ACCOUNTING READY!", flush=True)

def process_audio_via_groq(audio_bytes):
    try:
        if not GROQ_API_KEY:
            return "Chưa cấu hình API Key", "API Key Error", "vi"

        client = Groq(api_key=GROQ_API_KEY)
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_bytes)
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        # 1. Gọi Whisper lấy text và ngôn ngữ nhận diện
        start_time = time.time()
        transcription = client.audio.transcriptions.create(
            file=wav_io,
            model="whisper-large-v3",
            response_format="verbose_json"
        )
        
        data_dict = transcription.model_dump() if hasattr(transcription, 'model_dump') else dict(transcription)
        original_text = data_dict.get("text", "").strip()
        detected_lang = data_dict.get("language", "vietnamese").lower()
        
        if not original_text or len(original_text) < 2:
            return "", "", "vi"

        # 🌟 2. HỆ CONTEXT CHUYÊN NGÀNH CAO CẤP (TECH - FINANCE - ACCOUNTING)
        if "vietnamese" in detected_lang or "vi" == detected_lang:
            lang_side = "vi"
            system_prompt = """You are an elite, corporate-level simultaneous interpreter specializing in Technology, Finance, Accounting, and Business.
            Task: Translate the Vietnamese text into professional corporate English.
            Context Constraints:
            - Use accurate industry jargon (e.g., 'Báo cáo tài chính' -> 'Financial Statements', 'Doanh thu' -> 'Revenue', 'Khấu hao' -> 'Depreciation/Amortization', 'Triển khai hệ thống' -> 'System Deployment/Rollout').
            - Maintain a formal, high-level corporate tone suitable for board meetings.
            - Output ONLY the final English translation, no notes, no quotes, no explanations."""
        else:
            lang_side = "en"
            system_prompt = """Bạn là một thông dịch viên cabin cấp cao chuyên nghiệp, chuyên ngành Công nghệ thông tin, Tài chính, Kế toán và Vận hành doanh nghiệp.
            Nhiệm vụ: Dịch văn bản tiếng Anh sang tiếng Việt chuẩn văn phong công sở và giới học thuật doanh nghiệp.
            Yêu cầu bối cảnh:
            - Dịch chuẩn các thuật ngữ chuyên ngành (e.g., 'EBITDA' -> 'Lợi nhuận trước thuế, lãi vay và khấu hao', 'Balance Sheet' -> 'Bảng cân đối kế toán', 'Microservices' -> 'Kiến trúc vi dịch vụ', 'Cash Flow' -> 'Dòng tiền').
            - Văn phong trang trọng, gãy gọn, dùng trong cuộc họp cấp quản lý.
            - CHỈ trả về bản dịch tiếng Việt duy nhất, không kèm giải thích, không để trong dấu nháy."""

        print(f"🎤 [Detected: {lang_side.upper()}] ({time.time() - start_time:.2f}s): {original_text}", flush=True)

        # 3. Gọi Llama 3.1 xử lý dịch thuật chuyên sâu
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": original_text}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0, # Ép độ chính xác cao nhất, không sáng tạo linh tinh
        )
        translated_text = chat_completion.choices[0].message.content.strip()
        print(f"🤖 [Business Translation]: {translated_text}", flush=True)
        
        return original_text, translated_text, lang_side

    except Exception as e:
        print(f"❌ Lỗi Groq API: {e}", flush=True)
        return "Lỗi xử lý", str(e), "vi"

async def process_audio_pipeline(audio_data, websocket: WebSocket):
    original, translated, lang_side = await asyncio.to_thread(process_audio_via_groq, audio_data)
    if original:
        try:
            await websocket.send_json({
                "type": "result",
                "original": original,
                "translated": translated,
                "lang": lang_side
            })
        except Exception as e:
            print(f"❌ Lỗi gửi WebSocket: {e}", flush=True)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    audio_buffer = bytearray()
    silence_start_time = None
    speech_start_time = None
    is_speaking = False
    
    # 🌟 KHÔI PHỤC BỘ LỌC KHỬ ỒN ĐỘNG (DYNAMIC VAD) CỰC CHUẨN
    ambient_noise = 120.0
    dynamic_threshold = 200.0
    MAX_SPEECH_DURATION = 15.0 

    try:
        while True:
            data = await websocket.receive_bytes()
            audio_array = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2)) if len(audio_array) > 0 else 0
            
            # Cập nhật nền nhiễu môi trường khi không nói (tiếng quạt, tiếng thở nhỏ)
            if not is_speaking and rms < 400:
                ambient_noise = (ambient_noise * 0.95) + (rms * 0.05)
                dynamic_threshold = max(180, ambient_noise + 70) # Tự điều chỉnh khi phòng ồn
            
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
        pass
    except Exception as e:
        print(f"❌ Lỗi Endpoint: {e}", flush=True)

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
