import re
from typing import Dict, Any

# Marcadores de IA (Humanizer + Hallmark)
AI_SLOP_MARKERS = [
    r"\bdelve\b", r"\btapestry\b", r"\bleverage\b", r"\bgame-changer\b",
    r"\btestament\b", r"\bseamlessly\b", r"\brobust\b", r"\bharnessing\b",
    r"\bpivotal\b", r"\bfoster\b", r"\bmoreover\b", r"\bfurthermore\b",
    r"\bin summary\b", r"\bit is important to note\b", r"\bbeacon\b",
    r"\bunlocking\b", r"\bempower\b", r"\bparadigm\b"
]

# Padrões de código prolixo / comentários óbvios (Ponytail)
BLOAT_CODE_PATTERNS = [
    r"// Initialize [a-zA-Z0-9_]+",
    r"// Function to [a-zA-Z0-9_]+",
    r"# Initialize [a-zA-Z0-9_]+",
    r"# Function to [a-zA-Z0-9_]+"
]

class PromptSanitizer:
    def __init__(self):
        self.slop_patterns = [re.compile(p, re.IGNORECASE) for p in AI_SLOP_MARKERS]
        self.bloat_patterns = [re.compile(p, re.IGNORECASE) for p in BLOAT_CODE_PATTERNS]

    def audit(self, text: str) -> Dict[str, Any]:
        detected = []
        for p in self.slop_patterns:
            matches = p.findall(text)
            if matches:
                detected.extend(matches)
        
        bloat_detected = []
        for p in self.bloat_patterns:
            matches = p.findall(text)
            if matches:
                bloat_detected.extend(matches)

        total_violations = len(detected) + len(bloat_detected)
        score = max(0.0, 1.0 - (total_violations * 0.1))
        
        return {
            "score": round(score, 2),
            "is_clean": total_violations == 0,
            "total_violations": total_violations,
            "slop_detected": list(set(detected)),
            "bloat_comments_detected": list(set(bloat_detected))
        }

    def purify(self, text: str) -> str:
        res = text
        for p in self.slop_patterns:
            res = p.sub("", res)
        for p in self.bloat_patterns:
            res = p.sub("", res)
        # Normalização de espaços
        res = re.sub(r"[ \t]+", " ", res)
        res = re.sub(r"\n{3,}", "\n\n", res)
        return res.strip()
