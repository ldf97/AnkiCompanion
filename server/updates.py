"""GitHub release feed, with private-repository credentials kept on the server."""
from pathlib import Path
import hashlib, json, os, re, time, urllib.request, urllib.parse, urllib.error, threading

class UpdateError(ValueError): pass

def version_tuple(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',value)
    if not match: raise UpdateError('Expected a release version such as 1.2.3')
    return tuple(map(int,match.groups()))

class GithubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        target=urllib.parse.urlsplit(newurl)
        if target.scheme!='https' or target.hostname not in {'github.com','api.github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}:
            raise UpdateError('Unexpected release download host')
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if target.hostname!='api.github.com': redirected.remove_header('Authorization')
        return redirected

class ReleaseFeed:
    def __init__(self,directory,fetch=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.cache={};self.assets={}
        self.fetch=fetch or self._fetch
    def _request(self,url,accept):
        headers={'Accept':accept,'User-Agent':'AnkiCompanion/0.1','X-GitHub-Api-Version':'2022-11-28'}
        token=os.environ.get('ANKI_COMPANION_GITHUB_TOKEN')
        if token:headers['Authorization']='Bearer '+token
        return urllib.request.Request(url,headers=headers)
    def _fetch(self,url,accept='application/vnd.github+json',limit=2*1024*1024):
        with urllib.request.build_opener(GithubRedirect).open(self._request(url,accept),timeout=30) as response:
            payload=response.read(limit+1)
        if len(payload)>limit:raise UpdateError('Release metadata exceeds limit')
        return payload
    def release(self,repository,force=False):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository): raise UpdateError('Configure the GitHub repository as owner/name')
        with self.lock:
            cached=self.cache.get(repository)
            if cached and not force and time.time()-cached[0]<300:return cached[1]
            base='https://api.github.com/repos/'+repository
            release=json.loads(self.fetch(base+'/releases/latest'))
            if release.get('draft') or release.get('prerelease'):raise UpdateError('No stable published release')
            assets={a['name']:a for a in release.get('assets',[])}
            if 'update.json' not in assets:raise UpdateError('Release has no update manifest')
            manifest=json.loads(self.fetch(base+'/releases/assets/'+str(assets['update.json']['id']),'application/octet-stream'))
            if manifest.get('schema_version')!=1:raise UpdateError('Unsupported update manifest')
            version_tuple(manifest['version'])
            if release['tag_name'].removeprefix('v')!=manifest['version']:raise UpdateError('Release tag and manifest version disagree')
            if not re.fullmatch(r'[a-fA-F0-9]{40}',manifest.get('commit','')):raise UpdateError('Release must identify its source commit')
            if type(manifest.get('build')) is not int or manifest['build']<1:raise UpdateError('Invalid release build number')
            validated={}
            for platform,item in manifest.get('assets',{}).items():
                filename=item.get('filename','')
                if platform not in ('android','windows','source'):raise UpdateError('Unsupported update platform')
                if not re.fullmatch(r'[A-Za-z0-9_.-]+\.(apk|exe|zip)',filename):raise UpdateError('Invalid release filename')
                if not filename.endswith({'android':'.apk','windows':'.exe','source':'.zip'}[platform]):raise UpdateError('Wrong package type for platform')
                if not re.fullmatch(r'[a-f0-9]{64}',item.get('sha256','')):raise UpdateError('Invalid release checksum')
                asset=assets.get(filename)
                if not asset or asset.get('size')!=item.get('size') or not 0<item['size']<=500*1024*1024:raise UpdateError('Release asset size mismatch')
                identity=str(asset['id'])
                validated[platform]=dict(item,asset_id=identity,download_path='/v1/updates/download/'+identity)
                self.assets[(repository,identity)]=dict(item,url=base+'/releases/assets/'+identity)
            result=dict(version=manifest['version'],build=manifest['build'],commit=manifest['commit'],
                        notes=str(release.get('body') or '')[:6000],release_url=release['html_url'],assets=validated)
            self.cache[repository]=(time.time(),result)
            return result
    def check(self,repository,platform,current,build=0,force=False):
        if not repository:return dict(configured=False,available=False,message='GitHub release source is not configured yet')
        try:release=self.release(repository,force)
        except urllib.error.HTTPError as exc:
            if exc.code==404:return dict(configured=True,available=False,message='No approved stable release has been published yet')
            raise
        item=release['assets'].get(platform)
        if not item:return dict(configured=True,available=False,message='This release has no package for '+platform)
        newer=release['build']>build if platform=='android' else version_tuple(release['version'])>version_tuple(current)
        return dict(configured=True,available=newer,version=release['version'],build=release['build'],commit=release['commit'],notes=release['notes'],
                    release_url=release['release_url'],message='Update available' if newer else 'Up to date',**item)
    def download(self,repository,identity):
        with self.lock:
            if (repository,identity) not in self.assets:self.release(repository)
            item=self.assets.get((repository,identity))
            if not item:raise UpdateError('Release changed; check for updates again')
            destination=self.directory/(identity+'-'+item['filename'])
            if destination.exists() and destination.stat().st_size==item['size']:
                if hashlib.sha256(destination.read_bytes()).hexdigest()==item['sha256']:return destination,item['filename']
            temp=destination.with_suffix('.partial');digest=hashlib.sha256();total=0
            try:
                with urllib.request.build_opener(GithubRedirect).open(self._request(item['url'],'application/octet-stream'),timeout=60) as response,temp.open('wb') as output:
                    while chunk:=response.read(1024*1024):
                        total+=len(chunk)
                        if total>item['size']:raise UpdateError('Download exceeds declared size')
                        digest.update(chunk);output.write(chunk)
                if total!=item['size'] or digest.hexdigest()!=item['sha256']:raise UpdateError('Release checksum verification failed')
                temp.replace(destination);return destination,item['filename']
            finally:temp.unlink(missing_ok=True)
