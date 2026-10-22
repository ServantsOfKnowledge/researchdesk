"""What the Contact us form accepts, and what Telegram is told."""

from sok_resdesk.core import contact


def test_a_good_message_is_kept_with_tags_and_control_characters_removed():
	fields, why = contact.clean(
		" Asha  <b>K</b> ",
		"asha@example.org",
		"Hello,\x00 I found <script>x()</script>an error\r\non page 4.",
	)
	assert why == ""
	assert fields["full_name"] == "Asha K"
	assert fields["message"] == "Hello, I found x()an error\non page 4."


def test_the_name_and_contact_are_optional_but_the_message_is_not():
	assert contact.clean("", "", "A question about page four.")[0]["contact"] == ""
	assert contact.clean("", "", "   ")[1] == "empty"
	assert contact.clean("", "", "<br>")[1] == "empty"
	assert contact.clean("", "", "hi")[1] == "short"


def test_a_filled_hidden_field_means_a_robot_and_nothing_is_kept():
	assert contact.clean("a", "b", "A perfectly good message.", trap="http://spam")[1] == "trap"


def test_everything_is_cut_to_its_limit():
	fields, _ = contact.clean("n" * 500, "c" * 500, "m" * 5000)
	assert len(fields["full_name"]) == contact.MAX_NAME
	assert len(fields["contact"]) == contact.MAX_CONTACT
	assert len(fields["message"]) == contact.MAX_MESSAGE


def test_the_flood_limit():
	assert not contact.too_many(contact.FLOOD_PER_HOUR - 1)
	assert contact.too_many(contact.FLOOD_PER_HOUR)


def test_the_telegram_text_says_a_message_came_and_never_what_it_says():
	text = contact.alert_text("The Library", "https://x.example/app/rd-message/MSG-00001")
	assert "https://x.example/app/rd-message/MSG-00001" in text and "The Library" in text


def test_a_bot_token_looks_like_one_or_it_does_not():
	assert contact.looks_like_token("123456789:AAH-xyz_0123456789abcdefghijk")
	assert not contact.looks_like_token("123:abc")
	assert not contact.looks_like_token("not a token")
	assert not contact.looks_like_token("")


def test_each_telegram_refusal_says_what_to_do():
	assert "token" in contact.telegram_problem(401)
	assert "chat ID" in contact.telegram_problem(400, "Bad Request: chat not found")
	assert "Start" in contact.telegram_problem(403, "Forbidden: bot was blocked by the user")
	assert "api.telegram.org" in contact.telegram_problem(0)
	assert "slow down" in contact.telegram_problem(429)
	assert "999" in contact.telegram_problem(999)


def test_the_test_message_says_it_is_a_test():
	assert "works" in contact.test_text("The Library")


def test_a_telegram_username_is_cleaned_or_refused():
	for text in ("SOKLibrary", "@SOKLibrary", "t.me/SOKLibrary", "https://t.me/SOKLibrary/", " @SOKLibrary "):
		assert contact.clean_username(text) == "SOKLibrary"
	for text in (
		"",
		"abc",
		"9lives_library",
		"has space",
		"+91 98765 43210",
		"https://evil.example/SOKLibrary",
		"a" * 40,
	):
		assert contact.clean_username(text) == ""
	assert contact.telegram_link("@SOKLibrary") == "https://t.me/SOKLibrary"
	assert contact.telegram_link("nonsense here") == ""


def test_the_chats_a_bot_has_heard_from_are_found_newest_first_once_each():
	data = {
		"result": [
			{
				"update_id": 1,
				"message": {"chat": {"id": 11, "type": "private", "first_name": "Asha", "last_name": "K"}},
			},
			{
				"update_id": 2,
				"message": {"chat": {"id": -100, "type": "supergroup", "title": "Library team"}},
			},
			{
				"update_id": 3,
				"message": {"chat": {"id": 11, "type": "private", "first_name": "Asha", "last_name": "K"}},
			},
			{"update_id": 4, "channel_post": {"chat": {"id": -200, "type": "channel", "title": "News"}}},
			{"update_id": 5, "poll": {}},
		]
	}
	found = contact.chats_from_updates(data)
	assert [c["id"] for c in found] == ["-200", "11", "-100"]
	assert found[1]["label"] == "Asha K (private chat)"
	assert contact.chats_from_updates({}) == [] and contact.chats_from_updates(None) == []
