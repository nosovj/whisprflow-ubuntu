# Transcription Bias Design

## Goal

Improve recognition of project-specific phrases such as `Workspace ID` and code names by sending a short Whisper prompt with curated dictionary terms.

## Scope

Implement transcription bias, not long-form project understanding. The prompt is a compact glossary for speech-to-text spelling hints. It must not paste whole `AGENTS.md`, `CLAUDE.md`, or README content.

## Discovery Model

WhisprFlow loads terms in this order:

1. `custom_terms` from config.
2. `dictionary_files`, defaulting to `~/.config/whisprflow/dictionary.txt`.
3. For each configured `context_root`, walk from filesystem root down to that path and read supported dictionary files in each directory.

Supported project files:

- `.whisprflow-dictionary`: plain one-term-per-line file.
- `WHISPRFLOW.md`, `AGENTS.md`, `CLAUDE.md`: only explicit WhisprFlow dictionary sections.

Markdown dictionary sections are either:

```md
## WhisprFlow Dictionary
- Workspace ID
- Example Project Name
```

or:

```md
<!-- whisprflow-dictionary -->
Workspace ID
Example Project Name
<!-- /whisprflow-dictionary -->
```

## Data Flow

At transcription time, WhisprFlow builds a deduplicated prompt from configured terms and discovered files. It caps the prompt with `prompt_max_chars` and sends it as multipart `prompt` to both local OpenWhispr and OpenAI Whisper.

## Config

New defaults:

```json
{
  "custom_terms": [],
  "dictionary_files": ["~/.config/whisprflow/dictionary.txt"],
  "context_roots": [],
  "context_filenames": [".whisprflow-dictionary", "WHISPRFLOW.md", "AGENTS.md", "CLAUDE.md"],
  "prompt_max_chars": 900
}
```

## Error Handling

Missing dictionary files are ignored. Unreadable files are skipped with a short stderr warning. Bad config list values fail `whisprflowctl config validate`.

## Testing

Unit tests cover term parsing, root-down discovery order, prompt capping, local OpenWhispr request payloads, OpenAI request payloads, and config validation for list fields.
