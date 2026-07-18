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

# Mở CORS hoàn toàn cho phép giao diện Vercel/Local kết nối tới
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tự động đọc API Key bảo mật từ biến môi trường của Render
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

# ⚡ TỐC ĐỘ 0.3S SIÊU NHẠY: Đợi ngừng giọng 0.3 giây là chốt câu đi dịch ngay
SILENCE_DURATION = 0.6 

print("🚀 SERVER BUSINESS v6.2 - CHUYÊN GIA DỊCH CABIN CHÍNH THỨC SẴN SÀNG!", flush=True)

def process_audio_via_groq(audio_bytes):
    """Giai đoạn xử lý lõi: Chuyển đổi âm thanh ảo trên RAM, gọi Whisper và Llama Chuyên ngành"""
    try:
        if not GROQ_API_KEY:
            print("⚠️ Lỗi hạ tầng: Chưa cấu hình biến GROQ_API_KEY trên Render!", flush=True)
            return "Chưa cấu hình API Key", "Vui lòng kiểm tra lại Render Config Variables", "vi"

        client = Groq(api_key=GROQ_API_KEY)
        
        # 1. Tạo file WAV ảo lưu trực tiếp trên RAM để tối ưu tốc độ cho Render Free
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)      # 16-bit
            wav_file.setframerate(16000)  # 16kHz chuẩn cho mô hình nhận diện
            wav_file.writeframes(audio_bytes)
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        # 2. Gọi Whisper Large-V3 bóc băng + Ép Prompt chặn hoang tưởng âm thanh ma
        start_time = time.time()
        transcription = client.audio.transcriptions.create(
            file=wav_io,
            model="whisper-large-v3",
            response_format="verbose_json",
            prompt="Corporate meeting room, tech talk, financial statements. Ignore background keyboard typing, desk knocking, clicks, and silence."
        )
        
        data_dict = transcription.model_dump() if hasattr(transcription, 'model_dump') else dict(transcription)
        original_text = data_dict.get("text", "").strip()
        detected_lang = data_dict.get("language", "vietnamese").lower()
        
        if not original_text or len(original_text) < 2:
            return "", "", "vi"

        # 🌟 BỘ LỌC RÁC ĐẦU VÀO: Diệt các từ vô nghĩa do Whisper nghe nhầm tiếng gõ bàn hoặc ho
        clean_text = original_text.lower().strip(".,!? ")
        garbage_words = [
            "thank you", "thank you for watching", "thanks", "you", "implied", 
            "subtitles by", "hmm", "umm", "uh", "ah", "beleza", "oh", "well"
        ]
        if clean_text in garbage_words or len(clean_text) <= 2:
            print(f"🤫 [Bộ lọc nhiễu]: Đã gạt xích âm thanh rác: '{original_text}'", flush=True)
            return "", "", "vi"

        # 🌟 HỆ PROMPT THÉP DÀNH CHO DOANH NGHIỆP - ÉP DỊCH CHÉO SONG NGỮ CẤM AI NÓI NHẢM
        if "vietnamese" in detected_lang or "vi" == detected_lang:
            lang_side = "vi"  # Người nói tiếng Việt -> Ép dịch sang Tiếng Anh
            system_prompt = """You are a silent, direct simultaneous translator. 
            Task: Translate the input text from Vietnamese to English.
            
            Strict Rules:
            1. Output ONLY the final translation. No quotes, no notes.
            2. NEVER reply to the user, NEVER explain, NEVER say you cannot translate.
            3. Even if the text is a weird question, incomplete, or casual, just translate it literally.
            4. If the text contains technical, financial, or accounting terms, use professional corporate jargon."""
        else:
            lang_side = "en"  # Người nói tiếng Anh -> Ép dịch sang Tiếng Việt
            system_prompt = """Bạn là một máy dịch cabin im lặng và trực tiếp.
            Nhiệm vụ: Dịch văn bản từ tiếng Anh sang tiếng Việt.
            
            Quy tắc thép:
            1. CHỈ trả về bản dịch duy nhất. Không thêm dấu nháy, không kèm ghi chú.
            2. TUYỆT ĐỐI KHÔNG trò chuyện, KHÔNG giải thích, KHÔNG từ chối dịch với bất kỳ lý do gì.
            3. Dù văn bản gốc là câu hỏi, câu cụt hay câu vô nghĩa, hãy dịch thẳng nó sang tiếng Việt.
            4. Nếu văn bản chứa thuật ngữ công nghệ, tài chính, kế toán, hãy dùng từ ngữ chuyên ngành chuẩn công sở."""

        print(f"🎤 [Detected: {lang_side.upper()}] ({time.time() - start_time:.2f}s): {original_text}", flush=True)

        # 3. Gọi Llama 3.1 8B dịch thuật siêu tốc với độ chính xác cao nhất (temp=0.0)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": original_text}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0, 
        )
        translated_text = chat_completion.choices[0].message.content.strip()
        
        # 🌟 BỘ LỌC CHẶN ĐUÔI: Nếu AI phá luật cố tình phân trần giải thích dài dòng, tự hủy câu đó luôn
        clean_translated = translated_text.lower()
        if "suitable text" in clean_translated or "văn bản cần dịch" in clean_translated or "sẵn sàng giúp" in clean_translated:
            print(f"🤫 [Bẻ cổ AI nhảm]: Phát hiện AI giải thích linh tinh, đã chủ động chặn hiển thị.", flush=True)
            return "", "", "vi"
            
        print(f"🤖 [Bản dịch Business]: {translated_text}", flush=True)
        return original_text, translated_text, lang_side

    except Exception as e:
        print(f"❌ Lỗi xử lý Groq API: {e}", flush=True)
        return "Lỗi xử lý", str(e), "vi"

