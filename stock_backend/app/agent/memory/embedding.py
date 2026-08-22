"""Embedding 抽象（阶段六 6.1）：HashEmbedding（字符 n-gram 哈希，回退） + MiniLMEmbedding（ONNX 语义向量）。

- MiniLM 默认加载 `paraphrase-multilingual-MiniLM-L12-v2`（384 维、多语言含中文）int8 量化 ONNX，
  首次使用自动下载到本地 models 目录（urllib 直连 HF，兼容 Windows 证书库），本地 CPU 推理无需外部 API。
- `get_embedding()` 按配置选择模型，MiniLM 加载失败自动回退 HashEmbedding（保持记忆本地存储可用）。
"""

import hashlib
import logging
import platform
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class HashEmbedding(EmbeddingFunction[Documents]):
    """离线确定性 embedding：字符 n-gram 哈希到固定维度，无需下载模型（回退选项）。"""

    kind = "hash"

    def __init__(self, dim: int = 384):
        self.dim = dim

    def name(self) -> str:
        return "hash"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    def _embed(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        t = text.lower()
        for n in (1, 2, 3):
            for i in range(len(t) - n + 1):
                h = int(hashlib.md5(t[i : i + n].encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                vec[idx] += 1.0 if (h >> 8) % 2 == 0 else -1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def __call__(self, input: Documents) -> Embeddings:
        if isinstance(input, str):
            input = [input]
        return [self._embed(t) for t in input]


class MiniLMEmbedding(EmbeddingFunction[Documents]):
    """ONNX MiniLM 语义向量（int8/fp32 量化，本地 CPU 推理，mean pooling + L2 归一）。"""

    kind = "minilm"

    def __init__(
        self,
        dim: int | None = None,
        model_name: str | None = None,
        model_dir: str | None = None,
        quantization: str | None = None,
    ):
        self.dim = dim or settings.EMBEDDING_DIM
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.model_dir = model_dir or settings.EMBEDDING_MODEL_PATH
        self.quantization = quantization or settings.EMBEDDING_QUANTIZATION
        self._session = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def name(self) -> str:
        return f"minilm-{self.quantization}"

    def get_config(self) -> dict:
        return {"dim": self.dim, "model_name": self.model_name, "quantization": self.quantization}

    # ---- 加载 ----
    def _repo_dir(self) -> Path:
        return Path(self.model_dir) / self.model_name.replace("/", "__")

    def _onnx_filename(self) -> str:
        if self.quantization == "fp32":
            return "onnx/model.onnx"
        if platform.machine().lower() in ("aarch64", "arm64"):
            return "onnx/model_qint8_arm64.onnx"
        return "onnx/model_quint8_avx2.onnx"

    def _download(self, filename: str, dest: Path) -> None:
        url = f"https://huggingface.co/{self.model_name}/resolve/main/{filename}"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "stock-backend/0.1"})
                with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
                    while True:
                        chunk = r.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                return
            except Exception as e:  # noqa: BLE001
                last_exc = e
                logger.warning("download %s failed (attempt %d): %s", filename, attempt + 1, e)
                time.sleep(2)
        raise RuntimeError(f"下载模型文件失败: {filename}: {last_exc}")

    def ensure_loaded(self) -> None:
        """下载并加载 ONNX 模型 + tokenizer（失败抛异常，由 get_embedding 回退 hash）。"""
        with self._lock:
            if self._session is not None:
                return
            repo = self._repo_dir()
            repo.mkdir(parents=True, exist_ok=True)
            onnx_file = self._onnx_filename()
            onnx_path = repo / onnx_file.replace("/", "_")
            tok_path = repo / "tokenizer.json"
            if not onnx_path.exists():
                logger.info("downloading embedding model %s/%s ...", self.model_name, onnx_file)
                self._download(onnx_file, onnx_path)
            if not tok_path.exists():
                self._download("tokenizer.json", tok_path)

            import onnxruntime
            from tokenizers import Tokenizer

            self._session = onnxruntime.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
            self._tokenizer = Tokenizer.from_file(str(tok_path))
            self._tokenizer.enable_truncation(max_length=settings.EMBEDDING_MAX_LENGTH)
            self._tokenizer.enable_padding(length=settings.EMBEDDING_MAX_LENGTH)

    # ---- 推理 ----
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        encs = self._tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        type_ids = np.zeros_like(ids)
        out = self._session.run(None, {"input_ids": ids, "attention_mask": mask, "token_type_ids": type_ids})[0]
        mask_f = mask[:, : out.shape[1]].astype(np.float32)[:, :, None]
        pooled = (out * mask_f).sum(axis=1) / mask_f.sum(axis=1).clip(min=1e-9)
        pooled = pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
        return pooled.tolist()

    def embed(self, text: str) -> list[float]:
        self.ensure_loaded()
        return self._embed_batch([text])[0]

    def __call__(self, input: Documents) -> Embeddings:
        self.ensure_loaded()
        if isinstance(input, str):
            input = [input]
        return self._embed_batch(list(input))


# ---- 工厂（进程内单例，按配置缓存）----
_embedding_instance: EmbeddingFunction | None = None
_embedding_key: tuple | None = None


def get_embedding() -> EmbeddingFunction:
    """按配置返回 embedding 实例；MiniLM 加载失败回退 HashEmbedding（保持本地记忆可用）。"""
    global _embedding_instance, _embedding_key
    key = (settings.EMBEDDING_MODEL, settings.EMBEDDING_MODEL_NAME, settings.EMBEDDING_QUANTIZATION)
    if _embedding_instance is not None and _embedding_key == key:
        return _embedding_instance
    if settings.EMBEDDING_MODEL == "hash":
        _embedding_instance = HashEmbedding(settings.EMBEDDING_DIM)
    else:
        try:
            emb = MiniLMEmbedding()
            emb.ensure_loaded()
            _embedding_instance = emb
        except Exception as e:  # noqa: BLE001
            logger.warning("MiniLM embedding 加载失败，回退 HashEmbedding: %s", e)
            _embedding_instance = HashEmbedding(settings.EMBEDDING_DIM)
    _embedding_key = key
    return _embedding_instance
