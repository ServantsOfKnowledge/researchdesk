# Accessibility

Research Desk is for everyone who reads, including people who are blind or have low vision, people
who read with a screen reader, a magnifier or their voice, people who cannot use a mouse, and
people with dyslexia or cognitive disabilities. In India that is a legal duty as well as the
library's purpose: the Rights of Persons with Disabilities Act 2016 (sections 40–46), the
Guidelines for Indian Government Websites (GIGW 3.0) and the Indian standard IS 17802 all expect
public digital services to be accessible, and section 52(1)(zb) of the Copyright Act lets
libraries make accessible copies for people with print disabilities.

This page says what works today, what does not yet, the standards Research Desk follows, and the
plan. It doubles as the library's **accessibility statement**: tell the library about anything
that gets in your way (see *Reporting a problem*).

## What works today

**Moving around**

- **Skip to content**: the first Tab on every portal page jumps past the menu to the page itself.
- **Keyboard**: everything on the portal works with the keyboard: search, filters, the reader
  (← → turn pages), citations, My list and notes. The focus ring is drawn clearly in every theme.
- **Landmarks and headings**: one main area per page, labelled filters and results, headings in
  order, so screen-reader users move by region and heading.
- **Labels**: every field, menu and button has a name a screen reader reads out.
- **Status messages** (result counts, saving, OCR progress, reading aloud) are announced without
  moving focus.
- **Less motion** for readers who ask their system for it; colours follow Windows' high-contrast
  mode.
- Works at 200% zoom and on a phone held upright (no sideways scrolling).

**Indian languages**

- Titles, page text, quotes and search results carry their **language** (Kannada `kn`, Hindi
  `hi`, Tamil `ta`…), worked out from the script they are written in, so screen readers (NVDA,
  JAWS, TalkBack, VoiceOver) switch to the right voice instead of reading Kannada with an English
  one.
- Search in Latin letters for any Indic script (`kanakadasa` finds ಕನಕದಾಸ) helps readers who
  cannot type in the script.

**Reading**

- **Page & text** shows each page's OCR text beside its image: text a screen reader reads, a
  magnifier enlarges and a braille display shows. Proofread pages are the most reliable.
- **Read aloud** (Page & text) speaks the page with the device's own voice for the book's
  language, where it has one: Android and Chrome have Kannada, Hindi, Tamil, Telugu, Malayalam,
  Bengali, Gujarati and Marathi voices; Windows and macOS have voices to add.
- archive.org's own reader, also on every book page, has its own **Read aloud** and keyboard
  controls.
- Every page image has a text name (*Page image 12*). The book's page says whether text is
  available (schema.org accessibility metadata, read by search engines and accessibility tools).

**Notes and proofreading without a mouse**

- **Add a note** (Page & text) writes a note on the whole page, or on words you type or paste;
  words selected with Shift and the arrow keys (caret browsing, F7) also offer the note bar.
- Proofreading zones: **Add a zone**, then on the zone in the list the arrow keys move it and
  Shift with the arrow keys resizes it; each zone says where it is.

**Out of the box from Frappe**: the page's language and direction (`<html lang>`, right-to-left
for Urdu), a main landmark, an accessible menu button on phones, and the portal in other
languages (Frappe translations: a language switch at the top of the portal, when the library
offers Kannada or another language).

## Not yet

- **Marking a region of a page image** and **drawing a zone** still need a mouse or a finger;
  keyboard users use *Add a note* and *Add a zone* instead.
- **Scanned pages without OCR text** (and pages whose OCR is poor) cannot be read by a screen
  reader; proofreading fixes the text page by page.
- **The Desk** (the staff side) is Frappe's own interface: it works with the keyboard and has
  shortcuts, but it has not been tested with screen readers by us. Our own Desk pages (Server,
  People & Roles, Background Jobs, Help) have not had the audit the portal has.
- **Downloadable accessible formats** (EPUB 3, DAISY, plain text) of proofread books are not
  offered yet; the PDF is archive.org's image PDF.
- No testing yet **with disabled readers** themselves; automated checks find only part of the
  problems.

## Reporting a problem

Write to the library (the contact on the About page) with the page's address and what got in the
way. Staff: problems with the software itself go to
<https://github.com/ServantsOfKnowledge/researchdesk/issues> with the label *accessibility*.

## Standards

| Standard | What it covers | Research Desk |
|---|---|---|
| **WCAG 2.2, level AA** (W3C) | the web content rules everyone uses | the target for the portal and our own Desk pages |
| **GIGW 3.0** (Government of India, 2023) | government and publicly funded websites; WCAG 2.1 AA plus an accessibility statement, multilingual content, and feedback | followed; this page is the statement |
| **IS 17802** (BIS, 2021) | the Indian standard for accessible ICT, in line with Europe's EN 301 549 | followed through WCAG 2.2 AA |
| **ATAG 2.0** (W3C) | tools people use to write content: here, notes and proofreading | the keyboard paths above; the rest on the roadmap |
| **WAI-ARIA 1.2 and the APG patterns** | how custom controls tell screen readers what they are | used for the note bar, zones, reader and dialogs |
| **schema.org accessibility metadata**, **EPUB Accessibility 1.1** | describing how accessible a book is | on every book page; for EPUB exports when they come |
| **Marrakesh Treaty**, Copyright Act **52(1)(zb)** | accessible copies for people with print disabilities | the basis for sharing with Sugamya Pustakalaya (roadmap) |

## How it was checked (October 2026, v0.31)

1. **Automated**: axe-core 4.13 (WCAG 2.0–2.2 A and AA, plus best practice) on every portal page
   and on the reader, notes and proofreading in use. Before: two main landmarks on the search
   pages, unlabelled menus and text areas (notes, proofreading), thumbnail links with no name,
   headings out of order and a badge below 4.5:1 contrast. After: none on the pages checked.
2. **By reading the code**: keyboard paths, focus, language of text, live messages, motion.
   This found what axe cannot: Indic text announced in the wrong voice, notes and zones only by
   mouse, no skip link, no visible focus ring.
3. **Keyboard-only run** in a browser (CI-style test): skip link, adding a note by typing its
   words, adding and moving a zone with the arrow keys.

Not done yet: testing with NVDA and Kannada/Hindi voices, TalkBack on Android, and readers who use
them every day.

## Roadmap

**Next**

- [ ] Test with blind and low-vision readers through a partner (e.g. Mitra Jyothi, Bengaluru; the
      National Association for the Blind), using NVDA and TalkBack with Indic voices; fix what
      they find
- [ ] The accessibility checks above in CI (axe-core on the rendered portal pages), so nothing
      slips back
- [ ] Reader settings: text size, line spacing, a dyslexia-friendly font, and high-contrast
      colours for Page & text, kept per reader
- [ ] Audit and fix our own Desk pages (Server, People & Roles, Background Jobs, Help, the
      proofreaders' work list) against WCAG 2.2 AA

**Later**

- [ ] **Accessible downloads** of proofread books: EPUB 3 with page numbers and accessibility
      metadata, plain text, and DAISY via the DAISY Consortium's tools
- [ ] **Sugamya Pustakalaya** (India's online library for people with print disabilities, run by
      the DAISY Forum of India): share proofread books under section 52(1)(zb) and the
      Marrakesh Treaty, including books for members only
- [ ] Marking regions and drawing zones by keyboard on the image itself
- [ ] Better text for scans without OCR: proofreading drives, and re-OCR on ingest for books
      archive.org has no text for
- [ ] Plain-language help, and the help pages themselves in Kannada and other languages
- [ ] Contribute fixes for Frappe's Desk upstream where staff using screen readers need them
