#!/usr/bin/env bash
# scholar-megasearch installer
# Reconstitutes the scholar-megasearch literature-search stack on a fresh machine.
#
# Supported hosts:
#   claude - installs skills under ~/.claude/skills and writes Claude MCP JSON.
#   codex  - installs skills under ~/.agents/skills by default, builds venvs under
#            ${CODEX_HOME:-~/.codex}, and writes a Codex config.toml snippet.
#   both   - performs both installs.
#
# Usage:
#   bash setup/install.sh [you@example.com]
#   bash setup/install.sh --target codex --email you@example.com
#   bash setup/install.sh --target both --email you@example.com
#   bash setup/install.sh --target codex --register-codex-mcp you@example.com
#
# The email is used for Unpaywall OA lookup + arXiv politeness. Semantic Scholar
# (Asta) needs no key for basic use. For higher rate limits, request a free key at
# https://allenai.org/asta/resources/mcp and add it to the host MCP config as a
# literal x-api-key header. Do not use an ${ENV} placeholder for Asta in Claude Code:
# it is sent verbatim and rejected with HTTP 403.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="claude"
EMAIL="you@example.com"
REGISTER_CODEX_MCP=0
PYTHON_BIN="${PYTHON_BIN:-${PYTHON:-python3}}"

usage() {
  sed -n '2,/^set -euo pipefail$/p' "$0" | sed '$d; s/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --target=*)
      TARGET="${1#*=}"
      shift
      ;;
    --claude)
      TARGET="claude"
      shift
      ;;
    --codex)
      TARGET="codex"
      shift
      ;;
    --both)
      TARGET="both"
      shift
      ;;
    --email)
      EMAIL="${2:-}"
      shift 2
      ;;
    --email=*)
      EMAIL="${1#*=}"
      shift
      ;;
    --register-codex-mcp)
      REGISTER_CODEX_MCP=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      EMAIL="$1"
      shift
      ;;
  esac
done

case "${TARGET}" in
  claude|codex|both) ;;
  *)
    echo "unknown --target '${TARGET}' (expected claude, codex, or both)" >&2
    exit 2
    ;;
esac

if [ -z "${EMAIL}" ]; then
  echo "--email must not be empty" >&2
  exit 2
fi

CLAUDE_HOME="${CLAUDE_HOME:-${HOME}/.claude}"
CLAUDE_SKILLS_DST="${CLAUDE_HOME}/skills"
CLAUDE_SKILL_VENV="${CLAUDE_HOME}/skill_venv"
CLAUDE_PSM_VENV="${CLAUDE_HOME}/paper_search_mcp_venv"

CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
CODEX_SKILLS_DST="${CODEX_SKILLS_DIR:-${HOME}/.agents/skills}"
CODEX_SKILL_VENV="${CODEX_HOME_DIR}/skill_venv"
CODEX_PSM_VENV="${CODEX_HOME_DIR}/paper_search_mcp_venv"

echo "==> scholar-megasearch install"
echo "    repo:   ${REPO_DIR}"
echo "    target: ${TARGET}"
echo "    python: ${PYTHON_BIN}"

install_skills() {
  local host="$1"
  local skills_dst="$2"
  echo "==> [${host}] installing skills into ${skills_dst}"
  mkdir -p "${skills_dst}"
  for s in scholar-megasearch arxiv-search; do
    echo "    skill: ${s}"
    rm -rf "${skills_dst:?}/${s}"
    cp -R "${REPO_DIR}/skills/${s}" "${skills_dst}/${s}"
  done
  rm -rf "${skills_dst:?}/semantic-scholar-mcp"
}

ensure_venv_pip() {
  local venv="$1"
  if "${venv}/bin/python" -m pip --version >/dev/null 2>&1; then
    return
  fi
  echo "    repairing missing pip in ${venv}"
  "${venv}/bin/python" -m ensurepip --upgrade >/dev/null
}

install_skill_venv() {
  local host="$1"
  local skill_venv="$2"
  if [ ! -d "${skill_venv}" ]; then
    echo "==> [${host}] creating search/acquisition venv at ${skill_venv}"
    "${PYTHON_BIN}" -m venv "${skill_venv}"
  fi
  ensure_venv_pip "${skill_venv}"
  echo "==> [${host}] installing Python deps into ${skill_venv}"
  "${skill_venv}/bin/python" -m pip install -q --upgrade pip
  "${skill_venv}/bin/python" -m pip install -q -r "${REPO_DIR}/setup/requirements.txt"
  echo "==> [${host}] ensuring the isolated PDF-acquisition browser is installed"
  # Keep the branded system Chrome/Edge fast path, but install Playwright Chromium as
  # an automatic fallback so neither Claude nor Codex needs a browser extension.
  "${skill_venv}/bin/python" -m playwright install chromium
}

