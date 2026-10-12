"""ctypes layout for the pinned qwentts.cpp public ABI v5."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import time

F32=C.POINTER(C.c_float)
I32=C.POINTER(C.c_int32)
Chunk=C.CFUNCTYPE(C.c_bool,F32,C.c_int,C.c_void_p)
Cancel=C.CFUNCTYPE(C.c_bool,C.c_void_p)


class Init(C.Structure):
    _fields_=[('abi_version',C.c_int),('talker_path',C.c_char_p),('codec_path',C.c_char_p),
              ('use_fa',C.c_bool),('clamp_fp16',C.c_bool),('max_batch',C.c_int),('codec_chunk_sec',C.c_float)]


class Voice(C.Structure):
    _fields_=[('ref_spk_emb',F32),('ref_spk_dim',C.c_int),('ref_codes',I32),
              ('ref_T',C.c_int),('num_codebooks',C.c_int)]


class Audio(C.Structure):
    _fields_=[('samples',F32),('n_samples',C.c_int),('sample_rate',C.c_int),('channels',C.c_int)]


class Memory(C.Structure):
    _fields_=[('cb',C.c_ulong),('faults',C.c_ulong)]+[(name,C.c_size_t) for name in
        ('peakWorkingSet','workingSet','peakPagedPool','pagedPool','peakNonPagedPool',
         'nonPagedPool','pagefile','peakPagefile')]


class Params(C.Structure):
    _fields_=[('abi_version',C.c_int),('text',C.c_char_p),('lang',C.c_char_p),
              ('instruct',C.c_char_p),('speaker',C.c_char_p),('ref_audio_24k',F32),
              ('ref_n_samples',C.c_int),('ref_text',C.c_char_p),('seed',C.c_int64),
              ('max_new_tokens',C.c_int),('temperature',C.c_float),('top_k',C.c_int),
              ('top_p',C.c_float),('repetition_penalty',C.c_float),
              ('subtalker_temperature',C.c_float),('subtalker_top_k',C.c_int),('subtalker_top_p',C.c_float),
              ('dump_dir',C.c_char_p),('cancel',Cancel),('cancel_user_data',C.c_void_p),
              ('on_chunk',Chunk),('on_chunk_user_data',C.c_void_p),
              ('ref_spk_emb',F32),('ref_spk_dim',C.c_int),('ref_codes',I32),('ref_T',C.c_int)]

