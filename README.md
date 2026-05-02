# Chatnik

Python package that provides CLI scripts for conversing with persistent LLM personas.

This is a Python implementation of the CLI surface described in the Raku package ["Chatnik"](https://github.com/antononcube/Raku-Chatnik).
It persists chat objects under the XDG data directory, expands prompts through
`LLMPrompts`, and creates chat objects with `LLMFunctionObjects`.

## Commands

```shell
llm_chat --prompt=@Yoda -i yoda1 hi who are you
llm_chat_meta list --format=json
llm_chat_meta messages -i yoda1
```

**Remark:** The corresponding CLI scripts Raku package use kebab-case, i.e. `llm-chat` and `llm-chat-meta`.
In addition, the Raku package provides the "umbrella" CLI `chatnik`.

Set `CHATNIK_CHAT_OBJECTS_FILE` to override the persistent JSON file location.

