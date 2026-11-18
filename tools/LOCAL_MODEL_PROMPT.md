# Task for the local model: collect the one-sentence summary of each addon

You are helping build a directory of World of Warcraft addons. For each addon in
`tools/summaries_todo.json` (52 addons), open its CurseForge page in the browser and copy
the **summary**: the single short sentence shown at the very top of the page, directly
under the addon's name. Nothing else.

## Rules
1. **Only the summary.** Do not read, copy or paraphrase the long description further down
   the page, the changelog, comments, or the sidebar. If a page's summary is just the addon's
   name (for example "Titan Panel"), copy that as it is.
2. **Copy it exactly,** as one line of plain text. Do not shorten, reword, translate, fix
   spelling, or add anything. Never invent a summary. If you cannot find one, use an empty string.
3. **One tab, one page at a time, in order.** Open `url`, wait about 3 seconds for it to load,
   read the summary, then go to the next. Do not open pages in parallel.
4. **Do not use any API, key, script that calls CurseForge's endpoints, or any way around a
   block.** Read the page the way a person would. If a page shows a "Just a moment..." check, a
   CAPTCHA, a sign-in wall or an error, STOP and report which addon you were on. Do not try again
   in a loop.
5. If the user pauses the browser connection, stop and wait for them.
6. Do not click Download, Install, Follow, or anything else on the page. Do not sign in.

## Where the summary is (a hint for checking your work)
It is the same text as the page's `og:description` meta tag, first line only. For example,
https://www.curseforge.com/wow/addons/skada -> `Modular damage meter.`
The meta tag may also contain a line like "643.6M Downloads | Addons". Keep only the first line.

## Output
Write one JSON file, `tools/summaries_done.json`, shaped exactly like this (slug -> summary):

```json
{
  "clique": "the summary sentence here",
  "plumber": "the summary sentence here"
}
```

Save the file after every 10 addons so nothing is lost. When done, list any slugs you left
empty and why. The maintainer then runs:

```
python3 tools/merge_summaries.py tools/summaries_done.json
```
