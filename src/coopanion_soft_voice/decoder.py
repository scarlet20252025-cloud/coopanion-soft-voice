"""
CUDA-graph-accelerated decode loop for Qwen3-TTS.

Replaces HuggingFace's generate() with a custom loop that:
  Phase 1 — Manual decode with StaticKVCache (removes HF overhead)
  Phase 2 — CUDA graph capture of decode steps (removes kernel launch overhead)

Expected speedup: 0.13x → ~2x realtime on RTX 3080.
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import torch
import torch.nn.functional as F
from transformers.cache_utils import Cache, CacheLayerMixin

logger = logging.getLogger("qwen3_fast_decode")


# ---------------------------------------------------------------------------
# Static KV Cache (supports both normal and CUDA-graph modes)
# ---------------------------------------------------------------------------

class _StaticCacheLayer(CacheLayerMixin):
    """Single layer of pre-allocated KV buffers.

    Normal mode: uses _seen counter, returns view up to current position.
    Graph mode: uses cache_position tensor (index_copy_), returns full buffer.
    """

    def __init__(self, num_kv_heads: int, max_seq_len: int,
                 head_dim: int, device: torch.device, dtype: torch.dtype):
        super().__init__()
        self.keys = torch.zeros(1, num_kv_heads, max_seq_len, head_dim,
                                device=device, dtype=dtype)
        self.values = torch.zeros(1, num_kv_heads, max_seq_len, head_dim,
                                  device=device, dtype=dtype)
        self._max_seq = max_seq_len
        self._seen = 0
        self.is_initialized = True
        self.graph_mode = False

    def lazy_initialization(self, key_states):
        pass

    def update(self, key_states, value_states, cache_kwargs=None):
        if self.graph_mode:
            # CUDA graph compatible: use cache_position tensor for index_copy_
            pos = cache_kwargs['cache_position']  # [1] tensor on device
            self.keys.index_copy_(2, pos, key_states)
            self.values.index_copy_(2, pos, value_states)
            return self.keys, self.values  # Full buffer (static shape)
        else:
            # Normal mode: use _seen counter, return view
            seq_len = key_states.shape[2]
            start = self._seen
            end = start + seq_len
            self.keys[:, :, start:end, :].copy_(key_states)
            self.values[:, :, start:end, :].copy_(value_states)
            return self.keys[:, :, :end, :], self.values[:, :, :end, :]

    def get_mask_sizes(self, cache_position):
        return self._seen, self._max_seq

    def get_seq_length(self):
        return self._seen

    def get_max_cache_shape(self):
        return self._max_seq


class StaticKVCache(Cache):
    """Fixed-size pre-allocated KV cache."""

    def __init__(self, num_layers: int, num_kv_heads: int,
                 max_seq_len: int, head_dim: int,
                 device: torch.device, dtype: torch.dtype):
        cache_layers = [
            _StaticCacheLayer(num_kv_heads, max_seq_len, head_dim, device, dtype)
            for _ in range(num_layers)
        ]
        super().__init__(layers=cache_layers)
        self.max_seq_len = max_seq_len
        self._num_layers = num_layers

    def advance(self, n: int = 1):
        for layer in self.layers:
            layer._seen += n

    def reset(self):
        for layer in self.layers:
            layer._seen = 0

    def get_seq_length(self, layer_idx: int = 0) -> int:
        return self.layers[0]._seen if self.layers else 0

    def set_graph_mode(self, enabled: bool):
        for layer in self.layers:
            layer.graph_mode = enabled


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def _sample_token(logits: torch.Tensor,
                  top_k: int = 50, top_p: float = 0.95,
                  temperature: float = 0.9,
                  repetition_penalty: float = 1.0,
                  suppress_tokens: Optional[List[int]] = None,
                  past_tokens: Optional[List[int]] = None) -> torch.Tensor:
    """Sample one token from logits [1, vocab].  Returns [1, 1]."""
    logits = logits.clone()

    if suppress_tokens:
        logits[:, suppress_tokens] = float('-inf')

    if repetition_penalty != 1.0 and past_tokens:
        idx = torch.tensor(past_tokens, device=logits.device, dtype=torch.long)
        scores = logits[:, idx]
        scores = torch.where(scores > 0,
                             scores / repetition_penalty,
                             scores * repetition_penalty)
        logits[:, idx] = scores

    if temperature > 0 and temperature != 1.0:
        logits = logits / temperature

    if top_k > 0:
        top_k = min(top_k, logits.size(-1))
        kth, _ = torch.topk(logits, top_k)
        logits[logits < kth[:, -1:]] = float('-inf')

    if top_p < 1.0:
        sorted_logits, sorted_idx = torch.sort(logits, descending=True)
        cum = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
        remove = cum > top_p
        remove[:, 1:] = remove[:, :-1].clone()
        remove[:, 0] = False
        sorted_logits[remove] = float('-inf')
        logits.scatter_(1, sorted_idx, sorted_logits)

    probs = F.softmax(logits, dim=-1)
    return torch.multinomial(probs, 1)  # [1, 1]


def _sample_token_fast(logits: torch.Tensor,
                       top_k: int = 50,
                       temperature: float = 0.9) -> torch.Tensor:
    """Fast sampler for code predictor — no clone/suppress/repetition/top_p."""
    logits = logits / temperature if temperature != 1.0 else logits
    if top_k > 0:
        top_k = min(top_k, logits.size(-1))
        kth, _ = torch.topk(logits, top_k)
        logits = logits.masked_fill(logits < kth[:, -1:], float('-inf'))
    probs = F.softmax(logits, dim=-1)
    return torch.multinomial(probs, 1)  # [1, 1]


# ---------------------------------------------------------------------------
# Fake result wrapper (so model.generate post-processing works)
# ---------------------------------------------------------------------------

@dataclass
class _TalkerResult:
    """Mimics HF GenerateDecoderOnlyOutput just enough for model.generate()."""
    hidden_states: list
    sequences: Optional[torch.Tensor] = None


# ---------------------------------------------------------------------------
# CUDA Graph Decoder
# ---------------------------------------------------------------------------

class CUDAGraphDecoder:
    """Drop-in replacement for talker.generate() with custom decode loop.

    Usage::

        decoder = CUDAGraphDecoder(model.model)
        # Then in the worker, call model.generate() — it will use the fast path.
    """

    def __init__(self, model, max_seq_len: int = 2048):
        self.model = model
        self.talker = model.talker
        self.device = next(model.parameters()).device
        self.dtype = next(model.parameters()).dtype
        self.max_seq_len = max_seq_len

        tc = self.talker.config
        self.num_layers = tc.num_hidden_layers
        self.num_kv_heads = tc.num_key_value_heads
        self.head_dim = getattr(tc, 'head_dim',
                                tc.hidden_size // tc.num_attention_heads)
        self.hidden_size = tc.hidden_size
        self.num_code_groups = (model.config.num_code_groups
                                if hasattr(model.config, 'num_code_groups')
                                else tc.num_code_groups)
        self.codec_eos_id = tc.codec_eos_token_id
        self.suppress_tokens = [
            i for i in range(tc.vocab_size - 1024, tc.vocab_size)
            if i != self.codec_eos_id
        ]

        # ---- Talker static KV cache ----
        self.kv_cache = StaticKVCache(
            self.num_layers, self.num_kv_heads, max_seq_len,
            self.head_dim, self.device, self.dtype,
        )

        # ---- Talker CUDA graph resources ----
        self._talker_graph = None
        self._talker_graph_captured = False
        # Static I/O buffers for talker graph
        self._t_static_input = torch.zeros(1, 1, self.hidden_size,
                                           device=self.device, dtype=self.dtype)
        self._t_static_cache_pos = torch.zeros(1, device=self.device, dtype=torch.long)
        self._t_static_pos_ids = torch.zeros(3, 1, 1, device=self.device, dtype=torch.long)
        self._t_static_output_hidden = None   # Set after first forward
        self._t_static_output_logits = None   # Set after first forward
        # Attention mask: [1, 1, 1, max_seq_len] — updated before each replay
        self._t_attn_mask = torch.full((1, 1, 1, max_seq_len), float('-inf'),
                                       device=self.device, dtype=self.dtype)

        # ---- Code predictor resources ----
        cp = self.talker.code_predictor
        cpc = cp.config
        self.cp_num_layers = cpc.num_hidden_layers
        cp_kv_heads = cpc.num_key_value_heads
        cp_head_dim = getattr(cpc, 'head_dim',
                              cpc.hidden_size // cpc.num_attention_heads)
        cp_max_seq = self.num_code_groups + 4

        self.cp_kv_cache = StaticKVCache(
            self.cp_num_layers, cp_kv_heads, cp_max_seq,
            cp_head_dim, self.device, self.dtype,
        )
        # Code predictor CUDA graph (projection + 5-layer decode step)
        self._cp_graph = None
        self._cp_graph_captured = False
        # Static I/O for code predictor decode graph
        # Raw input (pre-projection, talker hidden size) — projection is inside graph
        self._cp_static_raw_input = torch.zeros(1, 1, self.hidden_size,
                                                device=self.device, dtype=self.dtype)
        # Unified position tensor: [1, 1] — used for both cache_position and position_ids
        self._cp_static_pos = torch.zeros(1, 1, device=self.device, dtype=torch.long)
        self._cp_static_output_hidden = None  # Set after first forward
        # Shared attention mask for graph mode (updated before each replay)
        self._cp_graph_mask = torch.full((1, 1, 1, cp_max_seq), float('-inf'),
                                        device=self.device, dtype=self.dtype)

        # Code predictor prefill CUDA graph (2-token prefill, captured once)
        self._cp_prefill_graph = None
        self._cp_prefill_graph_captured = False
        self._cp_prefill_static_input = torch.zeros(1, 2, self.hidden_size,
                                                     device=self.device, dtype=self.dtype)
        self._cp_prefill_static_output = None
        self._cp_prefill_graph_mask = torch.full((1, 1, 2, cp_max_seq), float('-inf'),
                                                  device=self.device, dtype=self.dtype)
        self._cp_prefill_graph_mask[:, :, 0, 0] = 0.0
        self._cp_prefill_graph_mask[:, :, 1, :2] = 0.0
        self._cp_prefill_cache_pos = torch.arange(2, device=self.device)
        self._cp_prefill_pos_ids = torch.arange(2, device=self.device).unsqueeze(0)

        # Pre-allocated tensor for main decode loop
        self._loop_cache_pos = torch.zeros(1, 1, device=self.device, dtype=torch.long)

        logger.info(
            "CUDAGraphDecoder: talker=%d layers, code_pred=%d layers, "
            "kv=%d/%d hd=%d/%d hidden=%d max_seq=%d",
            self.num_layers, self.cp_num_layers,
            self.num_kv_heads, cp_kv_heads,
            self.head_dim, cp_head_dim,
            self.hidden_size, max_seq_len,
        )

    # ------------------------------------------------------------------
    # Talker decode (with CUDA graph)
    # ------------------------------------------------------------------

    def _prefill(self, inputs_embeds, attention_mask):
        """Eager prefill — uses DynamicCache, copies KV to StaticKVCache."""
        self.kv_cache.reset()
        seq_len = inputs_embeds.shape[1]

        outputs = self.talker.model(
            input_ids=None,
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            past_key_values=None,
            use_cache=True,
            cache_position=torch.arange(seq_len, device=self.device),
        )

        # Copy KV from DynamicCache → StaticKVCache
        dynamic_cache = outputs.past_key_values
        for layer_idx, layer in enumerate(self.kv_cache.layers):
            dk, dv = dynamic_cache[layer_idx]
            actual_len = dk.shape[2]
            layer.keys[:, :, :actual_len, :].copy_(dk)
            layer.values[:, :, :actual_len, :].copy_(dv)
        self.kv_cache.advance(seq_len)

        # Set up attention mask for decode graph (allow all prefilled positions)
        self._t_attn_mask.fill_(float('-inf'))
        self._t_attn_mask[:, :, :, :seq_len] = 0.0

        hidden = outputs.last_hidden_state
        logits = self.talker.codec_head(hidden)
        past_hidden = hidden[:, -1:, :]
        return logits, past_hidden

    def _talker_decode_body(self):
        """The talker decode step computation. Used for both warmup and graph capture."""
        talker_model = self.talker.model

        # Build position_ids from static buffer
        position_ids = self._t_static_pos_ids  # [3, 1, 1]
        text_position_ids = position_ids[0]    # [1, 1]

        # RoPE for this position
        position_embeddings = talker_model.rotary_emb(self._t_static_input, position_ids)

        # Run through all layers
        h = self._t_static_input
        for layer in talker_model.layers:
            layer_out = layer(
                h,
                attention_mask=self._t_attn_mask,
                position_ids=text_position_ids,
                past_key_values=self.kv_cache,
                output_attentions=False,
                use_cache=True,
                cache_position=self._t_static_cache_pos,
                position_embeddings=position_embeddings,
            )
            h = layer_out[0]

        hidden = talker_model.norm(h)
        logits = self.talker.codec_head(hidden)
        # Write to static output buffers
        self._t_static_output_hidden = hidden
        self._t_static_output_logits = logits

    def _capture_talker_graph(self, cache_pos_val, pos_ids_val):
        """Capture talker decode step as a CUDA graph."""
        logger.info("Capturing talker CUDA graph...")

        # Set up cache for graph mode
        self.kv_cache.set_graph_mode(True)

        # Set static buffers to valid values for warmup
        self._t_static_cache_pos.fill_(cache_pos_val)
        self._t_static_pos_ids.copy_(pos_ids_val)

        # Update mask for this position
        self._t_attn_mask[:, :, :, cache_pos_val] = 0.0

        # Warmup runs (required before CUDA graph capture)
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3):
                self._talker_decode_body()
        torch.cuda.current_stream().wait_stream(s)

        # Capture
        self._talker_graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self._talker_graph, stream=s):
            self._talker_decode_body()
        torch.cuda.current_stream().wait_stream(s)

        self._talker_graph_captured = True
        self.kv_cache.advance(1)
        logger.info("Talker CUDA graph captured")

    def _decode_step(self, inputs_embeds, cache_pos, rope_deltas):
        """Single talker decode step — uses CUDA graph if available.
        Returns references to static buffers (no clone — caller must read before next replay)."""
        delta = cache_pos + rope_deltas
        position_ids = delta.unsqueeze(0).expand(3, -1, -1)
        cache_pos_val = cache_pos.item()

        if not self._talker_graph_captured:
            # First decode step: capture the CUDA graph
            self._t_static_input.copy_(inputs_embeds)
            self._capture_talker_graph(cache_pos_val, position_ids)
            return self._t_static_output_logits, self._t_static_output_hidden

        # Replay: update static buffers, replay graph
        self._t_static_input.copy_(inputs_embeds)
        self._t_static_cache_pos.fill_(cache_pos_val)
        self._t_static_pos_ids.copy_(position_ids)
        self._t_attn_mask[:, :, :, cache_pos_val] = 0.0

        self._talker_graph.replay()

        self.kv_cache.advance(1)
        return self._t_static_output_logits, self._t_static_output_hidden

    # ------------------------------------------------------------------
    # Code predictor (with CUDA graphs)
    # ------------------------------------------------------------------

    def _cp_decode_body(self):
        """Code predictor decode step: projection + 5 layers + norm.
        Captured as CUDA graph. Projection folded in to save 1 kernel launch per step."""
        cp = self.talker.code_predictor
        cp_model = cp.model

        # Project from talker hidden to code predictor hidden (inside graph)
        projected = cp.small_to_mtp_projection(self._cp_static_raw_input)

        # RoPE from static position (unified tensor used as both cache_pos and pos_ids)
        position_embeddings = cp_model.rotary_emb(projected, self._cp_static_pos)

        h = projected
        for layer in cp_model.layers:
            layer_out = layer(
                h,
                attention_mask=self._cp_graph_mask,
                position_ids=self._cp_static_pos,
                past_key_values=self.cp_kv_cache,
                output_attentions=False,
                use_cache=True,
                cache_position=self._cp_static_pos.view(-1),
                position_embeddings=position_embeddings,
            )
            h = layer_out[0]

        self._cp_static_output_hidden = cp_model.norm(h)

    def _capture_cp_graph(self):
        """Capture single CUDA graph for code predictor decode step."""
        logger.info("Capturing code predictor CUDA graph...")

        # Set graph mode on cp KV cache
        self.cp_kv_cache.set_graph_mode(True)

        # Set static buffers to valid values
        self._cp_static_pos.fill_(2)
        self._cp_static_raw_input.normal_()  # Random valid input
        self._cp_graph_mask.fill_(float('-inf'))
        self._cp_graph_mask[:, :, :, :3] = 0.0  # Allow positions 0..2

        # Warmup
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3):
                self._cp_decode_body()
        torch.cuda.current_stream().wait_stream(s)

        # Capture
        self._cp_graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self._cp_graph, stream=s):
            self._cp_decode_body()
        torch.cuda.current_stream().wait_stream(s)

        self._cp_graph_captured = True
        logger.info("Code predictor CUDA graph captured")

    def _cp_prefill_body(self):
        """Code predictor 2-token prefill computation (projection + 5 layers + norm).
        Captured as CUDA graph for zero-overhead replay."""
        cp = self.talker.code_predictor
        cp_model = cp.model

        # Project from talker hidden to code predictor hidden
        projected = cp.small_to_mtp_projection(self._cp_prefill_static_input)

        # RoPE
        position_embeddings = cp_model.rotary_emb(projected, self._cp_prefill_pos_ids)

        h = projected
        for layer in cp_model.layers:
            layer_out = layer(
                h,
                attention_mask=self._cp_prefill_graph_mask,
                position_ids=self._cp_prefill_pos_ids,
                past_key_values=self.cp_kv_cache,
                output_attentions=False,
                use_cache=True,
                cache_position=self._cp_prefill_cache_pos,
                position_embeddings=position_embeddings,
            )
            h = layer_out[0]
        self._cp_prefill_static_output = cp_model.norm(h)

    def _capture_cp_prefill_graph(self):
        """Capture 2-token code predictor prefill as CUDA graph.
        Caller must set _cp_prefill_static_input before calling."""
        logger.info("Capturing code predictor prefill CUDA graph...")

        self.cp_kv_cache.reset()
        self.cp_kv_cache.set_graph_mode(True)

        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3):
                self._cp_prefill_body()
        torch.cuda.current_stream().wait_stream(s)

        self._cp_prefill_graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self._cp_prefill_graph, stream=s):
            self._cp_prefill_body()
        torch.cuda.current_stream().wait_stream(s)

        self._cp_prefill_graph_captured = True
        logger.info("Code predictor prefill CUDA graph captured")

    def _run_code_predictor(self, past_hidden, first_code_id,
                            do_sample, top_k, top_p, temperature):
        """Run code predictor: CUDA graph prefill + CUDA graph decode steps."""
        cp = self.talker.code_predictor
        cp_model = cp.model

        # Reset code predictor cache
        self.cp_kv_cache.reset()
        self.cp_kv_cache.set_graph_mode(True)  # Graph mode for both prefill and decode

        # Build prefill input [1, 2, talker_hidden_size]
        first_embed = self.talker.get_input_embeddings()(first_code_id.view(1, 1))
        inp = torch.cat([past_hidden, first_embed], dim=1)

        # ---- Prefill: 2 tokens via CUDA graph (projection + 5 layers + norm) ----
        self._cp_prefill_static_input.copy_(inp)
        if not self._cp_prefill_graph_captured:
            self._capture_cp_prefill_graph()
        else:
            self._cp_prefill_graph.replay()
        self.cp_kv_cache.advance(2)

        logits = cp.lm_head[0](self._cp_prefill_static_output[:, -1:, :])
        codes = []

        # Capture decode graph on first invocation
        if not self._cp_graph_captured:
            self._capture_cp_graph()

        # Reset decode attention mask
        self._cp_graph_mask.fill_(float('-inf'))
        self._cp_graph_mask[:, :, :, :2] = 0.0

        # ---- Decode: 30 steps using CUDA graph ----
        for i in range(self.num_code_groups - 1):
            if do_sample and temperature > 0:
                token = _sample_token_fast(logits[:, -1, :], top_k=top_k,
                                           temperature=temperature)
            else:
                token = logits[:, -1, :].argmax(dim=-1, keepdim=True)
            codes.append(token)

            if i == self.num_code_groups - 2:
                break

            gen_step = i + 1
            pos = 2 + i

            # Embed (outside graph — different weights per step)
            # Projection is folded into the graph — pass raw embedding
            step_embed = cp_model.codec_embedding[gen_step - 1](token)

            self._cp_static_raw_input.copy_(step_embed)
            self._cp_static_pos.fill_(pos)
            self._cp_graph_mask[:, :, :, pos] = 0.0

            self._cp_graph.replay()
            self.cp_kv_cache.advance(1)

            logits = cp.lm_head[gen_step](self._cp_static_output_hidden)

        return torch.cat(codes, dim=-1)

    def _build_step_embedding(self, first_code_id, remaining_codes,
                              gen_step, trailing_text_hidden, tts_pad_embed):
        """Sum all codec-group embeddings + text conditioning (in-place)."""
        combined = self.talker.get_input_embeddings()(first_code_id.view(1, 1))

        pred_embeds = self.talker.code_predictor.get_input_embeddings()
        for i in range(self.num_code_groups - 1):
            combined = combined + pred_embeds[i](remaining_codes[:, i:i + 1])

        if gen_step < trailing_text_hidden.shape[1]:
            combined = combined + trailing_text_hidden[:, gen_step:gen_step + 1, :]
        else:
            combined = combined + tts_pad_embed
        return combined

    # ------------------------------------------------------------------
    # Main entry — called by monkey-patched talker.generate()
    # ------------------------------------------------------------------

    def custom_generate(self, *,
                        inputs_embeds, attention_mask,
                        trailing_text_hidden, tts_pad_embed,
                        max_new_tokens=4096, min_new_tokens=2,
                        do_sample=True, top_k=50, top_p=1.0,
                        temperature=0.9, repetition_penalty=1.05,
                        eos_token_id=None, suppress_tokens=None,
                        subtalker_dosample=True, subtalker_top_k=50,
                        subtalker_top_p=1.0, subtalker_temperature=0.9,
                        **kwargs):
        """Custom decode loop.  Returns _TalkerResult matching HF format."""
        eos = eos_token_id if eos_token_id is not None else self.codec_eos_id
        suppress = suppress_tokens if suppress_tokens is not None else self.suppress_tokens

        assert inputs_embeds.shape[0] == 1, "fast decoder requires batch_size=1"

        t0 = time.monotonic()

        # ---- Prefill ----
        logits, past_hidden = self._prefill(inputs_embeds, attention_mask)
        prefill_len = inputs_embeds.shape[1]
        t_prefill = time.monotonic() - t0
        logger.info("Prefill: %d tokens in %.2fs", prefill_len, t_prefill)

        # Compute rope_deltas for decode position tracking
        delta0 = (1 - attention_mask).sum(dim=-1).unsqueeze(1)
        _, rope_deltas = self.talker.get_rope_index(attention_mask)
        rope_deltas = rope_deltas - delta0

        # ---- Decode loop ----
        step_results: List[tuple] = []
        step_results.append(((past_hidden,), None))

        step_logits = logits[:, -1, :]
        past_first_codes: List[int] = []

        t_sample_total = 0.0
        t_codepred_total = 0.0
        t_embed_total = 0.0
        t_decode_total = 0.0

        for step in range(max_new_tokens):
            ts0 = time.monotonic()
            # _sample_token clones internally — no need to clone here
            if step < min_new_tokens:
                step_logits = step_logits.clone()
                step_logits[:, eos] = float('-inf')

            first_code = _sample_token(
                step_logits, top_k=top_k, top_p=top_p,
                temperature=temperature,
                repetition_penalty=repetition_penalty,
                suppress_tokens=suppress,
                past_tokens=past_first_codes,
            )
            first_id = first_code.squeeze()
            past_first_codes.append(first_id.item())
            t_sample_total += time.monotonic() - ts0

            if step >= min_new_tokens and first_id.item() == eos:
                eos_codes = torch.full((1, self.num_code_groups), eos,
                                       device=self.device, dtype=torch.long)
                eos_codes[:, 0] = first_id
                step_results.append(((past_hidden,), eos_codes))
                break

            tcp0 = time.monotonic()
            remaining = self._run_code_predictor(
                past_hidden, first_id,
                subtalker_dosample, subtalker_top_k,
                subtalker_top_p, subtalker_temperature,
            )
            codec_ids = torch.cat([first_code, remaining], dim=-1)
            t_codepred_total += time.monotonic() - tcp0

            step_results.append(((past_hidden,), codec_ids))
            hook = getattr(self, 'on_codec', None)
            if hook is not None: hook(codec_ids, False)

            te0 = time.monotonic()
            combined = self._build_step_embedding(
                first_id, remaining,
                step, trailing_text_hidden, tts_pad_embed,
            )
            t_embed_total += time.monotonic() - te0

            td0 = time.monotonic()
            self._loop_cache_pos.fill_(self.kv_cache.get_seq_length())
            new_logits, new_hidden = self._decode_step(
                combined, self._loop_cache_pos, rope_deltas,
            )
            t_decode_total += time.monotonic() - td0

            step_logits = new_logits[:, -1, :]
            past_hidden = new_hidden[:, -1:, :]

        num_steps = sum(1 for _, c in step_results if c is not None)
        elapsed = time.monotonic() - t0
        logger.info("Total: %d codec steps in %.2fs (%.1f steps/s)",
                     num_steps, elapsed, num_steps / max(elapsed, 1e-3))
        logger.info("Breakdown: prefill=%.2fs  sample=%.2fs  code_pred=%.2fs  "
                     "embed=%.2fs  decode=%.2fs",
                     t_prefill, t_sample_total, t_codepred_total,
                     t_embed_total, t_decode_total)

        hook = getattr(self, 'on_codec', None)
        if hook is not None: hook(None, True)
        return _TalkerResult(hidden_states=step_results)

    # ------------------------------------------------------------------
    # Monkey-patch helper
    # ------------------------------------------------------------------

    def patch_and_generate(self, **model_generate_kwargs):
        """Call model.generate() with the fast decode loop."""
        original = self.talker.generate

        def _patched(**gk):
            return self.custom_generate(**gk)

        self.talker.generate = _patched
        try:
            return self.model.generate(**model_generate_kwargs)
        finally:
            self.talker.generate = original
