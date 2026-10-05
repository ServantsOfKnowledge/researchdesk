# Giving back to Wikimedia with your own account

What Research Desk gives back to Wikidata (and, later, Wikisource) is sent under the account of
the person who sends it. Wikimedia credits edits to who made them and does not allow shared
accounts for people, so each contributor connects their own account, once.

## Connect your account

Research Desk → **My Wikimedia Account**. The page lists the steps:

1. Open the registration page (the link on that page) while logged in to Wikimedia.
2. Propose an **OAuth 2.0** consumer and tick *This consumer is for use only by* your own
   username. An owner-only consumer needs no approval.
3. Grant *Edit existing pages* and *Create, edit, and move pages*, and, to send photographs to
   Commons, *Upload new files*.
4. Submit, copy the **access token** Wikimedia shows, and paste it under **Connect**.

Research Desk asks Wikimedia who the token belongs to and whether it may edit, then keeps it
encrypted. Only you can read or use it; administrators cannot. **Disconnect** forgets it here
(revoke the consumer on Wikimedia as well if you want it dead everywhere).

## Send as yourself

Authorities → Give back shows **Send as {your username}** once you are connected: the names and
author links worked out from the library's matches are sent to Wikidata under your account.
Without a connection the page links here instead. A library's shared Push Target (a bot account)
still works for libraries that run one.

Wikimedia's own rules apply: edits can be reverted, the wiki's lag limits are respected, and
nothing is sent unless you press the button.

## Send your corrections back to Wikisource

A book that came from Wikisource has **Actions → Send to Wikisource**. It reads those pages as
they are on the wiki now and shows you, page by page, what would change, before anything is sent:

- a page **you proofread** here, which is not yet proofread there, goes back as *proofread*
  (level 3) with your corrected text, shown as a diff;
- a page **you validated** here, unchanged, which another person proofread there, goes back as
  *validated* (level 4), text untouched. Wikisource wants a different validator than the
  proofreader, so a page you proofread there yourself is left for someone else.

Only your own work is ever sent, under your own account. Never sent: a page already validated
there; a page proofread there that you changed (what is on the wiki is not overwritten from here:
correct it there); a page whose wikitext has templates, links or notes that plain text would lose;
a page that does not exist on the wiki (pages are not created from here). Each edit names the
revision you reviewed, so a page someone changed meanwhile is refused by the wiki itself and
reported, not overwritten. At most 25 pages go at a time, one by one.

**The licence.** Wikisource's text is CC BY-SA 4.0. Sending needs the library's *Ground truth
licence* (Settings) to be CC0, CC-BY or CC-BY-SA, so what goes back is text the library is free to
share on those terms. Until it is chosen the button explains what to do.

After sending, *Refresh from Source* on the book reads the pages again so this library shows the
wiki's new level.

## Giving photographs to Wikimedia Commons

A photograph item (see [Photographs](photographs.md)) has **Actions → Send to Wikimedia Commons**.
It uploads the original file under your own account, with a description page and, when the photograph
names Wikidata items under *Depicts*, a structured-data *depicts* statement for each.

Nothing is sent before you have seen it. The dialog shows the file name Commons will give it (you
can change it), the description, the categories you choose, the licence, the author, what it
depicts, and the description page exactly as Commons will receive it. It checks with Commons as you
go: whether it already has the same file (by checksum), whether the name is taken, and whether each
category exists. You then confirm that the photograph is yours to give, or that its owner agreed,
under that licence, and that publishing on Commons cannot be taken back.

What stops it, with the reason on screen:

- **A licence Commons does not take.** Only CC0, CC BY, CC BY-SA and public-domain marks go; the
  photograph's *Licence URL* (Rights) says which. NC and ND licences are refused, as is no licence.
- **No author.** Commons credits the photographer: name them under Creators.
- **A photograph that is not open to read here**, or whose original is not held here.
- **A file over 100 MB**, or not a JPEG, PNG, TIFF or WebP.
- **A token that may not upload**: register the consumer again with *Upload new files* granted.
- **A duplicate, a name already taken, a category that does not exist.** Commons' own warnings are
  never overridden.

After sending, the item records the Commons file name, who sent it and when, and links to it; the
button goes away. One photograph is sent at a time, by a person who looked at it.
