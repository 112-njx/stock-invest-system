"""阶段六 6.1 测试：Embedding 抽象（HashEmbedding 回退 / MiniLM 推理 / 工厂回退 / collection 隔离）。"""

import math
import re
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
from app.agent.memory import embedding as emb_mod
from app.agent.memory.embedding import HashEmbedding, MiniLMEmbedding


def test_hash_embedding_deterministic_normalized():
    h = HashEmbedding(dim=384)
    v = h._embed("止损不超过2%")
    assert len(v) == 384
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-4  # L2 归一
    assert h._embed("止损不超过2%") == h._embed("止损不超过2%")  # 确定性


class _FakeSession:
    def run(self, _outputs, feeds):
        ids = feeds["input_ids"]
        return [np.ones((len(ids), ids.shape[1], 384), dtype=np.float32)]


class _FakeEncoding:
    def __init__(self, ids, mask):
        self.ids = ids
        self.attention_mask = mask


class _FakeTokenizer:
    def encode_batch(self, texts):
        return [_FakeEncoding([0, 1, 2, 2], [1, 1, 1, 1]) for _ in texts]


def test_minilm_embed_batch_shape_and_normalized():
    emb = MiniLMEmbedding(dim=384)
    emb._session = _FakeSession()
    emb._tokenizer = _FakeTokenizer()
    vecs = emb._embed_batch(["左侧交易", "逢低买入"])
    assert len(vecs) == 2
    assert all(len(v) == 384 for v in vecs)
    norm = math.sqrt(sum(x * x for x in vecs[0]))
    assert abs(norm - 1.0) < 1e-4


def test_minilm_onnx_filename_by_quantization(monkeypatch):
    emb = MiniLMEmbedding(quantization="fp32")
    assert emb._onnx_filename() == "onnx/model.onnx"
    emb2 = MiniLMEmbedding(quantization="int8")
    assert emb2._onnx_filename() in ("onnx/model_quint8_avx2.onnx", "onnx/model_qint8_arm64.onnx")


def test_get_embedding_returns_hash(monkeypatch):
    monkeypatch.setattr(emb_mod.settings, "EMBEDDING_MODEL", "hash")
    emb_mod._embedding_instance = None
    emb_mod._embedding_key = None
    assert emb_mod.get_embedding().kind == "hash"


def test_get_embedding_falls_back_to_hash_on_load_failure(monkeypatch):
    monkeypatch.setattr(emb_mod.settings, "EMBEDDING_MODEL", "minilm")
    emb_mod._embedding_instance = None
    emb_mod._embedding_key = None

    def _fail(_self):
        raise RuntimeError("download fail")

    monkeypatch.setattr(emb_mod.MiniLMEmbedding, "ensure_loaded", _fail)
    assert emb_mod.get_embedding().kind == "hash"


def test_embedding_kind_tracks_model(monkeypatch):
    """G21：collection 名隔离改为 embedding_kind 列取值隔离（hash / minilm 向量空间不混用）。"""
    from app.agent.memory import store

    monkeypatch.setattr(store, "get_embedding", lambda: types.SimpleNamespace(kind="hash"))
    assert store.embedding_kind() == "hash"
    monkeypatch.setattr(store, "get_embedding", lambda: types.SimpleNamespace(kind="minilm"))
    assert store.embedding_kind() == "minilm"


_CHROMADB_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+chromadb\b", re.MULTILINE)


def test_embedding_module_has_no_chromadb_import():
    """G21 验收：embedding.py 无 chromadb 导入语句（自有 EmbeddingFunction 协议）。"""
    src = Path(emb_mod.__file__).read_text(encoding="utf-8")
    assert not _CHROMADB_IMPORT_RE.search(src), "embedding.py 仍导入 chromadb"
    assert issubclass(HashEmbedding, emb_mod.EmbeddingFunction)
    assert issubclass(MiniLMEmbedding, emb_mod.EmbeddingFunction)
    assert emb_mod.Documents == list[str]


def test_store_and_embedding_import_without_chromadb():
    """G21 验收（运行时）：导入 embedding/store 不得把 chromadb 拉进 sys.modules。

    源码文本检查会被注释/文档字符串干扰，故用子进程做真实导入验证 —— 这是「去 Chroma」的硬证据。
    """
    code = (
        "import sys;"
        "import app.agent.memory.embedding, app.agent.memory.store;"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] == 'chromadb');"
        "assert not bad, bad"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, f"导入链仍依赖 chromadb：{proc.stderr}"


def test_embedding_function_signature_matches_protocol():
    """自有协议与实现签名一致：`__call__(self, input)`（迁移期 chromadb 亦按签名结构校验）。"""
    import inspect

    params = list(inspect.signature(HashEmbedding.__call__).parameters.keys())
    assert params == ["self", "input"], f"HashEmbedding.__call__ 签名不符：{params}"
    assert list(inspect.signature(MiniLMEmbedding.__call__).parameters.keys()) == ["self", "input"]
