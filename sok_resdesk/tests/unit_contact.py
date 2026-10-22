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
