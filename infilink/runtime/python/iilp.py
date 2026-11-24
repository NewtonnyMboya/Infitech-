#!/usr/bin/env python3
"""Experimental IILP/1 frame codec. Python 3.9+, standard library only.

Wire format: MAGIC(4) | VERSION(1) | FLAGS(1) | LENGTH(4, big endian) | UTF-8 JSON.
This module encodes/decodes frames; it does not open sockets or execute message bodies.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from typing import Any, BinaryIO

MAGIC = b"IILP"
VERSION = 1
HEADER = struct.Struct("!4sBBI")
MAX_PAYLOAD = 1_048_576


class IILPError(ValueError):
    """Invalid or unsupported IILP frame."""


def _validate_message(message: Any) -> dict:
    if not isinstance(message, dict):
        raise IILPError("message must be a JSON object")
    if not isinstance(message.get("type"), str) or not (1 <= len(message["type"]) <= 64):
        raise IILPError("type must be a string of 1..64 characters")
    if not isinstance(message.get("id"), str) or not (1 <= len(message["id"]) <= 128):
        raise IILPError("id must be a string of 1..128 characters")
    if "body" not in message:
        raise IILPError("body is required")
    if "extensions" in message and not isinstance(message["extensions"], dict):
        raise IILPError("extensions must be an object")
    return message


def encode(message: dict) -> bytes:
    """Serialize a message into one bounded IILP/1 frame."""
    _validate_message(message)
    try:
        payload = json.dumps(
            message, ensure_ascii=False, separators=(",", ":"),
            sort_keys=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise IILPError("message is not valid interoperable JSON") from exc
    if len(payload) > MAX_PAYLOAD:
        raise IILPError("payload exceeds 1 MiB limit")
    return HEADER.pack(MAGIC, VERSION, 0, len(payload)) + payload


def decode_frame(data: bytes) -> dict:
    """Decode exactly one frame; reject truncation and trailing bytes."""
    if len(data) < HEADER.size:
        raise IILPError("truncated header")
    magic, version, flags, length = HEADER.unpack(data[:HEADER.size])
    if magic != MAGIC:
        raise IILPError("invalid magic")
    if version != VERSION:
        raise IILPError("unsupported version")
    if flags != 0:
        raise IILPError("reserved flags must be zero")
    if length > MAX_PAYLOAD:
        raise IILPError("payload exceeds 1 MiB limit")
    if len(data) != HEADER.size + length:
        raise IILPError("truncated payload or trailing bytes")
    try:
        obj = json.loads(data[HEADER.size:].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IILPError("payload must be valid UTF-8 JSON") from exc
    return _validate_message(obj)


def read_frame(stream: BinaryIO) -> dict:
    """Read one frame from a blocking binary stream without unbounded reads."""
    header = stream.read(HEADER.size)
    if len(header) != HEADER.size:
        raise IILPError("truncated header")
    magic, version, flags, length = HEADER.unpack(header)
    if magic != MAGIC or version != VERSION or flags != 0:
        raise IILPError("invalid magic, version, or flags")
    if length > MAX_PAYLOAD:
        raise IILPError("payload exceeds 1 MiB limit")
    payload = stream.read(length)
    if len(payload) != length:
        raise IILPError("truncated payload")
    return decode_frame(header + payload)


def self_test() -> None:
    sample = {"type": "ping", "id": "test-0001", "body": {"message": "hello"}}
    frame = encode(sample)
    assert decode_frame(frame) == sample
    for invalid in (b"", b"NOPE" + frame[4:]):
        try:
            decode_frame(invalid)
        except IILPError:
            pass
        else:
            raise AssertionError("invalid frame unexpectedly accepted")
    print("IILP/1 codec self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimental IILP/1 codec")
    parser.add_argument("--self-test", action="store_true", help="run codec checks")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
