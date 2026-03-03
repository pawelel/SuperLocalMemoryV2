#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
# Part of Qualixar — Advancing Agent Development Through Research
"""
Qualixar Watermark — Steganographic attribution for text outputs.

Embeds invisible zero-width Unicode characters in text to encode a tool
identifier. The watermark is invisible to human readers but can be
extracted programmatically to verify provenance.

Part of the 3-layer Qualixar attribution system:
  Layer 1: Visible attribution (ATTRIBUTION.md, get_attribution())
  Layer 2: Cryptographic signing (qualixar_attribution.py)
  Layer 3: Steganographic watermarking (this module)

No external dependencies required.
"""

# Zero-width characters for binary encoding
ZW_SPACE = '\u200b'    # Zero-width space  = bit 0
ZW_JOINER = '\u200d'   # Zero-width joiner = bit 1
ZW_SEP = '\ufeff'      # Byte order mark   = separator


def encode_watermark(text: str, tool_id: str) -> str:
    """Embed an invisible watermark in text output.

    Converts ``tool_id`` to binary and encodes each bit as a zero-width
    Unicode character. The watermark is inserted after the first paragraph
    break (``\\n\\n``) so it remains invisible to human readers.

    Args:
        text: The text to watermark.
        tool_id: Short identifier to embed (e.g. ``"slm"``).

    Returns:
        The original text with the invisible watermark inserted.
    """
    binary = ''.join(format(ord(c), '08b') for c in tool_id)
    watermark = ZW_SEP
    for bit in binary:
        watermark += ZW_SPACE if bit == '0' else ZW_JOINER
    watermark += ZW_SEP

    # Insert after first paragraph break (invisible to users)
    if '\n\n' in text:
        idx = text.index('\n\n') + 2
        return text[:idx] + watermark + text[idx:]
    return text + watermark


def decode_watermark(text: str) -> str:
    """Extract a hidden watermark from text.

    Locates the zero-width separator characters and decodes the binary
    payload between them back into the original tool identifier string.

    Args:
        text: Text that may contain a watermark.

    Returns:
        The decoded tool identifier, or an empty string if no watermark
        is found.
    """
    start = text.find(ZW_SEP)
    if start == -1:
        return ""
    end = text.find(ZW_SEP, start + 1)
    if end == -1:
        return ""
    encoded = text[start + 1:end]
    binary = ''.join(
        '0' if c == ZW_SPACE else '1'
        for c in encoded
    )
    chars = [binary[i:i + 8] for i in range(0, len(binary), 8)]
    return ''.join(chr(int(b, 2)) for b in chars if len(b) == 8)
