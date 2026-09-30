# dev/: specs, logs and tools for developing the workbench

This folder is the working space for the people and tools that develop sonify-viz. Nothing here is published to the site, and nothing here changes a track's audio.

## Layout

| Path | Contents |
|---|---|
| `specs/` | One spec per change, TL;DR first, options each with a recommendation, open questions in brackets for Graham to answer in the file. Naming: `YYMMDD-short-name.md`. |
| `logs/` | One dated entry per working session: what was done, what was verified, what is open. Naming: `YYYY-MM-DD-short-name.md`. |
| `decisions/` | Append-only record of decisions Graham has made, dated, with the reason. Created when the first decision is recorded. |
| `ab/` | A/B comparisons made to help a choice (materials or the scripts that generate them), created when the first one is made. |
| `reports/` | Audits and reviews, named `<topic>-YYMMDD.md`. (`/docs/` is git-ignored in this repository, so reports live here.) |
| `a11y/` | Scripts that reproduce the accessibility audit in `reports/`. |
| `dictionary/` | The script that audits the data dictionaries against the data. |

Reports meant to be read as documents (audits, reviews) go in `reports/`, named `<topic>-YYMMDD.md`.

## Rules for any session that works here

- Say what was verified and what was not. A finding needs the command, or the file and line, that shows it.
- Do not change published audio, `renders.lock.json`, `tracks/*.yaml` content or a track's version. A change that alters audio is a new version and needs Graham's listening.
- Do not add restricted or private material. Assume anything committed here is public.
- A spec, a decision or a change that alters how a piece looks or sounds waits for Graham's answer, recorded in the spec or in `decisions/`.

## Two sides of one repo

The repository is a build output. The maintainer's private vault is the source of truth, and a sync script copies a whitelisted set of files into the repository. A change made only here is overwritten by the next sync, unless the files are in a new folder such as `dev/`. So every change to an existing file records a **Port-back** line: `repo path -> vault path`, and whether it is a fix or new tooling. The log entry for a session carries that list.
