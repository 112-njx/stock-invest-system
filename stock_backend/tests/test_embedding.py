"""阶段六 6.1 测试：Embedding 抽象（HashEmbedding 回退 / MiniLM 推理 / 工厂回退 / collection 隔离）。"""

import math
import types

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


def test_collection_name_isolation(monkeypatch):
    from app.agent.memory import store

    monkeypatch.setattr(store, "get_embedding", lambda: types.SimpleNamespace(kind="hash"))
    assert store._collection_name(1) == "user_memory_1"
    monkeypatch.setattr(store, "get_embedding", lambda: types.SimpleNamespace(kind="minilm"))
    assert store._collection_name(1) == "user_memory_1_minilm"
