"""Document conversion to Markdown with MarkItDown.

Until 17/11/2026 this pipeline also offered OCR, audio transcription, speech synthesis and
diagram generation. None of them ran anything: OCR and transcription returned the same fixed
text for any file, and the diagram was the same for any request, all reported as SUCCESS.
They were removed for v0.17.0 so that no tool presents invented content as a result.
"""

import os
from typing import Any, Dict

from .documents.markdown_converter import MarkdownConverter


class MultimodalPipeline:
    def __init__(self):
        self.converter = MarkdownConverter()

    def ingest_asset(self, file_path: str) -> Dict[str, Any]:
        """Convert one file to Markdown with MarkItDown (whatever formats MarkItDown reads)."""
        if not os.path.exists(file_path):
            return {"status": "ERROR", "error": f"File not found: {file_path}"}
        conv = self.converter.convert_to_markdown(file_path)
        if conv.get("status") != "SUCCESS":
            return conv
        return {
            "type": "document",
            "pipeline": "MarkItDown",
            "markdown": conv.get("markdown", ""),
            "status": "SUCCESS",
        }
