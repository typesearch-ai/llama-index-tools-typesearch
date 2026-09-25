# Changelog

All notable changes to `llama-index-tools-typesearch` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

First release.

- `TypesearchToolSpec` with four tools: `search_news`, `get_contents`, `find_similar` and `check_coverage`,
  with the names, parameters and descriptions of the typesearch MCP server.
- Each tool returns the compact, readable text of the MCP server, with the link of every article.
- Filters fixed in the constructor (`countries`, `languages`, `include_domains`, `exclude_domains`) always apply.
- Readable errors (`TypesearchToolError`) with the SDK error as `__cause__`; the client is created on the
  first call.
