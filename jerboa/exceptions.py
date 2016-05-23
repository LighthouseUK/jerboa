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
