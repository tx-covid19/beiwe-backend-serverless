import os
from datetime import datetime

import jinja2
from flask import Flask, redirect, render_template
from flask_cdn import CDN
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from raven.contrib.flask import Sentry
from werkzeug.middleware.proxy_fix import ProxyFix
from config import load_django

from api import (admin_api, copy_study_api, dashboard_api, data_access_api, data_pipeline_api, external_api,
                 mobile_api, participant_administration, survey_api, user_auth_api, info_api)
from api.fitbit import fitbit_api
from api.redcap import redcap_api
from api.mindlogger import manage_api, applet_api, response_api, schedule_api, file_api, gps_api
from api.tracker import event_api, overview_api, refresh_api, tracker_api
from config.settings import SENTRY_ELASTIC_BEANSTALK_DSN, SENTRY_JAVASCRIPT_DSN, DOMAIN_NAME, \
    BEIWE_SUBDOMAIN, DIGITAL_SELFIE_SUBDOMAIN, FITBIT_SUBDOMAIN, BEIWE_ROOT_DOMAIN, CDN_DOMAIN
from database.token_models import TokenBlacklist
from libs.admin_authentication import is_logged_in
from libs.security import set_secret_key
from pages import (admin_pages, data_access_web_form, mobile_pages, survey_designer,
                   system_admin_pages, digital_selfie_web_form)

cdn = CDN()


def subdomain(directory):
    app = Flask(__name__, static_folder=directory + "/static", subdomain_matching=True)
    CORS(app)
    set_secret_key(app)
    app.config['JWT_SECRET_KEY'] = app.secret_key
    app.config['JWT_HEADER_NAME'] = 'Girder-Token'
    app.config['JWT_HEADER_TYPE'] = ''
    app.config['JWT_BLACKLIST_ENABLED'] = True
    app.config['JWT_BLACKLIST_TOKEN_CHECKS'] = ['access', 'refresh']

    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    app.config['CDN_DOMAIN'] = CDN_DOMAIN

    jwt = JWTManager(app)

    @jwt.token_in_blacklist_loader
    def check_if_token_in_blacklist(decoded_token):
        return TokenBlacklist.is_blacklisted(decoded_token)

    loader = [app.jinja_loader, jinja2.FileSystemLoader(directory + "/templates")]
    app.jinja_loader = jinja2.ChoiceLoader(loader)
    app.wsgi_app = ProxyFix(app.wsgi_app)
    cdn.init_app(app)
    print(app.config['CDN_DOMAIN'])

    return app


# Register pages here
print(
    f'Configuring {DOMAIN_NAME} with {BEIWE_SUBDOMAIN}, {DIGITAL_SELFIE_SUBDOMAIN}, {FITBIT_SUBDOMAIN}, static loaded from {CDN_DOMAIN}')

app = subdomain("frontend")
app.config['SERVER_NAME'] = BEIWE_ROOT_DOMAIN
app.config['CDN_DOMAIN'] = CDN_DOMAIN

app.jinja_env.globals['current_year'] = datetime.now().strftime('%Y')

# beiwe APIs
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

# Auth APIs, shared by tracker and mindlogger
app.register_blueprint(user_auth_api.auth_api, url_prefix='/api/v1/user')

# mindlogger (hornsense) APIs
app.register_blueprint(manage_api.manage_api, url_prefix='/api/v1/user')
app.register_blueprint(applet_api.applet_api, url_prefix='/api/v1/applet')
app.register_blueprint(response_api.response_api, url_prefix='/api/v1/response')
app.register_blueprint(schedule_api.schedule_api, url_prefix='/api/v1/schedule')
app.register_blueprint(file_api.file_api, url_prefix='/api/v1/file')
app.register_blueprint(gps_api.gps_api, url_prefix='/api/v1')

# covid19 information
app.register_blueprint(info_api.info_api, url_prefix='/info')

# selfie APIs
app.register_blueprint(external_api.external_api, subdomain=BEIWE_SUBDOMAIN)
app.register_blueprint(digital_selfie_web_form.digital_selfie_web_form, subdomain=DIGITAL_SELFIE_SUBDOMAIN)

# tracker APIs
app.register_blueprint(event_api.event_api, url_prefix='/tracker')
app.register_blueprint(overview_api.overview_api, url_prefix='/tracker')
app.register_blueprint(refresh_api.refresh_api, url_prefix='/tracker')
app.register_blueprint(tracker_api.tracker_api, url_prefix='/tracker')

# redcap integration
app.register_blueprint(redcap_api.redcap_api, subdomain=BEIWE_SUBDOMAIN)

# fitbit integration
app.register_blueprint(fitbit_api.fitbit_api, subdomain=FITBIT_SUBDOMAIN)

# Don't set up Sentry for local development
if os.environ['DJANGO_DB_ENV'] != 'local':
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
