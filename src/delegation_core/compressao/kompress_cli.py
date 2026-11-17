"""`delegation-core kompress setup|status`: baixar e conferir o modelo do Kompress."""

from __future__ import annotations


def cmd_kompress(args) -> int:
    from ..config import Config
    from .headroom_py.transforms.kompress_compressor import HF_MODEL_ID, KompressCompressor, KompressConfig
    cfg = Config.load()
    c = KompressCompressor(KompressConfig(device=cfg.kompress_device))
    if args.acao == "setup":
        print(f"downloading {HF_MODEL_ID} (ONNX int8, ~261 MB, and the ModernBERT tokenizer)...")
        print("ready, backend:", c.preload(allow_download=True))
        return 0
    try:
        print("ready, backend:", c.preload(allow_download=False))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"not ready: {type(e).__name__}: {e}. Run: delegation-core kompress setup")
        return 1


def registrar(sub) -> dict:
    p = sub.add_parser("kompress", help="Headroom's Kompress text compressor (ML model): setup or status")
    p.add_argument("acao", choices=["setup", "status"])
    return {"kompress": cmd_kompress}
