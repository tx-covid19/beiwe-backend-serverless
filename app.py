import os
from datetime import datetime, timedelta

import jinja2
from flask import Flask, redirect, render_template
from raven.contrib.flask import Sentry
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_jwt_extended import JWTManager

from config import load_django

from api import (admin_api, copy_study_api, dashboard_api, data_access_api, data_pipeline_api, external_api,
                 mobile_api, participant_administration, survey_api, redcap_api, survey_api,
                 participant_auth, event_api, overview_api, tracker_api, refresh_api)
from config.settings import SENTRY_ELASTIC_BEANSTALK_DSN, SENTRY_JAVASCRIPT_DSN, DOMAIN_NAME, BEIWE_SUBDOMAIN, DIGITAL_SELFIE_SUBDOMAIN, FITBIT_SUBDOMAIN, BEIWE_ROOT_DOMAIN, CDN_DOMAIN
from libs.admin_authentication import is_logged_in
from libs.security import set_secret_key
from pages import (admin_pages, data_access_web_form, mobile_pages, survey_designer,
    system_admin_pages, digital_selfie_web_form, fitbit_web_form)

from flask_cdn import CDN, url_for

cdn = CDN()

def envopts(local, prod):
    if DOMAIN_NAME == 'localhost':
        return local
    return prod

def subdomain(directory):
    app = Flask(__name__, static_folder=directory + "/static", subdomain_matching=True)
    set_secret_key(app)
    app.config['JWT_SECRET_KEY'] = app.secret_key
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=5)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=7)
    jwt = JWTManager(app)
    loader = [app.jinja_loader, jinja2.FileSystemLoader(directory + "/templates")]
    app.jinja_loader = jinja2.ChoiceLoader(loader)
    app.wsgi_app = ProxyFix(app.wsgi_app)

    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    app.config['CDN_DOMAIN'] = CDN_DOMAIN

    cdn.init_app(app)
    print(app.config['CDN_DOMAIN'])

    return app


# Register pages here
print(f'Configuring {DOMAIN_NAME} with {BEIWE_SUBDOMAIN}, {DIGITAL_SELFIE_SUBDOMAIN}, {FITBIT_SUBDOMAIN}, static loaded from {CDN_DOMAIN}')

app = subdomain("frontend")
app.config['SERVER_NAME'] = BEIWE_ROOT_DOMAIN
app.config['CDN_DOMAIN'] = CDN_DOMAIN

app.jinja_env.globals['current_year'] = datetime.now().strftime('%Y')
app.register_blueprint(external_api.external_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(mobile_api.mobile_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(admin_pages.admin_pages, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(mobile_pages.mobile_pages, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(system_admin_pages.system_admin_pages, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(survey_designer.survey_designer, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(admin_api.admin_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(participant_administration.participant_administration, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(survey_api.survey_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(data_access_api.data_access_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(data_access_web_form.data_access_web_form, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(copy_study_api.copy_study_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(data_pipeline_api.data_pipeline_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(dashboard_api.dashboard_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(redcap_api.redcap_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(digital_selfie_web_form.digital_selfie_web_form,  **envopts(local={'url_prefix': '/digital-selfie'}, prod={'subdomain': DIGITAL_SELFIE_SUBDOMAIN}))
app.register_blueprint(fitbit_web_form.fitbit_web_form, **envopts(local={'url_prefix': '/fitbit'}, prod={'subdomain': FITBIT_SUBDOMAIN}))

# Don't set up Sentry for local development
if os.environ['DJANGO_DB_ENV'] not in ['local', 'docker']:
    sentry = Sentry(app, dsn=SENTRY_ELASTIC_BEANSTALK_DSN)


@app.route("/<page>.html")
def strip_dot_html(page):
    # Strips away the dot html from pages
    return redirect("/%s" % page)


@app.context_processor
def inject_dict_for_all_templates():
    return {"SENTRY_JAVASCRIPT_DSN": SENTRY_JAVASCRIPT_DSN}


# Extra Production settings
if not __name__ == '__main__':
    # Points our custom 404 page (in /frontend/templates) to display on a 404 error
    @app.errorhandler(404)
    def e404(e):
        return render_template("404.html", is_logged_in=is_logged_in()), 404

# Extra Debugging settings
if __name__ == '__main__':
    # might be necessary if running on windows/linux subsystem on windows.
    # from gevent.wsgi import WSGIServer
    # http_server = WSGIServer(('', 8080), app)
    # http_server.serve_forever()
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", "8080")), debug=True)
