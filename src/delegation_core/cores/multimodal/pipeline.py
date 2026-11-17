import os
from typing import Dict, Any
from .documents.ocr_engine import OCREngine
from .documents.markdown_converter import MarkdownConverter
from .audio.speech_to_text import SpeechToTextEngine
from .audio.text_to_speech import TextToSpeechEngine
from .diagrams.generator import DiagramGenerator

class MultimodalPipeline:
    def __init__(self):
        self.ocr = OCREngine()
        self.converter = MarkdownConverter()
        self.stt = SpeechToTextEngine()
        self.tts = TextToSpeechEngine()
        self.diagrams = DiagramGenerator()

    def ingest_asset(self, file_path: str) -> Dict[str, Any]:
        """Identifica automaticamente o tipo do arquivo e processa de ponta a ponta"""
        if not os.path.exists(file_path):
            return {"status": "ERROR", "error": f"File not found: {file_path}"}
            
        ext = os.path.splitext(file_path)[1].lower()
        
        # 1. Roteamento de Documentos e PDFs
        if ext in [".pdf", ".png", ".jpg", ".tiff"]:
            # Aplica camada OCR e converte para Markdown limpo
            ocr_res = self.ocr.process_pdf_or_image(file_path)
            conv_res = self.converter.convert_to_markdown(file_path)
            return {
                "type": "document",
                "pipeline": "OCRmyPDF + MarkItDown",
                "ocr": ocr_res,
                "markdown": conv_res["markdown"],
                "status": "SUCCESS"
            }
            
        # 2. Roteamento de Áudio
        elif ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]:
            stt_res = self.stt.transcribe(file_path)
            return {
                "type": "audio",
                "pipeline": "OpenAI Whisper Transcriber",
                "transcription": stt_res["transcription"],
                "segments": stt_res["segments"],
                "status": "SUCCESS"
            }
            
        # 3. Documentos de Texto / Markdown
        else:
            conv_res = self.converter.convert_to_markdown(file_path)
            return {
                "type": "generic_document",
                "pipeline": "MarkItDown",
                "markdown": conv_res.get("markdown", ""),
                "status": "SUCCESS"
            }

    def generate_diagram(self, prompt: str) -> Dict[str, Any]:
        return self.diagrams.text_to_diagram(prompt)

    def synthesize_speech(self, text: str, output_path: str = "output.mp3") -> Dict[str, Any]:
        return self.tts.synthesize(text, output_path)
