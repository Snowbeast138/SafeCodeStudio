import base64
import json
from importlib.resources import files
from urllib.parse import quote


def render_graph(report):
    assets = files('safecode_core').joinpath('assets')
    logo = 'data:image/png;base64,' + base64.b64encode(assets.joinpath('safecode-logo.png').read_bytes()).decode('ascii')
    # Crop the brand shield through an SVG viewport; preserve the original PNG.
    icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="30 20 610 670"><image width="2122" height="741" href="' + logo + '"/></svg>'
    template = assets.joinpath('graph.html').read_text(encoding='utf-8')
    template = template.replace('__BRAND_LOGO__', logo).replace('__BRAND_ICON__', 'data:image/svg+xml,' + quote(icon, safe=''))
    payload = json.dumps({k: v for k, v in report.items() if k != 'csts'}, ensure_ascii=False)
    for char in ('&', '<', '>'):
        payload = payload.replace(char, '\\u%04x' % ord(char))
    return template.replace('__GRAPH_DATA__', payload)
