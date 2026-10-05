# Audio and video

Recordings (talks, interviews, songs, lectures) are catalogued like books and have a **player** with
a **time-coded transcript** beside it. The transcript is kept as segments, each with a start and an
end, so the words of a recording are searchable, a search hit opens the recording at that moment,
people can correct the text and a second person validates it, and captions reach the player for
those who need them. Switch it on or off in Settings → Features → **Audio and video**; it is part of the
*Public research portal* and *Archive keeping its own copies* profiles.

## Recordings in a folder

In a Folder or Server profile, a media file (MP3, M4A, AAC, OGG, OPUS, WAV, FLAC, MP4, M4V, WEBM, OGV)
is a recording. Files with the same name belong to it:

| File | What it is |
|---|---|
| `Ramesh 2019.mp3`, `Ramesh 2019.ogg` | the recording in more than one format (the player offers what the browser plays) |
| `Ramesh 2019.vtt` or `.srt` | its transcript (WebVTT or SRT), taken as segments about 30 seconds long |
| `Ramesh 2019.jpg` or `.png` | its poster (a video's, or a portrait for audio) |
| `Ramesh 2019.json` | its details |

```json
{
  "title": "Ramesh on temple music",
  "creator": ["Ramesh, K."],
  "language": "kan",
  "date": "2019",
  "description": "An interview about the Udupi temple tradition.",
  "subject": ["temple music", "Udupi"],
  "recording": {
    "speakers": ["K. Ramesh", "An interviewer"],
    "place": "Udupi",
    "recorded_on": "2019-03-14",
    "consent": "Consent on file"
  }
}
```

Without a `.json` the file's name is the title. The length is read from the file (the mutagen library,
or ffprobe when it is installed). Details from the `.json` fill the *Recording* section while it is
empty and are never put back over a person's edit. The files stay where they are; readers play and
download them from the portal, and a player can skip about without loading the whole file.

## Recordings from archive.org

On an Internet Archive profile tick **Also Bring in Audio and Video**: the collection's audio, video and
live-music items come in with their playable files (MP3, Ogg, h.264…), played from archive.org, and with
their WebVTT or SRT transcript when the item has one.

## The transcript

On a recording's page the transcript runs beside the player: the segment being played is marked and
followed (switch **Follow the recording** off to read ahead), a click on a time plays from there, and
`?page=3` opens at the fourth segment. Proofreaders and cataloguers **Edit** a segment in place; a
second person validates it, as for any page, and every version is kept.

A recording **without** a transcript: Desk → Item → Actions → **Read the Length**, then **Lay out
Transcript Segments** makes blank segments (a minute each, or as you choose) for people to transcribe
one at a time; the first words typed make the recording searchable. A transcript that already exists is
never laid over.

Speech-to-text (drafting the transcript by machine, for a person to correct) is planned.

## Captions, sharing and access

- A video's player offers the transcript as **captions** (WebVTT), made from the current text.
- The recording is a **IIIF Presentation 3.0** manifest: one canvas with a duration, painted with its sound
  or video, and the transcript as annotations that point at time ranges (`#t=31,65`).
- Access is the book's: public, login to read, login to find, and an embargo from a deposit. The
  *Recording* section's **Speaker's consent** says who agreed to the recording being shared;
  restrictions are set under Access.
