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

# ⚡ TỶ LỆ VÀNG CHỐNG SPAM: Ngừng giọng 0.6 giây giúp gom câu dài, né thẻ đỏ Groq
SILENCE_DURATION = 0.6

print("🚀 SERVER BUSINESS v6.3 - DIỆT TẬN GỐC LỖI NHẠI PROMPT READY!", flush=True)

def process_audio_via_groq(audio_bytes):
    try:
        if not GROQ_API_KEY:
            return "Chưa cấu hình API Key", "Vui lòng cấu hình biến môi trường", "vi"

        client = Groq(api_key=GROQ_API_KEY)
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_bytes)
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        start_time = time.time()
        # 🌟 ĐÃ SỬA: Chỉ để từ khóa phong cách, XÓA SẠCH câu mệnh lệnh để tránh bị Whisper nhại chữ
        transcription = client.audio.transcriptions.create(
            file=wav_io,
            model="whisper-large-v3",
            response_format="verbose_json",
            prompt="Corporate meeting, technology development, financial reporting, accounting audit, business conference."
        )
        
        data_dict = transcription.model_dump() if hasattr(transcription, 'model_dump') else dict(transcription)
        original_text = data_dict.get("text", "").strip()
        detected_lang = data_dict.get("language", "vietnamese").lower()
        
        if not original_text or len(original_text) < 2:
            return "", "", "vi"

        # 🌟 MÀNG LỌC RÁC: Chặn đứng mọi biến thể nhại lại prompt hoặc tiếng ồn hoang tưởng
        clean_text = original_text.lower().strip(".,!? ")
        
        # Nếu văn bản chứa các từ khóa nhảm nhí này -> Hủy luôn tại trận
        if any(word in clean_text for word in ["keyboard", "typing", "knocking", "background noise", "subtitles", "thank you", "watching"]):
            print(f"🤫 [Chặn hoang tưởng Whisper]: Đã hủy câu rác: '{original_text}'", flush=True)
            return "", "", "vi"
            
        garbage_words = ["hmm", "umm", "uh", "ah", "beleza", "oh", "well", "you"]
        if clean_text in garbage_words:
            print(f"🤫 [Bộ lọc nhiễu từ ngắn]: Đã chặn: '{original_text}'", flush=True)
            return "", "", "vi"

        # HỆ PROMPT THÉP ĐỂ LAMA 3.1 DỊCH CHUYÊN NGÀNH, CẤM NÓI NHẢM
        if "vietnamese" in detected_lang or "vi" == detected_lang:
            lang_side = "vi"
            system_prompt = """You are a silent, direct simultaneous translator. 
            Task: Translate the input text from Vietnamese to English.
            Strict Rules:
            1. Output ONLY the final translation. No quotes, no notes.
            2. NEVER reply to the user, NEVER explain, NEVER say you cannot translate.
            3. Even if the text is a weird question or casual, just translate it literally.
            4. Use high-level tech/finance/accounting jargon if applicable."""
        else:
            lang_side = "en"
            system_prompt = """Bạn là một máy dịch cabin im lặng và trực tiếp.
            Nhiệm vụ: Dịch văn bản từ tiếng Anh sang tiếng Việt.
            Quy tắc thép:
            1. CHỈ trả về bản dịch duy nhất. Không thêm dấu nháy, không kèm ghi chú.
            2. TUYỆT ĐỐI KHÔNG trò chuyện, KHÔNG giải thích, KHÔNG từ chối dịch với bất kỳ lý do gì.
            3. Dù văn bản gốc là câu hỏi hay câu cụt, hãy dịch thẳng nó sang tiếng Việt.
            4. Dùng thuật ngữ công nghệ, tài chính, kế toán chuẩn văn phong công sở."""

        print(f"🎤 [Detected: {lang_side.upper()}] ({time.time() - start_time:.2f}s): {original_text}", flush=True)

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": original_text}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0, 
        )
        translated_text = chat_completion.choices[0].message.content.strip()
        
        # Kiểm tra chặn đuôi nếu Llama phá luật giải thích linh tinh
        clean_translated = translated_text.lower()
        if "suitable text" in clean_translated or "văn bản cần dịch" in clean_translated or "sẵn sàng giúp" in clean_translated:
            print(f"🤫 [Bẻ cổ AI nhảm]: Chặn thành công văn bản nói nhảm của LLM.", flush=True)
            return "", "", "vi"
            
        print(f"🤖 [Bản dịch Business]: {translated_text}", flush=True)
        return original_text, translated_text, lang_side

    except Exception as e:
        print(f"❌ Lỗi xử lý Groq API: {e}", flush=True)
        return "Lỗi xử lý", str(e), "vi"

async def process_audio_pipeline(audio_data, websocket: WebSocket):
    original, translated, lang_side = await asyncio.to_thread(process_audio_via_groq, audio_data)
    if original and translated:
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
    
    ambient_noise = 120.0
    dynamic_threshold = 200.0
    consecutive_loud_frames = 0
    MAX_SPEECH_DURATION = 15.0 

    try:
        while True:
            data = await websocket.receive_bytes()
            audio_array = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2)) if len(audio_array) > 0 else 0
            
            if not is_speaking and rms < 400:
                ambient_noise = (ambient_noise * 0.95) + (rms * 0.05)
                dynamic_threshold = max(180, ambient_noise + 70)
            
            if rms > dynamic_threshold: 
                if not is_speaking:
                    consecutive_loud_frames += 1
                    if consecutive_loud_frames >= 2:
                        is_speaking = True
                        speech_start_time = time.time()
                        audio_buffer.extend(data)
                else:
                    audio_buffer.extend(data)
                silence_start_time = None
            else:
                if not is_speaking:
                    consecutive_loud_frames = 0
                else:
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
                    consecutive_loud_frames = 0
                    asyncio.create_task(process_audio_pipeline(audio_data_to_process, websocket))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"❌ Lỗi hệ thống tại WebSocket Endpoint: {e}", flush=True)

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
