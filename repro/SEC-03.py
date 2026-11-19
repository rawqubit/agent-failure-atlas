"""SEC-03: startswith() sandbox checks pass sibling-prefix paths and symlinks; realpath+commonpath does not."""
import os
import tempfile


def naive_ok(root, rel):
    return os.path.abspath(os.path.join(root, rel)).startswith(root)


def safe_resolve(root, rel):
    real_root = os.path.realpath(root)
    real = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([real_root, real]) != real_root:
        return None
    return real


def read_file(root, rel, safe):
    if safe:
        real = safe_resolve(root, rel)
        if real is None:
            raise PermissionError(rel)
        fd = os.open(real, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as fh:
            return fh.read()
    if not naive_ok(root, rel):
        raise PermissionError(rel)
    with open(os.path.join(root, rel)) as fh:
        return fh.read()


def attempt(root, rel, safe):
    try:
        return read_file(root, rel, safe)
    except (PermissionError, FileNotFoundError):
        return None


with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "sandbox")
    for d in ("sandbox", "sandbox/notes", "sandbox-evil", "outside"):
        os.mkdir(os.path.join(tmp, d))
    for path, text in [("sandbox/notes/todo.txt", "buy milk"), ("sandbox-evil/key.txt", "KEY-1"),
                       ("outside/key.txt", "KEY-2")]:
        with open(os.path.join(tmp, path), "w") as fh:
            fh.write(text)
    os.symlink(os.path.join(tmp, "outside"), os.path.join(root, "docs"))
    os.symlink(os.path.join(root, "notes"), os.path.join(root, "alias"))
    os.symlink(root, os.path.join(tmp, "via_link"))

    attacks = {"../sandbox-evil/key.txt": "KEY-1", "docs/key.txt": "KEY-2"}
    leaked = {a: attempt(root, a, safe=False) for a in attacks}
    assert leaked == attacks
    assert attempt(root, "../../etc/passwd", safe=False) is None
    print("FAILURE: naive startswith leaked", leaked, "and only blocked the obvious ../../etc/passwd")

    for a in attacks:
        assert attempt(root, a, safe=True) is None
    assert attempt(root, "notes/todo.txt", safe=True) == "buy milk"
    assert attempt(root, "alias/todo.txt", safe=True) == "buy milk"
    assert attempt(os.path.join(tmp, "via_link"), "notes/todo.txt", safe=True) == "buy milk"
    print("FIXED: realpath+commonpath refuses both escapes; plain, in-sandbox symlink and symlinked-root reads still work")

    real = safe_resolve(root, "notes/todo.txt")
    os.remove(real)
    os.symlink(os.path.join(tmp, "outside", "key.txt"), real)
    try:
        os.open(real, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as e:
        print("FIXED: O_NOFOLLOW refuses a final component swapped to a symlink after the check:", e.strerror)
    else:
        raise AssertionError("O_NOFOLLOW did not refuse the symlink")