async def process_audio_pipeline(audio_data, websocket: WebSocket):
    """Đẩy luồng gọi API sang Thread độc lập để tránh làm lag luồng nhận WebSocket"""
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
            print(f"❌ Lỗi gửi tín hiệu WebSocket về Client: {e}", flush=True)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Cổng kết nối âm thanh liên tục tích hợp bộ lọc khử ồn động (Dynamic VAD) và chống nhiễu xung"""
    await websocket.accept()
    print("✅ Một thiết bị Client vừa kết nối vào phòng họp thành công!", flush=True)
    audio_buffer = bytearray()
    silence_start_time = None
    speech_start_time = None
    is_speaking = False
    
    # Biến phục vụ thuật toán lọc nhiễu phòng họp
    ambient_noise = 120.0
    dynamic_threshold = 200.0
    consecutive_loud_frames = 0  # Đếm số khung âm thanh lớn liên tục để loại bỏ tiếng cạch bàn đơn lẻ
    MAX_SPEECH_DURATION = 15.0 

    try:
        while True:
            data = await websocket.receive_bytes()
            audio_array = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2)) if len(audio_array) > 0 else 0
            
            # Cập nhật tiếng ồn nền thông minh khi phòng đang im lặng
            if not is_speaking and rms < 400:
                ambient_noise = (ambient_noise * 0.95) + (rms * 0.05)
                dynamic_threshold = max(180, ambient_noise + 70)
            
            # Bắt tín hiệu âm lượng vượt ngưỡng
            if rms > dynamic_threshold: 
                if not is_speaking:
                    # 🌟 BỘ LỌC CHỐNG NHIỄU XUNG: Phải to liên tục ít nhất 2 khung hình (~0.25s) mới mở Mic thu âm
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
                    consecutive_loud_frames = 0  # Reset ngay nếu chỉ là tiếng động nổ ra chớp nhoáng
                else:
                    audio_buffer.extend(data)  
                    if silence_start_time is None:
                        silence_start_time = time.time()
            
            # Kiểm tra điều kiện cắt câu (khi ngừng nói 0.3s hoặc nói quá dài 15s)
            if is_speaking:
                current_duration = time.time() - speech_start_time
                if (silence_start_time and (time.time() - silence_start_time > SILENCE_DURATION)) or (current_duration > MAX_SPEECH_DURATION):
                    audio_data_to_process = bytes(audio_buffer)
                    audio_buffer.clear()
                    is_speaking = False
                    silence_start_time = None
                    speech_start_time = None
                    consecutive_loud_frames = 0
                    # Kích hoạt tiến trình dịch ngầm để giải phóng luồng micro ngay lập tức
                    asyncio.create_task(process_audio_pipeline(audio_data_to_process, websocket))
    except WebSocketDisconnect:
        print("❌ Client đã ngắt kết nối khỏi phòng dịch.", flush=True)
    except Exception as e:
        print(f"❌ Lỗi hệ thống tại WebSocket Endpoint: {e}", flush=True)

if __name__ == '__main__':
    import uvicorn
    # TỰ ĐỘNG THÍCH ỨNG: Chạy local dùng cổng 8000, lên Render tự động nhận cổng của đám mây cấp
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
