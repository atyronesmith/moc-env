"""Shell completion scripts for moc-env."""

from __future__ import annotations

import argparse

FILE_COMPLETION = "file"
ENVIRONMENT_COMPLETION = "environment"
WORKLOAD_COMPLETION = "workload"
COMPLETION_ATTRIBUTE = "moc_env_completion"

COMMANDS = (
    "check-environment",
    "check-infra",
    "check-workload",
    "charts",
    "completion",
    "discover-values",
    "document-values",
    "diff",
    "export-environment",
    "export-infra",
    "export-workload",
    "list",
    "plan-infra",
    "refresh-doc-catalog",
    "status",
    "status-hub",
    "status-workload",
    "validate",
)

COMMAND_DESCRIPTIONS = {
    "list": "list hub and workload clusters",
    "status": "report combined hub and workload repository status",
    "charts": "print the charts each cluster receives from oac-apps",
    "diff": "compare repository status for two environments",
    "status-hub": "report hub-cluster repository status",
    "status-workload": "report workload-cluster repository status",
    "export-infra": "export a draft hub-cluster desired-state document",
    "export-workload": "export a draft workload-cluster desired-state document",
    "export-environment": "export a draft Environment bundle",
    "validate": "validate a local desired-state document",
    "check-infra": "compare a hub-cluster document with merged main",
    "check-workload": "compare a workload document with merged main",
    "check-environment": "compare an Environment bundle with merged main",
    "plan-infra": "produce a read-only hub-cluster change plan",
    "document-values": "generate the chart-values reference",
    "refresh-doc-catalog": "refresh local documentation-source cache",
    "discover-values": "reconcile local values with manual documentation",
    "completion": "print a Bash or Zsh completion script",
}


def command_help_epilog() -> str:
    """Render the command catalog shown by top-level help."""

    width = max(len(command) for command in COMMAND_DESCRIPTIONS)
    lines = ["Commands:"]
    lines.extend(
        f"  {command:<{width}}  {description}"
        for command, description in COMMAND_DESCRIPTIONS.items()
    )
    lines.extend(
        [
            "",
            "Run 'moc-env COMMAND --help' for command-specific options.",
        ]
    )
    return "\n".join(lines)


def command_parser(root_parser: argparse.ArgumentParser, command: str) -> argparse.ArgumentParser | None:
    """Return the argparse parser for a subcommand, if it exists."""

    for action in root_parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            parser = action.choices.get(command)
            if isinstance(parser, argparse.ArgumentParser):
                return parser
    return None


def command_option_strings(parser: argparse.ArgumentParser) -> list[str]:
    """Return every option string a command parser accepts."""

    options = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    return sorted(options)


def option_action(parser: argparse.ArgumentParser, option: str) -> argparse.Action | None:
    """Return the argparse action registered for an exact option string."""

    for action in parser._actions:
        if option in action.option_strings:
            return action
    return None


def mark_argument(action: argparse.Action, completion: str) -> argparse.Action:
    """Declare how a parser argument should be completed."""

    setattr(action, COMPLETION_ATTRIBUTE, completion)
    return action


def mark_file_argument(action: argparse.Action) -> argparse.Action:
    """Mark an argument whose value is a filesystem path."""

    return mark_argument(action, FILE_COMPLETION)


def mark_environment_argument(action: argparse.Action) -> argparse.Action:
    """Mark a positional argument that names an environment."""

    return mark_argument(action, ENVIRONMENT_COMPLETION)


def mark_workload_argument(action: argparse.Action) -> argparse.Action:
    """Mark a positional argument that names a workload cluster."""

    return mark_argument(action, WORKLOAD_COMPLETION)


def argument_completion(action: argparse.Action) -> str | None:
    """Return the completion kind declared for an argument, if any."""

    completion = getattr(action, COMPLETION_ATTRIBUTE, None)
    return completion if isinstance(completion, str) else None


def positional_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """Return the parser's positional actions in declaration order."""

    return [action for action in parser._actions if not action.option_strings]


def positional_index(parser: argparse.ArgumentParser, tokens: list[str]) -> int:
    """Count completed positional values in the tokens typed so far."""

    index = 0
    skip_value = False
    for token in tokens:
        if skip_value:
            skip_value = False
            continue
        if token.startswith("-") and token != "-":
            if token.startswith("--") and "=" in token:
                continue
            action = option_action(parser, token)
            if action is not None and action.nargs != 0:
                skip_value = True
            continue
        index += 1
    return index


