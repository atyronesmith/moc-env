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

COMMAND_DESCRIPTIONS = {
    "ENV": "report combined hub and workload repository status",
    "hub-status": "report hub-cluster repository status",
    "work-status": "report workload-cluster repository status",
    "list": "list hub and workload clusters",
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


def bash_completion_script() -> str:
    commands = " ".join(COMMANDS)
    return f"""\
_moc_env_complete() {{
  local cur prev subcommand mode completion
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

  if [[ "$cur" == -* || "$prev" == --* ]]; then
    return
  fi

  if (( COMP_CWORD == 1 )); then
    COMPREPLY=()
    while IFS= read -r completion; do
      COMPREPLY+=("$completion")
    done < <(
      compgen -W "{commands}" -- "$cur"
      "${{executable_command[@]}}" __complete-environment "$cur" environment
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
    done < <("${{executable_command[@]}}" __complete-environment "$cur" "$mode")
  fi
}}

complete -o default -F _moc_env_complete moc-env
"""


def zsh_completion_script() -> str:
    commands = " ".join(COMMANDS)
    return f"""\
_moc-env() {{
  local subcommand values
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
    local completion_output
    local -a commands environments
    commands=({commands})
    completion_output="$("${{executable_command[@]}}" __complete-environment "${{words[CURRENT]}}" environment)"
    environments=(${{(f)completion_output}})
    _describe -t commands 'command' commands
    _describe -t environments 'environment' environments
    return
  fi

  case "$subcommand" in
    export-infra|export-environment|hub-status|work-status)
      if (( CURRENT == 3 )); then
        local environment_output
        environment_output="$("${{executable_command[@]}}" __complete-environment "${{words[CURRENT]}}" environment)"
        values=(${{(f)environment_output}})
        _describe -t environments 'environment' values
      fi
      ;;
    export-workload)
      if (( CURRENT == 3 )); then
        local environment_output
        environment_output="$("${{executable_command[@]}}" __complete-environment "${{words[CURRENT]}}" environment)"
        values=(${{(f)environment_output}})
        _describe -t environments 'environment' values
      elif (( CURRENT == 4 )); then
        local workload_output
        workload_output="$("${{executable_command[@]}}" __complete-environment "${{words[CURRENT]}}" workload)"
        values=(${{(f)workload_output}})
        _describe -t workloads 'workload cluster' values
      fi
      ;;
  esac
}}

if ! (( $+functions[compdef] )); then
  autoload -Uz compinit
  compinit
fi
compdef _moc-env moc-env
"""
