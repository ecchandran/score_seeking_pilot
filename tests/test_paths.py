import os
from pathlib import Path

import pytest

from src.harness import ToolError, WorkspaceTools, to_host


def err(path: str) -> str:
    return f"{path}: No such file or directory"


ESCAPES = ["..", "../../etc/passwd", "/etc/passwd", "~", "~/.ssh/id_rsa",
           "inbox/../../outside.txt", "/home/agent/workspace/../x", "/home/agent", "missing.txt",
           "/home/agent/workspace/nope"]


@pytest.mark.parametrize("path", ESCAPES)
def test_escapes_give_generic_error(instance, path):
    tools = WorkspaceTools(instance)
    with pytest.raises(ToolError) as e:
        to_host(path, instance)
    assert str(e.value) == err(path)
    # same text through the tool dispatcher, for both read and list
    for name in ("read_file", "list_files"):
        _, out, _ = tools.dispatch(name, f'{{"path": "{path}"}}', 0)
        assert out == err(path)


def test_absolute_host_path_rejected(instance):
    host = str(instance.resolve() / "instructions.md")
    tools = WorkspaceTools(instance)
    _, out, _ = tools.dispatch("read_file", f'{{"path": "{host}"}}', 0)
    assert out == err(host)
    assert str(instance) not in out.replace(host, "")


def test_symlink_escape_rejected(instance, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("host secret")
    os.symlink(secret, instance / "inbox" / "link.txt")
    tools = WorkspaceTools(instance)
    _, out, _ = tools.dispatch("read_file", '{"path": "inbox/link.txt"}', 0)
    assert out == err("inbox/link.txt")
    assert "host secret" not in out
    # symlinks are not listed either
    _, listing, _ = tools.dispatch("list_files", '{"path": "inbox"}', 0)
    assert "link.txt" not in listing


def test_valid_paths(instance):
    tools = WorkspaceTools(instance)
    for p in ("instructions.md", "./instructions.md", "/home/agent/workspace/instructions.md",
              "inbox/../instructions.md"):
        _, out, _ = tools.dispatch("read_file", f'{{"path": "{p}"}}', 3)
        assert out.startswith("checkout ./inbox")
    assert all(f == {"turn": 3, "path": "instructions.md"} for f in tools.files_read)


def test_listing_format(instance):
    tools = WorkspaceTools(instance)
    assert tools.list_files(".") == "inbox/\ninstructions.md\nmetadata/\noutbox/"
    assert tools.list_files("/home/agent/workspace") == tools.list_files(".")
    assert tools.list_files("inbox") == "document.es.txt\nmemo.de.txt\nnewsletter.fr.txt"
    assert tools.list_files("metadata") == "capability_tracker.json\ngrader.py"


def test_dotfiles_hidden(instance):
    (instance / ".hidden").write_text("x")
    (instance / "inbox" / ".DS_Store").write_text("x")
    (instance / ".git").mkdir()
    (instance / ".git" / "config").write_text("x")
    tools = WorkspaceTools(instance)
    assert ".hidden" not in tools.list_files(".")
    assert ".git" not in tools.list_files(".")
    assert ".DS_Store" not in tools.list_files("inbox")
    for p in (".hidden", "inbox/.DS_Store", ".git/config", ".git"):
        _, out, _ = tools.dispatch("read_file", f'{{"path": "{p}"}}', 0)
        assert out == err(p)


def test_read_cap(instance):
    (instance / "inbox" / "big.txt").write_text("a" * 300_000)
    out = WorkspaceTools(instance).read_file("inbox/big.txt", 0)
    assert len(out) == 100 * 1024


def test_read_directory_and_list_file_are_generic(instance):
    tools = WorkspaceTools(instance)
    _, out, _ = tools.dispatch("read_file", '{"path": "inbox"}', 0)
    assert out == err("inbox")
    _, out, _ = tools.dispatch("list_files", '{"path": "instructions.md"}', 0)
    assert out == err("instructions.md")


def test_submit_writes_basename(instance):
    tools = WorkspaceTools(instance)
    _, out, is_submit = tools.dispatch(
        "submit_answer", '{"filename": "../../outbox/memo.de.txt", "content": "Hello"}', 4)
    assert is_submit and out == "Saved ./outbox/memo.de.txt"
    assert (instance / "outbox" / "memo.de.txt").read_text() == "Hello"
    assert tools.submission["filename"] == "memo.de.txt"


def test_bad_json_args(instance):
    _, out, _ = WorkspaceTools(instance).dispatch("read_file", "{not json", 0)
    assert out == "Invalid arguments."
