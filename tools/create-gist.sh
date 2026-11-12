#!/bin/sh

set -eu

usage() {
  cat <<'EOF'
Usage: tools/create-gist.sh [--public] FILE

Create a GitHub gist from FILE. The gist is secret by default; pass --public
to list it publicly.
EOF
}

public=false
file=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --public)
      public=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      if [ "$#" -ne 1 ]; then
        usage >&2
        exit 2
      fi
      file=$1
      shift
      ;;
    -*)
      printf 'create-gist: unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ -n "$file" ]; then
        usage >&2
        exit 2
      fi
      file=$1
      shift
      ;;
  esac
done

if [ -z "$file" ]; then
  usage >&2
  exit 2
fi
if [ ! -f "$file" ]; then
  printf 'create-gist: file does not exist: %s\n' "$file" >&2
  exit 2
fi
if ! command -v gh >/dev/null 2>&1; then
  printf 'create-gist: GitHub CLI (gh) is required\n' >&2
  exit 127
fi

if [ "$public" = true ]; then
  exec gh gist create "$file" --public
fi

exec gh gist create "$file"
