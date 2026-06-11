Welcome to **plym**. Your instance is successfully deployed and running.

## Command Line Interface (CLI)

plym includes a built-in CLI to streamline environment management and deployment.

While plym can run behind any reverse proxy, the CLI offers automated routing and provisioning for **Nginx** and **Caddy**. To configure your domain and reverse proxy, run:

```bash
sudo plym set url example.com/blog --nginx

```

*(Use the --caddy flag instead if you prefer Caddy).*

> If the specified web server is not installed locally, the CLI will automatically install it and provision SSL certificates for your domain.

Run `plym -h` for a complete list of available commands.

### Manual Proxy Configuration

Automated routing requires root privileges. To configure the server manually without root access, configure your reverse proxy to forward traffic from your `/{blog_prefix}` routes to the application's `$PORT`. Refer to the [complete guide to plym](https://plym.io/blog/complete-guide-to-plym) for specific routing rules.

## Admin Dashboard

Manage users and content via the built-in [admin portal](/blog/plym-admin). The dashboard features a Markdown-native rich text editor tailored for developer-centric content creation.

## Templates

Modify your site's appearance by installing templates from the registry:

```bash
plym template install <template_name>

```

*Append the `--update` flag to force-sync an existing template.*

* **Find Templates:** [Browse the official plym template registry](https://github.com/plym-io/plym-templates).
* **Build Your Own:** Read the [template development guide](https://plym.io/blog/creating-templates-for-plym) to create custom layouts.

## Configuration

Core application behavior and visual parameters are managed via the `config.yaml` file.

| Key | Example | Description |
| --- | --- | --- |
| `language` | `en` | Default language code for content and metadata. |
| `template` | `default` | Active theme used for site rendering. |
| `logo` | `https://example.com/logo.webp` | Primary site logo URI for navigation/branding. |
| `favicon` | `https://example.com/favicon.ico` | Browser tab icon URI. |
| `prism.enabled` | `true` | Toggles syntax highlighting for code blocks. |
| `prism.languages` | `python,bash,yaml` | Comma-separated list of active Prism languages. |

To apply changes made in `config.yaml`, rebuild the application:

```bash
plym rebuild

```
> This command statically re-renders all blog pages to reflect the updated configuration.*

For advanced customization and environment variables, review the [complete guide to plym](https://plym.io/blog/complete-guide-to-plym).
