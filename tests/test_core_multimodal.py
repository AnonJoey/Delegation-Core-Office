import unittest
import os
import tempfile
from delegation_core.cores.multimodal.pipeline import MultimodalPipeline

class TestMultimodalMediaCore(unittest.TestCase):
    def setUp(self):
        self.pipeline = MultimodalPipeline()

    def test_document_ingestion(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(b"%PDF-1.4 mock content")
            temp_pdf = tf.name

        try:
            res = self.pipeline.ingest_asset(temp_pdf)
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["type"], "document")
            self.assertIn("MarkItDown", res["pipeline"])
            self.assertIn("markdown", res)
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_audio_transcription(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(b"RIFF mock wave audio data")
            temp_wav = tf.name

        try:
            res = self.pipeline.ingest_asset(temp_wav)
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["type"], "audio")
            self.assertIn("Whisper", res["pipeline"])
            self.assertIn("transcription", res)
        finally:
            if os.path.exists(temp_wav):
                os.remove(temp_wav)

    def test_diagram_generation(self):
        res = self.pipeline.generate_diagram("fluxo de dados")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("mermaid_code", res)

    def test_tts_synthesis(self):
        res = self.pipeline.synthesize_speech("Texto para narracao neural", "test.mp3")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("Audiblez", res["engine"])

if __name__ == "__main__":
    unittest.main()
