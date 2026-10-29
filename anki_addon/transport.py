import json, urllib.request, urllib.parse, ipaddress


def validate_url(url, allow_lan_http=False):
    u = urllib.parse.urlsplit(url.strip().rstrip('/'))
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('Use a server URL such as https://your-server.example')
    host = u.hostname
    loopback = host in ('localhost', '127.0.0.1', '::1')
    try:
        addr = ipaddress.ip_address(host)
        private = addr.is_private and not addr.is_unspecified
    except ValueError:
        private = host.endswith('.local')
    if u.scheme != 'https' and not loopback and not (allow_lan_http and private):
        raise ValueError('HTTPS is required; local-network HTTP needs explicit opt-in')
    return url.strip().rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Server redirects are not accepted')


class Client:
    def __init__(self, url, token, allow_lan_http=False):
        self.url = validate_url(url, allow_lan_http)
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, path, method='GET', data=None, raw=False, content_type='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.url + path, data=body, method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': content_type})
        with self.opener.open(req, timeout=20) as response:
            payload = response.read(52 * 1024 * 1024 + 1)
        if len(payload) > 52 * 1024 * 1024:
            raise ValueError('Server response too large')
        return payload if raw else json.loads(payload)
