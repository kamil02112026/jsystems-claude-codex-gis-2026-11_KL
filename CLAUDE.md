# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Claude Code Instructions

- Verify library APIs in the order from `AGENTS.md` → "Documentation lookup": `--help` first for CLI tools, then Context7 MCP (`resolve-library-id` + `query-docs`), then web search. The starter enables no MCP servers in `.mcp.json`; Context7 may be configured at user scope. Configure optional integrations during the corresponding exercise; `.mcp.example.json` is an inert Windows example, not a required startup configuration.
