# Changelog

The main changes in each version. A version is a tag and a [release](https://github.com/microtaro/llm-agents-for-image-annotation/releases) of this repository.

[日本語](CHANGELOG.ja.md)

## Unreleased

### Added

- [Choosing a model](docs/models.md): which model to pick for outlines, from a test on 2026-11-18, with a tip for Claude Opus 5.5 (ask it in the plan to zoom in on each object). The README links it from its top row and from step 1 of installing.
- The README's Good to know lists the models you can choose, and what happens with a model the app has no price for.

## 0.7.6.0 - 2026-11-18

### Added

- Prices for GPT-6.2 Astra and GPT-6.2 Sol (OpenAI's Standard rates on 2026-11-18). Codex CLI already offered them, but their cost showed as unknown and a run's cost limit did not stop them. Both work now.

### Removed

- The tools that built zip packages. The app is given only through this repository.

### Updating from 0.7.5.9

Run `git pull` in the app's folder, then start it with `start.cmd` or `sh start.sh`. Your datasets and results stay as they are.

## 0.7.5.9 - 2026-11-12

The first public release.
