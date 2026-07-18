import asyncio
import numpy as np
import requests
import time
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import mlx_whisper  

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MLX_MODEL_PATH = "mlx-community/whisper-medium-mlx"
OLLAMA_URL = "http://localhost:11434/api/generate"

# 🌟 CẢI TIẾN 4: Kéo dài nhịp cắt lên 0.8 giây để bắt trọn câu, tránh băm vụn ngữ pháp
SILENCE_DURATION = 0.8 

gpu_lock = asyncio.Lock()

print("🚀 Đang kích hoạt bộ não MLX Whisper Medium trên GPU M4...", flush=True)
try:
    dummy_audio = np.zeros(16000, dtype=np.float32)
    mlx_whisper.transcribe(dummy_audio, path_or_hf_repo=MLX_MODEL_PATH)
    print("✅ ĐÃ NẠP MODEL MLX MEDIUM THÀNH CÔNG VÀO GPU/RAM! HỆ THỐNG SẴN SÀNG.", flush=True)
except Exception as e:
    print(f"❌ THẤT BẠI KHI KHỞI ĐỘNG MODEL: {e}", flush=True)

def is_garbage_or_foreign(text):
    clean = text.lower().strip(".,!? ")
    garbage_words = [
        "thank you", "thank you.", "thanks", "you", "subtitles", 
        "hmm", "umm", "uh", "ah", "oh", "well", "beleza", "implied", "chau", "chau."
    ]
    if clean in garbage_words or len(clean) <= 2:
        return True
    return False

def double_check_language(text, detected_lang):
    text_lower = text.lower()
    vi_chars = set("àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệđìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ")
    if detected_lang == 'vi':
        has_vi_accent = any(char in vi_chars for char in text_lower)
        en_keywords = ['is', 'that', 'what', 'you', 'it', 'was', 'to', 'the', 'how', 'about', 'of', 'good', 'course', 'luck', 'great', 'busy', 'project', 'hot', 'running', 'hard']
        has_en_keywords = any(word in text_lower.split() for word in en_keywords)
        if not has_vi_accent and has_en_keywords:
            return 'en'
    return detected_lang

