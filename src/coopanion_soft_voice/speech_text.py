"""Bounded natural clauses for repeatedly conditioning a fixed reference voice."""
import re

_SENTENCE = re.compile(r'(?<=[。！？!?；;])')
_CLAUSE = re.compile(r'[，,：:。！？!?；;]|——|…{2,}')


def complete_native_piece(text):
    """Terminate independently conditioned clauses without changing spoken words.

    A dangling comma on a mixed-language clause can make the fixed-reference
    model continue generating after its text is exhausted. Completed sentences
    (including the approved short sample) remain byte-for-byte unchanged.
    """
    # Limit this remediation to the reproduced mixed-language failure. Keep
    # established Chinese-only phrase boundaries and their PCM unchanged.
    if not re.search(r'[A-Za-z]', text):
        return text
    value = text.rstrip()
    if not value:
        return value
    if value[-1] in '，,：:；;':
        return value[:-1] + '。'
    if value[-1] not in '。！？!?.…—':
        return value + '。'
    return value


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