install_paper_search_mcp() {
  local host="$1"
  local psm_venv="$2"
  if [ ! -d "${psm_venv}" ]; then
    echo "==> [${host}] creating paper-search MCP venv at ${psm_venv}"
    "${PYTHON_BIN}" -m venv "${psm_venv}"
  fi
  ensure_venv_pip "${psm_venv}"
  echo "==> [${host}] installing paper-search-mcp (git main)"
  "${psm_venv}/bin/python" -m pip install -q --upgrade pip
  "${psm_venv}/bin/python" -m pip install -q "git+https://github.com/openags/paper-search-mcp.git"
}

uvx_path() {
  if command -v uvx >/dev/null 2>&1; then
    command -v uvx
  else
    printf '%s/.local/bin/uvx\n' "${HOME}"
  fi
}

write_claude_config() {
  local resolved="${REPO_DIR}/setup/mcp.servers.resolved.json"
  sed -e "s|HOME|${HOME}|g" -e "s|you@example.com|${EMAIL}|g" \
      "${REPO_DIR}/setup/mcp.servers.json" > "${resolved}"
  echo "==> [claude] wrote resolved MCP config: ${resolved}"
}

write_codex_config() {
  local resolved="${REPO_DIR}/setup/mcp.servers.codex.resolved.toml"
  sed \
    -e "s|__UVX__|$(uvx_path)|g" \
    -e "s|__PSM_PYTHON__|${CODEX_PSM_VENV}/bin/python|g" \
    -e "s|__EMAIL__|${EMAIL}|g" \
    "${REPO_DIR}/setup/mcp.servers.codex.toml" > "${resolved}"
  echo "==> [codex] wrote resolved MCP config: ${resolved}"
}

register_codex_mcp() {
  if ! command -v codex >/dev/null 2>&1; then
    echo "!!  codex CLI not found; skip --register-codex-mcp" >&2
    return
  fi
  echo "==> [codex] registering MCP servers with codex mcp add"
  codex mcp remove arxiv-mcp-server >/dev/null 2>&1 || true
  codex mcp remove asta >/dev/null 2>&1 || true
  codex mcp remove paper-search-mcp >/dev/null 2>&1 || true
  codex mcp add arxiv-mcp-server -- "$(uvx_path)" arxiv-mcp-server
  codex mcp add asta --url https://asta-tools.allen.ai/mcp/v1
  codex mcp add paper-search-mcp \
    --env "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL=${EMAIL}" \
    -- "${CODEX_PSM_VENV}/bin/python" -m paper_search_mcp.server
}

install_claude() {
  install_skills "claude" "${CLAUDE_SKILLS_DST}"
  install_skill_venv "claude" "${CLAUDE_SKILL_VENV}"
  install_paper_search_mcp "claude" "${CLAUDE_PSM_VENV}"
  write_claude_config
}

install_codex() {
  install_skills "codex" "${CODEX_SKILLS_DST}"
  install_skill_venv "codex" "${CODEX_SKILL_VENV}"
  install_paper_search_mcp "codex" "${CODEX_PSM_VENV}"
  write_codex_config
  if [ "${REGISTER_CODEX_MCP}" -eq 1 ]; then
    register_codex_mcp
  fi
}

case "${TARGET}" in
  claude)
    install_claude
    ;;
  codex)
    install_codex
    ;;
  both)
    install_claude
    install_codex
    ;;
esac

if ! command -v uvx >/dev/null 2>&1; then
  echo "!!  uvx not found. Install uv:  curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

echo "==> Semantic Scholar uses the remote Ai2 Asta MCP (no local install, no key needed)"
echo
echo "Done. Final steps:"
if [ "${TARGET}" = "claude" ] || [ "${TARGET}" = "both" ]; then
  echo "  Claude:"
  echo "    1. merge setup/mcp.servers.resolved.json into the mcpServers block of ~/.claude.json"
  echo "    2. restart Claude Code"
  echo "    3. verify: python3 ${CLAUDE_SKILLS_DST}/scholar-megasearch/scripts/merge_corpus.py --help"
fi
if [ "${TARGET}" = "codex" ] || [ "${TARGET}" = "both" ]; then
  echo "  Codex:"
  if [ "${REGISTER_CODEX_MCP}" -eq 1 ]; then
    echo "    1. restart Codex so new skill metadata and MCP tools are loaded"
  else
    echo "    1. merge setup/mcp.servers.codex.resolved.toml into ~/.codex/config.toml"
    echo "       or re-run with --register-codex-mcp to call codex mcp add automatically"
    echo "    2. restart Codex so new skill metadata and MCP tools are loaded"
  fi
  echo "    verify: python3 ${CODEX_SKILLS_DST}/scholar-megasearch/scripts/merge_corpus.py --help"
fi
