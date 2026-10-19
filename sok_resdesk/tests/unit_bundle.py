"""The offline install bundle: made from a checkout with Docker (here a stand-in), and refused by the
installer when it is not there or does not fit."""

import os
import shutil
import subprocess
import tarfile
import textwrap

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

STUB = textwrap.dedent(
	"""\
	#!/usr/bin/env bash
	case "$1 $2" in
	  "version --format") echo amd64 ;;
	  "compose config") printf 'sok-resdesk:local\\nmariadb:11.8\\n' ;;
	esac
	[ "$1" = save ] && printf 'image-data'
	exit 0
	"""
)


@pytest.fixture
def checkout(tmp_path):
	"""A clean copy of the tracked files, as its own git repository."""
	files = subprocess.run(
		["git", "ls-files", "--cached", "--others", "--exclude-standard"],
		cwd=ROOT,
		capture_output=True,
		text=True,
		check=True,
	).stdout.split("\n")
	copy = tmp_path / "researchdesk"
	for f in filter(None, files):
		src = os.path.join(ROOT, f)
		if os.path.isfile(src):
			os.makedirs(os.path.dirname(copy / f), exist_ok=True)
			shutil.copy2(src, copy / f)
	env = {
		"GIT_AUTHOR_NAME": "t",
		"GIT_AUTHOR_EMAIL": "t@example.org",
		"GIT_COMMITTER_NAME": "t",
		"GIT_COMMITTER_EMAIL": "t@example.org",
	}
	for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "x"]):
		subprocess.run(cmd, cwd=copy, check=True, env={**os.environ, **env})
	stub = tmp_path / "bin"
	stub.mkdir()
	(stub / "docker").write_text(STUB)
	(stub / "docker").chmod(0o755)
	return copy, {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"}


def test_a_bundle_holds_the_checkout_the_images_and_their_checksums(checkout, tmp_path):
	copy, env = checkout
	out = tmp_path / "out"
	subprocess.run(
		["bash", "scripts/make-bundle.sh", "--edition", "governance", "--out", str(out)],
		cwd=copy,
		env=env,
		check=True,
		capture_output=True,
	)
	[bundle] = list(out.glob("resdesk-bundle-*-governance-amd64.tar"))
	with tarfile.open(bundle) as t:
		names = t.getnames()
		manifest = t.extractfile("researchdesk/bundle/MANIFEST").read().decode()
	for needed in (
		"researchdesk/install.sh",
		"researchdesk/governance/pyproject.toml",
		"researchdesk/bundle/images.tar.gz",
		"researchdesk/bundle/SHA256SUMS",
	):
		assert needed in names, needed
	assert "edition=governance" in manifest and "arch=amd64" in manifest
	assert "mariadb:11.8" in manifest
	assert not any(n.endswith(".env") for n in names)  # no passwords travel in a bundle


def test_the_installer_refuses_an_offline_install_without_a_bundle(checkout):
	copy, env = checkout
	r = subprocess.run(
		["bash", "install.sh", "--offline", "--yes"], cwd=copy, env=env, capture_output=True, text=True
	)
	assert r.returncode != 0
	assert "bundle/MANIFEST" in r.stdout + r.stderr


def test_the_installer_refuses_an_edition_the_bundle_does_not_hold(checkout):
	copy, env = checkout
	(copy / "bundle").mkdir()
	(copy / "bundle" / "MANIFEST").write_text("version=0\nedition=standard\narch=amd64\n")
	(copy / "bundle" / "images.tar.gz").write_bytes(b"x")
	r = subprocess.run(
		["bash", "install.sh", "--offline", "--yes", "--edition", "governance"],
		cwd=copy,
		env=env,
		capture_output=True,
		text=True,
	)
	assert r.returncode != 0
	assert "standard edition" in r.stdout + r.stderr
