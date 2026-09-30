#!/usr/bin/env python3
"""Small local MiniLM runtime without the heavyweight model auto-loader stack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence


def _model_snapshot(model_name: str, model_cache: Path, allow_model_download: bool) -> Path:
    local_model = Path(model_name).expanduser()
    if local_model.is_dir():
        return local_model

    repo_dir = model_cache / ("models--" + model_name.replace("/", "--"))
    refs_main = repo_dir / "refs" / "main"
    if refs_main.is_file():
        revision = refs_main.read_text(encoding="utf-8").strip()
        snapshot = repo_dir / "snapshots" / revision
        if snapshot.is_dir():
            return snapshot

    if not allow_model_download:
        raise FileNotFoundError(
            f"Model '{model_name}' is not complete under {model_cache}. "
            "Run once with --allow-model-download."
        )

    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise RuntimeError(
            "Downloading the local model requires huggingface-hub. "
            "Install requirements-semantic.txt, then retry."
        ) from error

    return Path(snapshot_download(repo_id=model_name, cache_dir=str(model_cache)))


class _BertEmbeddings:
    def __init__(self, torch: Any, config: dict[str, Any]) -> None:
        import torch.nn as nn

        self.module = nn.Module()
        self.module.word_embeddings = nn.Embedding(config["vocab_size"], config["hidden_size"])
        self.module.position_embeddings = nn.Embedding(
            config["max_position_embeddings"], config["hidden_size"]
        )
        self.module.token_type_embeddings = nn.Embedding(
            config["type_vocab_size"], config["hidden_size"]
        )
        self.module.LayerNorm = nn.LayerNorm(config["hidden_size"], eps=config["layer_norm_eps"])

    def __call__(self, input_ids: Any, token_type_ids: Any) -> Any:
        position_ids = input_ids.new_tensor(range(input_ids.shape[1])).unsqueeze(0)
        position_ids = position_ids.expand_as(input_ids)
        return self.module.LayerNorm(
            self.module.word_embeddings(input_ids)
            + self.module.position_embeddings(position_ids)
            + self.module.token_type_embeddings(token_type_ids)
        )


class _BertSelfAttention:
    def __init__(self, torch: Any, config: dict[str, Any]) -> None:
        import torch.nn as nn

        self.torch = torch
        self.num_heads = config["num_attention_heads"]
        self.head_size = config["hidden_size"] // self.num_heads
        self.all_head_size = self.num_heads * self.head_size
        self.module = nn.Module()
        self.module.query = nn.Linear(config["hidden_size"], self.all_head_size)
        self.module.key = nn.Linear(config["hidden_size"], self.all_head_size)
        self.module.value = nn.Linear(config["hidden_size"], self.all_head_size)

    def _split_heads(self, value: Any) -> Any:
        shape = value.size()[:-1] + (self.num_heads, self.head_size)
        return value.view(*shape).permute(0, 2, 1, 3)

    def __call__(self, hidden: Any, attention_mask: Any) -> Any:
        query = self._split_heads(self.module.query(hidden))
        key = self._split_heads(self.module.key(hidden))
        value = self._split_heads(self.module.value(hidden))
        scores = self.torch.matmul(query, key.transpose(-1, -2)) / (self.head_size**0.5)
        scores = scores + attention_mask
        probabilities = self.torch.nn.functional.softmax(scores, dim=-1)
        context = self.torch.matmul(probabilities, value).permute(0, 2, 1, 3).contiguous()
        return context.view(context.size(0), context.size(1), self.all_head_size)


class _BertLayer:
    def __init__(self, torch: Any, config: dict[str, Any]) -> None:
        import torch.nn as nn

        self.torch = torch
        self.attention = _BertSelfAttention(torch, config)
        self.attention_output = nn.Module()
        self.attention_output.dense = nn.Linear(config["hidden_size"], config["hidden_size"])
        self.attention_output.LayerNorm = nn.LayerNorm(
            config["hidden_size"], eps=config["layer_norm_eps"]
        )
        self.intermediate = nn.Module()
        self.intermediate.dense = nn.Linear(config["hidden_size"], config["intermediate_size"])
        self.output = nn.Module()
        self.output.dense = nn.Linear(config["intermediate_size"], config["hidden_size"])
        self.output.LayerNorm = nn.LayerNorm(config["hidden_size"], eps=config["layer_norm_eps"])

    def __call__(self, hidden: Any, attention_mask: Any) -> Any:
        attention_output = self.attention(hidden, attention_mask)
        attention_output = self.attention_output.dense(attention_output)
        attention_output = self.attention_output.LayerNorm(attention_output + hidden)
        intermediate = self.torch.nn.functional.gelu(self.intermediate.dense(attention_output))
        output = self.output.dense(intermediate)
        return self.output.LayerNorm(output + attention_output)


class _BertEncoder:
    def __init__(self, torch: Any, config: dict[str, Any]) -> None:
        import torch.nn as nn

        self.torch = torch
        self.embeddings = _BertEmbeddings(torch, config)
        self.layers = [_BertLayer(torch, config) for _ in range(config["num_hidden_layers"])]
        self.module = nn.Module()
        self.module.embeddings = self.embeddings.module
        self.module.encoder = nn.Module()
        self.module.encoder.layer = nn.ModuleList()
        for layer in self.layers:
            registered = nn.Module()
            registered.attention = nn.Module()
            registered.attention.self = layer.attention.module
            registered.attention.output = layer.attention_output
            registered.intermediate = layer.intermediate
            registered.output = layer.output
            self.module.encoder.layer.append(registered)

    def load(self, weights: dict[str, Any]) -> None:
        tensor_weights = {key: self.torch.from_numpy(value) for key, value in weights.items()}
        missing, unexpected = self.module.load_state_dict(tensor_weights, strict=False)
        meaningful_missing = [key for key in missing if not key.startswith("pooler.")]
        if meaningful_missing:
            raise RuntimeError(
                "The local MiniLM weights do not match the encoder architecture: "
                + ", ".join(meaningful_missing[:6])
            )
        del unexpected

    def __call__(self, input_ids: Any, attention_mask: Any, token_type_ids: Any) -> Any:
        hidden = self.embeddings(input_ids, token_type_ids)
        extended_mask = (1.0 - attention_mask[:, None, None, :].float()) * -10000.0
        for layer in self.layers:
            hidden = layer(hidden, extended_mask)
        return hidden


class LocalEmbeddingModel:
    """Encode MiniLM text with direct tokenization and a compact BERT encoder."""

    def __init__(
        self,
        model_name: str,
        model_cache: Path,
        allow_model_download: bool = False,
        device: str = "auto",
    ) -> None:
        try:
            import numpy as np
            import torch
            from safetensors.numpy import load_file
            from tokenizers import Tokenizer
        except ImportError as error:
            raise RuntimeError(
                "Local semantic search requires tokenizers, safetensors, torch, and numpy. "
                "Install requirements-semantic.txt, then retry."
            ) from error

        snapshot = _model_snapshot(model_name, model_cache, allow_model_download)
        config = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
        if config.get("model_type") != "bert":
            raise RuntimeError(
                f"The direct local encoder supports BERT models, not {config.get('model_type')!r}."
            )
        tokenizer = Tokenizer.from_file(str(snapshot / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=config["max_position_embeddings"])
        tokenizer.enable_padding(pad_id=config.get("pad_token_id", 0), pad_token="[PAD]")
        weights_path = snapshot / "model.safetensors"
        if not weights_path.is_file():
            raise RuntimeError(f"Local MiniLM model is missing {weights_path}")

        self.torch = torch
        self.np = np
        self.tokenizer = tokenizer
        self.config = config
        self.device = self._select_device(device)
        self.encoder = _BertEncoder(torch, config)
        self.encoder.load(load_file(str(weights_path)))
        self.encoder.module.to(self.device)
        self.encoder.module.eval()

    def _select_device(self, requested: str):
        if requested and requested != "auto":
            return self.torch.device(requested)
        if getattr(self.torch.backends, "mps", None) is not None and self.torch.backends.mps.is_available():
            return self.torch.device("mps")
        return self.torch.device("cpu")

    def _encode(self, texts: Sequence[str], batch_size: int = 32):
        if not texts:
            return self.np.empty((0, self.config["hidden_size"]), dtype="float32")

        embeddings = []
        for start in range(0, len(texts), batch_size):
            encodings = self.tokenizer.encode_batch(list(texts[start : start + batch_size]))
            max_length = max(len(item.ids) for item in encodings)
            input_ids = self.torch.tensor([item.ids[:max_length] for item in encodings], dtype=self.torch.long)
            attention_mask = self.torch.tensor(
                [item.attention_mask[:max_length] for item in encodings], dtype=self.torch.long
            )
            token_type_ids = self.torch.tensor(
                [item.type_ids[:max_length] for item in encodings], dtype=self.torch.long
            )
            input_ids = input_ids.to(self.device)
            attention_mask = attention_mask.to(self.device)
            token_type_ids = token_type_ids.to(self.device)
            with self.torch.inference_mode():
                output = self.encoder(input_ids, attention_mask, token_type_ids)
                mask = attention_mask.unsqueeze(-1).expand(output.size()).float()
                pooled = (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
                pooled = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
                embeddings.append(pooled.cpu().numpy())

        return self.np.concatenate(embeddings, axis=0).astype("float32")

    def encode_document(
        self,
        documents: Sequence[str],
        *,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        batch_size: int = 32,
        **_: Any,
    ):
        del normalize_embeddings, show_progress_bar
        embeddings = self._encode(documents, batch_size=batch_size)
        if convert_to_numpy:
            return embeddings
        return self.torch.from_numpy(embeddings)

    def encode_query(
        self,
        query: str,
        *,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        **kwargs: Any,
    ):
        return self.encode_queries(
            [query],
            convert_to_numpy=convert_to_numpy,
            normalize_embeddings=normalize_embeddings,
            show_progress_bar=show_progress_bar,
            **kwargs,
        )[0]

    def encode_queries(
        self,
        queries: Sequence[str],
        *,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        batch_size: int = 32,
        **_: Any,
    ):
        """Encode multiple requirements in one tokenizer/model pass.

        Batch encoding matters more than it first appears on Apple Silicon:
        one larger tensor avoids repeatedly paying tokenizer, tensor-transfer,
        and framework dispatch overhead for each short JD requirement.
        """

        del normalize_embeddings, show_progress_bar
        embeddings = self._encode(queries, batch_size=batch_size)
        if convert_to_numpy:
            return embeddings
        return self.torch.from_numpy(embeddings)


def load_embedding_model(
    model_name: str,
    model_cache: Path,
    allow_model_download: bool = False,
    device: str = "auto",
) -> LocalEmbeddingModel:
    try:
        return LocalEmbeddingModel(model_name, model_cache, allow_model_download, device)
    except Exception as error:
        if isinstance(error, RuntimeError) and str(error).startswith("Local semantic search requires"):
            raise
        raise RuntimeError(
            f"Could not load local semantic model '{model_name}'. "
            "Re-run with --allow-model-download to download the model only."
        ) from error
