# Operating Signet

**Tiếng Việt:** [van-hanh.md](van-hanh.md)

*Translator's note: other documents linked from this guide are in Vietnamese unless they have an English version.*

Administrator tasks on a running installation: adding a unit, backup and restore, the secrets vault, GitOps and
self-healing, monitoring, the system status page, the internal wiki, automation with Node-RED, IT/OT convergence. First
install: [README](../README.en.md), section "Building from source"; moving to a server with a domain name and HTTPS:
[`trien-khai.md`](trien-khai.md). The operations command is `python3 scripts/moc.py …` (the technical codename `moc`
is kept from the product's former name).

## Adding a unit (tenant)

One installation serves many units (faculties, offices, member schools); each person sees only their own unit's data.
A unit is added with one command on the server, and the command can be run again (what exists is kept, only the missing
parts are added):

```bash
python3 scripts/moc.py tenant create --code KTCK --name "Khoa Cơ khí" \
    --parent-name "Trường Đại học Công nghiệp" --place-name "Hà Nội" --head-title "Trưởng khoa" \
    --department "VP=Văn phòng khoa" --department "ĐT=Tổ Đào tạo" \
    --admin quantrick --admin-name "Lê Văn Cường" --admin-email quantri@ck.example.edu.vn --dry-run
# drop --dry-run to do it for real; then:
python3 scripts/moc.py tenant list           # units, departments, users, documents, Organization
python3 scripts/moc.py tenant check KTCK     # do the Organization, its members and the directory match
```

- The command writes the `core.tenants` row and the departments (the audit log records who ran it), creates an
  **Organization** in Keycloak (alias derived from the code: `KTCK` → `ktck`, `ĐT` → `dt`; attribute `tenant_id` = the
  unit's id) and the unit administrator account (`tenant_admin`, in no department) with a temporary password printed
  **once**: the first sign-in must change the password and set up TOTP. If that password is lost, run the command
  again with `--reset-password`.
- The command waits for `svc-workflow` to copy the unit administrator into the directory (at most 90 seconds,
  `--wait`), then prints what it created, what it kept, what comes by itself (registers, NGSI-LD subscription, search
  filter, file prefix) and what is shared on purpose.
- Other accounts of the unit (clerks, directors…) are created in the Keycloak admin console with `tenant_id`,
  `department_id`, `moc_role`; then run `tenant create` again to add them to the Organization. `tenant check` points out
  accounts that are missing or have strayed into another unit's Organization (exit code 1). `make seed` does this for
  the two sample units.
- There is no bucket or data key per unit: isolation lies in the token, the Hasura permissions, the database
  constraints and encryption bound to the unit — the reasons are in [`docs/mo-hinh-du-lieu.md`](mo-hinh-du-lieu.md)
  §1. The one exception is the key that digitally signs outgoing documents (F4.5, demonstration only), which belongs
  to each unit so that the certificate can say which unit issued the document; `svc-files` creates it in the vault the
  first time the unit issues a document.
- If the internal wiki is on, also run `python3 scripts/moc.py wiki sync` so that the new unit gets its own space
  (section Internal wiki); until then, people of the new unit can only read the wiki's start page.

## Backup and restore

`make backup` backs up every database (business data, Keycloak, Flowable), all files (SeaweedFS, including the audit
log anchors) and the OpenBao vault (which holds the keys that open restricted-document files) into an encrypted
[restic](https://restic.net) repository at `MOC_BACKUP_DIR` (default `./backups`); later runs add only what changed. To
capture every database and file at the same moment, Signet pauses writes while it dumps the databases (a few seconds),
and file uploads and downloads wait until the files have been copied. `make restore` checks that the backup reads back
in full, and only then stops Signet, replaces the databases and files with the latest snapshot (asking first), records
the restore in the audit log and starts Signet again; `make audit` afterwards still matches the anchors in the bucket.
Anchors copied to a file off the server (`audit anchor --to`) after the backup time no longer match — as they should,
because those rows are gone; `make audit` points out the restore so the two can be compared.

```bash
python3 scripts/moc.py backup create --keep 14    # back up, keep the 14 latest snapshots (put it in a nightly cron)
python3 scripts/moc.py backup list                # snapshots in the repository
python3 scripts/moc.py backup check               # check the repository structure
python3 scripts/moc.py backup restore 20261020-020000   # restore one specific snapshot
```

- **The repository key is `MOC_BACKUP_PASSWORD` in `.env`: lose the key and you lose the backups.** Copy `.env` off
  the server. The restored vault is unsealed with `MOC_OPENBAO_SEAL_KEY`, also in `.env`: without it, restricted
  document files cannot be opened even though all the data is back. Keep the copy of `.env` somewhere other than the
  backup repository: whoever has both can open every encrypted file. Installations older than this command: add a line
  `MOC_BACKUP_PASSWORD=` with a long random string (e.g. `openssl rand -hex 24`) to the installation's `.env`.
- The repository should sit on another disk or on a network drive mounted on the server (`MOC_BACKUP_DIR=/mnt/nas/moc`,
  an empty folder or an existing repository), with one more copy outside the unit: the repository holds only encrypted
  files and can be copied with `rsync`. restic runs as root in its container (to read SeaweedFS's files): an NFS share
  must let root write (`no_root_squash`).
- The search index and the ClamAV signatures are not backed up: `svc-files` rebuilds the index from the database at
  startup, and ClamAV downloads its signatures by itself.
- Internal wiki (profile `wiki`): the `wiki_data` volume goes into the same snapshot, and the wiki pauses while its
  volume is copied (databases and files do not wait). A restore replaces that volume too; a running wiki is stopped
  first and started again afterwards. Snapshots from before the wiki existed leave the current wiki as it is.
- Node-RED automation (profile `tu-dong`): the `tu_dong_data` volume goes into the same snapshot in the same way
  (Node-RED pauses while it is copied, is stopped before a restore and started again afterwards).
- A finished backup writes a `system.backed_up` row to the audit log; the system status page shows the time of the
  latest snapshot from that row. If the row cannot be written, the command only warns, and the backup is still usable.

## Secrets vault

`svc-files` and `svc-workflow` do not receive the S3 storage keys, the Hasura admin key, the Flowable password… through
environment variables. At startup, each service signs in to the [OpenBao](https://openbao.org) vault with its own
AppRole and can read only its own part of the secrets; the vault logs every sign-in and read
(`docker compose logs openbao`, values HMAC-hashed). The vault uses a *static seal*: it unseals itself on restart, with
no one typing a key. The vault also holds the `moc-files` key (transit) that wraps the key of each restricted-document
file: `svc-files` can only ask for new keys and ask the vault to unwrap wrapped keys; it cannot get the wrapping key
itself. Since F4.5 the vault also has an internal PKI for digitally signing outgoing documents (demonstration only):
root CA `moc-root` in the `pki` mount, signing keys `moc-ky-so-<unit>` in transit; `svc-files` asks the vault to sign
each issued document and cannot get the private key. The vault further holds the Ed25519 key `moc-anchor` (transit) that
signs the audit log anchors: `svc-files` can only sign and read the public key (section Public anchors below). Try it:
`make demo-ket-bi-mat`, `make demo-han-che`, `make demo-ky-so` (`docs/demo-script.md`).

The limits, stated plainly:

- `.env` is still the source of the secrets: the `openbao` container receives them through environment variables and
  loads them into the vault again at every startup. Upstream software still reads its secrets from environment
  variables: PostgreSQL, Keycloak, Flowable, Hasura, SeaweedFS, Meilisearch, Centrifugo, and Parseable, Scorpio,
  restic when their profiles are on.
- The unseal key `MOC_OPENBAO_SEAL_KEY` is in `.env`; the recovery key, the startup token and the services'
  role_id/secret_id are in a volume on disk. Anyone with Docker access on the server can still read the vault. The
  vault sits only on the internal network `secrets` with the two services (other containers cannot reach it), and has
  no TLS yet.
- The vault (volume `openbao_data`) is part of `make backup`. If the volume is lost and not restored, the vault
  initialises again and loads the secrets from `.env`, but the new transit key is different: stored restricted-document
  files can no longer be opened.
- **Changing `MOC_OPENBAO_SEAL_KEY` after the vault has been initialised leaves the vault unable to unseal.**
  Installations older than the vault: add a line `MOC_OPENBAO_SEAL_KEY=` with a long random string (e.g. `openssl rand
  -hex 32`) to the installation's `.env`.
- Changing the vault's configuration (adding keys, policies, PKI) needs an admin token. On first initialisation,
  `platform/openbao/start.sh` configures it with the root token and then revokes that token; later startups use only
  the startup token. The startup token cannot read secrets directly or change policies, but it can issue secret_ids, so
  it can do anything the two services can do: guard the `openbao_data` volume like the vault itself.
- **Internal PKI (F4.5): root CA in the vault, a signing key per unit in Transit; demonstration only.** A self-built
  single-tier CA (rsa-4096, 10 years, no CRL, no OCSP), unit certificates valid for 1 year, no trusted timestamp: the
  signatures carry no legal weight the way a public digital signature does. The CA and the signing keys are in the
  `openbao_data` volume, already part of `make backup`. The `svc-files` policy allows creating, reading and signing with
  `transit/keys/moc-ky-so-*`; this glob also covers `config`, `rotate`, `trim` and `import` of those keys, and
  `pki/sign/moc-van-thu` signs any CSR. Whoever takes over `svc-files` can sign, rotate the signing keys and get
  certificates for keys it generated itself, but cannot export the private keys (no `transit/export`,
  `transit/backup`). This level of trust is as before: `svc-files` could already open every `moc-files` data key.
- **A vault initialised before F4.5 does not sign digitally** until the administrator upgrades it by hand or rebuilds
  the vault: that vault has no PKI, the `svc-files` policy has no right to sign, and the startup token cannot add one.
  When `svc-files` sees that the vault has no CA, it turns digital signing off by itself (log
  `office.signing.disabled`, checked again every 5 minutes): documents are still issued as before, only without a
  digital signature; everything else runs as before. A failed PKI setup while a new vault initialises behaves the same:
  `start.sh` logs "chưa dựng được PKI nội bộ" (internal PKI not set up), the vault still comes up, and it does not try
  again by itself.
- **A vault initialised before anchor signatures existed does not sign anchors** until it is upgraded by hand as below:
  that vault has no `moc-anchor` key, and the `svc-files` policy has no right to sign. `svc-files` still anchors into
  the cold bucket as before, only without a signature (log `core.audit.anchor_unsigned`, once per startup);
  `/api/verify/anchor-key.pem` returns 404, the `/xac-thuc` page hides the anchor block; `moc audit anchor --to`,
  `--publish` write unsigned lines. Old unsigned anchors are still valid when checked. Once the vault is upgraded,
  `svc-files` signs from the next anchoring round, without a restart: the new policy applies at once to the token in
  use.
- Upgrading an old vault by hand, once: first stop the reconciler (systemd timer or cron line, as in the GitOps
  section below), take a backup (`python3 scripts/moc.py backup create`), then from the source folder of the installed
  version run `scripts/nang_cap.sh ket /opt/moc`. If the vault already has the `moc-anchor` key
  (`/api/verify/anchor-key.pem` returns the public key), the script does nothing. The steps:
  1. Temporarily add, at the end of the installation's `platform/openbao/openbao.hcl`, a listener that listens only
     inside the container (`127.0.0.1:8210`, `disable_unauthed_generate_root_endpoints = false`): this turns back on
     the endpoint that creates a root token from the recovery key, which OpenBao turns off by default since 2.5.3; the
     `bao operator generate-root` command needs an existing token from 2.6 on, so it cannot be used here. Restart the
     vault.
  2. Inside the container, create a root token with the recovery key and write it to `root-token` next to the recovery
     key in the `openbao_data` volume. The recovery key, the OTP code and the token pass only through temporary files
     (mode 600) and stdin, never through command-line arguments (which `ps` can see); a step that yields no value
     stops the script, which never writes an empty `root-token`.
  3. Put `openbao.hcl` back exactly as installed and restart the vault. Seeing the root token, `start.sh` runs the
     configuration again — this can be repeated and does not change the secrets, the `moc-files` key or the AppRoles; it
     adds the PKI, the `moc-anchor` key and the new `svc-files` policy — then revokes the token (vault log: "đã cấu hình
     két; token root đã thu hồi", vault configured, root token revoked). The script restarts `svc-files` (which caches
     the result of reading the key for 5 minutes) and waits for `/api/verify/anchor-key.pem` to return a `PUBLIC KEY`
     block; `svc-files` signs anchors from the next anchoring round.

  If any step fails, the script cancels the unfinished root token generation, puts `openbao.hcl` back as it was and
  restarts the vault; fix the error and run it again. If the vault does not finish configuring itself, the root token
  just created stays in the volume: the script prints the commands that revoke and delete it, for when you will not run
  the script again. The CI workflow `.github/workflows/nang-cap.yml` rehearses exactly this script on the vault of the
  previous release, after upgrading the installation: restricted-document files created by the old version still open,
  and smoke passes.
- The last resort is to rebuild the vault (delete the `openbao_data` volume and restart): the secrets are loaded again
  from `.env` and there is a PKI, but the new `moc-files` key is different, so stored restricted-document files can no
  longer be opened — **do not do this on a machine with real data**. The `moc-anchor` key is new as well: anchors
  published before can still be checked with the old key, which remains in the history of the public anchor
  repository.
- Change a secret in `.env`, then `make up`: the vault is recreated and loads the new secrets, and `svc-files`,
  `svc-workflow` restart after it (`depends_on … restart: true`, needs Docker Compose 2.17 or later).

## Public anchors

The audit log is a hash chain; `svc-files` anchors the head of the chain (the last row number and its hash) into a
write-locked cold bucket every 10 minutes, and `moc audit verify` points out rewritten rows by comparing them with the
anchors (`docs/mo-hinh-du-lieu.md` §1). That bucket is still on the server itself. Public anchors take a copy outside,
which anyone can check without trusting the server:

- The vault signs each anchor with the Ed25519 key `moc-anchor` in transit — the vault generates the key and does not
  allow it to be exported; the `svc-files` policy only allows signing and reading the public key. Anchors written while
  the vault had no key (an old vault, section Secrets vault) are still valid, only unsigned.
- Every hour, a timer on the server copies the latest anchor with its signature into `anchors.jsonl` of a **public git
  repository** kept by the unit, commits and pushes. The repository's branch forbids force pushes, so a published
  anchor cannot be taken back, even if the server is taken over.
- Public key: `https://<server>/api/verify/anchor-key.pem` (no sign-in needed), with a copy, `anchor-key.pem`, in the
  anchor repository; its SHA-256 fingerprint is shown at the bottom of the `/xac-thuc` page.

The message the vault signs for an anchor is five UTF-8 lines, each ending with a newline character (`\n`):

```text
signet-anchor-v1
<audit_id: the log row number, decimal>
<hash: 64 lowercase hex characters>
<anchored_at: when the anchor was written to the cold bucket, UTC, as 2026-10-25T01:15:03Z>
<system: the system's public URL, MOC_PUBLIC_URL>
```

The signature is plain Ed25519 (RFC 8032, no pre-hashing). The first line sets this signature apart from any other
signing, and `system` ties the anchor to exactly one system (anchors of a test installation cannot pass for anchors of
the real one). Every field is derived from the anchor locked in the bucket, so signing an anchor again gives the same
signature. Each line of `anchors.jsonl` holds every field needed to rebuild the message, with the key fingerprint
(`key`, SHA-256 of the public key's DER) and the signature (`sig`, base64) — one line in the file, broken here to make
it easier to read:

```json
{"v": "signet-anchor-v1", "audit_id": 42, "hash": "abab…ab", "anchored_at": "2026-10-25T01:15:03Z",
 "system": "https://signet.example", "key": "sha256:06e3fd8f…", "sig": "6Zd3HmfkSkXW…"}
```

### Setup (once)

1. **Create a separate public repository** for the anchors, e.g. `signet-anchors` on the unit's GitHub, GitLab or
   Gitea — holding nothing else, not shared with the source code. Protect the default branch: **no force pushes, no
   branch deletion**, no required review (the server pushes directly). GitHub: Settings → Rules → Rulesets (or
   Branches) → turn on *Block force pushes* and *Restrict deletions* for the default branch, with no one allowed to
   bypass them (administrators included). GitLab: Settings → Repository → Protected branches, *Allowed to force push*
   off.
2. **A deploy key** that can write only to that repository; not a personal token or anyone's own key. On the server,
   as the `moc` operator user:
   ```bash
   ssh-keygen -t ed25519 -N '' -C "signet-anchor@$(hostname)" -f ~/.ssh/signet-anchors
   cat >> ~/.ssh/config <<'CONF'
   Host signet-anchors
     HostName github.com
     User git
     IdentityFile ~/.ssh/signet-anchors
     IdentitiesOnly yes
   CONF
   ```
   Add `~/.ssh/signet-anchors.pub` to the repository: GitHub Settings → Deploy keys → *Allow write access*; GitLab
   Settings → Repository → Deploy keys → *Grant write permissions*. This key cannot read or write any other
   repository.
3. **The clone on the server**, at exactly the path in `platform/systemd/moc-anchor-publish.service`:
   ```bash
   sudo install -d -o moc -g moc /var/lib/moc
   sudo -u moc git clone signet-anchors:<organisation>/signet-anchors.git /var/lib/moc/neo-cong-khai
   sudo -u moc python3 /opt/moc/scripts/moc.py audit anchor --publish /var/lib/moc/neo-cong-khai   # try one round
   ```
   The first round commits `anchors.jsonl` and `anchor-key.pem` with the fixed author "Signet anchor" and the message
   `Anchor #<row number> <first 16 hex characters of the hash>`, then runs `git push` to `origin`.
4. **Timer** (sample files, like the GitOps reconciler):
   ```bash
   sudo cp platform/systemd/moc-anchor-publish.service platform/systemd/moc-anchor-publish.timer /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now moc-anchor-publish.timer
   journalctl -u moc-anchor-publish -f
   ```

`--publish` only adds commits: never `--force`, no amend, no history rewriting. If the head of the chain has not
changed, there is no new commit. If the push fails (network down, the repository refuses), the command exits 2, the
commit stays in the clone and the next round pushes it; if the branch on the repository has moved elsewhere (someone
pushed a different commit), the push is refused and the operator has to look by hand — the command never forces. If
the clone has no remote, it only commits locally. Without a git repository: `moc audit anchor --to FILE` only appends
lines to a file, to be copied out some other way.

Once the vault has a key, no anchor is written to a file without a signature: if the vault does not answer when
signing (or when asked for the key), if the file already has signed lines, or if there is already an `anchor-key.pem`
next to the file, `--to`/`--publish` do not write the unsigned line, exit 2, and the next round signs again (the same
anchor gives the same signature). This lets a checker treat an unsigned line after a signed line as a removed
signature — an error, like a wrong signature. `--publish` writes `anchor-key.pem` only when the file already has a
signed line, so an `anchor-key.pem` next to a file with no signed line left is also an error; `anchor_sig.py` exits 2
when it finds no signed line (nothing has been checked yet). Unsigned lines before every signed line are anchors
written while the vault had no key: if someone removes the signatures of the first lines of the file (keeping the
signed lines after them), only the git history of the public repository shows it (the `git log -p` command below).

### Checking from outside (only git, jq and OpenSSL 3 needed)

```bash
git clone https://github.com/<organisation>/signet-anchors.git && cd signet-anchors
# the system's real key: the fingerprint must match the one at the bottom of https://<server>/xac-thuc
openssl pkey -pubin -in anchor-key.pem -outform DER | sha256sum
# the history only adds lines: this command prints nothing (no line of anchors.jsonl was ever changed or deleted)
git log -p --format= -- anchors.jsonl | grep '^-[^-]'
```

Checking the signature of one line (here the last line; for another line replace `tail -n 1` with
`sed -n <line number>p`):

```bash
tail -n 1 anchors.jsonl > line.json
jq -r '.v, .audit_id, .hash, .anchored_at, .system' line.json > msg.bin     # exactly the five signed lines
jq -r .sig line.json | openssl base64 -d -A > sig.bin
openssl pkeyutl -verify -pubin -inkey anchor-key.pem -rawin -in msg.bin -sigfile sig.bin
```

`Signature Verified Successfully`: the line was signed by the system's vault and not one character has changed.
Without jq, write the message by hand from the line's fields:
`printf '%s\n' signet-anchor-v1 <audit_id> <hash> <anchored_at> <system> > msg.bin`. To check the whole file at once,
from the Signet source: `python3 scripts/anchor_sig.py anchors.jsonl anchor-key.pem` (plain Python, nothing to
install, no running system needed).

The unit compares the log with the published anchors on the server: `python3 scripts/moc.py audit verify --anchors
/var/lib/moc/neo-cong-khai/anchors.jsonl` — checks the signature of each line (with the `anchor-key.pem` next to the
file, `--key`, or the vault's current key), then compares each anchor with the recomputed chain: an anchor that differs
means the log was rewritten from around that point; a line with a wrong signature, or an unsigned line after a signed
line, is an error (exit code 1) and is not used to draw a conclusion.

The limits, stated plainly:

- The signature proves that the line was signed by the system's vault, not that the log is right: someone who takes
  over `svc-files` can sign new anchors for a rewritten chain. What stops them is that old published anchors cannot be
  taken back — the branch forbids force pushes, and other people have cloned it — so the old anchors disagree with the
  new log and `moc audit verify --anchors` points it out.
- `anchored_at` is the time of the object store on the server; the time in the commit is also set by the server.
  Independent evidence of time is when the git provider recorded the push (GitHub: the repository's Activity page) and
  other people's clones.
- The deploy key is on the server: someone who takes over the server can add commits (including commits that change
  old lines) but cannot delete history; the `git log -p … | grep` command above shows it at once.
- Rebuilding the vault gives a new `moc-anchor` key: `anchor-key.pem` in the repository is overwritten on the next
  round, and anchors signed before are checked with the old key in the history (`git log -p -- anchor-key.pem`); the
  `key` field of each line says which key.
- The public repository lets outsiders see the pace of activity (log row numbers per hour) and the system URL, but no
  content: a hash is only a hash.
- A printed document register (`/api/registers/…/pdf`) carries the latest anchor at print time in its footer
  (`Audit anchor #<number> · <16 hex characters> · <time>`; `Mốc neo #…` when printed in Vietnamese): finding that
  line in the anchor repository shows that the audit log at print time has not been rewritten since.

## GitOps and self-healing

`scripts/reconcile.py` brings the running system back to the state declared in git, one round per call. On the
server, a systemd timer calls it every 60 seconds (sample files in [`platform/systemd/`](../platform/systemd/); it runs
on the server, not in a container: no container gets the Docker socket mounted); on a machine without systemd (WSL2),
the `moc` user's cron calls it every minute ([`trien-khai.md`](trien-khai.md) section 7). Each round:

- **Self-healing**: an unhealthy container is restarted; a service declared in compose whose container is missing or
  stopped is brought up again (`docker compose up -d` for exactly those services). The one-off service
  `keycloak-fonts` (copies the sign-in theme's fonts into a volume, #305) has finished with exit code 0 and does not
  count as stopped. Try it: `make demo-tu-phuc-hoi` (`docs/demo-script.md`).
- **GitOps** (when `MOC_GITOPS_DIR` is set in the installation's `.env`): pulls the `MOC_GITOPS_BRANCH` branch (default
  `deploy`) into the reconciler's own git clone. On the first run, if the clone has uncommitted changes, the reconciler
  refuses and deletes no one's work; once a commit has been applied, every apply runs `checkout -f` and `clean -fd` on
  the clone, so do not edit anything in it by hand. When there is a new commit, or an installed file has been edited by
  hand (its hash differs from install time), it builds that commit's images, stops Signet, installs exactly that
  commit into the install folder and starts again. If the install breaks halfway, it reinstalls the commit that was
  running before. A commit that fails to apply is not retried every minute; the reconciler waits for the next commit.

```bash
# on the server, after make install PREFIX=/opt/moc; the moc operator user is in the docker group. The deploy branch
# must exist on GitHub: the repo has none yet, so -b deploy fails until it is created (docs/git_flow.md section 7)
sudo install -d -o moc -g moc /opt/moc-src      # the reconciler runs as moc, and moc cannot create folders in /opt
git clone -b deploy https://github.com/HIT-Champion/Signet.git /opt/moc-src
echo "MOC_GITOPS_DIR=/opt/moc-src" >> /opt/moc/.env
python3 /opt/moc/scripts/reconcile.py          # try one round
sudo cp platform/systemd/moc-reconcile.* /etc/systemd/system/ && sudo systemctl enable --now moc-reconcile.timer
```

- Applying a commit is a full reinstall: Signet stops for about a minute (`install.sh` does not swap configuration
  under running containers). Old images of earlier commits are not deleted automatically.
- Extra profiles in the installation's `MOC_EXTRA_PROFILES` (`tunnel`, `ai`…) go with every compose command of the
  reconciler, as in the `Makefile`: applying a commit stops and starts them too, and self-healing sees them (#351).
- `.env` (secrets, the server's own configuration) is not in git, and the reconciler does not touch it.
- A reconciler round is skipped during a backup, a restore or `make install` (all three share one lock on the install
  folder), when the previous restore stopped halfway (Signet is not started on half-restored data: run `backup restore`
  again), or when a service is paused on purpose. A service still paused by a backup that was killed hard is started
  again by the reconciler.
- For manual maintenance (`docker compose down`, trying a configuration change), stop the timer first: `sudo systemctl
  stop moc-reconcile.timer`, otherwise the reconciler brings everything back within a minute. When the reconciler runs
  from cron, put `#` in front of the cron line (`crontab -e`): `scripts/nang_cap.sh` only detects a running systemd
  timer, not a cron line.
- `make smoke` and `make demo-tu-phuc-hoi` call `reconcile.py --heal-only`: self-healing only, no new commits pulled.
- **Apply signed commits only** (recommended on a real server): set `MOC_GITOPS_ALLOWED_SIGNERS` to an
  allowed_signers file listing the SSH keys of the people allowed to push the `deploy` branch. The reconciler runs
  `git verify-commit` on the branch's head commit before stopping Signet; an unsigned commit, one signed with an
  unknown key, or one signed with OpenPGP/X.509 (even when the key is in the `moc` user's keyring) is not applied,
  Signet keeps running the old version, and the next round checks again (adding the key to the file is enough for it to
  be applied, no new commit needed).

```bash
# machine of the person who pushes the deploy branch (once): sign commits with an existing SSH key (.pub when the key
# is in ssh-agent; without an agent, point to the private key file ~/.ssh/id_ed25519)
git config --global gpg.format ssh && git config --global user.signingkey ~/.ssh/id_ed25519.pub
# server: the list of allowed keys (only root can edit it; id_ed25519.pub copied from the pusher's machine), then enable
sudo install -d /etc/moc && echo "releaser@example namespaces=\"git\" $(cat id_ed25519.pub)" |
  sudo tee /etc/moc/allowed_signers
echo "MOC_GITOPS_ALLOWED_SIGNERS=/etc/moc/allowed_signers" >> /opt/moc/.env
```

  The head of the `deploy` branch must be a commit signed by someone on the list: bring a release in with
  `git merge --no-ff -S` instead of `--ff-only` (`docs/git_flow.md` section 7) — a merge commit made on GitHub carries
  GitHub's OpenPGP signature and is not accepted.
- **Production: upgrade with a backup, roll back on failure** (`MOC_GITOPS_MODE=nang-cap`, #344): a new commit on
  `deploy` is not reinstalled straight away with `install.sh`; it goes through the manual upgrade path of that commit,
  `scripts/nang_cap.sh nang` (build while the site is still up, backup, stop, install, realm, data, service and smoke
  checks). A failure before the backup leaves the old version running. A failure after it, a failed check included,
  makes the reconciler run `nang_cap.sh lui` back to the previous commit (its source extracted with `git archive` into
  `.git/moc-lui` of the clone, with the `.env` from before) and restore the backup it had just taken: data written
  during the checks is lost. The failed commit is not retried; the reconciler waits for the next one. The output of the
  latest upgrade and rollback is in `moc-nang-cap.log` inside the clone's `.git` directory. The version written into
  the installation (`/api/status`) is the tag whose tree matches the `deploy vX.Y.Z` commit, not `X.Y.Z-1-g…`. On the
  first run, when the running installation already matches the tag at the head of `deploy` (same tree), the reconciler
  only records it and does not stop the site to reinstall. Enable it together with `MOC_GITOPS_ALLOWED_SIGNERS`.
  Limitation (#491): the checks always run smoke, and smoke signs in with the sample accounts through the `moc-cli`
  client (and writes test data). On a machine with real data (`seed.py` not run, `MOC_CLI_CLIENT_ENABLED=false`,
  `trien-khai.md` section 3) every upgrade fails its checks and rolls back: for now this mode only works on a machine
  with sample data, like the online site.
- **Every release upgrades production** (`MOC_GITOPS_FOLLOW=release` with `MOC_GITOPS_BRANCH=main`): the reconciler
  applies the newest `vX.Y.Z` tag reachable from `main` instead of the branch head. Untagged commits on `main`, `-rc`
  tags and tags not yet on `main` are never applied. With `MOC_GITOPS_ALLOWED_SIGNERS` set, the tag's signature is
  checked (`git verify-tag`), because merge commits on `main` carry GitHub's OpenPGP signature: the tag must be signed
  with an SSH key on the list (`git tag -s`). But `make release` (`scripts/release.sh`) currently tags with
  `git tag -a`, unsigned, so with this variable set the reconciler accepts no release tagged by that command and the
  old version keeps running (#492). Without it, anyone who can push a `v*` tag to GitHub can put a version on the
  server: restrict that with a ruleset on tags.

```bash
# production: every release on main upgrades the site, with a backup and automatic rollback (real data: not yet, #491)
sudo install -d -o moc -g moc /opt/moc-src      # as above: moc cannot create folders in /opt
git clone -b main https://github.com/HIT-Champion/Signet.git /opt/moc-src
printf '%s\n' MOC_GITOPS_DIR=/opt/moc-src MOC_GITOPS_BRANCH=main MOC_GITOPS_FOLLOW=release \
  MOC_GITOPS_MODE=nang-cap >> /opt/moc/.env
python3 /opt/moc/scripts/reconcile.py          # first run: adopts the running version if it is the newest tag

# or the signed deploy-branch gate: the releaser brings each tag in (their key is in the server's allowed_signers)
git switch deploy && git merge -S --no-ff vX.Y.Z -m "deploy vX.Y.Z" && git push origin deploy
```

## Malware scanning (ClamAV)

Every uploaded file goes through ClamAV before it is stored. The `clamav` container downloads new signatures by itself
(freshclam, once a day); the operator has nothing to do. There is one limitation (#287): each time clamd reloads its
signatures, it stops scanning until the reload is done. Measured: about 10 seconds on the CI machine, 8 seconds with a
test container on the machine that runs the online instance; a busy or weak machine may take up to about 1 minute. The
reason is that compose sets `ConcurrentDatabaseReload no` to save RAM (#288 measures this choice again). Clamd reloads
at two moments:

- once a day, right after freshclam downloads a new signature version;
- about 10 minutes after ClamAV starts (`make up`, an upgrade, a machine restart), if freshclam happened to download a
  new version at startup.

How to recognise it and what to do:

- **What users see:** the file stays at "Uploading and scanning for malware…". After 60 seconds
  (`CLAMAV_TIMEOUT_S` of `svc-files`) it reports that the malware scanner is not ready (`503 scanner_unavailable`), and
  the file has not been stored. The status page may show "Malware scanning" as down during that time.
- **What to do:** wait about 1 minute, then upload again. Nothing needs restarting: restarting `clamav` only makes it
  load the signatures again from the start.
- **How to spot it in the logs:** on the server, in the install folder, run `docker compose logs clamav`. When a reload
  starts there is a line "SelfCheck: Database modification detected. Forcing reload" or "Clamd successfully notified
  about the update", then "Reading databases from /var/lib/clamav". When it is done there is "Database correctly
  reloaded".
- **Testing uploads right after an upgrade:** a log line "daily.cld updated" (or "daily.cvd updated") with "Clamd was
  NOT notified" means clamd will reload by itself about 10 minutes after startup. To test right away, make it reload
  now: run `docker compose exec -T clamav clamdscan --reload`, wait for the line "Database correctly reloaded", and only
  then upload.
- **Downloading new signatures now, without waiting for the daily round.** For example before an upgrade, so that the
  signatures are already the newest at restart and clamd does not have to reload midway. The command:

  ```bash
  docker compose exec -T clamav freshclam --log=/tmp/freshclam-tay.log
  ```

  - **`--log` is required.** The background freshclam holds a lock on the log file `/var/log/clamav/freshclam.log`, so
    without this flag the command reports "Failed to lock the log file" and stops without updating anything.
  - **Running as root is still safe.** The command drops root privileges according to `DatabaseOwner`, so the
    signature files still belong to the `clamav` user and the background freshclam can keep updating them.
  - **If there is a new version, clamd reloads at once.** freshclam reports "Clamd successfully notified about the
    update"; uploads stop until the log shows "Database correctly reloaded". Measured with a test container on the
    machine that runs the online instance: about 8 seconds; it may take longer while the machine is busy.
  - **Already up to date:** the command only reports "database is up-to-date".
  - **Still a lock error:** the background freshclam may be updating by itself; wait 1 minute and run it again.

## Official public holidays (public data source B)

Suggested due dates (F4.3) skip Lunar New Year, the Hung Kings' day, days off in lieu, and count make-up Saturdays as
working days, following the official calendar for civil servants and public employees (#427). The snapshot lives in
`seed/du-lieu-mo/ngay-nghi-le/`:

- `ngay-nghi.json`: fixed holidays (Article 112 of the Labour Code, Vietnam Culture Day 24/11), the days off of each
  year, make-up working days; each entry names the document it comes from;
- `trich/*.txt`: quotes from the Government News articles that state those dates, with the article URL;
- `manifest.json`: URL, fetch date, SHA-256 of each file, reuse basis (Article 15 of the Law on Intellectual Property),
  maximum age 400 days.

`docker-compose.yml` mounts this folder read-only into svc-workflow; `MOC_HOLIDAYS_FILE` (default
`/app/du-lieu-mo/ngay-nghi-le/ngay-nghi.json`, empty turns it off) adds the calendar to `MOC_HOLIDAYS`. Without the
file only `MOC_HOLIDAYS` applies, as before; a broken file stops svc-workflow at start-up with a `MOC_HOLIDAYS_FILE`
error.

Refresh it when the Government announces the next year's days off (usually in October), no Docker needed:

1. add an entry to `PAGES` in `scripts/nguon_ngay_nghi_le.py`: article URL, quote file, date range, and the date strings
   exactly as the article writes them;
2. `python3 scripts/nguon_ngay_nghi_le.py` fetches every article again and checks each date is on its page before it
   replaces the snapshot. A page that does not load or has lost a date makes it exit 1 and keeps the old snapshot;
3. `docker compose restart svc-workflow`. Suggestions already saved keep their due dates.

If the source stops working, suggestions keep using the snapshot; for a year the snapshot does not cover, add the days
to `MOC_HOLIDAYS`.

## Monitoring

APISIX counts every request through the gateway (plugin `prometheus`; the metrics export port 9091 is not published:
only containers on the `moc` and `apps` networks can reach it — application containers can read the counts per route,
with no tokens or business data). Prometheus also scrapes the status table of `svc-files` (`GET /metrics`, #274): one
`moc_component_up` line per component of the `/trang-thai` page, with the same probes and 10-second cache as
`/api/status`; `/metrics` can be called only inside the `moc` network, and returns 404 through the API gateway.
Prometheus scrapes every 15 seconds, keeps `MOC_METRICS_RETENTION` (default 15 days), and opens no port to the outside.
Grafana shows the preloaded dashboard **Signet — cổng API** (API gateway): requests per second per route, status codes
(429 = rate limit exceeded), 5xx error ratio, p95 latency, bandwidth, open connections.

- Grafana listens only on `127.0.0.1:MOC_GRAFANA_PORT` (default 3300) on the server — view it from another machine
  through an SSH tunnel: `ssh -L 3300:127.0.0.1:3300 server` then open `http://localhost:3300`.
- There are no Grafana accounts: whoever reaches that port can only view. Dashboards are edited in
  `platform/monitoring/grafana/dashboards/` and installed again, not edited in the interface.
- Grafana (AGPL-3.0) runs unmodified in its own container; Signet only loads configuration through files and does not
  link to its code.
- Metrics are not part of the backup (`make backup`): after a restore, Prometheus starts collecting from scratch.
- Prometheus reads `platform/monitoring/prometheus.yml` and `canh-bao.yml` only at startup, and so does Alertmanager
  with `alertmanager.yml`. After a manual edit on a running machine, restart that service: `docker compose restart
  prometheus` (`alertmanager`) in the install folder. During an upgrade, `scripts/nang_cap.sh` already stops and starts
  the whole system, so the new version loads the new files by itself.

### Alerts

Prometheus evaluates 8 rules in `platform/monitoring/canh-bao.yml` every 15 seconds: the `cong-api` group on the APISIX
metrics (#255), the `thanh-phan` group on the svc-files status table (#274). The `route` label is the route id in
`platform/apisix/apisix.yaml`; the `component` label is the component code in `services/svc-files/README.md`, section
Trạng thái hệ thống (system status).

| Alert | Severity | Fires when |
|---|---|---|
| `GatewayMetricsDown` | critical | Prometheus has not been able to scrape APISIX metrics for over 2 minutes: the gateway may have stopped |
| `UpstreamUnreachable` | critical | A route returns 502 or 504 continuously for 3 minutes: APISIX generates these two codes itself when the service behind the gateway is dead or times out |
| `High5xxRatio` | warning | Over 5% of requests fail with 5xx within 5 minutes, when there are more than 0.1 requests/second |
| `SlowRoute` | warning | p95 response time above 3 seconds for 10 minutes, on the routes graphql, app-office, app-ca-nhan, keycloak, dang-nhap, dang-nhap-post |
| `ComponentDown` | critical | A required component (`cong-api`, `dang-nhap`, `csdl`, `quet-ma-doc`, `quy-trinh`, `luu-tru`) has been down for over 2 minutes: the `/trang-thai` page reports all of Signet as down |
| `OptionalComponentDown` | warning | The key vault (`ket-khoa`) or search (`tim-kiem`) has been down for over 5 minutes |
| `StatusMetricsDown` | critical | Prometheus has not been able to read svc-files' `/metrics` for over 2 minutes: svc-files may have stopped. The `moc_component_up` lines then disappear rather than drop to 0, so `ComponentDown` does not fire |
| `AlertRulesFailing` | warning | Prometheus failed to evaluate rules in the last 10 minutes |

- See the "Cảnh báo đang bật" (firing alerts) row at the bottom of the Grafana dashboard. `pending` means the condition
  is already true but has not yet lasted the rule's duration. On the server, in the install folder:
  `docker compose exec -T prometheus wget -q -O - http://localhost:9090/api/v1/alerts`.
- Firing alerts go on to Alertmanager (#284, `platform/monitoring/alertmanager.yml`): grouped by alert name, it waits
  30 seconds before the first send, sends the changes every minute, and repeats an alert still firing after 12 hours.
  Alertmanager calls `svc-workflow` (`POST /ops/alerts`, token `MOC_ALERT_TOKEN`): each firing and each resolution is a
  notification in the bell of every unit administrator (role `tenant_admin`) of every unit, and clicking it opens the
  `/trang-thai` page. If the installation has turned on email, webhook, SMS or Zalo (section Thông báo đa kênh,
  multi-channel notifications), alerts go through that channel as well, unless `MOC_NOTIFY_*_KINDS` lists kinds
  without `ops.alert`.
- A notification carries only the rule's `summary` sentence, the severity, and the `component` and `route` labels.
  When Alertmanager sends again (the 12-hour reminder, or a restart that lost its send log), no row is added: the
  de-duplication key is the fingerprint, the firing time and the state.
- `MOC_ALERT_TOKEN`: generated by `make env`; if an old `.env` lacks this line, `make up` and `make install` (and
  `scripts/nang_cap.sh`) add a random string by themselves. Leaving it empty turns sending off: Alertmanager runs
  `alertmanager-khong-gui.yml` (receives without sending), and `POST /ops/alerts` returns 404. The token is a secret of
  svc-workflow in the vault; to change it: edit `.env`, `docker compose up -d` (recreates `openbao`, `alertmanager`),
  then `docker compose restart svc-workflow`.
- Alertmanager's API on 9093 has no sign-in (pushing alerts, creating silences): Alertmanager sits only on the `alerts`
  network (`internal`) with Prometheus and `svc-workflow`; other services on the `moc` network cannot reach it.
- Limitation: when PostgreSQL, Hasura or `svc-workflow` is down, the alert about that very outage cannot reach the bell
  yet (`svc-workflow` returns 503, and Alertmanager sends again later); meanwhile only Grafana and Prometheus see it. A
  failed send because of a wrong token (401) has no alert of its own: Prometheus does not scrape Alertmanager's metrics
  yet. Silencing an alert for a while has to be done with `amtool` in the container:
  `docker compose exec alertmanager amtool silence add alertname=<name> --comment=<reason>
  --alertmanager.url=http://localhost:9093`.
- Try the whole path: `make demo-canh-bao` (a fake alert, real services untouched). Alerts Alertmanager is holding:
  `docker compose exec -T alertmanager wget -q -O - http://localhost:9093/api/v2/alerts`. If sending fails, look at
  `docker compose logs alertmanager` and the `ops.alert.failed` line of svc-workflow.
- 503 does not count as "not responding". svc-files returns 503 on purpose (`busy`, `scanner_unavailable`… with
  `Retry-After`), so 503 counts only toward the 5xx ratio. The latency of svc-files is not considered: uploading,
  reading incoming documents and question answering are slow by design.
- svc-workflow has no route of its own but sits behind Hasura Actions; its errors reach the browser as GraphQL 200 with
  `errors`, so the `cong-api` group does not see them. The `thanh-phan` group sees them through the `quy-trinh`
  component: the status table calls svc-workflow's `/readyz`, which includes a check of Flowable.
- The `cong-api` group relies on real traffic: if nobody calls a service, this group does not see it die. The
  `thanh-phan` group needs no traffic: Prometheus scrapes the status table every 15 seconds.
- The AI assistant has no alert: when Ollama does not answer, the status table reports `off` just as when it is not
  turned on (the two cannot be told apart), and an `off` component has no `moc_component_up` line.
- Changing a threshold: edit `canh-bao.yml` together with the matching case in
  `platform/monitoring/kiem-tra/canh-bao.test.yml`, run `promtool test rules` as the "Giám sát" step of the build job in
  `.github/workflows/ci.yml` does, then install again.

## Public data

Signet ships snapshots of public government data in `seed/du-lieu-mo/<source code>/` (#424): the original files and a
`manifest.json` with the URL, fetch date, reuse basis and SHA-256 of each file. Source A `cong-bao-gddt`: four
circulars of the Ministry of Education and Training on higher education, as published in the Official Gazette
(`seed/du-lieu-mo/cong-bao-gddt/README.md`).

- **An installed copy never calls the source at run time.** `svc-files` reads the manifests through the read-only
  mount `/srv/du-lieu-mo`, checks the SHA-256 and reports in `GET /api/status` (key `open_data`: `ok`, `stale` past
  `max_age_days`, `broken` when a file is missing or its hash differs) and on `/trang-thai`. If the source goes
  offline Signet keeps using the latest snapshot, and the status page shows how many days old the data is.
- **Import:** `make seed` imports each file as an incoming document of the IT faculty through the batch import API
  (CSV + zip, ClamAV, as a clerk would), type "Thông tư" (migration `1792281604000_document_type_tt`). On a copy that
  already has its sample data run `python3 scripts/moc.py du-lieu-mo nap`; running it again creates no duplicates. The
  document page recognises a document from a public source because the SHA-256 of its attachment matches the
  manifest; the assistant quotes it like any incoming document.
- **Check:** `make du-lieu-mo` (`python3 scripts/moc.py du-lieu-mo kiem`) compares the hashes and prints the age of
  the data; it exits 1 when a snapshot is broken.
- **Refresh** (on a team machine with Internet access, not on the server): `make du-lieu-mo-lay`. The command only
  replaces a snapshot once every file has downloaded, matches the manifest and the total stays within 3 MB; if the
  source fails it keeps the old snapshot and exits 1. A new snapshot goes through a pull request like any file in
  `seed/`.
- **Adding a source:** a module `scripts/nguon_<code>.py` with `NGUON`, `TEN` and `lay(thu_muc)` returning a manifest
  (template in `scripts/du_lieu_mo.py`). Only use sources with a clear reuse basis (an open licence, or Article 15 of
  the Law on Intellectual Property for state documents), follow `robots.txt` and the site terms, take no personal
  data, and declare the files' licence in `REUSE.toml`.

## Assistant answers through an external API

By default the question-answering assistant (F4.2) writes its answers with a model running locally in Ollama. On a
slow machine (CPU only), or to use a larger model, the writing step can go to a server that speaks the OpenAI API
(#430): vLLM or llama.cpp on a GPU machine of the unit, or a cloud service. Set in `.env`:

```
MOC_ASK_API=openai
MOC_ASK_API_URL=https://model-server/v1
MOC_ASK_MODEL=<model name that server accepts>
MOC_ASK_API_KEY=<key, empty if the server needs none>
```

then `docker compose up -d` (recreates `openbao`, `svc-files`). To change the key later: edit `.env`,
`docker compose up -d`, then `docker compose restart svc-files`.

- **What leaves the machine:** only the answer-writing call: the question and at most 4 source passages, **masked**
  first (phone numbers, citizen ID numbers, email addresses, bank account numbers; F4.4). Semantic search (the
  embedding model) and incoming-document summaries stay in Ollama; without the `ai` profile the assistant searches by
  keyword and only the writing step uses the API. An open-weight model (Apache-2.0) running locally remains the
  recommended default: sending documents to a cloud service is the unit's own decision about its data.
- **Same checks:** the output is forced to a JSON Schema (`response_format`), and Signet still checks every sentence
  against the source passages and numbers before adding citations; otherwise it returns the verbatim quote.
- **Key:** a `svc-files` secret in the vault like the other keys (section Secrets vault), not in the `svc-files`
  container environment, never logged. It is only sent in the `Authorization` header to `MOC_ASK_API_URL`. With an
  `http://` URL `svc-files` logs `config.warning` at start-up: the key and the passages travel unencrypted, which only
  suits a model server on a trusted internal network.
- **Model name:** `MOC_ASK_MODEL` is required and must be a name that server accepts (e.g. `Qwen/Qwen3-4B` on vLLM);
  it does not fall back to `MOC_AI_MODEL` as it does for local answers. Without it `svc-files` stops at start-up.
- **Readiness:** `svc-files` calls `GET {MOC_ASK_API_URL}/models` at start-up and every 60 seconds; a wrong key (401,
  403) or model name (404) counts as not ready until the next probe. Log events `office.assist.ai_ready`,
  `office.assist.ai_unavailable` carry `"where": "external"` and the HTTP code, never the key.
- **Audit log:** the `assistant.answered` row records `model` and `model_where` (`local`: Ollama; `external`: the API).

## System status page

`<MOC_PUBLIC_URL>/trang-thai` is a public page, with no sign-in needed: users can see for themselves whether Signet is
running normally before calling the technical staff. The sign-in page (on errors), the footer of the verification
portal and the sidebar after sign-in all link here. While open, the page refreshes itself every 30 seconds.

- **What it shows:** the overall state and each component (*Operational*, *Partial*, *Down*, *Off*) by layer, users →
  core → process → data → intelligence: API gateway, Single sign-on, Database, Key vault, Malware scanning, Workflow,
  File storage, Search, AI assistant; the version (`MOC_VERSION`), how long `svc-files` has been running, the time of
  the latest backup, and whether the AI assistant is on or off with the model name.
- **How to read it:** if the API gateway, Single sign-on, Database, Malware scanning, Workflow or File storage is down,
  the overall state is *Service disruption*. If the Key vault, Search or AI assistant is down, or a component runs only
  in part, it is *Some components are having problems*: restricted documents and digital signing (vault), search and
  question answering are unavailable for the time being, and the rest still runs. The AI assistant is *Off* when the
  `ai` profile is not on, question answering is turned off, or Ollama does not answer: the page cannot tell these three
  cases apart, so if it shows *Off* while the `ai` profile is on, look at `docker compose logs ollama`. The assistant
  still searches by keyword. When answers are written through an external API (section below), the component's
  software reads "API ngoài".
- **What it does not reveal:** only fixed labels and states; no host names, IP addresses, internal URLs, per-component
  versions, user or document counts, or error messages. The specific reason is in the `svc-files` log (event
  `core.status.changed`, written when a component changes state): `docker compose logs svc-files | grep
  status.changed`.
- **Not an attack path:** `svc-files` caches the result for 10 seconds for everyone, and each probe of a component
  takes at most 3 seconds (defaults of `MOC_STATUS_CACHE_S`, `MOC_STATUS_TIMEOUT_S` in `svc-files`; compose does not
  pass these two variables, so setting them in `.env` has no effect); APISIX limits each IP address to
  `MOC_RATE_STATUS_PER_MIN` (default 30) requests a minute, and returns `429` beyond that.
- The page only answers "running or not" right now; trends over time, latency and error ratios are in Grafana (section
  Monitoring). API: `GET /api/status` ([`docs/api/README.md`](api/README.md) §3).

## Centralised logs

The `logs` profile (off by default) gathers the services' logs in one place so they can be searched by **request id**.
APISIX attaches an `X-Request-Id` to every request (keeping the id the client sent, returning it in a response header)
and writes it at the end of the access line; Hasura passes the id on to `svc-workflow`; `svc-workflow` writes the id in
its log and sends it on to Hasura and `svc-files`. The same id appears in the log lines of APISIX, `svc-workflow`,
Hasura and `svc-files`, and in the `request_id` column of the audit log `core.audit_log`.

The path: Docker's `fluentd` log driver → **Vector** 0.59 (port `127.0.0.1:24224` on the server; extracts the request
id, redacts a second time) → **Parseable** 3.2 (stored on the `parseable_data` volume, API and interface at
`127.0.0.1:8400`, account `moc`). The driver is set in the compose override file
[`platform/logs/docker-compose.logs.yml`](../platform/logs/docker-compose.logs.yml), loaded only when the profile is
on. No `docker.sock` is mounted and `/var/lib/docker` is not read. `docker logs` and `make logs` still read as before
(Docker keeps a local copy of 10 MB × 3 for external drivers).

- **Collected:** `apisix`, `app-office`, `app-ca-nhan`, `svc-files`, `svc-workflow` — the services that redact
  personal data in their own logs (F4.4) — plus `hasura`, `keycloak`, `postgres`, `meilisearch`: these four do not
  redact by themselves, so Vector redacts them with dedicated rules (below) before the shared redaction step. **Not
  collected:** OpenBao, Flowable, SeaweedFS…: they have no dedicated rules yet, and putting them in the log store would
  carry unredacted personal data one place further.
- **Dedicated rules** for the four services that do not redact by themselves, each rule with a case in
  `vector.test.yaml`:
  - **Hasura** (JSON lines): `event` is `hasura.<log type>` (`hasura.http-log`, `hasura.websocket-log`…);
    `request_id` is taken from `detail` (`detail.request_id`, `detail.operation.request_id`, and in `websocket-log`
    `detail.event.detail.request_id`). That is the `X-Request-Id` that APISIX, `svc-workflow` and `svc-files` send with
    their GraphQL calls, so `make logs-tra` returns Hasura's lines too. The keys `query`, `raw_query` when they are
    strings (the GraphQL query, the request body) and the whole `query.variables` branch (keys inside a `jsonb`
    variable are data too), `generated_sql` (from `query-log`, off by default), and an error's `internal` (parameters,
    the SQL statement, PostgreSQL's `DETAIL`) are replaced with `[REDACTED]`; `operationName` is kept. Hasura 2.51
    logs the query and variables each time a subscription opens. Its failed `http-log` lines have only `code`, `error`,
    `path`, even with the admin role and `DEV_MODE=true` (tried on 26/10/2026). The `raw_query` and `internal` rules
    guard against other versions.
  - **PostgreSQL**: each log entry starts with the default prefix `%m [%p] ` followed by the level (`ERROR:`,
    `DETAIL:`…). Lines without the prefix are dropped: they are continuation lines of a multi-line entry (a statement
    or a failing row containing a line break) or messages of the init script; there is no knowing which entry they
    belong to, so they cannot be redacted correctly. What is redacted:
    - `STATEMENT:`, `QUERY:` keep only the first word (`STATEMENT:  insert [REDACTED]`);
    - `DETAIL:` redacts key values (`Key (email)=([REDACTED]) already exists.`), the failing row (`Failing row contains
      ([REDACTED]).`), and the `Token "…"` of invalid JSON;
    - `CONTEXT:` redacts quoted statements (`SQL statement "…"`) and the excerpt after `line N:` (`JSON data`, `COPY`);
    - parameters `$1 = '…'`, and values of the wrong type (`invalid input syntax for type uuid: "…"`, `malformed array
      literal: "…"`; this rule also runs on error messages that Hasura passes through unchanged).

    A line that stops in the middle of a value (a value containing a line break) is redacted to the end of the line.
    `ERROR:` messages are kept as they are: the messages of the functions in `db/migrations` contain only codes,
    states and case file numbers. Changing `log_line_prefix` makes every line get dropped.
  - **Keycloak**: `username="…"` in `LOGIN_ERROR` events (the user name as typed: a password typed into the user name
    field by mistake would leak). `userId`, `clientId`, `error` are kept. `sessionId` and the query string of
    `redirect_uri` are already redacted by the shared step.
  - **Meilisearch** writes JSON (`MEILI_EXPERIMENTAL_LOGS_MODE=json` in `docker-compose.yml`): one line per HTTP
    request when the `HTTP request` span closes, with `event` set to `meilisearch.http` (other lines:
    `meilisearch.<target>`). The whole value of `query_parameters` (a `GET` call carries the search text `q=…` and the
    expression `filter=…`) and of `error` (error messages quote document values and filter expressions, sometimes over
    several lines) is replaced; `spans` is dropped (it repeats `span`). Other strings are redacted from the first
    `` ` `` to the end of the string: Meilisearch quotes values inside that mark (``Document identifier `…` is
    invalid``). `route`, `method`, `status_code` and the processing time are kept. `/health` lines that return 200 (the
    status table asks all the time) are dropped. Without JSON mode, text rules with the same content still run, but the
    continuation lines of multi-line error messages cannot be redacted. Do not set `MEILI_LOG_LEVEL=DEBUG` while logs
    are collected: that level writes search texts and results into `fields`, which the rules do not redact.
- **Second redaction** ([`platform/logs/vector.yaml`](../platform/logs/vector.yaml)); each form below has a case in
  [`vector.test.yaml`](../platform/logs/vector.test.yaml) (43 cases including the dedicated rules above; removing any
  rule turns a case red):
  - `Bearer`/`Basic` tokens (8 characters or more, including trailing `=` padding as in
    `Basic dXNlcjpwYXNzd29yZA==`), JWT-shaped strings;
  - values of keys containing `password`, `passwd`, `pwd`, `secret`, `token`, `api key`, `private key`, `credential`,
    `session`, including with a prefix or suffix (`HASURA_ADMIN_SECRET=`, `POSTGRES_PASSWORD=`, `access_token`,
    `client_secret`, `x-api-key`): in double quotes, single quotes (Python dicts in tracebacks), or unquoted (up to the
    next key, including passwords with spaces); a quote opened but not closed (a line cut in the middle of a value:
    `password="X…`, `{'password': 'X…`) runs to the end of the line, and inside a string of a JSON line to the end of
    that string;
  - values that follow long command-line flags containing `passw`, `pwd`, `secret`, `token`, `key`, `credential`:
    `'--password', 'X'`, `'--api-key', 'X'` (Python list), `["--db-password", "X"]` (JSON array), `--password X` (also
    at the start of a line);
  - the whole value of `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`: when quoted, to the closing
    quote (an unclosed quote as above); unquoted, to the **end of the line** (several pairs `a=b; c=d`,
    `Digest username="u", response="…"`), except inside a string of a JSON line, where it runs to the end of that
    string;
  - the password in a connection string `scheme://user:password@host`;
  - the query string of a URL with a `/` before the `?` (absolute, relative, `host:port/path` as in
    `svc-files:8000/api/search?q=…`): unquoted, in single quotes (`URL('…?q=…')`), in double quotes (when the whole
    quoted value is a URL, the whole query string is dropped, spaces included);
  - email addresses (including accented letters, and `@` written as `\u0040` or `%40`), phone numbers `0…`, `+84…`,
    `84…` (10-digit mobile, 11-digit landline), 12-digit CCCD (citizen ID) numbers, including when stuck to letters
    (`sđt0912…`) and two numbers in a row;
  - numbers after a keyword (up to 20 non-digit characters apart), including when written in groups: `CCCD`/`căn
    cước` (citizen ID) and `CMND`/`chứng minh` (ID card), from 9 digits; `STK`/`tài khoản` (bank account) and
    `MST`/`mã số thuế` (tax code), from 6 digits; `SĐT`/`điện thoại`/`fax`/`tel`/`phone`, from 8 digits; e.g.
    `CMND 123456789`, `STK 0011004123456`, `MST 0101234567`, `SĐT: 0912 345 678`. A keyword followed directly by
    letters (`telemetry`, `telegram`) does not count.

  JSON lines are decoded and written again (keys in alphabetical order) before redaction: escape characters
  (`pass\u0077ord`) cannot hide letters; secret keys at any level, with any type of value (number, `null`, nested
  object), have the whole value replaced — even harmless keys such as `max_tokens`. In lines that are not JSON,
  `\u00XX` sequences that are printable ASCII characters are decoded (unless they follow a real `\`; hex digits in
  upper or lower case, several codes in a row) before redaction: an escaped key in a JSON fragment in the middle of a
  plain line (`ERROR {"pass\u0077ord": …}`) is redacted too. Docker splits lines longer than 16 KiB into several
  records: Vector joins them again (by container and partial id, done as soon as the last part arrives) before
  redaction (tried with the real driver: a 40,000-byte line still had its `request_id` extracted, and a password
  straddling the cut was still redacted); ordinary lines are not merged; messages are cut at 16,384 characters. If the
  redaction step fails at run time, the line is dropped rather than sent as it is (`drop_on_error: true`, with a static
  test in `scripts/tests/test_log_tap_trung.py` because `vector test` cannot cause a run-time error).

  This is only a safety net for lines that slip through (nginx error lines, tracebacks); it does **not replace** each
  service's own redaction layer (F4.4). **Still slips through** (tried on 24/10/2026):
  - numbers with no keyword before them written in groups (`0912 345 678`, `0912.345.678`, `(+84) 912-345-678`,
    `(+84)912345678`, `+84 912345678`, `84-912-345-678`, `024 3869 1234`) or not shaped like a phone or CCCD number
    (9-digit CMND, account numbers, tax codes standing alone such as `123456789`, `0011004123456`, `0101234567`); a
    keyword followed directly by letters (`phones 0912 345 671`);
  - full names, addresses; numbers stuck to other digits;
  - keys without the words above: `pass`, `passphrase`, `pin`, `otp`, `auth`, `key`, `signature` (including
    `X-Amz-Signature`), Vietnamese keys (`mat_khau`, `khoa_bi_mat`);
  - short command-line flags: `'-p', 'X'`, `-pX`; flag values starting with `-` (`--password -X`); the body of a PEM
    key (base64 on a line of its own);
  - headers as pairs in a list, tuple or JSON array (`[(b'authorization', b'Digest …')]`, `Headers([('cookie',
    'sid=…')])`, `{"headers": [["Cookie", "sid=…"]]}`): redacted only when the value is a `Bearer`/`Basic` token, a JWT,
    or a pair whose key contains `session` (`KEYCLOAK_SESSION=…`, `AUTH_SESSION_ID=…`, `session=…`);
  - JSON strings inside JSON strings (escaped twice: `{"body": "{\"inner\": \"{\\\"password\\\": …}\"}"}`; escaped
    once is still redacted); values containing `\u0022` (an escaped `"`; Python and Node write `\"`): the decoding step
    turns it into `"`, so what follows slips through (`"ab\u0022cd X"` becomes `"[REDACTED]"cd X"`);
  - two unclosed single-quoted values on the same line (`Cookie: 'a ; token: 'X`): the part after the second quote;
  - query strings with no `/` before them (`search?q=…`); a query string containing spaces is dropped only up to the
    first space when unquoted, in single quotes (`URL('svc-files:8000/x?q=Tran Thi B')` leaves `Thi B`) or in the
    middle of a double-quoted string (`msg="tim svc-files:8000/a?q=Do Thi I"`);
  - numbers after a keyword grouped with no-break spaces (U+00A0); keywords typed in combining Unicode form (NFD);
  - multi-byte characters exactly where Docker cuts, which become `�`; lines over 64 parts (about 1 MiB), or whose last
    part arrives after 10 seconds, are redacted part by part (a secret straddling the split slips through);
  - PostgreSQL: `ERROR:` messages of hand-written functions (`raise exception '… %', value`), the token after
    `syntax error at or near "…"`, `HINT:`, and `DETAIL:` forms other than those above;
  - Hasura: error messages other than the two wrong-type value forms above; `user_vars` (role, user id, unit id),
    `http_info.ip`, and URL paths are kept as they are;
  - Keycloak: event fields other than `username` (`ipAddress`, the path of `redirect_uri`), Java traceback lines.

  **Over-redaction** (nothing leaks, only text is lost): harmless keys containing `token`, `session`, `pwd`
  (`max_tokens`, `session_timeout=3600`, `PWD=/app`); numbers, dates and times included, within 20 characters after a
  keyword (`tài khoản a lúc 2026-10-24 10:00` becomes `tài khoản a lúc [STK]:00`); stretches that look like phone or
  CCCD numbers inside hex strings (`uuid4().hex` ids) — the `request_id` column is extracted before redaction, so
  searches still work; the rest of the line after an unquoted `Authorization` or `Cookie`, after an unclosed quote (in
  a JSON line: of that string), after an unquoted command-line flag value (up to the next `a=` key: `--password X
  --host db` becomes `--password [REDACTED]`; `--no-password db_moc --format c` and `--sort-key name` are redacted too);
  words of 8 characters or more after `basic`, `bearer` (`basic authentication`); a `,` or `;` right after a redacted
  value (`token=X,user=a` becomes `token=[REDACTED]user=a`).
- **Columns** of the `moc` stream: `service`, `container`, `stream` (stdout/stderr), `timestamp`, `event`, `request_id`
  (JSON lines of `svc-files`, `svc-workflow` and Hasura; APISIX lines; only ids of the form `[A-Za-z0-9._:-]{1,128}`,
  like `event`; PostgreSQL and Keycloak lines have none, search them by `service`), `message`; Parseable adds
  `p_timestamp` (time received, UTC), `p_src_ip` (Vector's IP on the `logs` network), `p_user_agent` (Vector's).

```bash
make logs-up                       # on: Vector, Parseable; recreates 9 containers, sets retention; until next make up
make logs-tra ID=<id>              # lines of every service carrying the id, last 60 minutes (PHUT=… to change)
make demo-log-tap-trung            # demo: one id through APISIX → svc-workflow → Hasura, svc-files; failed SQL…
make logs-down                     # off: 9 services back to json-file, stops Vector, Parseable; keeps stored logs
```

- **Keeping it on:** add `logs` to `MOC_EXTRA_PROFILES` in `.env` (e.g. `MOC_EXTRA_PROFILES=tunnel,logs`), then run
  `make up` (or `make logs-up`); from then on `make up`, `make down`, `make ps`… load the override file and the profile
  by themselves, and every `make up` adds the password to an old `.env` if it is missing, creates the stream and sets
  the log retention again (including after the `parseable_data` volume has been deleted). Running only `make logs-up`
  without adding it to `MOC_EXTRA_PROFILES` means the next `make up` puts the 9 services back on `json-file` (Vector and
  Parseable still run but receive nothing).
- **Password:** `MOC_LOGS_PASSWORD` is generated by `make env`; if a `.env` generated before F3.14 lacks this line,
  `make logs-up` (and `make up` when `logs` is in `MOC_EXTRA_PROFILES`) adds a random string by itself, exactly like
  `make env` (without printing it). If the line exists but is empty, these two commands stop; Parseable also does not
  start with an empty password (`P_ADDR` empty) — a port that accepts an empty sign-in is never opened. Like the
  repository's other passwords (`POSTGRES_PASSWORD`…), this password shows in plain text in `docker compose config` and
  in `docker inspect` of `parseable` (variable `P_PASSWORD`; Parseable 3.2.4 does not read the password from a file).
  Vector reads it from a compose secret: it is not in Vector's environment variables, configuration or log.
- **Where to get the request id:** the `X-Request-Id` header of the response (the browser's developer tools, Network
  tab); the error message "đã ghi nhật ký với mã …" (logged with id …) of Hasura Actions; the `request_id` column of
  the audit log. Background work with no originating request (the task assignment suggestion agent) uses the id
  `goi-y:<task>`.
- **Interface:** `http://127.0.0.1:8400`, account `moc`, password `MOC_LOGS_PASSWORD`; from another machine through an
  SSH tunnel: `ssh -L 8400:127.0.0.1:8400 server`. Search with SQL on the `moc` stream, e.g.
  `select p_timestamp, service, event, message from moc where service = 'svc-workflow' order by p_timestamp desc
  limit 50`. The interface bundle references outside servers (fonts, Parseable's support tools) — whether it loads
  them at run time has not been checked; the main path is `make logs-tra` and the API. See the CORS risk below.
- **Retention:** `MOC_LOGS_RETENTION_DAYS` days (default 7); Parseable deletes old data every day at 00:00 UTC. After
  changing the number of days, run `python3 scripts/log_tap_trung.py init` again. The log store is **not** part of the
  backup (`make backup`).
- **Deleting stored logs for good:** after `make logs-down`, `docker volume rm moc_parseable_data` (`make reset` deletes
  it too).
- **Installation** (`make install`): if `MOC_EXTRA_PROFILES` has `logs`, `install.sh` writes `COMPOSE_FILE` (the
  override file) into the installation's `.env`, so both `docker compose` typed by hand and the reconciler load it; the
  installation's `.env` must have `MOC_LOGS_PASSWORD`; run `python3 scripts/log_tap_trung.py init` in the install folder
  once to set the log retention. The reconciler goes with every profile in `MOC_EXTRA_PROFILES` (GitOps section, #351),
  so Vector and Parseable are self-healed too when their container is lost or stopped, like the other services.
- **Checking the configuration** needs nothing turned on and no network, only the repository's files mounted (CI can
  run the same commands):

  ```bash
  V=timberio/vector:0.59.0-distroless-static@sha256:2138c72ef15477d3a60126da851407a198ec61d2ff4cd600a4e69db5f6a29ff7
  M=(-v "$PWD/platform/logs:/etc/vector:ro"
     -v "$PWD/platform/logs/kiem-tra/mat-khau-gia.txt:/run/secrets/moc_logs_password:ro")
  docker run --rm --network none "${M[@]}" "$V" validate --deny-warnings /etc/vector/vector.yaml
  docker run --rm --network none "${M[@]}" "$V" test /etc/vector/vector.yaml /etc/vector/vector.test.yaml
  ```

**Risks and limitations the operator needs to know:**

- **Turning it on or off recreates 9 containers** (`apisix`, `app-office`, `app-ca-nhan`, `svc-files`,
  `svc-workflow`, `hasura`, `keycloak`, `postgres`, `meilisearch`): a log driver change takes effect only when the
  container is recreated. `make logs-up`, `make logs-down` (and the first `make up` after adding or removing `logs` in
  `MOC_EXTRA_PROFILES`) restart the database, Hasura, Keycloak and Meilisearch too: a few seconds with no sign-in, no
  writes, no search; other services that hold database connections (Flowable) have to reconnect by themselves. Turn it
  on or off outside working hours.
- **The fluent port `127.0.0.1:24224` needs no sign-in** (Docker's `fluentd` driver has no authentication): any process
  on the server can send fake lines into the log store (fake lines still go through redaction). On a server shared by
  many people, this is a real limitation.
- **Vector uses Parseable's single admin account `moc`** (through a compose secret, not an environment variable): there
  is no separate ingest-only account yet; whoever can read the secret in the Vector container has full rights over the
  log store.
- **Parseable runs as root** in its container, but drops every capability (`cap_drop: [ALL]`) and has
  `no-new-privileges`. It cannot run with a uid other than 0: on a new volume Parseable cannot create its folders and
  stops ("Permission denied", tried on 23/10/2026). The image is distroless, with no shell, so there is no healthcheck;
  it sits only on the `logs` network and cannot reach any other Signet service. The `logs` network is not `internal`
  (it has to open a port on 127.0.0.1), so Parseable and Vector can reach the Internet; Parseable's update check and
  usage reporting are turned off.
- **Parseable's CORS for `https://cdn.parseable.com`:** Parseable 3.2.4 always lets this origin call the API with
  credentials (preflight 200, `access-control-allow-credentials: true`); other origins cannot. This cannot be turned
  off: `P_CORS=false` opens it to **every** origin, and `P_ALLOW_ORIGINS` only adds origins (tried on 23/10/2026). It
  means that a page on `cdn.parseable.com` opened in a browser that is signed in to the Parseable interface can read
  the log store. The interface bundle also references `orchestrator.cloud-staging.parseable.com`. To reduce the risk:
  search with `make logs-tra`; if you use the interface, close the browser when done or use a separate browser
  profile.
- **Logs are lost when Parseable or Vector is down for long:** if Parseable does not accept, Vector holds up to 10,000
  lines in memory and then drops new ones; if Vector is down, Docker buffers in bounded memory (`mode: non-blocking`,
  `max-buffer-size: 4m`) and then drops — services are not blocked. The local copy (`docker logs`) is still there.
  Measured with the real driver (independent testing, 23/10/2026): stopping Vector (`docker stop -t 1`) lost the 13
  lines in Vector's current batch; lines that long-running containers wrote while Vector was down still arrived after
  Vector came back; short-lived containers that wrote while Vector was down lost everything (0/100,000 lines). These
  measurements predate acknowledgements (next item).
- **Per-line acknowledgement** (`fluentd-request-ack: "true"`, #226): the driver sends a `chunk` id, and Vector returns
  an `ack` as soon as the line has entered the pipeline. Vector does not turn on end-to-end `acknowledgements`, so it
  does not wait for Parseable to store the line. Without an `ack` (a dead connection, e.g. after Vector restarts), the
  driver closes the connection, reconnects and sends that line again. Before #226, the first line of a service that
  had been quiet for a long time (PostgreSQL, Keycloak), if written into a dead connection, was lost without an
  error.
  `make demo-log-tap-trung` (step 8) checks this. Consequences:
  - if Vector receives a line and dies before it can return the `ack`, that line reaches the store twice;
  - each container sends one line at a time and waits for the `ack` before sending the next. The waiting happens in
    dockerd: services are still not blocked (`mode: non-blocking`), and unsent lines sit in the buffer as when Vector
    is down.
- **Vector's redaction layer cannot replace F4.4:** only services that already redact are collected; a new service
  that should be collected has to redact in its own code first.
- `X-Request-Id` can be set by the client (APISIX keeps the id the client sends). `svc-workflow` accepts only ids
  matching `[A-Za-z0-9._:-]{1,128}` and replaces any other id with a new one (returned in the header); `svc-files` does
  not check yet (as before): any string goes into its log and into the audit log rows it writes. Vector puts only ids
  of that form into the `request_id` column; `make logs-tra` checks the id before putting it into the SQL query.
- Logs only join lines by id; the time of each hop is in the Distributed tracing section below. Rootless Docker and
  Docker Desktop (dockerd not on the same network as the host): the `127.0.0.1:24224` port has not been tried. Idle RAM
  is about 18 MiB (Vector) and 45 MiB (Parseable) — `docker stats` on a development machine on 23/10/2026; not measured
  under load.

## Distributed tracing

The `trace` profile (off by default, #364) shows which hops a request goes through and how long each hop takes:
APISIX → `svc-files` or Hasura → `svc-workflow` → the services' HTTP calls (Hasura, Meilisearch, OpenBao, Ollama,
Flowable…).
**Jaeger** 2.22 receives spans over OTLP/HTTP (port 4318, only inside the `moc` network), keeps the latest 10,000
traces in RAM ([`platform/trace/jaeger.yaml`](../platform/trace/jaeger.yaml)) and serves its interface at
`127.0.0.1:16686` on the server.

```bash
# .env: add trace to MOC_EXTRA_PROFILES (e.g. MOC_EXTRA_PROFILES=tunnel,trace) and set the ratio, then
MOC_TRACE_RATIO=0.1
make up
ssh -L 16686:127.0.0.1:16686 <server>   # view remotely: http://127.0.0.1:16686
```

- **Sampling at APISIX:** the `opentelemetry` plugin (a global rule in `apisix.yaml`) picks `MOC_TRACE_RATIO` of the
  requests (0–1) by `trace_id` and sends `traceparent` to the service behind. `svc-files` and `svc-workflow` do not
  pick by themselves: they record spans only when `traceparent` carries the sampled flag, so background work
  (directory sync, sending notifications, indexing) produces no spans. Hasura forwards `traceparent` to Actions
  (`forward_client_headers`), so `svc-workflow`'s spans sit in the same trace as APISIX's; Hasura has no spans of its
  own (the CE edition does not support OpenTelemetry).
- **Finding by request id:** APISIX spans carry the tag `x-request-id`; in the Jaeger interface pick the `apisix`
  service and type `x-request-id=<id>` in the Tags box. This is also the id of `make logs-tra` (section Centralised
  logs).
- **Off** (`MOC_TRACE_RATIO=0`, the default): APISIX records no spans, and the two services do not load
  OpenTelemetry. Keep `0` when the `trace` profile is not on: a non-zero ratio without Jaeger makes APISIX and the
  services log span-sending errors. The value must be a number from 0 to 1 (`0`, `0.1`, `1`); otherwise `make up`, the
  GitOps reconciler and the APISIX container itself stop with an error, because on a wrong value APISIX would drop the
  whole global rule it shares with the WAF and the request id.
- **Data redaction, in two layers:**
  - `svc-files` and `svc-workflow` (`tracing.py`) send only attributes on an allowlist: method, status code, route,
    path without the query string, host name. Strings go through the personal data redactor (F4.4). Calls to hosts
    outside Signet's network (names with a dot or IP addresses: webhooks, document exchange) get no span and carry no
    `traceparent`, so trace ids do not leave the internal services. Errors keep only the exception type name, not the
    message or the traceback. No headers are recorded (`Authorization`, cookies).
  - Jaeger drops `http.target` (path with query string) from APISIX spans and keeps `url.path`.
- **Limitations:**
  - APISIX spans still have `user_agent.original` and the client-sent `x-request-id` (arbitrary strings);
  - if a client sends its own `traceparent`, APISIX joins that `trace_id` and samples by that same `trace_id`: a client
    can pick a `trace_id` that falls inside the ratio, which only increases the number of spans (rate limits still
    apply);
  - Flowable, Keycloak and PostgreSQL do not send spans yet;
  - Jaeger 2.22 dropped the v1 HTTP API that Grafana's Jaeger data source uses, so traces cannot be viewed in Grafana
    yet;
  - traces are lost when the Jaeger container restarts; the interface has no accounts, like Grafana.
- **RAM** (development machine, 28/10/2026): Jaeger idles at 11 MiB and peaks at 123 MiB when full with 10,000 traces
  of 6 spans (the container's cgroup memory; compose limit 256m). Each `svc-files` and `svc-workflow` process adds
  about 15 MiB when it is on (RSS, measured before and after loading OpenTelemetry); when it is off, nothing is added.

## Internal wiki

The `wiki` profile (off by default, #367) adds **DokuWiki** at `/wiki/`: handbooks, procedures and internal guides
written as wiki pages, not numbered official documents. Each unit has a space `don-vi:<code>` that only that unit's
people can read, edit and upload files to; the start page lists the units' spaces. Sign-in is only through Keycloak
(the same account and sign-in steps as the e-Office); without a sign-in, `/wiki/` redirects to the sign-in page. The
e-Office's Applications page has an "Internal wiki" card while the wiki is answering.

```bash
# keep it on: add wiki to MOC_EXTRA_PROFILES in .env (e.g. MOC_EXTRA_PROFILES=tunnel,wiki), then
make up                                 # builds the image, runs the wiki, runs moc wiki sync
# or turn it on once (make down turns it off, a later make up does not turn it back on)
make wiki-up
make demo-wiki                          # check: two units cannot read or edit each other's pages
python3 scripts/moc.py wiki sync        # after each new unit (moc tenant create)
make wiki-down                          # off: remove wiki from MOC_EXTRA_PROFILES first; keeps stored pages, files
```

- **`moc wiki sync`** adds the Keycloak client `wiki` (confidential, secret `MOC_WIKI_CLIENT_SECRET` — `make up` and
  `make wiki-up` add it to an old `.env` if missing) or resets its secret, redirect URIs and `groups` mapper
  (= `tenant_id`); then writes the permission list `conf/acl.auth.php` and the start page from `core.tenants`. It can
  be run again; `--dry-run` only prints what it would do. A unit code becomes a space name the same way as the
  Organization alias (`KTCK` → `ktck`, `ĐT` → `dt`).
- **Permissions:** DokuWiki evaluates from the deepest namespace upwards. Each unit has exactly one line for its own
  space; the parent namespace `don-vi` is granted to no one, so a space left without a line (a unit that changed its
  code, a new unit before `wiki sync` has run) falls back to the line `* @ALL 0`: no one reads, no one creates pages.
  Signed-in people can read the start page and the syntax help pages that ship with DokuWiki (`wiki:*`), but cannot
  edit them. A person's groups are fetched again from Keycloak at every sign-in: someone who moves to another unit
  loses access to the old unit at the next sign-in.
- **There is no DokuWiki admin account** (an admin could read every space): the admin page, plugin installation and
  configuration editing in the interface are all off. The configuration is in
  [`platform/wiki/signet.protected.php`](../platform/wiki/signet.protected.php) (mounted read-only), plugins come with
  the image; the `install.php` installer has been removed. Wiki accounts are created by the oauth plugin at the first
  sign-in; there is no registration or password reset in the wiki.
- **The sitemap** (`?do=index`) shows the space names of every unit (the start page lists them anyway), but not the
  pages of other units. Search returns only pages the searcher can read.
- **Network, resources:** the container is on the `apps` network like plugged-in applications, runs as uid 33, drops
  every capability, with a 256 MiB limit (issue #367 measured an empty container at 37–70 MiB; not measured under
  load); uploads up to 64 MB like every path through APISIX. The wiki calls Keycloak through `http://apisix:9080` and
  reaches no core service directly. The WAF drops some rules on the page content field and the sign-in parameters
  (exclusion 10070, [`platform/apisix/README.md`](../platform/apisix/README.md)): chosen from the exclusions measured on
  the e-Office; false blocks on the wiki itself have not been measured.
- **Backup:** the `wiki_data` volume (pages, old page revisions, uploaded files, accounts, permission list) goes into
  `moc backup` (section Backup and restore).
- **Limitations:** there is no school-wide shared space for joint editing yet; when a unit changes its code, the old
  pages stay in the volume but no one can read them until they are moved by hand to the new space; wiki pages are not
  in the e-Office search box.
  - The oauth plugin links a wiki account to a Keycloak account by email: people without an email in Keycloak cannot
    sign in to the wiki; if a Keycloak account is deleted and another person is created with the same email, the new
    person reuses the old wiki name (page edit history records one shared name), while permissions still follow the
    new person's unit. Email and `tenant_id` can be changed only by administrators in Keycloak, so users cannot claim
    someone else's wiki account.
  - Page content still goes through the WAF's SQLi and XSS rules, like the e-Office's free-text fields: a page with
    example SQL statements or HTML code may be blocked (403) on save; when that happens, the administrator adds an
    exclusion in `apisix.yaml`.

## Automation with Node-RED

The `tu-dong` profile (off by default, #366) adds **Node-RED 5.0.8** at `/tu-dong/`: platform operators drag and drop
flows (timers, HTTP calls, JavaScript functions, text templates) instead of writing more loops in service code.
Sign-in is only through Keycloak (public client `tu-dong`, PKCE), and only people with that client's `operator` role
can enter the editor; no one has this role by default, unit administrators included.

```bash
# keep it on: add tu-dong to MOC_EXTRA_PROFILES in .env (e.g. MOC_EXTRA_PROFILES=wiki,tu-dong), then
make up                                 # builds the image, runs Node-RED, runs moc tu-dong sync
# or turn it on once (make down turns it off, a later make up does not turn it back on)
make tu-dong-up
python3 scripts/moc.py tu-dong operator add <username>      # grants the role; remove takes it away, list lists
make demo-tu-dong                       # check: no way in without sign-in or the role; deploys a flow via the gateway
make tu-dong-down                       # off: remove tu-dong from MOC_EXTRA_PROFILES first; keeps stored flows
```

- **`moc tu-dong sync`** adds the Keycloak client `tu-dong`, the `operator` role and the `tu-dong-roles` mapper (puts
  the roles into the ID token), or resets the redirect URIs when `MOC_PUBLIC_URL` changes. It can be run again;
  `--dry-run` only prints what it would do. Node-RED trusts only the roles in the ID token, whose signature, `iss` and
  `aud` the `openid-client` library has checked.
- **Removing the role** takes effect at the next sign-in: an editor token still within its lifetime (8 hours) keeps
  working until it expires or Node-RED restarts (`docker compose --profile tu-dong restart tu-dong`).
- **Locked down in [`platform/tu-dong/settings.js`](../platform/tu-dong/settings.js)** (built into the image, not
  editable in the interface): no `exec` node (runs shell commands), no nodes that read, write or watch files (`file`,
  `file in`, `watch`); no installing or uploading nodes from the editor; Function nodes cannot load external modules;
  flows open no HTTP endpoints yet (`httpNodeRoot` off); no diagnostics are sent out. When the image is built,
  `kiem-tra.cjs` actually loads this file and checks those settings, and checks the role-checking function too.
- **`MOC_TU_DONG_SECRET`** encrypts the credentials stored in flows (node passwords, tokens): `make up` and
  `make tu-dong-up` add it to an old `.env` if missing. If the key changes, Node-RED cannot open the stored
  credentials; restoring to a new machine also needs exactly this key, so it goes with the copy of `.env` (section
  Backup and restore).
- **Network, resources:** the container is on the `apps` network like plugged-in applications: flows reach the core
  only through `http://apisix:9080` (token check, rate limits, WAF as for a browser), and reach no database or core
  service. The root filesystem is read-only (writes go to `/data`, `/tmp`), every capability is dropped, with a 256 MiB
  limit (issue #366 measured an empty container at about 75 MiB; not measured under load). The WAF removes three rules
  that misfire on the sign-in token (exclusion 10080) and does not inspect the bodies of the flow and library save APIs
  (10081), because those bodies are JavaScript and HTML code
  ([`platform/apisix/README.md`](../platform/apisix/README.md)).
- **Backup:** the `tu_dong_data` volume (flows, encrypted credentials, editor sessions) goes into `moc backup` (section
  Backup and restore). Who edited which flow is written to the container log (`docker compose --profile tu-dong logs
  tu-dong`, Node-RED's audit lines), not yet to the audit log.
- **Limitations:**
  - Node-RED is a single shared flow space, not split by unit: people with the `operator` role can edit every flow,
    and a flow can call any API through the gateway that the credentials in the flow allow. That is why this is a tool
    for platform operators, not for individual units.
  - Not yet available: an endpoint that receives webhooks (`/tu-dong/hook/…`) and a BPMN step that calls a flow through
    `svc-workflow` — the next step of #366.

### Flow robots and the two sample flows

Flows call the core API with **a unit's robot**, not by borrowing a person's account (#366):

```bash
python3 scripts/moc.py tu-dong robot add CNTT     # prints ROBOT_ID, ROBOT_SECRET; rerun: config reset, secret kept
python3 scripts/moc.py tu-dong robot list         # existing robots and each robot's unit
python3 scripts/moc.py tu-dong robot rotate CNTT  # leaked secret: Keycloak makes a new one, the old one stops at once
python3 scripts/moc.py tu-dong robot remove CNTT  # removes it; issued tokens work until they expire (5 minutes)
```

- **What a robot is:** a confidential Keycloak client `tu-dong-robot-<code>` with only the `client_credentials` flow
  (no browser sign-in, no personal password), without full scope. Its access token carries the fixed Hasura role
  `tu_dong`, the robot's unit, and `x-hasura-user-id` set to the robot's own name. The client's service account does
  not enter the user directory.
- **What a robot may do:** read the **unrestricted** documents of its own unit, including outgoing drafts (`draft`,
  `returned`) as directors and clerks see them (reference number, summary, urgency, status, deadline, registration
  date, handling department; no content, creator or recipients), and call the `notifyFromFlow` Action to notify people
  in the unit by role. It writes no table, and reads no directory, notifications, restricted documents or anything of
  other units ([`db/tests/test_tu_dong.py`](../db/tests/test_tu_dong.py)).
- **`notifyFromFlow(roles, title, text, document_id, key)`** (svc-workflow): sends a notification of type
  `flow.message` to the bell, pushed in real time like other notifications; the same `key` is not sent again (a flow
  that runs again does not notify twice). With a `document_id` it can be sent only to `director` and `clerk` — the two
  roles that can see every unrestricted document of the unit — so the summary does not reach people who may not see
  that document. Documents of other units and restricted documents are refused. This rule only guards the attached
  document: if the flow copies the summary or reference number into `title`, `text` itself, they reach every chosen
  role — flow authors should send that information only to `director`, `clerk`, as the two sample flows do.
- **External channels:** `flow.message` goes to the bell and also to email, webhook, SMS and Zalo when
  `MOC_NOTIFY_*_KINDS` is empty (all kinds); the list of documents nearing their deadline carries several summaries.
  To keep flow messages in the bell only, list the other kinds in `MOC_NOTIFY_*_KINDS` and leave out `flow.message`.
- **Two sample flows** ([`platform/tu-dong/flow-mau.json`](../platform/tu-dong/flow-mau.json), tab "Signet — flow mẫu"
  (sample flows), disabled): (1) every day at 07:00, gather unfinished incoming documents due within the next 3 days
  and send the unit's directors one message; (2) every minute, look for Express ("Hỏa tốc") documents just registered
  and send directors one message per document, which opens the document when clicked. To use them: editor → menu ☰ →
  Import → choose the file; open the tab, fill in `ROBOT_ID`, `ROBOT_SECRET` (secret variables, encrypted with
  `MOC_TU_DONG_SECRET`) in the tab's Environment section; enable the tab, Deploy. One robot per unit: to run them for
  another unit, duplicate the tab and fill in that unit's robot.

## IT/OT convergence

The `iot` profile (not on by default, about 550 MB of RAM) adds the NGSI-LD context broker **Scorpio** (ETSI standard)
with its own PostGIS database. Devices update their digital twins in the broker; in each unit's NGSI-LD tenant
(`NGSILD-Tenant` = the unit code; for a code with diacritics, `t` + a hash of the code) `svc-workflow` keeps a
subscription `temperature>MOC_OT_THRESHOLD`. When a sensor goes over the threshold, the broker calls `svc-workflow`,
and the service builds an outgoing draft "Báo cáo sự cố" (incident report; type Báo cáo (report), urgency "Urgent"
("Khẩn")) from a template for the officer responsible for the sensor, writes an `ot.alarm` event to the timeline and
notifies that person at once. If there is still an unsubmitted (or returned) draft for the same sensor, no new one is
built; the responsible person is only reminded, at most once a day. The time and date of the report and of the
reminder follow the measurement time sent by the device (`observedAt`); if that time is more than 2 minutes later than
the server's clock (a device clock running fast, as with the **Future time** flag below), they
follow the time the server received the reading, and the draft states the device time — otherwise a device 30 minutes
fast sending a reading at 23:50 would make the report carry the next day's date. The draft then continues through the
outgoing documents flow like any other document.

```bash
make demo-it-ot                       # turns on the iot profile, simulated sensor 24 → 41 °C, draft, submission
docker compose --profile iot --profile iot-sim run --rm ot-sensor --tenant CNTT --responsible chuyenviendt \
    --name "Phòng máy chủ tầng 3" --readings 30,36   # send a few readings by hand
```

- The sensor entity `urn:ngsi-ld:TemperatureSensor:<code>` has `name` (room name), `responsible` (username of the
  responsible officer), `room` (room code on the storage map, optional: `sensor.py --room kho-1`) and `temperature`
  (°C, `observedAt`). The responsible person must be an active officer of that very unit, with a department;
  otherwise the event is ignored (log `ot.alarm_ignored`).
- **Sensor map** (`/cam-bien` in the e-Office, for clerks, officers, department heads and directors): a sample floor
  plan of the archive storage (SVG, nothing loaded from outside), each room coloured by the latest reading of the sensor
  with the same room code compared with `MOC_OT_THRESHOLD`. It is read through the Hasura Action `otSensorMap`:
  `svc-workflow` only queries the broker in the viewer's unit tenant. Four quality flags are computed in `svc-workflow`:
  **Signal lost** — no new reading for over `MOC_OT_STALE_MIN` minutes (default 10, 1–1440); set it to 2–3 times the
  real device's sending period; **Out of range** — a value that is not a number or is outside −55…125 °C (the measuring
  range of the DS18B20 sensor, a constant in `ot.py`); **Repeated time** (same `observedAt`) — the latest reading has
  the same measurement time as another one among the last 10 (temporal API); **Future time** — `observedAt` more than 2
  minutes later than the server's clock (`FUTURE_SLACK` in `ot.py`): the device clock runs fast. In that case signal
  loss is judged by the time the broker received the reading (`modifiedAt`), not by the device time — otherwise a device
  with a skewed clock that loses its signal would never be flagged. When the `iot` profile is off, the page shows
  "Sensors are not enabled", not an error. To fake faults and see the flags: `sensor.py --late 30` (a reading 30 minutes
  old), `--frozen-clock` (a stopped clock), `--clock-ahead 30` (a clock 30 minutes fast), `--readings 22,-127`.
- The broker and its database open no port on the host. Three separate internal networks: devices ↔ broker
  (`iot-devices`), broker ↔ `svc-workflow` (`iot`), broker ↔ its database (`iot-db`) — devices cannot call
  `svc-workflow`. Every call to `POST /ot/notify/<tenant>` must carry the unit's own token (an HMAC from
  `svc-workflow`'s Actions key); a wrong one gets 401.
- **Limitations of the map:** the sample floor plan is fixed in `apps/office/app/utils/otMap.ts` (one floor, 6 rooms)
  and shared by every unit; the measuring range is not per sensor; the broker records history asynchronously, so the
  duplicate `observedAt` flag may lag a few seconds; at most 100 sensors per unit. The flags show only on the map: a
  reading over the threshold still builds a "Báo cáo sự cố" draft even when it is out of range.
- **Limitations:** the broker has no authentication — anyone who can reach the device network can write into any
  unit's tenant, including naming an officer of that unit as the responsible person. A real deployment must put a
  device gateway in front of the broker (a FIWARE IoT Agent or PEP proxy) that assigns the tenant by each device's key;
  this cut-down version has only a simulated sensor.
- The broker sends each notification once: if the database write fails, that threshold crossing is lost, and the next
  reading still above the threshold builds the draft.
- `MOC_NGSI_DB_PASSWORD` is needed in `.env` (`make env` generates it). Real devices go through an IoT gateway (e.g.
  FIWARE's IoT Agent) or send NGSI-LD to the broker themselves; the measurement history stays in the broker (temporal
  API), not in Signet's database, and is not part of the backup.
- `make down` also turns off the `iot` and `iot-sim` profiles (the simulated sensor, which runs only once per call).
