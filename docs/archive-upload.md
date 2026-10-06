# Giving a book to the Internet Archive

A book that is yours to give can be uploaded from Research Desk to archive.org, so it is kept and
read there too. Whatever is sent is **always public** on archive.org: Research Desk never makes a
dark or hidden item, so only a book that is public here, with a licence, can go.

## Who can send

- **A depositor** sends their own accepted deposit, under their own archive.org account, into the
  library's collection.
- **Library staff** (manager, cataloguer) can send any book whose files are held on this
  server. They can choose the collection (one their account may add to) and send under their own
  account or under a shared account kept on a Push Target (type Internet Archive).

Nobody sends under someone else's account, and the keys are never shown: not to administrators,
not in the browser.

## Connect your account

Do this once. Staff: Research Desk → My archive.org Account. Depositors: the box on the deposit
page. You need an archive.org account (free); the page shows your access key and secret key:

1. Log in to archive.org.
2. Open <https://archive.org/account/s3.php> and copy both keys.
3. Paste them under Connect. Research Desk asks archive.org whether they work before keeping them
   (the secret encrypted).

Disconnect forgets them.

## Send a book

Open the book in the Desk and choose Actions → Send to the Internet Archive (depositors: Send to
the Internet Archive beside an accepted deposit). The review shows:

- the archive.org **identifier** (made from the title; change it, it is permanent);
- the **collection** (staff may change it; everyone else uses the library's, set in
  Settings → Catalogue → Internet Archive);
- the **account** it goes under;
- the title, creators, year, licence and the **files** that will be uploaded.

It refuses, and says why, when the identifier is already taken on archive.org, the book is not
public or has no licence, its files are not held here (a book on archive.org already, or on a web
server), or there are no keys. You confirm that the work is yours to give and will be public, then
Send. The upload runs in the background (books are large); the book records *Queued*,
*Uploading*, *On archive.org* or *Failed*. After a failure, send again to resume: files already
there are put again.

archive.org makes its own copies (text, derivatives) after the upload; that takes a while.
