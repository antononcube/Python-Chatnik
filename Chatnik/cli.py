"""Command-line interfaces corresponding to the Raku Chatnik scripts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import (
    chat_object_to_dict,
    evaluate_message,
    export_chats,
    get_chat_objects_file_name,
    import_chats,
    load_llm_personas,
)


def _coerce_value(value: str) -> Any:
    lower = value.lower()
    if lower in {"true", "yes"}:
        return True
    if lower in {"false", "no"}:
        return False
    if lower in {"none", "null"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _kwargs_from_unknown(tokens: list[str]) -> dict[str, Any]:
    res: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            index += 1
            continue
        key = token.lstrip("-").replace("-", "_")
        if "=" in key:
            key, value = key.split("=", 1)
            res[key] = _coerce_value(value)
        elif index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
            res[key] = _coerce_value(tokens[index + 1])
            index += 1
        else:
            res[key] = True
        index += 1
    return res


def _read_input(words: list[str]) -> str:
    if words:
        return " ".join(words)
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().rstrip("\n")


def _load_raw_chats() -> dict[str, dict[str, Any]]:
    path = Path(get_chat_objects_file_name())
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return data


def _save_raw_chats(chats: dict[str, dict[str, Any]]) -> None:
    export_chats(chats)


def _message_range(count: int, n: int | None) -> tuple[int, int]:
    if count == 0:
        return 0, -1
    if n is None:
        return 0, count - 1
    if n >= 0:
        return 0, min(n - 1, count - 1)
    return max(count + n, 0), count - 1


def _cannot_find(chat_id: str) -> str:
    return f"Cannot find chat object {chat_id}." if chat_id else "No chat ID is specified"


def llm_chat_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chat with persistent LLM-chat objects.")
    parser.add_argument("words", nargs="*", help="Chat input text.")
    parser.add_argument("-i", "--id", "--chat-id", dest="chat_id", default="NONE")
    parser.add_argument("--conf", default="ChatGPT")
    parser.add_argument("--model", default="")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--echo", action="store_true")
    args, unknown = parser.parse_known_args(argv)

    chats = import_chats()
    kwargs = _kwargs_from_unknown(unknown)
    kwargs.update(
        {
            "chat_id": args.chat_id,
            "conf": args.conf,
            "model": args.model,
            "prompt": args.prompt,
            "echo": args.echo,
        }
    )
    try:
        res = evaluate_message(_read_input(args.words), chats, **kwargs)
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    export_chats(chats)
    print(res)
    return 0


def llm_chat_meta_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Meta processing of persistent LLM-chat objects.",
    )
    parser.add_argument(
        "command",
        help=(
            "Command, one of: card, clear, delete, file, first-message, "
            "last-message, list, load-llm-personas, message, messages."
        ),
    )
    parser.add_argument("-i", "--id", "--chat-id", dest="chat_id", default="NONE")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("-n", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--format", default="")
    args, unknown = parser.parse_known_args(argv)
    kwargs = _kwargs_from_unknown(unknown)
    command = args.command.lower()

    if command in {"file", "filename", "file-name"}:
        print(get_chat_objects_file_name())
        return 0

    if command in {"delete", "drop"} and args.all:
        export_chats({})
        print("Deleted all chat objects.")
        return 0

    if command in {"load-llm-personas", "load_llm_personas", "load-personas", "load_personas"}:
        chats = _load_raw_chats()
        personas = {key: chat_object_to_dict(value, key) for key, value in load_llm_personas(**kwargs).items()}
        common = sorted(set(chats).intersection(personas))
        if common:
            print(
                f"Overwriting chat objects with identifiers: <{' '.join(common)}>.",
                file=sys.stderr,
            )
        chats.update(personas)
        _save_raw_chats(chats)
        print(
            f"Ingested {len(personas)} chat objects with identifiers: "
            f"<{' '.join(sorted(personas))}>."
        )
        return 0

    path = Path(get_chat_objects_file_name())
    if not path.exists():
        print("No chat objects file.")
        return 0

    chats = _load_raw_chats()

    if command in {"list", "personas", "chats", "chat-objects", "chat_objects", "chatobjects"}:
        if not chats:
            print("No chat objects.")
            return 0
        rows = []
        for chat_id, record in chats.items():
            evaluator = record.get("llm_evaluator") or record.get("llm-evaluator") or {}
            conf = evaluator.get("conf") or {}
            rows.append(
                {
                    "chat-id": chat_id,
                    "context": evaluator.get("context"),
                    "messages": len(record.get("messages") or []),
                    "llm-configuration": {k: conf.get(k) for k in ("name", "model") if k in conf},
                }
            )
        if args.format.lower() == "json":
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for row in rows:
                print(row)
        return 0

    if command in {"delete", "drop"}:
        if args.chat_id in chats:
            del chats[args.chat_id]
            _save_raw_chats(chats)
            print(f"Deleted chat object {args.chat_id}.")
        else:
            print(_cannot_find(args.chat_id))
        return 0

    if command in {"card", "form", "table-form", "table_form"} and not args.all:
        record = chats.get(args.chat_id)
        print(json.dumps(record, ensure_ascii=False, indent=2) if record else _cannot_find(args.chat_id))
        return 0

    if command == "messages" and args.all:
        for chat_id, record in chats.items():
            print("=" * 60)
            print(f"Chat ID: {chat_id}")
            print("-" * 60)
            print(record.get("messages") or [])
        return 0

    if command == "messages":
        record = chats.get(args.chat_id)
        if record is None:
            print(_cannot_find(args.chat_id))
            return 0
        messages = list(record.get("messages") or [])
        start, end = _message_range(len(messages), args.n)
        for index, message in enumerate(messages):
            if start <= index <= end:
                print(f"{index} : {json.dumps(message, ensure_ascii=False)}")
        return 0

    if command in {"first-message", "first_message", "firstmessage", "last-message", "last_message", "lastmessage"} and not args.all:
        record = chats.get(args.chat_id)
        if record is None:
            print(_cannot_find(args.chat_id))
            return 0
        messages = list(record.get("messages") or [])
        if not messages:
            print(f"The chat object {args.chat_id} has no messages.")
            return 0
        message = messages[0] if command.startswith("first") else messages[-1]
        print(message.get("content", message) if isinstance(message, dict) else message)
        return 0

    if command in {"message", "take-message", "take_message", "takemessage"} and not args.all:
        record = chats.get(args.chat_id)
        if record is None:
            print(_cannot_find(args.chat_id))
            return 0
        if args.index is None:
            print("The message index is not specified; use --index.")
            return 0
        messages = list(record.get("messages") or [])
        try:
            message = messages[args.index]
            print(message.get("content", message) if isinstance(message, dict) else message)
        except IndexError:
            print(f"Cannot find message with index {args.index}.")
        return 0

    if command in {"clear", "clear-messages", "clear_messages", "clearmessages"} and args.all:
        for record in chats.values():
            record["messages"] = []
        _save_raw_chats(chats)
        return 0

    if command in {"clear", "clear-messages", "clear_messages", "clearmessages"}:
        record = chats.get(args.chat_id)
        if record is None:
            print(_cannot_find(args.chat_id))
            return 0
        if args.n is None:
            record["messages"] = []
            descriptor = "messages "
        else:
            messages = list(record.get("messages") or [])
            start, end = _message_range(len(messages), args.n)
            descriptor = f"message {start} " if start == end else f"messages from {start} to {end} "
            if start <= end:
                del messages[start : end + 1]
            record["messages"] = messages
        _save_raw_chats(chats)
        print(f"Cleared the {descriptor}of chat object {args.chat_id}.")
        return 0

    print("Do not know how to process the given command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(llm_chat_main())
