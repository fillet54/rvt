from .handlers.home import HomeHandler
from .handlers.sidebar import SidebarHandler

app_routes = [
    (r'/', HomeHandler),
    (r'/(.*)/?nav', SidebarHandler)
]
