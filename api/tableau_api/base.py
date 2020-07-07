from django import forms
from flask import request
from flask.views import MethodView
from werkzeug.exceptions import abort

from database.security_models import ApiKey
from database.study_models import Study


X_ACCESS_KEY_ID = 'X-Access-Key-Id'
X_ACCESS_KEY_SECRET = 'X-Access-Key-Secret'

class AuthenticationFailed(Exception): pass
class PermissionDenied(Exception): pass


class AuthenticationForm(forms.Form):
    """
    Form for fetching
    """
    def __init__(self, *args, **kwargs):
        """
        Define authentication form fields since the keys contain illegal characters for
        variable names.
        """
        super().__init__(*args,**kwargs)
        self.fields[X_ACCESS_KEY_ID] = forms.CharField(error_messages={'required': 'This header is required'})
        self.fields[X_ACCESS_KEY_SECRET] = forms.CharField(error_messages={'required': 'This header is required'})


class TableauApiView(MethodView):
    """
    The base class for all Tableau API views that implements authentication and other functionality
    specific to this API.
    """
    CREDENTIALS_NOT_VALID_ERROR_MESSAGE = 'Credentials not valid'
    
    def check_permissions(self, *args, study_id=None, participant_id=None, **kwargs):
        return True
        """
        Authenticate API key and check permissions for access to a study/participant data.
        """
        # Authentication
        form = AuthenticationForm(request.headers)
        if not form.is_valid():
            raise AuthenticationFailed(form.errors)
        
        try:
            api_key = ApiKey.objects.get(
                access_key_id=form.cleaned_data[X_ACCESS_KEY_ID],
                is_active=True,
            )
        except ApiKey.DoesNotExist:
            raise AuthenticationFailed(self.CREDENTIALS_NOT_VALID_ERROR_MESSAGE)
        
        if not api_key.proposed_secret_key_is_valid(form.cleaned_data[X_ACCESS_KEY_SECRET]):
            raise AuthenticationFailed(self.CREDENTIALS_NOT_VALID_ERROR_MESSAGE)
        
        # Authorization
        if not api_key.has_tableau_api_permissions:
            raise PermissionDenied('ApiKey does not have access to Tableau API')
        
        if study_id is None:
            raise PermissionDenied('No study id specified')
        if not Study.objects.filter(object_id=study_id).exists():
            raise PermissionDenied('No matching study found')
        
        # Todo (CD): Implement the rest of this
        
        return True
    
    def dispatch_request(self, *args, **kwargs):
        """
        Override `super().dispatch_request` to return 404 if a method is not allowed.
        """
        try:
            self.check_permissions(*args, **kwargs)
        except AuthenticationFailed:
            # Todo (CD): Handle returning the error message for this case
            return abort(401)
        except PermissionDenied:
            # Prefer 404 over 403 to hide information about validity of these resource identifiers
            return abort(404)
        return super().dispatch_request(*args, **kwargs)
    
    @classmethod
    def register_urls(cls, app):
        """
        Register this class' URLs with Flask
        """
        app.add_url_rule(cls.path, view_func=cls.as_view('summary_statistics_daily_study_view'))