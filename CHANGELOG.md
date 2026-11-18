# Changelog

The main changes in each version. A version is a tag and a [release](https://github.com/microtaro/llm-agents-for-image-annotation/releases) of this repository.

[日本語](CHANGELOG.ja.md)

## 0.7.6.0 - 2026-11-18

### Added

- Prices for GPT-6.2 Astra and GPT-6.2 Sol (OpenAI's Standard rates on 2026-11-18). Codex CLI already offered them, but their cost showed as unknown and a run's cost limit did not stop them. Both work now.

### Removed

- The tools that built zip packages. The app is given only through this repository.

### Updating from 0.7.5.9

Run `git pull` in the app's folder, then start it with `start.cmd` or `sh start.sh`. Your datasets and results stay as they are.

## 0.7.5.9 - 2026-11-12

The first public release.
