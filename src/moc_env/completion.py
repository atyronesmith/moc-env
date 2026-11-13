"""Shell completion scripts for moc-env."""

from __future__ import annotations

COMMANDS = (
    "check-environment",
    "check-infra",
    "check-workload",
    "completion",
    "discover-values",
    "document-values",
    "export-environment",
    "export-infra",
    "export-workload",
    "hub-status",
    "list",
    "plan-infra",
    "refresh-doc-catalog",
    "validate",
    "work-status",
)


def bash_completion_script() -> str:
    commands = " ".join(COMMANDS)
    return f"""\
_moc_env_complete() {{
  local cur prev subcommand mode executable completion
  executable="${{MOC_ENV_COMPLETION_COMMAND:-moc-env}}"
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  prev="${{COMP_WORDS[COMP_CWORD-1]}}"
  subcommand="${{COMP_WORDS[1]}}"

  if [[ "$cur" == -* || "$prev" == --* ]]; then
    return
  fi

  if (( COMP_CWORD == 1 )); then
    COMPREPLY=()
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done < <(
      compgen -W "{commands}" -- "$cur"
      "$executable" __complete-environment "$cur" environment
    )
    return
  fi

  case "$subcommand" in
    export-infra|export-environment|hub-status|work-status)
      [[ $COMP_CWORD -eq 2 ]] && mode=environment
      ;;
    export-workload)
      if (( COMP_CWORD == 2 )); then
        mode=environment
      elif (( COMP_CWORD == 3 )); then
        mode=workload
      fi
      ;;
  esac

  if [[ -n "$mode" ]]; then
    COMPREPLY=()
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done < <("$executable" __complete-environment "$cur" "$mode")
  fi
}}

complete -o default -F _moc_env_complete moc-env
"""


def zsh_completion_script() -> str:
    commands = " ".join(COMMANDS)
    return f"""\
_moc-env() {{
  local subcommand values executable
  executable="${{MOC_ENV_COMPLETION_COMMAND:-moc-env}}"
  subcommand="${{words[2]}}"

  if (( CURRENT == 2 )); then
    local completion_output
    local -a commands environments
    commands=({commands})
    completion_output="$("$executable" __complete-environment "${{words[CURRENT]}}" environment)"
    environments=(${{(f)"$completion_output"}})
    _describe -t commands 'command' commands
    _describe -t environments 'environment' environments
    return
  fi

  case "$subcommand" in
    export-infra|export-environment|hub-status|work-status)
      if (( CURRENT == 3 )); then
        values=(${{(f)"$("$executable" __complete-environment "${{words[CURRENT]}}" environment)"}})
        _describe -t environments 'environment' values
      fi
      ;;
    export-workload)
      if (( CURRENT == 3 )); then
        values=(${{(f)"$("$executable" __complete-environment "${{words[CURRENT]}}" environment)"}})
        _describe -t environments 'environment' values
      elif (( CURRENT == 4 )); then
        values=(${{(f)"$("$executable" __complete-environment "${{words[CURRENT]}}" workload)"}})
        _describe -t workloads 'workload cluster' values
      fi
      ;;
  esac
}}

compdef _moc-env moc-env
"""
