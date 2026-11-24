#!/usr/bin/env python3
"""Make long-text fields render as Markdown across templates."""
import sys

PATCHES = [
    ("bugs.html",
     '<p class="entry-body"><b>\u65b9\u6848\uff1a</b>{{ b.solution }}</p>',
     '<div class="entry-body md-body"><b>\u65b9\u6848\uff1a</b>{{ b.solution|md }}</div>'),
    ("compile_errors.html",
     '<p class="entry-body"><b>\u89e3\u51b3\uff1a</b>{{ e.solution }}</p>',
     '<div class="entry-body md-body"><b>\u89e3\u51b3\uff1a</b>{{ e.solution|md }}</div>'),
    ("error_codes.html",
     '<p class="entry-body"><b>\u65b9\u6848\uff1a</b>{{ c.solution }}</p>',
     '<div class="entry-body md-body"><b>\u65b9\u6848\uff1a</b>{{ c.solution|md }}</div>'),
    ("handbook.html",
     '<p class="entry-body"><b>\u65b9\u6848\uff1a</b>{{ c.solution }}</p>',
     '<div class="entry-body md-body"><b>\u65b9\u6848\uff1a</b>{{ c.solution|md }}</div>'),
    ("perf.html",
     '<p class="entry-body">{{ r.detail }}</p>',
     '<div class="entry-body md-body">{{ r.detail|md }}</div>'),
    ("printers.html",
     '<p class="entry-body"><b>\u5907\u6ce8\uff1a</b>{{ p.notes }}</p>',
     '<div class="entry-body md-body"><b>\u5907\u6ce8\uff1a</b>{{ p.notes|md }}</div>'),
    ("protocols.html",
     '<p class="entry-body"><b>\u5907\u6ce8\uff1a</b>{{ p.notes }}</p>',
     '<div class="entry-body md-body"><b>\u5907\u6ce8\uff1a</b>{{ p.notes|md }}</div>'),
    ("diary.html",
     '<p class="entry-body">{{ d.content }}</p>',
     '<div class="entry-body md-body">{{ d.content|md }}</div>'),
    ("review.html",
     '<p class="entry-body">{{ log.content }}</p>',
     '<div class="entry-body md-body">{{ log.content|md }}</div>'),
    ("work.html",
     '<p class="entry-body">{{ log.content }}</p>',
     '<div class="entry-body md-body">{{ log.content|md }}</div>'),
]

apply = "--apply" in sys.argv
for name, old, new in PATCHES:
    path = "templates/" + name
    with open(path, encoding="utf-8") as f:
        text = f.read()
    n = text.count(old)
    if n == 0:
        print("SKIP  %-22s pattern not found" % name)
        continue
    if apply:
        text = text.replace(old, new)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print("%-6s %-22s replacements=%d" % ("APPLY" if apply else "DRY", name, n))
