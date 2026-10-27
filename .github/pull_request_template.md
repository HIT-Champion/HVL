<!--
Feature, fix and docs PRs target develop. Write the title and description in English (docs/git_flow.md 3.1);
the title follows Conventional Commits, e.g.:
  feat(workflow): add a director approval step above the amount threshold
With "Squash and merge" the title and description become the commit on develop; CI checks the title.
Release PRs (develop → main): the title is exactly "chore(release): vX.Y.Z". See docs/git_flow.md section 6.
-->

## Summary

<!-- What this change does and WHY it is needed. -->

Closes #

## Areas and components

- [ ] Backend
- [ ] AI
- [ ] Frontend
- [ ] Infrastructure / CI / shared docs

<!-- Main component (commit scope): gateway · auth · db · workflow · files · realtime · office · ca-nhan · bang-tin ·
     nghi-phep · ai · data · ops · cli · scripts · e2e · ci · deps · docs · release -->

## Checklist

- [ ] The PR title follows Conventional Commits; the description has `Closes #<issue>`
- [ ] *(Team members)* Area label and the current phase milestone are set
- [ ] `make license-check` passes with no warning about unsupported file types
- [ ] `make check` passes — the Compose configuration is valid
- [ ] Tests are added or updated for the change (where it can be tested)
- [ ] The feature documentation is updated **in this PR**
- [ ] New configuration (if any) is declared in `.env.example` with a comment
- [ ] `CHANGELOG.md` section `[Chưa phát hành]` is updated (user-visible changes, written in Vietnamese)
- [ ] New upstream software (if any) is in `DEPENDENCIES.md` with its OSI license; `COPYRIGHT.txt` regenerated
- [ ] No upstream project is forked, patched or bundled
- [ ] No secrets, `.env`, real data or model weights in the change

## How to verify

<!-- Steps for the reviewer to run and confirm that the change works. -->
