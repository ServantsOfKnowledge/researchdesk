# Members, lending and acquisitions

Research Desk can run the lending side of a library too: a roll of **members** with ID cards, **lending** and
returns at a desk, **holds**, **fines** (payable online), **acquisitions** (vendors, purchase orders, **budgets and
invoices**), **periodicals** (serials) and **interlibrary loan**. It is for schools,
colleges and small libraries that do not run a separate library system. A library that lends through
[Koha](koha.md) keeps using Koha and leaves this switched off.

It is **off by default**. Switch it on under Settings → Features → *Members, lending and acquisitions*, or
tick the profile *School or college library (lends books)*. While it is off nothing is collected and none of
its screens show.

## Turning it on

1. Settings → Features: tick **Members, lending and acquisitions** (the school profile also switches on reader
   accounts and page-level search).
2. Settings → Readers & Access → **Members and Lending**: the days the library is closed, how long a held book
   waits, the category new sign-ups get, the currency symbol, whether overdue loans can be renewed, how long
   returned loans are kept, and the text printed on the back of the ID card.
3. Make at least one **Member Category** (see below) and choose it as the category for new sign-ups.
4. Add copies of your books (see [Copies](#copies)) and members (see [Members](#members)).

Cataloguers and Managers work the lending screens. Readers see only their own page, **My library**.

## Member categories

Desk → Members and Lending → **Member Categories**. A category holds the rules for the people in it, for
example *Student*, *Teacher*, *Staff*:

| Rule | What it does |
|---|---|
| Loan days | how long a book may be kept; the due date moves to the next day the library is open |
| Books at once | most loans at a time (0 = no limit) |
| Renewals | how many times one loan can be extended |
| Holds at once | most holds a member can have (0 = no limit) |
| Fine per day, grace days, fine cap | the late fine: days after the grace days times the rate, never above the cap |
| Block borrowing over | a member who owes more than this cannot borrow until they pay (0 = never) |
| Membership lasts | months a new membership runs (0 = no end date) |

## Members

Desk → **Members**. Each member has a name, a category, a status, the number on their own **ID card** (school,
college or employee number), a photo and, optionally, a date of birth, email, phone and class or department.
The member number (M-00001, M-00002…) is made when you save; it is the number on the library card and in its
barcode.

Statuses: **Active**, **Expired** (past the end date; set again by giving a later date), **Blocked**, **Listed**
(on the roster, has not joined the portal yet), **Pending** (joined, waiting for staff) and **Rejected**.

### Loading a roster

To load all the students or staff at once, use Frappe's **Data Import** (Desk → Data Import) on *RD Patron*:
one row per person with *full name*, *category*, *status* (**Listed**), *institution id*, and a *date of birth*
and/or *email* (these are what the person types to prove who they are). Include *valid until* if the
membership ends on a set date.

### Joining the portal with an ID card

People join at **/library/membership** (the library's home page and book pages point there). They give their
name, email and a password, the number on their ID card and their date of birth. They may also add a photo of
the card.

- **On the roster and the date of birth matches:** they are a member at once: active membership, the Reader
  role, a digital card on **My library**.
- **Anything else** (no date given, a different one, the number is not on the roster, or the email alone matches
  the roster): they get an account and a *Pending* membership. A **manager** opens the member (Desk → Members),
  looks at the photo of the ID card, and presses **Approve** or **Turn Down**. Managers get an alert in the Desk
  bell when someone is waiting.

An email alone never makes a member, because anyone can type someone else's email. The form gives the same
answer whether or not the number is on the roster (My library shows the truth), and an ID number that is guessed
at more than ten times in an hour is closed for that hour, so it cannot be used to find out dates of birth. Sign-ups
are rate limited and the photo is checked and redrawn (JPEG or PNG, 2 MB at most, only library staff can see
it). The date of birth and the photo are deleted as soon as a manager has decided; a turned-down sign-up is
deleted after 30 days.

A person who already has a portal account signs in and uses the same page to **link** it to their roster entry
(the date of birth must match).

### The ID card

**Print ID Card** on a member (or tick several in the list and choose **Print ID Cards**) opens a page of
credit-card-size cards (85.6 × 54 mm): the library's name and logo, the photo, name, category, class or
department, ID number, end date and a **Code 39 barcode** of the member number. The back carries the text from
Settings. Print at 100% on card stock or sticker sheets and cut. Members can show or print their own card from
**My library**.

## Copies

Desk → **Copies**. A copy is one physical book: it belongs to a catalogue record (an *Item*, which may also be
a digitised book), has a **barcode**, a call number and a shelf or branch, and a status: *Available*, *On loan*,
*On hold shelf*, *In processing*, *Lost*, *Withdrawn*. **Reference only** copies are read in the library and
never lent.

The barcode is made when you save (C-000001, C-000002…) unless you type one first. **Print Barcode Label** (on
a copy, or **Print Barcode Labels** from the list) makes labels to stick on the books. Copies arrive
automatically when you receive an order. To load existing holdings, use Data Import on *RD Copy*.

A copy goes on loan, on the hold shelf or back on the shelf only through the Circulation Desk, so the loans and
the shelf never disagree.

## The Circulation Desk

Desk → **Circulation Desk**. A barcode scanner types the code and presses Enter, so every box works with one.

- **Lend:** scan the member's card (or type their ID number or name), then scan each book. The due date comes
  from the member's category and the closed days. A refusal says why: expired or blocked member, too many
  loans, fines over the limit, a copy already on loan, lost, reference only, or kept for another member.
- **Return:** scan the book. A late fine is charged by the category's rule. If another member is waiting for the
  title, the screen says *Keep it on the hold shelf for …*.
- **Renew** and **Lost** on each loan. Lost closes the loan, marks the copy lost and, when the copy has a price, charges it.
- **Fines:** mark *Paid*, or *Waive*.
- Two lists: what is **overdue** and what waits on the **hold shelf**.

No email is sent about loans (Research Desk's email is for account messages only). Members see what is due on
**My library**, and staff see what is overdue here.

## Holds

When every copy of a book is out, a member can place a **hold** on the book's page (or staff place one at the
desk). The next returned copy goes on the hold shelf for the first member waiting, and is kept for the number of
days in Settings; then it goes to the next one. A loan cannot be renewed while someone is waiting for the book.

## Fines

A late fine is made when the book is returned. Staff mark it **Paid** or **Waived** at the desk; the library
takes payment itself (cash or its own way), Research Desk records it. A fine due counts toward *Block borrowing
over*. A member can also pay online (see [Paying fines online](#paying-fines-online)).

## Paying fines online

Optional, off until the library sets it up: Settings → Members and Lending → **Online Payment of Fines**, choose
**Razorpay** and give its *Key ID*, *Key Secret* and a *Webhook Secret* you choose. In the Razorpay dashboard add a
webhook to `https://<your portal>/api/method/sok_resdesk.payments.webhook` for the event **payment_link.paid**,
with the same secret.

A member with fines due sees **Pay online** on My library. Research Desk makes a Razorpay *payment link* for the
total and sends them to it: the card or UPI details go to Razorpay and never touch this server, and Razorpay sends
no email or SMS for it. When Razorpay's webhook says the link was paid, the fines are marked **Paid**. The webhook
is believed only with the right signature and for a link this site made, an amount that is not what was asked for is
not accepted (it is written to the Error Log), and being told twice changes nothing. If a member pays a link for
fines the desk had already cleared, the payment is recorded and the Error Log says a refund may be needed. The
Razorpay keys can be changed only by a System Manager. Desk → **Online Payments** lists every link and its
state (read only). It is not available in Classified mode, which refuses outside connections. Fines still due can
always be paid at the desk.

## My library

Members open **/library/loans** (or **Show my ID card**): what they have on loan and when it is due, a
**Renew** button, their holds, the fines due, and their card. The library's own rules decide what a renewal
may do.

## Acquisitions

Desk → **Vendors** and **Purchase Orders** (money: see [Budgets and invoices](#budgets-and-invoices)).

1. Add the **Vendor**.
2. Write a **Purchase Order**: the vendor and the books (title, author, ISBN, how many, unit price). A line can
   point at a catalogue record you already have; if not, one is made when the books arrive.
3. **Place Order** when it goes to the vendor.
4. **Receive Books** when they come: say how many of each arrived (a delivery can be partial). One copy is made
   per book, on the shelf and ready to lend, with its barcode; the order shows *Part Received* or *Received*.
   **Print barcode labels** from the message that follows.

## Budgets and invoices

Desk → **Budgets**: a budget has a name, an amount and a period (*Books 2026-27*). Put it on a **Purchase Order**
(the *Budget* field): **Place Order** refuses an order that is more than what is left. A budget shows what orders
**committed**, what invoices **spent** and what is **left**: an order holds back its total less what has been
invoiced against it, so an invoice turns a commitment into spending without counting it twice.

Desk → **Invoices**: the vendor's invoice (number, date, amount) against the order. Research Desk checks it
against the order and what actually arrived (*the three-way check*): more than 5% above the order, or above the
value of the books received, is flagged in orange so a manager looks before **Approve**. Managers approve and
record **payment** (how it was paid: cheque, transfer, voucher). The library pays outside Research Desk; it
records that it did. An invoice number is not accepted twice for one vendor (capitals and spaces do not make it
different), and one for another vendor's order is refused. Only the buttons move an invoice along: an approved invoice
cannot be edited or deleted (cancel it and enter another), and Settings can require that **someone else** approves an
invoice a manager entered.

## Periodicals (serials)

Desk → **Serial Subscriptions**: the periodical, its vendor, how often it comes (weekly to yearly), when the first
issue is due and how many days late it may be. **Generate Issues** makes the expected issues (the 15th stays the 15th;
31 January + a month is 28 February). When an issue arrives open it and press **Check In**: it becomes a reference
copy with a barcode (a current issue is read in the library), under the periodical's catalogue record (made the
first time if there is none). Each night, issues that are overdue by the claim period become **Late** and
managers get one alert in the Desk bell (no email). **Claimed from Vendor** and **Mark Missing** record what
happened; asking the vendor is done outside Research Desk.

## Interlibrary loan

Desk → **Interlibrary Loans**, in either direction.

- **Borrowing**: a member asks for a book the library does not have (they can, from **My library**, up to the
  number set in Settings; or staff enter it for them). Staff move it along: **Sent** (to the other library, whose
  name goes in the request), **Received**, **Lent to Patron** (the due date comes from the member's category; an
  expired or blocked member is refused), **Returned**, **Sent Back**, **Closed**. A fee the other library charges
  can be **charged to the member**, who then sees it as a fine (and can pay it like one). The member sees the
  request and its step on My library; no email is sent.
- **Lending**: another library asks for one of ours: **Requested**, **Approved**, **Sent** (the chosen copy goes
  off the shelf as *Interlibrary loan*), **Returned** (it goes back on the shelf, or to a member waiting for it),
  **Closed**.

The steps are fixed: a book cannot be lent to the member before it has been received. A request can be **Refused**
or **Cancelled** while nothing has been sent. Research Desk does not talk to other libraries' systems (ISO ILL,
NCIP): it keeps the library's own record, and the library writes to the other library in its usual way.

## Privacy

The library keeps no record of what people read: returned (and lost) loans with no unpaid fine are deleted after the number
of days in Settings (180 by default; 0 keeps them). A settled fine keeps no link to the book. Photos of ID cards
are private files. Deleting a member is for managers.

## What is not here

Not built: invoice line items and tax (GST) handling, automatic claims to vendors, electronic ordering (EDI),
bundling several periodical titles in one subscription, ILL protocols (ISO ILL, NCIP), self-service kiosks, and
payment providers other than Razorpay. A library that needs them keeps Koha or another library system; Research
Desk links to it ([Koha](koha.md)).
