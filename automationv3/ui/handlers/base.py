import tornado
from jinja2 import TemplateNotFound

class Jinja2TemplateRenderer:
    """
    Helper class for rendering jinja2 templates. 
    """

    def render_template(self, template_name, **kwargs):
        try:
            env = self.settings['jinja_env']
            template = env.get_template(template_name)
        except TemplateNotFound:
            raise TemplateNotFound(template_name)

        return template.render(kwargs)


# pylint: disable=W0223
class BaseHandler(tornado.web.RequestHandler, Jinja2TemplateRenderer):
    """
    Base handler for application. Sets up global template arguments
    """

    def render(self, template_name, **kwargs):
        """
        This is for making requests specific items available to 
        template environment and to render jinja template render
        """

        # List of request specific items available to templates.
        kwargs.update({
            'static_url': self.static_url,
            'request': self.request,
            'xsrf_token': self.xsrf_token,
            'xsrf_form_html': self.xsrf_form_html
        })

        try:
            content = self.render_template(template_name, **kwargs)
        except TemplateNotFound:
            content = self.render_template('500.html', error_msg='Could not find template "%s"' % template_name)

        self.write(content)