def translate_with_qwen(text, detected_language, context_history):
    if not text.strip():
        return ""
    source_lang = "Vietnamese" if detected_language == "vi" else "English"
    target_lang = "English" if detected_language == "vi" else "Vietnamese"
    
    # Chuẩn bị bộ nhớ ngữ cảnh (tối đa 3 câu gần nhất)
    history_text = "\n".join(context_history) if context_history else "No previous context."
    
    # 🌟 CẢI TIẾN 2 & 3: Bơm bộ nhớ ngữ cảnh và Từ điển ép buộc vào Prompt
    prompt = f"""You are an elite bilingual simultaneous interpreter.
    Task: Translate the CURRENT TEXT from {source_lang} to {target_lang}.

    --- CONTEXT HISTORY (For reference only, DO NOT translate this again) ---
    {history_text}
    -----------------------------------------------------------------------

    --- DICTIONARY & SMART CORRECTIONS ---
    - If you hear "mỳ độ" or "nhật độ" -> Correct it to "nhiệt độ" (Temperature).
    - If you hear "chạy rất hard" -> Correct it to "running heavily" or "overloaded".
    - Keep IT terms standard (backend, frontend, deploy, server, database).
    --------------------------------------

    Strict Rules:
    1. Output ONLY the direct translation of the CURRENT TEXT. No notes, no explanation.
    2. SECONDARY FILTER: If the current text is meaningless gibberish or a hallucination, output EXACTLY: [DROP]
    
    CURRENT TEXT TO TRANSLATE: {text}"""
    
    payload = {
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,    
            "num_predict": 100
        }
    }
    try:
        start_time = time.time()
        response = requests.post(OLLAMA_URL, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json().get("response", "").strip()
        print(f"🤖 [Qwen] Dịch hoàn tất ({time.time() - start_time:.2f}s)", flush=True)
        return result
    except Exception as e:
        print(f"❌ [Lỗi Qwen]: {e}", flush=True)
        return "Error in LLM translation."

async def process_audio_pipeline(audio_data, websocket: WebSocket, current_threshold, chat_history):
    try:
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        
        # 🌟 CẢI TIẾN 1: Mồi từ khóa chuyên ngành vào thẳng tai của Whisper
        def run_mlx_whisper():
            return mlx_whisper.transcribe(
                audio_array, 
                path_or_hf_repo=MLX_MODEL_PATH, 
                temperature=0,
                initial_prompt="Cuộc họp doanh nghiệp, công nghệ, tài chính, nhiệt độ, dự án, hệ thống máy chủ, backend, frontend, API, database."
            )

        stt_start = time.time()
        
        async with gpu_lock:
            result = await asyncio.to_thread(run_mlx_whisper)
            
        original_text = result.get("text", "").strip()
        detected_lang = result.get("language", "vi")

        if detected_lang not in ['vi', 'en', 'en-US', 'en-GB']:
            print(f"🤫 [Ảo giác Whisper]: Nhận diện nhầm thành '{detected_lang}' -> Đã hủy bóc băng!", flush=True)
            return

        if not original_text or is_garbage_or_foreign(original_text):
            return

        corrected_lang = double_check_language(original_text, detected_lang)
        print(f"🎤 [MLX GPU] [{corrected_lang.upper()}] ({time.time() - stt_start:.2f}s): {original_text}", flush=True)

        await websocket.send_json({"type": "status", "message": f"Detected {corrected_lang.upper()}, translating..."})
        
        # Truyền lịch sử ngữ cảnh vào Qwen
        translated_text = await asyncio.to_thread(translate_with_qwen, original_text, corrected_lang, chat_history)
        
        if not translated_text or "[DROP]" in translated_text.upper():
            print(f"🤫 [Qwen Filter]: LLM từ chối dịch câu rác -> Đã chặn hiển thị.", flush=True)
            return

        # Lưu lại câu vừa dịch vào bộ nhớ ngắn hạn (tối đa giữ 3 câu)
        memory_string = f"[{corrected_lang.upper()}] {original_text} -> Translated: {translated_text}"
        chat_history.append(memory_string)
        if len(chat_history) > 3:
            chat_history.pop(0)

        await websocket.send_json({
            "type": "result",
            "original": original_text,
            "translated": translated_text,
            "language": "vi" if corrected_lang == "vi" else "en"
        })
    except Exception as e:
        print(f"❌ Lỗi Pipeline tổng thể: {e}", flush=True)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Client đã kết nối WebSocket!", flush=True)
    audio_buffer = bytearray()
    silence_start_time = None
    speech_start_time = None
    is_speaking = False
    
    # 🌟 KHỞI TẠO BỘ NHỚ NGẮN HẠN CHO PHIÊN CHAT NÀY
    chat_history = []
    
    ambient_noise = 100.0
    dynamic_threshold = 180.0
    consecutive_loud_frames = 0
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
                    consecutive_loud_frames += 1
                    if consecutive_loud_frames >= 3:
                        is_speaking = True
                        speech_start_time = time.time()
                        print(f"🎙️ [PHÁT HIỆN GIỌNG NÓI] RMS: {rms:.1f} (Vượt ngưỡng: {dynamic_threshold:.1f})", flush=True)
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
                    print(f"⏳ [CHỐT BĂNG] Độ dài: {current_duration:.2f}s | Gửi vào hàng đợi MLX GPU...", flush=True)
                    audio_data_to_process = bytes(audio_buffer)
                    audio_buffer.clear()
                    is_speaking = False
                    silence_start_time = None
                    speech_start_time = None
                    consecutive_loud_frames = 0
                    
                    asyncio.create_task(process_audio_pipeline(audio_data_to_process, websocket, dynamic_threshold, chat_history))
    except WebSocketDisconnect:
        print("❌ Client ngắt kết nối.", flush=True)
    except Exception as e:
        print(f"❌ Lỗi WebSocket Endpoint: {e}", flush=True)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
