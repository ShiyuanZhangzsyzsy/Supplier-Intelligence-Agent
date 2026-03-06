# Git Cheat Sheet (Beginner-Friendly)

This project is already under Git, so you can safely make changes and roll back when needed.

## 1) Daily workflow (most common)

```bash
git status
git add .
git commit -m "Describe what you changed"
```

- `git status` → shows what changed
- `git add .` → stages changed files
- `git commit` → saves a restore point

---

## 2) See history

```bash
git log --oneline --decorate --graph
```

Shows commits in a compact list.

---

## 3) See exactly what changed

```bash
git diff
```

Shows unstaged changes.

```bash
git diff --staged
```

Shows staged changes (what will be committed).

---

## 4) Undo local changes (before commit)

### Discard one file

```bash
git restore path/to/file.py
```

### Discard all local file edits

```bash
git restore .
```

Use with care: this removes uncommitted edits.

---

## 5) Unstage files (keep file edits)

```bash
git restore --staged .
```

Useful when you staged too much by mistake.

---

## 6) Recover to a previous commit

### Safe way: create a branch from old commit

```bash
git switch -c recover-branch <commit-hash>
```

You can explore old code without destroying current branch.

### Hard reset current branch (destructive)

```bash
git reset --hard <commit-hash>
```

Moves branch back permanently and drops newer local commits.

---

## 7) Quick branch workflow (recommended)

Create feature branch:

```bash
git switch -c feature/my-change
```

After work:

```bash
git add .
git commit -m "Implement my change"
```

Go back to main branch:

```bash
git switch master
```

---

## 8) Helpful checks

```bash
git branch
git status
git log --oneline -n 5
```

---

## 9) Your current restore point

Your initial project snapshot commit:

- Message: `Initial scaffold: LM Studio bridge, resilient ingestion, web UI, supplier agents`
- Hash (short): `bdbab6f`

You can always return to this point.

---

## 10) Good habits

- Commit often (small, meaningful commits)
- Write clear commit messages
- Use branches for experiments
- Keep `.env` and secrets out of Git (already handled by `.gitignore`)
