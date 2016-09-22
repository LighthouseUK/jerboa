

class StatusManager(object):
    DEFAULT_SUCCESS_CODE = '1'
    DEFAULT_FAILURE_CODE = '2'
    DEFAULT_FORM_FAILURE_CODE = '3'

    statuses = {
        DEFAULT_SUCCESS_CODE: ('Successfully completed operation', 'success'),
        DEFAULT_FAILURE_CODE: ('Failed to complete operation.', 'alert'),
        DEFAULT_FORM_FAILURE_CODE: ('Please correct the errors on the form below.', 'alert'),
    }

    @classmethod
    def add_status(cls, message, status_type):
        new_code = str(len(cls.statuses)+1)
        cls.statuses[new_code] = (message, status_type)
        return new_code


def parse_request_status_code(request, response):
    request_status_code = request.GET.get('status_code', False)
    if not request_status_code:
        response.raw.status_code = 0
        return

    try:
        response.raw.status_message = StatusManager.statuses[request_status_code]
    except KeyError:
        response.raw.status_code = 0
    else:
        response.raw.status_code = request_status_code
