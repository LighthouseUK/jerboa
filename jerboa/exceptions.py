__author__ = 'Matt'


# All further exceptions inherit from this so that we can have a catch all handler in the
# custom dispatcher
class BaseAppException(Exception):
    pass


class ApplicationError(BaseAppException):
    # This can be used when something goes wrong when handling a request
    pass


class ClientError(BaseAppException):
    def __init__(self, message, response_code=400):

        # Call the base class constructor with the parameters it needs
        super(ClientError, self).__init__(message)

        # Now for your custom code...
        self.response_code = response_code


class UserLoggedInException(ClientError):
    def __init__(self, message=None, response_code=403):
        if message is None:
            message = 'User cannot be logged in for this operation'
        super(UserLoggedInException, self).__init__(message=message, response_code=response_code)


class InvalidUserException(ClientError):
    def __init__(self, message=None, response_code=403):
        if message is None:
            message = 'Either the user is missing or invalid for this request'
        super(InvalidUserException, self).__init__(message=message, response_code=response_code)


class UnauthorizedUserException(ClientError):
    def __init__(self, message=None, response_code=403):
        if message is None:
            message = 'User is valid but does not have permission to execute this request'
        super(UnauthorizedUserException, self).__init__(message=message, response_code=response_code)


# === Handler Exceptions ===
class InvalidResourceUID(ClientError):
    def __init__(self, message=None, response_code=403, resource_uid=''):
        if message is None:
            message = '`{}` is not a valid resource UID'.format(resource_uid)
        super(InvalidResourceUID, self).__init__(message=message, response_code=response_code)


class UIFailed(Exception):
    """
    Can be used by ui functions. Allows them to fail if some condition is not met e.g. request parameter missing.
    """
    pass


class CallbackFailed(Exception):
    """
    Can be used by callback functions that are invoked upon form validation. Allows them to fail despite the form data
     begin valid e.g. if a unique value already exists.
    """
    pass


class FormDuplicateValue(ValueError, CallbackFailed):
    """
    Can be used by implementors that use the supplied hooks. Say you go to attempt to insert data into a datastore and
    it fails because a value already exists. Rather than having to do lots of checking and fetching of values, simply
    pass this exception the field names of the duplicates and raise it. The CRUD handler will do the rest.
    """

    def __init__(self, duplicates, message=u'Could not save the form because duplicate values were detected'):
        super(FormDuplicateValue, self).__init__(message)
        self.duplicates = duplicates


# === End Handler Exceptions ===
