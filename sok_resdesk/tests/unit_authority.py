"""Matching authors to Wikidata and subjects to LCSH (core/authority.py). Pure Python."""

from sok_resdesk.core import authority as a


def _claim_time(t):
	return {"mainsnak": {"datavalue": {"value": {"time": t}}}}


def _claim_id(q):
	return {"mainsnak": {"datavalue": {"value": {"id": q}}}}


ENTITIES = {
	"entities": {
		"Q2724213": {
			"labels": {"en": {"value": "Purandara Dasa"}, "kn": {"value": "ಪುರಂದರದಾಸರು"}},
			"descriptions": {"en": {"value": "Indian composer and poet"}},
			"aliases": {"en": [{"value": "Purandaradasa"}]},
			"claims": {
				"P31": [_claim_id("Q5")],
				"P569": [_claim_time("+1484-00-00T00:00:00Z")],
				"P570": [_claim_time("+1564-01-02T00:00:00Z")],
				"P214": [{"mainsnak": {"datavalue": {"value": "100219138"}}}],
			},
		},
		"Q999": {
			"labels": {"en": {"value": "Purandara Dasa (film)"}},
			"descriptions": {"en": {"value": "1937 film"}},
			"claims": {"P31": [_claim_id("Q11424")]},
		},
		"Q1": {"missing": ""},
	}
}


def test_names_compare_whatever_their_order_titles_and_accents():
	assert a.name_key("Rao, B. Venkoba, 1890-1960") == "b venkoba rao"
	assert a.name_key("Sri Rāmānuja") == "ramanuja"
	assert a.name_dates("Rao, B. Venkoba, 1890-1960") == ("Rao, B. Venkoba", 1890, 1960)
	assert a.name_similarity("Rao, B. Venkoba", "B. Venkoba Rao") == 1.0
	assert a.name_similarity("B. Venkoba Rao", "Bhimasena Venkoba Rao") > 0.85
	assert a.name_similarity("Kanakadasa", "Purandara Dasa") < 0.7
	assert a.name_similarity("ಕುವೆಂಪು", "ಕುವೆಂಪು") == 1.0  # Indic letters are kept


def test_people_are_read_from_wikidata():
	people = {p["id"]: p for p in a.parse_people(ENTITIES)}
	assert set(people) == {"Q2724213", "Q999"}
	p = people["Q2724213"]
	assert (p["human"], p["born"], p["died"], p["viaf"]) == (True, 1484, 1564, "100219138")
	assert p["labels"]["kn"] == "ಪುರಂದರದಾಸರು" and "Purandaradasa" in p["aliases"]
	assert people["Q999"]["human"] is False


def test_the_person_ranks_above_the_film_and_dates_count():
	ranked = a.rank(["Purandaradasa"], a.parse_people(ENTITIES), years=[1950])
	assert ranked[0]["id"] == "Q2724213" and ranked[0]["score"] > ranked[1]["score"]
	assert "has a VIAF record" in ranked[0]["reasons"]
	# a book older than the candidate's twelfth birthday makes the match unlikely
	young = {**ranked[0], "born": 1945}
	assert a.score_person(["Purandaradasa"], young, [1950])["score"] < ranked[0]["score"]
	# the catalogue's own birth year agreeing raises it
	assert a.score_person(["Purandara Dasa, 1484-1564"], ranked[0])["score"] == 1.0


def test_only_near_certain_matches_are_accepted_alone():
	people = a.parse_people(ENTITIES)
	assert a.decide(a.rank(["Purandara Dasa"], people)) == "auto"
	assert a.decide(a.rank(["Purandara"], people)) == "propose"
	assert a.decide(a.rank(["Kanakadasa"], people)) == "none"
	assert a.decide([]) == "none"
	close = [{"score": 0.97, "human": True}, {"score": 0.9, "human": True}]
	assert a.decide(close) == "propose"  # two people alike: a person decides


def test_lcsh():
	data = {
		"hits": [
			{"uri": "http://id.loc.gov/authorities/subjects/sh85061212", "aLabel": "India--History"},
			{"uri": "", "aLabel": "broken"},
		]
	}
	hits = a.parse_lcsh(data)
	assert hits == [
		{
			"id": "sh85061212",
			"label": "India--History",
			"uri": "http://id.loc.gov/authorities/subjects/sh85061212",
		}
	]
	assert a.score_subject("History -- India", hits[0]) == 1.0
	assert a.score_subject("Kannada poetry", hits[0]) < 0.6
	assert "searchtype=keyword" in a.lcsh_url("India history")
