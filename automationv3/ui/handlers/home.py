from .base import BaseHandler

class HomeHandler(BaseHandler):
    def get(self):
        return self.render('home.html', heading_text='Dashboard')
