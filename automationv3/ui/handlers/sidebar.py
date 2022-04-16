from collections import namedtuple

from .base import BaseHandler


NavItem = namedtuple('NavItem', ['display', 'path', 'icon'])

class SidebarHandler(BaseHandler):
    def get(self, path=''):
        navitems = [
            NavItem('Dashboard', '/', 'home'),
            NavItem('Test Cases', '/testcases', 'collection'),
            NavItem('Snippets', '/snippets', 'document-text'),
            NavItem('Requirements', '/requirements', 'clipboard-list'),
            NavItem('Reports', '/reports', 'chart-bar')
        ]
        return self.render('sidebar.html', navitems=navitems, nav_path="/"+path)