def bash_completion_script() -> str:
    commands = " ".join(COMMANDS)
    return f"""\
_moc_env_complete() {{
  local cur prev subcommand completion option_output option_status
  local positional_output positional_status
  local -a executable_command
  if [[ -n "${{MOC_ENV_COMPLETION_COMMAND:-}}" ]]; then
    read -ra executable_command <<< "$MOC_ENV_COMPLETION_COMMAND"
  elif command -v moc-env >/dev/null 2>&1; then
    executable_command=(moc-env)
  else
    executable_command=(uv run moc-env)
  fi
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  prev="${{COMP_WORDS[COMP_CWORD-1]}}"
  subcommand="${{COMP_WORDS[1]}}"

  COMPREPLY=()

  if (( COMP_CWORD == 1 )); then
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done < <(
      compgen -W "{commands}" -- "$cur"
    )
    return
  fi

  if [[ "$prev" == -* ]]; then
    option_output="$("${{executable_command[@]}}" __complete-option "$subcommand" "$prev" "$cur")"
    option_status=$?
    if (( option_status == 4 )); then
      while IFS= read -r completion; do
        COMPREPLY+=("$completion")
      done < <(compgen -f -- "$cur")
      return
    fi
    if (( option_status == 0 )); then
      if [[ -n "$option_output" ]]; then
        while IFS= read -r completion; do
          COMPREPLY+=("$completion")
        done <<< "$option_output"
      fi
      return
    fi
  fi

  if [[ "$cur" == -* ]]; then
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done < <("${{executable_command[@]}}" __complete-options "$subcommand" "$cur")
    return
  fi

  if [[ -z "$cur" ]]; then
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done < <("${{executable_command[@]}}" __complete-options "$subcommand" "")
  fi

  positional_output="$("${{executable_command[@]}}" __complete-positional "$subcommand" "$COMP_CWORD" "${{COMP_WORDS[@]}}")"
  positional_status=$?
  if (( positional_status == 4 )); then
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done < <(compgen -f -- "$cur")
  elif (( positional_status == 0 )) && [[ -n "$positional_output" ]]; then
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done <<< "$positional_output"
  fi
}}

complete -o filenames -F _moc_env_complete moc-env
"""


def zsh_completion_script() -> str:
    commands = " ".join(COMMANDS)
    return f"""\
_moc-env() {{
  local subcommand values option_output option_status positional_output positional_status
  local -a executable_command
  if [[ -n "${{MOC_ENV_COMPLETION_COMMAND:-}}" ]]; then
    executable_command=(${{(z)MOC_ENV_COMPLETION_COMMAND}})
  elif (( $+commands[moc-env] )); then
    executable_command=(moc-env)
  else
    executable_command=(uv run moc-env)
  fi
  subcommand="${{words[2]}}"

  if (( CURRENT == 2 )); then
    local -a commands
    commands=({commands})
    _describe -t commands 'command' commands
    return
  fi

  if [[ "${{words[CURRENT-1]}}" == -* ]]; then
    option_output="$("${{executable_command[@]}}" __complete-option "$subcommand" "${{words[CURRENT-1]}}" "${{words[CURRENT]}}")"
    option_status=$?
    if (( option_status == 4 )); then
      _files
      return
    fi
    if (( option_status == 0 )); then
      if [[ -n "$option_output" ]]; then
        values=(${{(f)option_output}})
        _describe -t option-values 'value' values
      fi
      return
    fi
  fi

  if [[ "${{words[CURRENT]}}" == -* ]]; then
    option_output="$("${{executable_command[@]}}" __complete-options "$subcommand" "${{words[CURRENT]}}")"
    if [[ -n "$option_output" ]]; then
      values=(${{(f)option_output}})
      _describe -t options 'option' values
    fi
    return
  fi

  if [[ -z "${{words[CURRENT]}}" ]]; then
    option_output="$("${{executable_command[@]}}" __complete-options "$subcommand" "")"
    if [[ -n "$option_output" ]]; then
      local -a option_values
      option_values=(${{(f)option_output}})
      _describe -t options 'option' option_values
    fi
  fi

  positional_output="$("${{executable_command[@]}}" __complete-positional "$subcommand" "$((CURRENT - 1))" "${{words[@]}}")"
  positional_status=$?
  if (( positional_status == 4 )); then
    _files
  elif (( positional_status == 0 )) && [[ -n "$positional_output" ]]; then
    values=(${{(f)positional_output}})
    _describe -t candidates 'candidate' values
  fi
}}

if ! (( $+functions[compdef] )); then
  autoload -Uz compinit
  compinit
fi
compdef _moc-env moc-env
"""
