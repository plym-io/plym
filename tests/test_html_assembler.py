from plym.render.html_assembler import HtmlAssembler


def test_injects_head_and_body() -> None:
    html = "<html><head><title>x</title></head><body><p>hi</p></body></html>"
    result = HtmlAssembler.inline_assets(
        html,
        css=".foo{color:red}",
        prism_js="console.log('x')",
        inject_head='<script src="ga.js"></script>',
        inject_body="<noscript>fallback</noscript>",
    )
    assert '<style>.foo{color:red}</style><script src="ga.js"></script></head>' in result
    assert "<script>console.log('x')</script><noscript>fallback</noscript></body>" in result


def test_omits_empty_injections() -> None:
    html = "<html><head></head><body></body></html>"
    result = HtmlAssembler.inline_assets(html, css="a{}", prism_js="")
    assert "<style>a{}</style></head>" in result
    assert "<script>" not in result


def test_inject_order_css_first_then_user_head() -> None:
    html = "<html><head></head><body></body></html>"
    result = HtmlAssembler.inline_assets(
        html, css="a{}", prism_js="", inject_head="<meta name='foo'>"
    )
    assert "<style>a{}</style><meta name='foo'></head>" in result


def test_inject_order_prism_first_then_user_body() -> None:
    html = "<html><head></head><body></body></html>"
    result = HtmlAssembler.inline_assets(
        html, css="", prism_js="P()", inject_body="<span>S</span>"
    )
    assert "<script>P()</script><span>S</span></body>" in result
