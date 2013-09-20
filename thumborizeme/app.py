import sys
import os.path
from json import dumps
from datetime import datetime

import tornado.ioloop
import tornado.web
import tornado.gen
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.concurrent import return_future
import lxml.html


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        url = self.get_argument('url', None)

        if url is None:
            title = "Check how you would benefit from using thumbor"
        else:
            title = "Test results for %s" % url

        self.render('index.html', title=title)


class GetReportHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    @tornado.web.asynchronous
    def get(self):
        site_url = self.get_argument('url')

        if site_url in self.application.STUDIES:
            study = self.application.STUDIES[site_url]
            if not self.is_expired(study['date']):
                print "GETTING FROM CACHE"
                self.write(self.to_json(study))
                self.finish()
                return

        response = yield self.get_content(site_url)

        html = lxml.html.fromstring(response.body)
        imgs = html.cssselect('img[src]')

        images = {}

        for img in imgs:
            url = img.get('src').lstrip('//')

            if not url.startswith('http'):
                url = "%s/%s" % (site_url.rstrip('/'), url)

            print "Loading %s..." % url

            try:
                if url in images:
                    continue

                loaded = yield self.get_content(url)
                if loaded.code != 200:
                    continue
                original_size = len(loaded.body)

                #thumborized = "http://thumbor.thumborize.me/unsafe/filters:strip_icc()/%s" % url
                #print "Loading thumborized %s..." % thumborized
                #loaded = yield http_client.fetch(thumborized)
                #thumborized_size = len(loaded.body)

                webp = "http://thumbor.thumborize.me/unsafe/filters:strip_icc():format(webp):quality(80)/%s" % url
                #print "Loading webp %s..." % webp
                loaded = yield self.get_content(webp)
                if loaded.code != 200:
                    continue
                webp_size = len(loaded.body)

                images[url] = {
                    'original': original_size / 1024.0,
                    #'thumborized': thumborized_size / 1024.0,
                    'webp': webp_size / 1024.0
                }
            except Exception, err:
                print str(err)
                continue

        self.application.STUDIES[site_url] = {
            'url': site_url,
            'images-count': len(images.keys()),
            'images-size': round(sum([image['original'] for image in images.values()]), 2),
            'images-webp-size': round(sum([image['webp'] for image in images.values()]), 2),
            'date': datetime.now()
        }

        self.write(self.to_json(self.application.STUDIES[site_url]))

        self.finish()

    def to_json(self, value):
        dthandler = lambda obj: obj.isoformat() if isinstance(obj, datetime) else None
        return dumps(value, default=dthandler)

    @return_future
    def get_content(self, url, callback):
        req = HTTPRequest(
            url=url,
            connect_timeout=1,
            request_timeout=3,
        )

        http_client = AsyncHTTPClient()
        http_client.fetch(req, callback)

    def is_expired(self, dt):
        return (datetime.now() - dt).total_seconds() > (6 * 60 * 60)


root_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
settings = dict(
    static_path=root_path,
    template_path=root_path
)

application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/report", GetReportHandler),
], **settings)

application.STUDIES = {}

if __name__ == "__main__":
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    else:
        port = int(sys.argv[1])

    application.listen(port)
    tornado.ioloop.IOLoop.instance().start()