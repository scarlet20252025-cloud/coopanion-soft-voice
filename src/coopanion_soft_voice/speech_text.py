"""Bounded natural clauses for repeatedly conditioning a fixed reference voice."""
import re

_SENTENCE = re.compile(r'(?<=[。！？!?；;])')
_CLAUSE = re.compile(r'[，,：:。！？!?；;]|——|…{2,}')


def split_speech_text(text, max_chars=60, target_chars=None):
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError('max_chars must be a positive integer')
    target = max_chars if target_chars is None else target_chars
    if type(target) is not int or not 1 <= target <= max_chars:
        raise ValueError('target_chars must be within the piece limit')
    pieces = []
    current = ''
    for sentence in _SENTENCE.split(text):
        if len(current) + len(sentence) > max_chars and current:
            pieces.append(current)
            current = ''
        while len(sentence) > max_chars:
            # Keep punctuation with its clause. Avoid cutting after a very short
            # opener if a useful boundary is available further into the sentence.
            boundaries = [m.end() for m in _CLAUSE.finditer(sentence[:max_chars])
                          if m.end() >= min(12, target)]
            cut = min(boundaries, key=lambda n: (abs(n-target), -n)) if boundaries else max_chars
            pieces.append(sentence[:cut])
            sentence = sentence[cut:]
        current += sentence
    if current:
        pieces.append(current)
    return [piece for piece in pieces if piece.strip()]


def model_speech_pieces(model, text):
    return split_speech_text(text, getattr(model, 'speech_piece_limit', 60),
                             getattr(model, 'speech_piece_target', None))
