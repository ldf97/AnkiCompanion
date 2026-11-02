"""Smoke-check real hosted HTTPS and rejection of unauthenticated API calls."""
import ssl, sys, urllib.error, urllib.parse, urllib.request

def check(url):
    base=urllib.parse.urlsplit(url)
    if base.scheme!='https' or not base.hostname or base.username or base.password:
        raise ValueError('Expected a public HTTPS hostname')
    with urllib.request.urlopen(url.rstrip('/')+'/health',timeout=15,context=ssl.create_default_context()) as r:
        if r.status!=200 or b'"ok"' not in r.read(1024):
            raise RuntimeError('Server health check failed')
    try:
        urllib.request.urlopen(url.rstrip('/')+'/v1/state',timeout=15,context=ssl.create_default_context())
        raise RuntimeError('Unauthenticated state endpoint was exposed')
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise RuntimeError(f'Expected auth rejection 401, received {e.code}') from e
    print('Server healthy over validated HTTPS; private state requires authentication')

if __name__=='__main__':check(sys.argv[1])
