from .base import BaseHandler

class NotFoundHandler(BaseHandler):
    def get(self):
        return self.render('404.html')
