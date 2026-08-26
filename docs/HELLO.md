Welcome to **plym**. Your instance is deployed, running, and already serving this page as a static HTML file — no framework booted up to answer the request.

This post is a real post. Open it in the editor, rewrite it, delete it. Nothing here is special.

## Open the admin dashboard

Your blog is managed from the [admin dashboard](__ADMIN_PATH__), a Markdown-native editor built for people who write in Markdown anyway.

Sign in with the email and password the installer printed. Change that password first — it was generated for you and printed to a terminal.

:::note
The dashboard lives at `<your-blog-url>/plym-admin` and moves with your blog. Serve the blog at `example.com/writing` and the dashboard follows to `example.com/writing/plym-admin`.
:::

## Put it on your own domain

plym runs behind any reverse proxy, and the CLI can configure the common ones for you:

```bash
plym set url example.com/blog --caddy
```

Swap `--caddy` for `--nginx` or `--traefik`. nginx and Caddy are installed and configured for you, with a TLS certificate obtained on the spot; both need `sudo`. `--traefik` writes router labels for you to finish, and needs no root at all.

Doing it by hand instead? Forward `/{blog_prefix}` to the app's `$PORT`. The exact rules per proxy are in [reverse proxy examples](https://plym.io/docs/deployment/reverse-proxy-examples), and serving from a subfolder has [its own guide](https://plym.io/docs/deployment/subdirectory).

Run `plym -h` for the full command list.

## Change how it looks

Every page you serve is rendered from a template — Jinja2 for the markup, YAML for the fonts and colours. Install a different one:

```bash
plym template install <template_name>
```

Add `--update` to force a fresh download over an existing copy.

* **Browse templates:** the [official registry](https://github.com/plym-io/plym-templates)
* **Build your own:** the [custom templates guide](https://plym.io/docs/configuration/custom-templates)
* **Restyle the one you have:** [template configuration](https://plym.io/docs/configuration/template-configuration)

## Configure the instance

Site-wide behaviour lives in `config.yaml`:

| Key | What it does |
| --- | --- |
| `name` | Site name, used in titles and metadata. |
| `description` | One line about the blog, used as the index page's meta description. |
| `blog_prefix` | Path your blog is served from, e.g. `/blog`. |
| `language` | Language code for content and metadata, e.g. `en`. |
| `template` | Template used to render every page, e.g. `default`. |
| `logo` | URL of the logo shown in the header. SVG, PNG, WebP or JPEG. |
| `favicon` | URL of the browser tab icon. Must be a real `.ico` file. |
| `prism.enabled` | Syntax highlighting for code blocks, `true` or `false`. |
| `prism.languages` | Languages loaded for highlighting, e.g. `python,bash,yaml`. |
| `pagination.page_size` | Posts per page on the index, e.g. `10`. |

Two commands apply changes:

```bash
plym reload    # runtime-only settings: pagination, robots, media
plym rebuild   # anything that changes rendered HTML: template, logo, prism
```

The full key-by-key reference is in [instance configuration](https://plym.io/docs/configuration/instance-configuration).

## What you get for free

Every published post is written to disk as `.html` and `.md` at the same time. Your web server hands over a file; nothing renders per request.

* **Agents get Markdown.** Send `Accept: text/markdown` to any post URL and you get the Markdown twin instead of the HTML — no scraping, no parsing.
* **Metadata is generated, not configured.** Open Graph tags, JSON-LD, `sitemap.xml`, `robots.txt` and `llms.txt` are rewritten every time you publish.
* **Leads collect themselves.** `POST /api/collect` takes any JSON object from any form on your site and stores it. The form at the bottom of this page is wired to it — try it, then read the entries back on the Leads page of your dashboard. Details in the [leads guide](https://plym.io/docs/content-management/leads).
* **Your editor can be an agent.** The optional MCP server lets Claude and other clients draft, publish and update posts directly. Start it with `plym enable mcp`, or read the [MCP introduction](https://plym.io/docs/mcp-server/mcp-introduction).

## Where to go next

* [Write your first post](https://plym.io/docs/content-management/your-first-post)
* [Markdown reference](https://plym.io/docs/content-management/markdown-reference) — admonitions, tabs, galleries, FAQs
* [Add your team](https://plym.io/docs/identity-and-access/managing-users)
* [Full documentation](https://plym.io/docs/)
