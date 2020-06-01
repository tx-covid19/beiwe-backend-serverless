from django.db import models


class TokenBlacklist(models.Model):
    jti = models.CharField(max_length=36)
    token_type = models.CharField(max_length=10)
    user_identity = models.CharField(max_length=50)

    @classmethod
    def blacklist_token(cls, decoded_token):
        jti = decoded_token['jti']
        token_type = decoded_token['type']
        user_identity = decoded_token['identity']
        cls(jti=jti, token_type=token_type, user_identity=user_identity).save()

    @classmethod
    def is_blacklisted(cls, decoded_token):
        jti = decoded_token['jti']
        try:
            token = cls.objects.get(jti__exact=jti)
            return True
        except:
            return False
