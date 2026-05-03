"""Core persistence and object conversion helpers for Chatnik."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from LLMFunctionObjects import Chat, llm_chat, llm_configuration, llm_evaluator
from LLMPrompts import llm_prompt_data, llm_prompt_expand
from xdg import xdg_data_home

# =========================================================
# Parametrization
# =========================================================

CHAT_OBJECTS_ENV_VAR = "CHATNIK_CHAT_OBJECTS_FILE"
CHAT_OBJECTS_FILE_NAME = "chat_objects.json"

_CONFIG_KEYS = {
    "api_key",
    "base_url",
    "api_user_id",
    "model",
    "temperature",
    "total_probability_cutoff",
    "max_tokens",
    "fmt",
    "prompt_delimiter",
    "stop_tokens",
    "known_params",
    "response_object_attribute",
    "response_value_keys",
}

# =========================================================
# Utilities
# =========================================================
def _unquote(v):
    if isinstance(v, str) and ((v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'"))):
        return v[1:-1]
    return v


def _expand_path(path):
    if not isinstance(path, str):
        return None
    path = os.path.expanduser(os.path.expandvars(path.strip()))
    if not path:
        return None
    return path


def _is_chat_conf_name(conf_name: str | None) -> bool:
    if not conf_name:
        return False
    return str(conf_name).strip().lower().startswith("chat")


def _filter_evaluator_args(conf_name: str | None, args: Mapping[str, Any]) -> dict[str, Any]:
    """Keep evaluator kwargs compatible with the chosen evaluator class."""

    allowed = {"formatron"}
    if _is_chat_conf_name(conf_name):
        allowed.update({"context", "examples", "user_role", "assistant_role", "system_role"})

    res: dict[str, Any] = {}
    for key, value in args.items():
        if key in allowed and value is not None:
            res[key] = value
    return res


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return None


def _configuration_to_dict(conf: Any) -> dict[str, Any]:
    if conf is None:
        return {}
    data = conf.to_dict() if hasattr(conf, "to_dict") else dict(getattr(conf, "__dict__", {}))
    res = {"name": getattr(conf, "name", data.get("name", "ChatGPT"))}
    for key in _CONFIG_KEYS:
        if key in data:
            res[key] = _jsonable(data[key])
    return {k: v for k, v in res.items() if v is not None}

# =========================================================
# Chat objects import and export
# =========================================================
def get_chat_objects_file_name() -> str:
    """Return the JSON file used for persistent chat objects."""

    override = os.environ.get(CHAT_OBJECTS_ENV_VAR)
    if override:
        return str(Path(override).expanduser())
    return str(Path(xdg_data_home()) / "Python" / "LLM" / "Chatnik" / CHAT_OBJECTS_FILE_NAME)


def parse_model_spec(model: str | None, conf: str | None = None) -> tuple[str, str | None]:
    """Parse model specs like ``ollama::llama3`` into configuration and model."""

    conf_local = conf or "ChatGPT"
    if model is None or str(model).strip() == "":
        return conf_local, None

    model_local = str(model).strip()
    if "::" not in model_local:
        return conf_local, model_local

    provider, model_name = model_local.split("::", 1)
    provider_lc = provider.strip().lower()
    conf_map = {
        "chatgpt": "ChatGPT",
        "openai": "ChatGPT",
        "ollama": "Ollama",
        "llama": "Ollama",
        "gemini": "Gemini",
        "palm": "Gemini",
    }
    return conf_map.get(provider_lc, provider.strip()), model_name.strip() or None

def create_chat_object(
    *,
    chat_id: str = "NONE",
    prompt: str = "",
    conf: str = "ChatGPT",
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    examples: list[Any] | None = None,
    **kwargs: Any,
) -> Chat:
    """Create an ``LLMFunctionObjects.Chat`` object without evaluating it."""

    model_local = model
    if model_local is None or model_local.strip() == "":
        model_local = os.environ.get("CHATNIK_DEFAULT_MODEL", "")
    conf_spec, model_name = parse_model_spec(model_local, conf=conf)
    conf_args = {k: v for k, v in kwargs.items() if k in _CONFIG_KEYS and v is not None}
    if model_name:
        conf_args["model"] = model_name

    prompt_spec = llm_prompt_expand(prompt, messages=[], sep="\n") if prompt else ""
    conf_obj = llm_configuration(conf_spec, **conf_args)
    evaluator_args = _filter_evaluator_args(
        conf_obj.name,
        {k: v for k, v in kwargs.items() if k not in _CONFIG_KEYS},
    )
    chat = llm_chat(prompt_spec, llm_evaluator=llm_evaluator(conf_obj, **evaluator_args))
    chat.chat_id = chat_id
    chat.messages = list(messages or [])
    chat.examples = list(examples or [])
    return chat


def chat_object_to_dict(chat: Chat | Mapping[str, Any], chat_id: str | None = None) -> dict[str, Any]:
    """Return a JSON-serializable chat-object record."""

    if isinstance(chat, Mapping):
        data = dict(chat)
        if chat_id is not None:
            data.setdefault("id", chat_id)
        return data

    evaluator = getattr(chat, "llm_evaluator", None)
    conf = getattr(evaluator, "conf", None)
    conf_dict = _configuration_to_dict(conf)
    evlr = {
        "conf": conf_dict,
        "context": getattr(evaluator, "context", None),
        "examples": getattr(evaluator, "examples", None),
        "formatron": getattr(evaluator, "formatron", None),
    }
    if _is_chat_conf_name(conf_dict.get("name")):
        evlr["user_role"] = getattr(evaluator, "user_role", "user")
        evlr["assistant_role"] = getattr(evaluator, "assistant_role", "assistant")
        evlr["system_role"] = getattr(evaluator, "system_role", "system")

    record_id = chat_id or getattr(chat, "chat_id", "") or "NONE"
    return {
        "id": record_id,
        "type": "chat",
        "llm_evaluator": evlr,
        "messages": list(getattr(chat, "messages", []) or []),
        "examples": list(getattr(chat, "examples", []) or []),
    }


def to_chat_object(data: Chat | Mapping[str, Any], chat_id: str | None = None) -> Chat:
    """Reconstruct an ``LLMFunctionObjects.Chat`` object from persisted data."""

    if isinstance(data, Chat):
        if chat_id is not None:
            data.chat_id = chat_id
        return data

    record = dict(data)
    evaluator_data = record.get("llm_evaluator") or record.get("llm-evaluator") or {}
    conf_data = dict(evaluator_data.get("conf") or {})
    conf_name = conf_data.pop("name", record.get("conf", "ChatGPT")) or "ChatGPT"
    context = evaluator_data.get("context") or record.get("prompt") or ""
    if isinstance(context, str) and context.startswith("'") and context.endswith("'"):
        context = context[1:-1]

    kwargs = {k: v for k, v in conf_data.items() if k in _CONFIG_KEYS}
    evaluator_kwargs: dict[str, Any] = {}
    if "formatron" in evaluator_data and evaluator_data["formatron"] is not None:
        evaluator_kwargs["formatron"] = evaluator_data["formatron"]
    if _is_chat_conf_name(conf_name):
        for key in ("context", "examples", "user_role", "assistant_role", "system_role"):
            if key in evaluator_data and evaluator_data[key] is not None:
                evaluator_kwargs[key] = evaluator_data[key]

    return create_chat_object(
        chat_id=chat_id or record.get("id", "NONE"),
        prompt=context,
        conf=conf_name,
        messages=list(record.get("messages") or []),
        examples=list(record.get("examples") or []),
        **kwargs,
        **evaluator_kwargs,
    )


def import_chats(file_name: str | os.PathLike[str] | None = None) -> dict[str, Chat]:
    """Read persistent chat objects and reconstruct them."""

    path = Path(file_name or get_chat_objects_file_name())
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return {chat_id: to_chat_object(record, chat_id=chat_id) for chat_id, record in data.items()}


def export_chats(
    chats: Mapping[str, Chat | Mapping[str, Any]],
    file_name: str | os.PathLike[str] | None = None,
) -> None:
    """Persist chat objects as JSON."""

    path = Path(file_name or get_chat_objects_file_name())
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {chat_id: chat_object_to_dict(chat, chat_id=chat_id) for chat_id, chat in chats.items()}
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)


# This is an interesting idea. But in addition to all personas,
# chat object creation based on a list of names should be implemented.
def create_llm_personas(**kwargs: Any) -> dict[str, Chat]:
    """Create chat objects for all prompts categorized as personas."""

    personas: dict[str, Chat] = {}
    for name, record in llm_prompt_data().items():
        categories = record.get("Categories") or []
        if "Personas" in categories or "Persona" in categories:
            prompt = record.get("PromptText") or ""
            personas[name] = create_chat_object(chat_id=name, prompt=prompt, **kwargs)
    return personas

# =========================================================
# Load pre-defined LLM personas
# =========================================================
def _normalize_personas(data):
    personas = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str):
                spec = {"prompt": v}
            elif isinstance(v, dict):
                spec = dict(v)
            else:
                continue
            spec.setdefault("chat_id", k)
            personas.append(spec)
    elif isinstance(data, list):
        for v in data:
            if isinstance(v, dict):
                personas.append(dict(v))
    return personas

def _register_personas(personas):
    chatObjects: dict[str, Chat] = {}
    for spec in personas:
        chat_id = spec.get("chat_id") or spec.get("id") or spec.get("name")
        if not chat_id:
            continue

        prompt_spec = _unquote(spec.get("prompt", ""))
        if isinstance(prompt_spec, str) and prompt_spec.strip():
            prompt_spec = llm_prompt_expand(prompt_spec, messages=[], sep="\n")
        else:
            prompt_spec = ""

        model_local = spec.get("model", None)
        if model_local is None or model_local.strip() == "":
            model_local = os.environ.get("CHATNIK_DEFAULT_MODEL", "")
        conf = spec.get("conf", None)
        conf_name, model_name = parse_model_spec(model_local, conf=conf)
        conf_args = {k: v for k, v in spec.items() if k in _CONFIG_KEYS and k != 'model' and v is not None}
        if model_name:
            conf_args["model"] = model_name

        conf_spec = llm_configuration(_unquote(conf_name), **conf_args)

        evaluator_args = {}
        if isinstance(spec.get("evaluator_args"), dict):
            evaluator_args.update(spec.get("evaluator_args"))
        if spec.get("api_key") is not None:
            evaluator_args["api_key"] = spec.get("api_key")

        chat_obj = llm_chat(prompt_spec, llm_evaluator=llm_evaluator(conf_spec, **evaluator_args))
        chatObjects[chat_id] = chat_obj
    return chatObjects


def load_llm_personas(**kwargs: Any) -> dict[str, Chat]:
    """Create chat objects for pre-defined LLM personas."""

    personas_path = _expand_path(os.getenv("PYTHON_CHATBOOK_LLM_PERSONAS_CONF", ""))
    if personas_path and os.path.isfile(personas_path):
        path = personas_path
    else:
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        personas = _normalize_personas(data)
        return _register_personas(personas)
    except Exception as e:
        print(f"Chatnik pre-defined LLM personas load failed for {path}: {e}")

    return {}


# =========================================================
# Evaluate message(s)
# =========================================================
def evaluate_message(message: str, chats: dict[str, Chat], **kwargs: Any) -> Any:
    """Evaluate a message using the same flow as ``JupyterChatbook.chat``."""

    chat_id = kwargs.get("chat_id", kwargs.get("id", "NONE"))
    if chat_id in chats:
        chat_obj = chats[chat_id]
    else:
        creation_args = {
            k: v
            for k, v in kwargs.items()
            if k not in {"chat_id", "id", "conf", "prompt", "echo", "format", "no_clipboard", "model"}
        }
        chat_obj = create_chat_object(
            chat_id=chat_id,
            prompt=str(kwargs.get("prompt") or ""),
            conf=str(kwargs.get("conf") or "ChatGPT"),
            model=kwargs.get("model") or "",
            **creation_args,
        )
        chats[chat_id] = chat_obj

    message_history = [
        item.get("content", "")
        for item in (getattr(chat_obj, "messages", None) or [])
        if isinstance(item, Mapping)
    ]
    expanded_message = llm_prompt_expand(str(message), messages=message_history, sep="\n")
    return chat_obj.eval(expanded_message, echo=bool(kwargs.get("echo", False)))
