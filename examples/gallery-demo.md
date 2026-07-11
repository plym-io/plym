Most CMS engines make you reach for JavaScript the moment you want images to
scroll sideways. plym does not. This post is a live demo of the `gallery` fence,
plus the everyday markdown features the engine renders to static HTML.

## The gallery fence

Wrap any number of images in a `gallery` fence — one image per line. You can use
full markdown image syntax (the alt text is preserved for accessibility and SEO)
or a bare URL. The engine emits a pure-CSS, scroll-snapping horizontal carousel:
no JavaScript, fully crawlable, swipeable on touch.

```gallery
![Coastal cliffs at golden hour](https://picsum.photos/seed/plym-a/960/640)
![Pine forest from above](https://picsum.photos/seed/plym-b/960/640)
![Quiet harbour at dawn](https://picsum.photos/seed/plym-c/960/640)
https://picsum.photos/seed/plym-d/960/640
![Mountain switchbacks](https://picsum.photos/seed/plym-e/960/640)
```

Drag, scroll, or swipe the strip above. Each slide snaps into place.

## How it renders

Under the hood the fence is a `pymdownx.superfences` custom handler. It does two
things that are easy to get wrong:

1. It sets `loading="lazy"` and `decoding="async"` on every image directly,
   because superfences stashes the raw HTML past the lazy-image tree processor.
2. It HTML-escapes every URL and alt string, so untrusted content can't break
   out of the attribute.

Here is the entire formatter — small, as plym functions should be:

```python
def render_gallery(source, language, css_class, options, md, **kwargs):
    images = "".join(
        _gallery_image(line.strip())
        for line in source.splitlines()
        if line.strip()
    )
    return f'<div class="{css_class}">{images}</div>'
```

Note that ordinary fenced code blocks like the one above are **untouched** — they
still flow through the default Pygments highlighter.

## The rest of markdown still works

A single inline image is not a gallery; it renders as a normal centered figure:

![A lone lighthouse](https://picsum.photos/seed/plym-solo/1200/500)

> The goal was a CMS that nginx can serve entirely on its own — so every feature
> has to survive with zero client-side JavaScript.

Other niceties the engine supports out of the box:

- **Tables** with accent-underlined headers
- ~~Strikethrough~~ and task lists
- Auto-linked, anchored headings feeding the table of contents

| Feature        | JavaScript needed | SEO-friendly |
|----------------|-------------------|--------------|
| Gallery        | No                | Yes          |
| Code highlight | No                | Yes          |
| Table of contents | No             | Yes          |

- [x] Add the gallery fence
- [x] Keep code highlighting intact
- [ ] Ship your own photo essay

That last box is yours to check.
