class HtmlAssembler:
    @staticmethod
    def inline_assets(
        html: str,
        css: str,
        prism_js: str,
        inject_head: str = "",
        inject_body: str = "",
    ) -> str:
        head_payload = f"<style>{css}</style>"
        if inject_head:
            head_payload = f"{head_payload}{inject_head}"
        if "</head>" in html:
            html = html.replace("</head>", f"{head_payload}</head>", 1)
        else:
            html = head_payload + html

        body_payload = ""
        if prism_js:
            body_payload += f"<script>{prism_js}</script>"
        if inject_body:
            body_payload += inject_body
        if body_payload:
            if "</body>" in html:
                html = html.replace("</body>", f"{body_payload}</body>", 1)
            else:
                html = html + body_payload
        return html
