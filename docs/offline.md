# Offline copies and Kiwix

For schools, villages and archives with poor or no internet, a collection can be taken away as an
**offline copy**: a folder of ordinary web pages that opens from a USB stick, a phone or a laptop
with no server and no internet. It can also be packaged as a **ZIM file**, the format the Kiwix
apps read (Android, iOS, desktop and Kiwix hotspots).

## Making one

Research Desk → **Exports** → New → Format **Offline copy (zip, for Kiwix)**, then choose the books
(a collection, a search, selected books…) as for any export. **Estimate Size** says how many books
have files and text and how big the copy will be. Save: a small copy is made straight away, a big
one in the background (the Export shows *Download* when it is done).

The zip holds:

- `index.html`: the books with a search box (titles, authors, subjects and the text of the books),
  working from `file://`, with no internet;
- a page per book: its details, cover and a download link for each file the library holds;
- for books whose text the library holds, the text page by page (`text/`);
- `HOW-TO-MAKE-A-ZIM.txt`.

**Who is in it.** The copy goes wherever a person carries it, so only books that are **open to
read and public** get their files and text. A members-only or restricted book is listed by its
details alone. Books held on archive.org or another repository have no files here; their page
links to where they are.

## A ZIM file for Kiwix

If the server has **zimwriterfs** (the `zim-tools` package; `apt install zim-tools`), the export
makes the ZIM file too, next to the zip. Otherwise unzip the copy on any computer with
zimwriterfs and run the command in `HOW-TO-MAKE-A-ZIM.txt`. Add the `.zim` file to the Kiwix app
or host it on a Kiwix hotspot.

Up to 20,000 books go in one copy; the Export checks that the disk has room first.
