"""Text in a `like` pattern matches itself (core/access.py)."""

from sok_resdesk.core.access import like_literal


def test_wildcards_are_escaped():
	assert like_literal("100%_Kannada") == "100\\%\\_Kannada"
	assert like_literal("a\\b") == "a\\\\b"
	assert like_literal("plain") == "plain"
