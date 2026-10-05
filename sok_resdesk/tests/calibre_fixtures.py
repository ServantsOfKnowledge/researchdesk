"""A small Calibre library on disk: its metadata.db (Calibre's own table names) and book folders."""

import os
import sqlite3

from sok_resdesk.tests.oai_fixtures import make_pdf

SCHEMA = """
create table books (id integer primary key autoincrement, title text, sort text, timestamp timestamp,
  pubdate timestamp, series_index real, author_sort text, isbn text, lccn text, path text, flags integer,
  uuid text, has_cover bool, last_modified timestamp);
create table authors (id integer primary key autoincrement, name text, sort text, link text);
create table books_authors_link (id integer primary key autoincrement, book integer, author integer);
create table tags (id integer primary key autoincrement, name text);
create table books_tags_link (id integer primary key autoincrement, book integer, tag integer);
create table series (id integer primary key autoincrement, name text, sort text);
create table books_series_link (id integer primary key autoincrement, book integer, series integer);
create table publishers (id integer primary key autoincrement, name text, sort text);
create table books_publishers_link (id integer primary key autoincrement, book integer, publisher integer);
create table languages (id integer primary key autoincrement, lang_code text);
create table books_languages_link (id integer primary key autoincrement, book integer, lang_code integer, item_order integer);
create table comments (id integer primary key autoincrement, book integer, text text);
create table identifiers (id integer primary key autoincrement, book integer, type text, val text);
create table ratings (id integer primary key autoincrement, rating integer);
create table books_ratings_link (id integer primary key autoincrement, book integer, rating integer);
create table data (id integer primary key autoincrement, book integer, format text, uncompressed_size integer, name text);
create table custom_columns (id integer primary key autoincrement, label text, name text, datatype text,
  mark_for_delete bool, editable bool, display text, is_multiple bool, normalize bool);
create table custom_column_1 (id integer primary key autoincrement, value text);
create table books_custom_column_1_link (id integer primary key autoincrement, book integer, value integer);
create table custom_column_2 (id integer primary key autoincrement, book integer, value integer);
"""

UUID_EPUB = "aaaaaaaa-1111-4222-8333-444444444444"
UUID_PDF = "bbbbbbbb-1111-4222-8333-444444444444"
UUID_BARE = "cccccccc-1111-4222-8333-444444444444"
ID_EPUB, ID_PDF, ID_BARE = "calibre-aaaaaaaa1111", "calibre-bbbbbbbb1111", "calibre-cccccccc1111"
EPUB = b"PK\x03\x04 pretend epub"
PDF_PAGES = ["Calibre book first page", "Calibre book second page"]


def make_library(root: str) -> str:
	"""Three books: an EPUB and MOBI with a cover; a PDF with text; one whose file is gone."""
	os.makedirs(root, exist_ok=True)
	con = sqlite3.connect(os.path.join(root, "metadata.db"))
	con.executescript(SCHEMA)
	con.execute(
		"insert into custom_columns (id, label, name, datatype, normalize) values "
		"(1, 'place', 'Shelf', 'text', 1), (2, 'pages', 'Read Pages', 'int', 0)"
	)
	con.execute("insert into custom_column_1 (id, value) values (1, 'Rack 7')")
	con.execute("insert into languages (id, lang_code) values (1, 'kan'), (2, 'eng')")
	con.execute("insert into series (id, name) values (1, 'Dasa Sahitya')")
	con.execute("insert into publishers (id, name) values (1, 'Mysore Press')")
	con.execute("insert into authors (id, name) values (1, 'Kanakadasa'), (2, 'Smith| John')")
	con.execute("insert into tags (id, name) values (1, 'poetry'), (2, 'devotional')")
	con.execute("insert into ratings (id, rating) values (1, 8)")
	books = [
		(1, "Kirtanegalu", UUID_EPUB, "Kanakadasa/Kirtanegalu (1)", "1931-05-01 00:00:00+00:00", 1),
		(2, "Typed notes", UUID_PDF, "Smith, John/Typed notes (2)", "0101-01-01 00:00:00+00:00", 0),
		(
			3,
			"File went missing",
			UUID_BARE,
			"Kanakadasa/File went missing (3)",
			"2001-01-01 00:00:00+00:00",
			0,
		),
	]
	for i, title, uuid, path, pubdate, cover in books:
		con.execute(
			"insert into books (id, title, uuid, path, pubdate, timestamp, last_modified, series_index, has_cover, isbn) "
			"values (?, ?, ?, ?, ?, '2020-02-02 10:00:00+00:00', '2023-03-03 10:00:00+00:00', 2.0, ?, '')",
			(i, title, uuid, path, pubdate, cover),
		)
	con.executescript(
		"""
		insert into books_authors_link (book, author) values (1, 1), (1, 2), (2, 2), (3, 1);
		insert into books_tags_link (book, tag) values (1, 1), (1, 2);
		insert into books_series_link (book, series) values (1, 1);
		insert into books_publishers_link (book, publisher) values (1, 1);
		insert into books_languages_link (book, lang_code, item_order) values (1, 1, 0), (1, 2, 1), (2, 2, 0);
		insert into comments (book, text) values (1, '<div><p>Songs by <b>Kanakadasa</b>.</p></div>');
		insert into identifiers (book, type, val) values (1, 'isbn', '9780000000002'), (1, 'goodreads', '77');
		insert into books_ratings_link (book, rating) values (1, 1);
		insert into books_custom_column_1_link (book, value) values (1, 1);
		insert into custom_column_2 (book, value) values (1, 120);
		insert into data (book, format, uncompressed_size, name) values
		  (1, 'EPUB', 17, 'Kirtanegalu - Kanakadasa'), (1, 'MOBI', 5, 'Kirtanegalu - Kanakadasa'),
		  (2, 'PDF', 900, 'Typed notes - John Smith'), (3, 'EPUB', 5, 'File went missing - Kanakadasa');
		"""
	)
	con.commit()
	con.close()
	for path, files in (
		(
			"Kanakadasa/Kirtanegalu (1)",
			{
				"Kirtanegalu - Kanakadasa.epub": EPUB,
				"Kirtanegalu - Kanakadasa.mobi": b"MOBI",
				"cover.jpg": b"\xff\xd8jpeg",
				"metadata.opf": b"<package/>",
			},
		),
		("Smith, John/Typed notes (2)", {"Typed notes - John Smith.pdf": make_pdf(PDF_PAGES)}),
		("Kanakadasa/File went missing (3)", {}),
	):
		os.makedirs(os.path.join(root, path), exist_ok=True)
		for name, data in files.items():
			with open(os.path.join(root, path, name), "wb") as f:
				f.write(data)
	return root
